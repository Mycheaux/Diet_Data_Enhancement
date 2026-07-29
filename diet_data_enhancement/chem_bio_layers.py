import csv
import json
import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from .canonical import canonical_as_foods, load_canonical_foods, run_canonical_pipeline
from .foodatlas import extract_food_entities_from_parquet, map_hpp_to_foodatlas
from .mapping import map_hpp_to_public
from .sources import ROOT


OUT = ROOT / "outputs"
LAYERED = OUT / "layered"
REFERENCE = OUT / "reference"
FOODB_JSON = ROOT / "data/FooDB/foodb_2020_04_07_json"
HMDB_DIR = ROOT / "data/HMDB"
FOODATLAS_ZIP = ROOT / "data/FoodAtlas/foodatlas-v4.5.zip"

HMDB_BIOSPECIMEN_FILES = [
    ("serum", "serum_metabolites.xml"),
    ("urine", "urine_metabolites.xml"),
    ("feces", "feces_metabolites.xml"),
    ("saliva", "saliva_metabolites.xml"),
    ("sweat", "sweat_metabolites.xml"),
    ("csf", "csf_metabolites.xml"),
]


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _int_value(value, default=0):
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return default
    return int(numeric)


def _jsonl(path, limit=None):
    with Path(path).open() as handle:
        for idx, line in enumerate(handle):
            if limit is not None and idx >= limit:
                break
            line = line.strip()
            if line:
                yield json.loads(line)


def _ensure_canonical_foods():
    if not (OUT / "canonical/canonical_foods.csv").exists():
        run_canonical_pipeline()
    canonical = load_canonical_foods()
    return canonical, canonical_as_foods(canonical)


def load_foodb_foods():
    rows = []
    for record in _jsonl(FOODB_JSON / "Food.json"):
        rows.append(
            {
                "source": "FooDB",
                "source_food_id": str(record.get("id") or ""),
                "foodb_public_id": record.get("public_id") or "",
                "food_name": record.get("name") or "",
                "category": record.get("food_group") or record.get("category") or "",
                "food_subgroup": record.get("food_subgroup") or "",
                "scientific_name": record.get("name_scientific") or "",
                "food_type": record.get("food_type") or "",
            }
        )
    return pd.DataFrame(rows)


def build_layer3_foodb_candidates(top_k=5):
    """Map canonical foods to FooDB foods for food-chemical extraction."""
    LAYERED.mkdir(parents=True, exist_ok=True)
    _, canonical_foods = _ensure_canonical_foods()
    foodb = load_foodb_foods()
    candidates = map_hpp_to_public(canonical_foods, foodb, top_k=top_k).rename(
        columns={
            "hpp_food_id": "canonical_food_id",
            "hpp_food_name": "canonical_name",
            "hpp_short_description": "representative_original_name",
            "hpp_category": "canonical_category",
        }
    )
    extra = foodb.drop_duplicates(["source", "source_food_id"])
    candidates = candidates.merge(extra, on=["source", "source_food_id"], how="left", suffixes=("", "_foodb"))
    candidates["source_layer"] = "layer_3_food_chemicals"
    candidates["mapping_role"] = "foodb_food_chemical_source"
    candidates["stage"] = "layered_foodb_food_candidate"
    out_path = LAYERED / "layer3_foodb_food_candidates.csv"
    candidates.to_csv(out_path, index=False)
    top = candidates[candidates["candidate_rank"] == 1]
    summary = {
        "layer": "Layer 3: food chemicals",
        "source": "FooDB",
        "foodb_food_rows": int(foodb.shape[0]),
        "candidate_rows": int(candidates.shape[0]),
        "canonical_food_count": int(candidates["canonical_food_id"].nunique()),
        "top_match_confidence_counts": top["confidence"].value_counts().to_dict(),
        "output": str(out_path),
    }
    _write_json(LAYERED / "layer3_foodb_food_candidates_summary.json", summary)
    return candidates, summary


def _top_by_id(df, id_col):
    if df.empty:
        return df
    return df.sort_values([id_col, "candidate_rank"]).groupby(id_col, as_index=False).head(1)


def _compound_lookup():
    rows = []
    for record in _jsonl(FOODB_JSON / "Compound.json"):
        rows.append(
            {
                "foodb_compound_id": str(record.get("id") or ""),
                "foodb_compound_public_id": record.get("public_id") or "",
                "compound_name": record.get("name") or "",
                "annotation_quality": record.get("annotation_quality") or "",
                "chemical_class": record.get("klass") or "",
                "chemical_subclass": record.get("subklass") or "",
                "chemical_superclass": record.get("superklass") or "",
                "kingdom": record.get("kingdom") or "",
                "inchikey": record.get("moldb_inchikey") or "",
                "inchi": record.get("moldb_inchi") or "",
                "smiles": record.get("moldb_smiles") or "",
                "mono_mass": record.get("moldb_mono_mass") or "",
            }
        )
    return pd.DataFrame(rows)


def build_foodb_compound_reference():
    """Extract FooDB compounds for top-matched canonical FooDB foods."""
    REFERENCE.mkdir(parents=True, exist_ok=True)
    cand_path = LAYERED / "layer3_foodb_food_candidates.csv"
    if not cand_path.exists():
        build_layer3_foodb_candidates()
    candidates = pd.read_csv(cand_path, dtype=str).fillna("")
    top = _top_by_id(candidates, "canonical_food_id")
    food_ids = set(top["source_food_id"].astype(str))
    food_lookup = defaultdict(list)
    for record in top.to_dict("records"):
        food_lookup[str(record.get("source_food_id") or "")].append(record)
    compound_ids = set()
    content_rows = []
    max_rows = int(os.getenv("FOODB_MAX_CONTENT_ROWS", "0") or "0")
    for idx, record in enumerate(_jsonl(FOODB_JSON / "Content.json")):
        if max_rows and idx >= max_rows:
            break
        if record.get("source_type") != "Compound":
            continue
        food_id = str(record.get("food_id") or "")
        if food_id not in food_ids:
            continue
        compound_id = str(record.get("source_id") or "")
        compound_ids.add(compound_id)
        for food in food_lookup.get(food_id, []):
            content_rows.append(
                {
                    "canonical_food_id": food.get("canonical_food_id", ""),
                    "canonical_name": food.get("canonical_name", ""),
                    "foodb_food_id": food_id,
                    "foodb_food_name": food.get("matched_food_name", ""),
                    "foodb_compound_id": compound_id,
                    "orig_content": record.get("orig_content") or "",
                    "orig_min": record.get("orig_min") or "",
                    "orig_max": record.get("orig_max") or "",
                    "orig_unit": record.get("orig_unit") or "",
                    "standard_content": record.get("standard_content") or "",
                    "preparation_type": record.get("preparation_type") or "",
                    "citation": record.get("citation") or "",
                    "source_database": "FooDB",
                }
            )
    content = pd.DataFrame(content_rows)
    compounds = _compound_lookup()
    if not content.empty:
        out = content.merge(compounds, on="foodb_compound_id", how="left")
    else:
        out = pd.DataFrame(columns=["canonical_food_id", "foodb_compound_id"])
    out_path = REFERENCE / "canonical_food_foodb_compound_reference.csv"
    out.to_csv(out_path, index=False)
    summary = {
        "foodb_matched_food_count": int(len(food_ids)),
        "foodb_compound_reference_rows": int(out.shape[0]),
        "canonical_foods_with_foodb_compounds": int(out["canonical_food_id"].nunique()) if not out.empty else 0,
        "unique_foodb_compounds": int(out["foodb_compound_id"].nunique()) if not out.empty else 0,
        "output": str(out_path),
    }
    _write_json(REFERENCE / "canonical_food_foodb_compound_reference_summary.json", summary)
    return out_path, summary


def build_layer3_chemical_features():
    """Build compact per-canonical-food chemical feature counts."""
    REFERENCE.mkdir(parents=True, exist_ok=True)
    foodb_path = REFERENCE / "canonical_food_foodb_compound_reference.csv"
    if not foodb_path.exists():
        build_foodb_compound_reference()
    stats = defaultdict(
        lambda: {
            "canonical_name": "",
            "foodb_compounds": set(),
            "chemical_classes": Counter(),
            "chemical_superclasses": Counter(),
            "annotation_quality": Counter(),
        }
    )
    usecols = [
        "canonical_food_id",
        "canonical_name",
        "foodb_compound_public_id",
        "chemical_class",
        "chemical_superclass",
        "annotation_quality",
    ]
    for chunk in pd.read_csv(foodb_path, dtype=str, usecols=lambda col: col in usecols, chunksize=200000):
        chunk = chunk.fillna("")
        for record in chunk.to_dict("records"):
            cid = record.get("canonical_food_id", "")
            if not cid:
                continue
            item = stats[cid]
            item["canonical_name"] = record.get("canonical_name", "")
            if record.get("foodb_compound_public_id"):
                item["foodb_compounds"].add(record["foodb_compound_public_id"])
            if record.get("chemical_class"):
                item["chemical_classes"][record["chemical_class"]] += 1
            if record.get("chemical_superclass"):
                item["chemical_superclasses"][record["chemical_superclass"]] += 1
            if record.get("annotation_quality"):
                item["annotation_quality"][record["annotation_quality"]] += 1
    rows = []
    for cid, item in stats.items():
        rows.append(
            {
                "canonical_food_id": cid,
                "canonical_name": item["canonical_name"],
                "foodb_compound_count": len(item["foodb_compounds"]),
                "foodb_top_chemical_classes": "|".join(name for name, _ in item["chemical_classes"].most_common(10)),
                "foodb_top_chemical_superclasses": "|".join(
                    name for name, _ in item["chemical_superclasses"].most_common(10)
                ),
                "foodb_annotation_quality_counts": "|".join(
                    f"{name}:{count}" for name, count in item["annotation_quality"].most_common()
                ),
            }
        )
    features = pd.DataFrame(rows)
    foodatlas_features = REFERENCE / "canonical_food_graph_features.csv"
    if foodatlas_features.exists():
        fa = pd.read_csv(foodatlas_features, dtype=str).fillna("")
        keep = [
            col
            for col in [
                "canonical_food_id",
                "foodatlas_compound_count",
                "foodatlas_food_count",
            ]
            if col in fa.columns
        ]
        if keep:
            features = features.merge(fa[keep], on="canonical_food_id", how="outer")
    for col in ["foodb_compound_count", "foodatlas_compound_count", "foodatlas_food_count"]:
        if col in features:
            features[col] = pd.to_numeric(features[col], errors="coerce").fillna(0).astype(int)
    out_path = REFERENCE / "canonical_food_chemical_features.csv"
    features.to_csv(out_path, index=False)
    summary = {
        "layer": "Layer 3: food chemicals",
        "canonical_food_rows": int(features.shape[0]),
        "canonical_foods_with_foodb_compounds": int((features.get("foodb_compound_count", 0) > 0).sum()),
        "output": str(out_path),
    }
    _write_json(REFERENCE / "canonical_food_chemical_features_summary.json", summary)
    return out_path, summary


def _hmdb_text(elem, name):
    ns = "{http://www.hmdb.ca}"
    child = elem.find(ns + name)
    return (child.text or "").strip() if child is not None and child.text else ""


def _hmdb_nested_texts(elem, parent_name, child_name):
    ns = "{http://www.hmdb.ca}"
    parent = elem.find(ns + parent_name)
    if parent is None:
        return []
    values = []
    for child in parent.iter(ns + child_name):
        if child.text and child.text.strip():
            values.append(child.text.strip())
    return values


def _hmdb_pathway_names(elem):
    ns = "{http://www.hmdb.ca}"
    pathways = elem.find(ns + "biological_properties/" + ns + "pathways")
    if pathways is None:
        return []
    values = []
    for pathway in pathways.findall(ns + "pathway"):
        name = pathway.find(ns + "name")
        if name is not None and name.text and name.text.strip():
            values.append(name.text.strip())
    return values


def _parse_hmdb_file(biospecimen, path, max_metabolites=0):
    rows = []
    ns = "{http://www.hmdb.ca}"
    count = 0
    max_pathways = int(os.getenv("HMDB_MAX_PATHWAYS_PER_METABOLITE", "200") or "0")
    max_diseases = int(os.getenv("HMDB_MAX_DISEASES_PER_METABOLITE", "200") or "0")
    for _, elem in ET.iterparse(path, events=("end",)):
        if not elem.tag.endswith("metabolite"):
            continue
        count += 1
        taxonomy = elem.find(ns + "taxonomy")
        tax = {}
        if taxonomy is not None:
            for key in ["kingdom", "super_class", "class", "sub_class", "direct_parent"]:
                child = taxonomy.find(ns + key)
                tax[key] = (child.text or "").strip() if child is not None and child.text else ""
        disease_names = sorted(set(_hmdb_nested_texts(elem, "diseases", "name")))
        pathway_names = sorted(set(_hmdb_pathway_names(elem)))
        disease_overflow = bool(max_diseases and len(disease_names) > max_diseases)
        pathway_overflow = bool(max_pathways and len(pathway_names) > max_pathways)
        rows.append(
            {
                "hmdb_id": _hmdb_text(elem, "accession"),
                "hmdb_name": _hmdb_text(elem, "name"),
                "biospecimen": biospecimen,
                "chemical_formula": _hmdb_text(elem, "chemical_formula"),
                "average_molecular_weight": _hmdb_text(elem, "average_molecular_weight"),
                "inchikey": _hmdb_text(elem, "inchikey"),
                "inchi": _hmdb_text(elem, "inchi"),
                "smiles": _hmdb_text(elem, "smiles"),
                "foodb_id": _hmdb_text(elem, "foodb_id"),
                "pubchem_compound_id": _hmdb_text(elem, "pubchem_compound_id"),
                "chebi_id": _hmdb_text(elem, "chebi_id"),
                "kegg_id": _hmdb_text(elem, "kegg_id"),
                "kingdom": tax.get("kingdom", ""),
                "super_class": tax.get("super_class", ""),
                "class": tax.get("class", ""),
                "sub_class": tax.get("sub_class", ""),
                "direct_parent": tax.get("direct_parent", ""),
                "disease_names": "" if disease_overflow else "|".join(disease_names),
                "pathway_names": "" if pathway_overflow else "|".join(pathway_names),
                "disease_name_count_raw": len(disease_names),
                "pathway_name_count_raw": len(pathway_names),
                "hmdb_scope_filter": "|".join(
                    [
                        label
                        for label, active in [
                            ("disease_overflow", disease_overflow),
                            ("pathway_overflow", pathway_overflow),
                        ]
                        if active
                    ]
                ),
            }
        )
        elem.clear()
        if max_metabolites and count >= max_metabolites:
            break
    return rows


def build_hmdb_metabolite_index():
    """Parse HMDB biospecimen XML files into a compact metabolite index."""
    LAYERED.mkdir(parents=True, exist_ok=True)
    rows = []
    max_per_file = int(os.getenv("HMDB_MAX_METABOLITES_PER_FILE", "0") or "0")
    for biospecimen, filename in HMDB_BIOSPECIMEN_FILES:
        path = HMDB_DIR / filename
        if not path.exists():
            continue
        rows.extend(_parse_hmdb_file(biospecimen, path, max_metabolites=max_per_file))
    index = pd.DataFrame(rows).drop_duplicates()
    out_path = LAYERED / "layer4_hmdb_metabolite_index.csv"
    index.to_csv(out_path, index=False)
    summary = {
        "layer": "Layer 4: human metabolomics biology",
        "hmdb_rows": int(index.shape[0]),
        "unique_hmdb_metabolites": int(index["hmdb_id"].nunique()) if not index.empty else 0,
        "biospecimen_counts": index["biospecimen"].value_counts().to_dict() if not index.empty else {},
        "output": str(out_path),
    }
    _write_json(LAYERED / "layer4_hmdb_metabolite_index_summary.json", summary)
    return out_path, summary


def build_hmdb_food_compound_links():
    """Summarize canonical FooDB food compounds that map to HMDB metabolites."""
    REFERENCE.mkdir(parents=True, exist_ok=True)
    foodb_path = REFERENCE / "canonical_food_foodb_compound_reference.csv"
    if not foodb_path.exists():
        build_foodb_compound_reference()
    hmdb_path = LAYERED / "layer4_hmdb_metabolite_index.csv"
    if not hmdb_path.exists():
        build_hmdb_metabolite_index()
    hmdb = pd.read_csv(hmdb_path, dtype=str).fillna("")
    out_path = REFERENCE / "canonical_food_hmdb_metabolite_links.csv"
    examples_path = REFERENCE / "canonical_food_hmdb_metabolite_link_examples.csv"
    edges_path = REFERENCE / "canonical_food_hmdb_metabolite_edges.csv"
    output_fields = [
        "canonical_food_id",
        "canonical_name",
        "foodb_compound_count_with_hmdb",
        "hmdb_metabolite_count",
        "hmdb_biospecimen_count",
        "hmdb_disease_count",
        "hmdb_pathway_count",
        "hmdb_biospecimens",
        "hmdb_link_methods",
        "hmdb_top_diseases",
        "hmdb_top_pathways",
    ]
    example_fields = [
        "canonical_food_id",
        "canonical_name",
        "foodb_food_id",
        "foodb_food_name",
        "foodb_compound_public_id",
        "foodb_compound_id",
        "compound_name",
        "hmdb_id",
        "hmdb_name",
        "biospecimen",
        "hmdb_link_method",
        "foodb_id",
        "inchikey",
        "pubchem_compound_id",
        "chebi_id",
        "kegg_id",
        "kingdom",
        "super_class",
        "class",
        "sub_class",
        "direct_parent",
        "disease_names",
        "pathway_names",
    ]
    edge_fields = [
        "canonical_food_id",
        "canonical_name",
        "foodb_food_id",
        "foodb_food_name",
        "foodb_compound_public_id",
        "foodb_compound_id",
        "compound_name",
        "hmdb_id",
        "hmdb_name",
        "biospecimen",
        "hmdb_link_method",
        "foodb_id",
        "inchikey",
        "pubchem_compound_id",
        "chebi_id",
        "kegg_id",
        "kingdom",
        "super_class",
        "class",
        "sub_class",
        "direct_parent",
    ]
    if hmdb.empty or not foodb_path.exists():
        pd.DataFrame(columns=output_fields).to_csv(out_path, index=False)
        pd.DataFrame(columns=example_fields).to_csv(examples_path, index=False)
        pd.DataFrame(columns=edge_fields).to_csv(edges_path, index=False)
        out_rows = 0
        canonical_ids = set()
        hmdb_ids = set()
        method_counts = Counter()
    else:
        foodb_lookup = defaultdict(list)
        inchikey_lookup = defaultdict(list)
        for record in hmdb.to_dict("records"):
            if record.get("foodb_id"):
                foodb_lookup[str(record["foodb_id"])].append(record)
            if record.get("inchikey"):
                inchikey_lookup[str(record["inchikey"])].append(record)
        example_rows = 0
        example_limit = int(os.getenv("HMDB_LINK_EXAMPLE_LIMIT", "50000") or "0")
        canonical_ids = set()
        hmdb_ids = set()
        method_counts = Counter()
        per_food = defaultdict(
            lambda: {
                "canonical_name": "",
                "foodb_compounds": set(),
                "hmdb_ids": set(),
                "biospecimens": set(),
                "diseases": Counter(),
                "pathways": Counter(),
                "methods": Counter(),
            }
        )
        seen_links = set()
        seen_food_compounds = set()
        usecols = [
            "canonical_food_id",
            "canonical_name",
            "foodb_food_id",
            "foodb_food_name",
            "foodb_compound_public_id",
            "foodb_compound_id",
            "compound_name",
            "inchikey",
        ]
        with examples_path.open("w", newline="") as example_handle, edges_path.open("w", newline="") as edge_handle:
            writer = csv.DictWriter(example_handle, fieldnames=example_fields)
            edge_writer = csv.DictWriter(edge_handle, fieldnames=edge_fields)
            writer.writeheader()
            edge_writer.writeheader()
            for chunk in pd.read_csv(foodb_path, dtype=str, usecols=lambda col: col in usecols, chunksize=200000):
                chunk = chunk.fillna("")
                for food_record in chunk.to_dict("records"):
                    food_compound_key = (
                        food_record.get("canonical_food_id", ""),
                        food_record.get("foodb_compound_public_id", ""),
                        food_record.get("inchikey", ""),
                    )
                    if food_compound_key in seen_food_compounds:
                        continue
                    seen_food_compounds.add(food_compound_key)
                    matches = []
                    foodb_public_id = str(food_record.get("foodb_compound_public_id") or "")
                    inchikey = str(food_record.get("inchikey") or "")
                    for record in foodb_lookup.get(foodb_public_id, []):
                        matches.append(("foodb_public_id", record))
                    if not matches:
                        for record in inchikey_lookup.get(inchikey, []):
                            matches.append(("inchikey", record))
                    for method, hmdb_record in matches:
                        key = (
                            food_record.get("canonical_food_id", ""),
                            food_record.get("foodb_compound_public_id", ""),
                            hmdb_record.get("hmdb_id", ""),
                            hmdb_record.get("biospecimen", ""),
                        )
                        if key in seen_links:
                            continue
                        seen_links.add(key)
                        row = {
                            **{field: food_record.get(field, "") for field in example_fields},
                            **{field: hmdb_record.get(field, "") for field in example_fields},
                            "canonical_food_id": food_record.get("canonical_food_id", ""),
                            "canonical_name": food_record.get("canonical_name", ""),
                            "foodb_food_id": food_record.get("foodb_food_id", ""),
                            "foodb_food_name": food_record.get("foodb_food_name", ""),
                            "foodb_compound_public_id": food_record.get("foodb_compound_public_id", ""),
                            "foodb_compound_id": food_record.get("foodb_compound_id", ""),
                            "compound_name": food_record.get("compound_name", ""),
                            "hmdb_link_method": method,
                        }
                        cid = row["canonical_food_id"]
                        stats = per_food[cid]
                        stats["canonical_name"] = row["canonical_name"]
                        stats["foodb_compounds"].add(row["foodb_compound_public_id"])
                        stats["hmdb_ids"].add(row["hmdb_id"])
                        stats["biospecimens"].add(row.get("biospecimen", ""))
                        stats["methods"][method] += 1
                        for disease in str(row.get("disease_names", "")).split("|"):
                            if disease:
                                stats["diseases"][disease] += 1
                        for pathway in str(row.get("pathway_names", "")).split("|"):
                            if pathway:
                                stats["pathways"][pathway] += 1
                        if not example_limit or example_rows < example_limit:
                            writer.writerow({field: row.get(field, "") for field in example_fields})
                            example_rows += 1
                        edge_writer.writerow({field: row.get(field, "") for field in edge_fields})
                        canonical_ids.add(row["canonical_food_id"])
                        hmdb_ids.add(row["hmdb_id"])
                        method_counts[method] += 1
        summary_rows = []
        for cid, stats in per_food.items():
            summary_rows.append(
                {
                    "canonical_food_id": cid,
                    "canonical_name": stats["canonical_name"],
                    "foodb_compound_count_with_hmdb": len(stats["foodb_compounds"]),
                    "hmdb_metabolite_count": len(stats["hmdb_ids"]),
                    "hmdb_biospecimen_count": len([value for value in stats["biospecimens"] if value]),
                    "hmdb_disease_count": len(stats["diseases"]),
                    "hmdb_pathway_count": len(stats["pathways"]),
                    "hmdb_biospecimens": "|".join(sorted(value for value in stats["biospecimens"] if value)),
                    "hmdb_link_methods": "|".join(f"{key}:{value}" for key, value in stats["methods"].most_common()),
                    "hmdb_top_diseases": "|".join(name for name, _ in stats["diseases"].most_common(10)),
                    "hmdb_top_pathways": "|".join(name for name, _ in stats["pathways"].most_common(10)),
                }
            )
        pd.DataFrame(summary_rows, columns=output_fields).to_csv(out_path, index=False)
        out_rows = len(summary_rows)
    summary = {
        "canonical_food_hmdb_summary_rows": int(out_rows),
        "canonical_foods_with_hmdb_links": int(len(canonical_ids)),
        "unique_hmdb_metabolites": int(len(hmdb_ids)),
        "link_methods": dict(method_counts),
        "output": str(out_path),
        "edges_output": str(edges_path),
        "examples_output": str(examples_path),
    }
    _write_json(REFERENCE / "canonical_food_hmdb_metabolite_links_summary.json", summary)
    return out_path, summary


def build_layer5_disease_pathway_features():
    """Summarize FoodAtlas and HMDB disease/pathway evidence per canonical food."""
    REFERENCE.mkdir(parents=True, exist_ok=True)
    foodatlas_features = REFERENCE / "canonical_food_graph_features.csv"
    if not foodatlas_features.exists():
        from .layered import build_foodatlas_reference

        build_foodatlas_reference()
    hmdb_summary_path = REFERENCE / "canonical_food_hmdb_metabolite_links.csv"
    if not hmdb_summary_path.exists():
        build_hmdb_food_compound_links()

    canonical = load_canonical_foods()[["canonical_food_id", "canonical_name", "canonical_category"]].copy()
    fa = pd.read_csv(foodatlas_features, dtype=str).fillna("") if foodatlas_features.exists() else pd.DataFrame()
    hmdb = pd.read_csv(hmdb_summary_path, dtype=str).fillna("") if hmdb_summary_path.exists() else pd.DataFrame()

    rows = []
    for _, food in canonical.iterrows():
        cid = food["canonical_food_id"]
        row = food.to_dict()
        if not fa.empty:
            fa_row = fa[fa["canonical_food_id"].eq(cid)]
            if not fa_row.empty:
                for col in [
                    "foodatlas_compound_count",
                    "foodatlas_food_count",
                    "foodatlas_disease_edge_count",
                    "foodatlas_positive_disease_edge_count",
                    "foodatlas_negative_disease_edge_count",
                ]:
                    row[col] = fa_row.iloc[0].get(col, 0)
        hmdb_row = hmdb[hmdb["canonical_food_id"].eq(cid)] if not hmdb.empty else pd.DataFrame()
        if hmdb_row.empty:
            row.update(
                {
                    "hmdb_metabolite_count": 0,
                    "hmdb_biospecimen_count": 0,
                    "hmdb_disease_count": 0,
                    "hmdb_pathway_count": 0,
                    "hmdb_biospecimens": "",
                    "hmdb_top_diseases": "",
                    "hmdb_top_pathways": "",
                }
            )
        else:
            hmdb_record = hmdb_row.iloc[0]
            row.update(
                {
                    "hmdb_metabolite_count": _int_value(hmdb_record.get("hmdb_metabolite_count", 0)),
                    "hmdb_biospecimen_count": _int_value(hmdb_record.get("hmdb_biospecimen_count", 0)),
                    "hmdb_disease_count": _int_value(hmdb_record.get("hmdb_disease_count", 0)),
                    "hmdb_pathway_count": _int_value(hmdb_record.get("hmdb_pathway_count", 0)),
                    "hmdb_biospecimens": hmdb_record.get("hmdb_biospecimens", ""),
                    "hmdb_top_diseases": hmdb_record.get("hmdb_top_diseases", ""),
                    "hmdb_top_pathways": hmdb_record.get("hmdb_top_pathways", ""),
                }
            )
        rows.append(row)
    features = pd.DataFrame(rows)
    for col in [
        "foodatlas_compound_count",
        "foodatlas_food_count",
        "foodatlas_disease_edge_count",
        "foodatlas_positive_disease_edge_count",
        "foodatlas_negative_disease_edge_count",
    ]:
        if col not in features:
            features[col] = 0
        features[col] = pd.to_numeric(features[col], errors="coerce").fillna(0).astype(int)
    out_path = REFERENCE / "canonical_food_disease_pathway_features.csv"
    features.to_csv(out_path, index=False)
    summary = {
        "layer": "Layer 5: disease/pathway graph features",
        "canonical_food_count": int(features["canonical_food_id"].nunique()),
        "canonical_foods_with_foodatlas_disease_edges": int((features["foodatlas_disease_edge_count"] > 0).sum()),
        "canonical_foods_with_hmdb_metabolite_links": int((features["hmdb_metabolite_count"] > 0).sum()),
        "output": str(out_path),
    }
    _write_json(REFERENCE / "canonical_food_disease_pathway_features_summary.json", summary)
    return out_path, summary


def run_chem_bio_layers():
    foodb_candidates, foodb_candidate_summary = build_layer3_foodb_candidates()
    foodb_compounds, foodb_compound_summary = build_foodb_compound_reference()
    chemical_features, chemical_features_summary = build_layer3_chemical_features()
    hmdb_index, hmdb_index_summary = build_hmdb_metabolite_index()
    hmdb_links, hmdb_link_summary = build_hmdb_food_compound_links()
    disease_pathway, disease_pathway_summary = build_layer5_disease_pathway_features()
    summary = {
        "layer3_foodb_candidates": foodb_candidate_summary,
        "layer3_foodb_compounds": foodb_compound_summary,
        "layer3_chemical_features": chemical_features_summary,
        "layer4_hmdb_index": hmdb_index_summary,
        "layer4_hmdb_links": hmdb_link_summary,
        "layer5_disease_pathway_features": disease_pathway_summary,
        "outputs": {
            "layer3_foodb_candidates": str(LAYERED / "layer3_foodb_food_candidates.csv"),
            "foodb_compound_reference": str(foodb_compounds),
            "chemical_features": str(chemical_features),
            "hmdb_metabolite_index": str(hmdb_index),
            "hmdb_food_compound_links": str(hmdb_links),
            "disease_pathway_features": str(disease_pathway),
        },
    }
    _write_json(REFERENCE / "chem_bio_layers_summary.json", summary)
    return summary
