"""Food-card preparation utilities."""

from __future__ import annotations

import json
import math
import getpass
import os
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "food_card"
CATEGORIZATION_DIR = OUTPUT_DIR / "categorization"
DEFAULT_FOOD_CARD_EMBEDDING_MODEL = os.getenv("OPENAI_FOOD_CARD_EMBEDDING_MODEL", "text-embedding-3-large")
SCENARIOS = {
    "denovo": PROJECT_ROOT / "outputs" / "enhanced_hpp" / "1.denovo",
    "nutrimatch_based": PROJECT_ROOT / "outputs" / "enhanced_hpp" / "2.nutrimatch_based",
}
CARD_TOP_K = {
    "nutrients": 18,
    "chemical_themes": 10,
    "chemical_examples": 12,
    "metabolite_themes": 10,
    "metabolite_examples": 12,
    "disease_themes": 8,
    "pathway_themes": 8,
}
GENERIC_PHRASES = {
    "chemical annotation",
    "general biology annotation",
    "uncategorized chemical or metabolite annotation",
    "uncategorized chemical or metabolite",
}
CORE_NUTRIENTS = [
    "Energy",
    "Water",
    "Protein",
    "Total lipid (fat)",
    "Carbohydrate, by difference",
    "Fiber, total dietary",
    "Sugars, Total",
    "Sugars, total including NLEA",
    "Sodium, Na",
    "Potassium, K",
    "Calcium, Ca",
    "Magnesium, Mg",
    "Iron, Fe",
    "Zinc, Zn",
    "Caffeine",
    "Theobromine",
    "Alcohol, ethyl",
    "Cholesterol",
    "Vitamin C, total ascorbic acid",
    "Vitamin B-12",
    "Vitamin B-6",
    "Niacin",
    "Riboflavin",
    "Thiamin",
    "Folate, total",
    "Vitamin D (D2 + D3)",
    "Vitamin E (alpha-tocopherol)",
    "Vitamin K",
    "Choline, total",
]


def _split_pipe(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [part.strip() for part in str(value).split("|") if part and part.strip()]


def _clean_label(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    label = re.sub(r"\s+", " ", str(value)).strip()
    return "" if label.lower() in {"nan", "none", "null"} else label


def _fmt_number(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    value = float(value)
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    if abs(value) >= 1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _safe_int(value: object) -> int:
    if value is None or pd.isna(value):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _join(items: Iterable[str], limit: int | None = None) -> str:
    clean = []
    seen = set()
    for item in items:
        item = _clean_label(item)
        if item and item.lower() not in seen:
            clean.append(item)
            seen.add(item.lower())
    if limit:
        clean = clean[:limit]
    if not clean:
        return "unavailable"
    if len(clean) == 1:
        return clean[0]
    return ", ".join(clean[:-1]) + ", and " + clean[-1]


def _pipe_items(value: object, limit: int | None = None) -> list[str]:
    return _split_pipe(value)[:limit] if value is not None else []


def _read_ndjson(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _append_source(record: dict, source: str) -> None:
    sources = set(_split_pipe(record.get("sources")))
    sources.add(source)
    record["sources"] = "|".join(sorted(sources))


def _foodatlas_entities() -> pd.DataFrame:
    zip_path = PROJECT_ROOT / "data" / "FoodAtlas" / "foodatlas-v4.5.zip"
    if not zip_path.exists():
        return pd.DataFrame()
    with zipfile.ZipFile(zip_path) as zf:
        name = next((n for n in zf.namelist() if n.endswith("entities.parquet")), None)
        if not name:
            return pd.DataFrame()
        with zf.open(name) as handle:
            return pd.read_parquet(handle)


def build_global_categorization_candidates(output_dir: Path = CATEGORIZATION_DIR) -> dict:
    """Create whole-KG entity lists for one-time LLM/expert categorization."""
    output_dir.mkdir(parents=True, exist_ok=True)

    hmdb_path = PROJECT_ROOT / "outputs" / "layered" / "layer4_hmdb_metabolite_index.csv"
    foodb_compound_path = PROJECT_ROOT / "data" / "FooDB" / "foodb_2020_04_07_json" / "Compound.json"
    foodb_pathway_path = PROJECT_ROOT / "data" / "FooDB" / "foodb_2020_04_07_json" / "Pathway.json"
    foodb_health_path = PROJECT_ROOT / "data" / "FooDB" / "foodb_2020_04_07_json" / "HealthEffect.json"
    foodatlas_compound_ref = PROJECT_ROOT / "outputs" / "reference" / "canonical_food_compound_reference.csv"
    foodatlas_disease_ref = PROJECT_ROOT / "outputs" / "reference" / "canonical_food_disease_pathway_features.csv"

    metabolites: dict[str, dict] = {}
    chemicals: dict[str, dict] = {}
    pathways: dict[str, dict] = {}
    diseases: dict[str, dict] = {}

    hmdb_disease_counter: Counter[str] = Counter()
    hmdb_pathway_counter: Counter[str] = Counter()
    hmdb_metabolite_biospecimens: defaultdict[str, set] = defaultdict(set)

    if hmdb_path.exists():
        hmdb_cols = [
            "hmdb_id",
            "hmdb_name",
            "biospecimen",
            "foodb_id",
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
        for chunk in pd.read_csv(hmdb_path, usecols=hmdb_cols, chunksize=10000):
            for _, row in chunk.iterrows():
                name = _clean_label(row["hmdb_name"])
                if name:
                    rec = metabolites.setdefault(
                        name,
                        {
                            "label": name,
                            "example_ids": set(),
                            "kingdom": _clean_label(row["kingdom"]),
                            "super_class": _clean_label(row["super_class"]),
                            "chemical_class": _clean_label(row["class"]),
                            "sub_class": _clean_label(row["sub_class"]),
                            "direct_parent": _clean_label(row["direct_parent"]),
                            "biospecimens": set(),
                            "source_database": "HMDB",
                            "sources": "",
                        },
                    )
                    if _clean_label(row["hmdb_id"]):
                        rec["example_ids"].add(_clean_label(row["hmdb_id"]))
                    if _clean_label(row["biospecimen"]):
                        rec["biospecimens"].add(_clean_label(row["biospecimen"]))
                    _append_source(rec, "HMDB metabolite index")
                    hmdb_metabolite_biospecimens[name].update(rec["biospecimens"])

                for disease in _split_pipe(row["disease_names"]):
                    hmdb_disease_counter[disease] += 1
                    rec = diseases.setdefault(
                        disease,
                        {
                            "label": disease,
                            "source_database": "HMDB",
                            "annotation_count": 0,
                            "sources": "",
                        },
                    )
                    rec["annotation_count"] += 1
                    _append_source(rec, "HMDB metabolite disease annotations")

                for pathway in _split_pipe(row["pathway_names"]):
                    hmdb_pathway_counter[pathway] += 1
                    rec = pathways.setdefault(
                        pathway,
                        {
                            "label": pathway,
                            "source_database": "HMDB",
                            "annotation_count": 0,
                            "sources": "",
                        },
                    )
                    rec["annotation_count"] += 1
                    _append_source(rec, "HMDB metabolite pathway annotations")

    if foodb_compound_path.exists():
        for row in _read_ndjson(foodb_compound_path):
            name = _clean_label(row.get("name"))
            if not name:
                continue
            rec = chemicals.setdefault(
                name,
                {
                    "label": name,
                    "foodb_public_id": _clean_label(row.get("public_id")),
                    "source_database": "FooDB",
                    "kingdom": _clean_label(row.get("kingdom")),
                    "super_class": _clean_label(row.get("superklass")),
                    "chemical_class": _clean_label(row.get("klass")),
                    "sub_class": _clean_label(row.get("subklass")),
                    "annotation_quality": _clean_label(row.get("annotation_quality")),
                    "description": _clean_label(row.get("description")),
                    "sources": "",
                },
            )
            _append_source(rec, "FooDB Compound.json")

    if foodb_pathway_path.exists():
        for row in _read_ndjson(foodb_pathway_path):
            name = _clean_label(row.get("name"))
            if not name:
                continue
            rec = pathways.setdefault(
                name,
                {
                    "label": name,
                    "source_database": "FooDB",
                    "annotation_count": 0,
                    "sources": "",
                },
            )
            if _clean_label(row.get("smpdb_id")):
                rec["smpdb_id"] = _clean_label(row.get("smpdb_id"))
            if _clean_label(row.get("kegg_map_id")):
                rec["kegg_map_id"] = _clean_label(row.get("kegg_map_id"))
            _append_source(rec, "FooDB Pathway.json")

    if foodb_health_path.exists():
        for row in _read_ndjson(foodb_health_path):
            name = _clean_label(row.get("name"))
            if not name:
                continue
            rec = diseases.setdefault(
                name,
                {
                    "label": name,
                    "source_database": "FooDB HealthEffect",
                    "annotation_count": 0,
                    "sources": "",
                },
            )
            rec["description"] = _clean_label(row.get("description"))
            _append_source(rec, "FooDB HealthEffect.json")

    if foodatlas_compound_ref.exists():
        for chunk in pd.read_csv(
            foodatlas_compound_ref,
            usecols=["compound_name", "compound_entity_type", "source_database"],
            chunksize=100000,
        ):
            for _, row in chunk.drop_duplicates().iterrows():
                name = _clean_label(row["compound_name"])
                if not name:
                    continue
                rec = chemicals.setdefault(
                    name,
                    {
                        "label": name,
                        "foodb_public_id": "",
                        "source_database": "FoodAtlas",
                        "kingdom": "",
                        "super_class": "",
                        "chemical_class": _clean_label(row["compound_entity_type"]),
                        "sub_class": "",
                        "annotation_quality": "",
                        "description": "",
                        "sources": "",
                    },
                )
                _append_source(rec, "FoodAtlas compound reference")

    if foodatlas_disease_ref.exists():
        df = pd.read_csv(foodatlas_disease_ref, nrows=1)
        for col in df.columns:
            if "disease" not in col.lower() and "pathway" not in col.lower():
                continue
            for chunk in pd.read_csv(foodatlas_disease_ref, usecols=[col], chunksize=100000):
                values = chunk[col].dropna().astype(str)
                for value in values:
                    for part in _split_pipe(value):
                        target = diseases if "disease" in col.lower() else pathways
                        rec = target.setdefault(
                            part,
                            {
                                "label": part,
                                "source_database": "FoodAtlas",
                                "annotation_count": 0,
                                "sources": "",
                            },
                        )
                        rec["annotation_count"] = rec.get("annotation_count", 0) + 1
                        _append_source(rec, f"FoodAtlas {col}")

    foodatlas_entities = _foodatlas_entities()
    if not foodatlas_entities.empty:
        lower_cols = {c.lower(): c for c in foodatlas_entities.columns}
        name_col = lower_cols.get("name") or lower_cols.get("label") or lower_cols.get("title")
        type_col = lower_cols.get("type") or lower_cols.get("entity_type") or lower_cols.get("kind")
        if name_col:
            for _, row in foodatlas_entities.iterrows():
                name = _clean_label(row[name_col])
                if not name:
                    continue
                typ = _clean_label(row[type_col]).lower() if type_col else ""
                if "chemical" in typ or "compound" in typ or "metabolite" in typ:
                    target = chemicals
                    source_database = "FoodAtlas"
                elif "disease" in typ or "phenotype" in typ:
                    target = diseases
                    source_database = "FoodAtlas"
                elif "pathway" in typ:
                    target = pathways
                    source_database = "FoodAtlas"
                else:
                    continue
                rec = target.setdefault(
                    name,
                    {
                        "label": name,
                        "source_database": source_database,
                        "annotation_count": 0,
                        "sources": "",
                    },
                )
                _append_source(rec, "FoodAtlas entities.parquet")

    metabolite_rows = []
    for rec in metabolites.values():
        metabolite_rows.append(
            {
                "label": rec["label"],
                "example_hmdb_ids": "|".join(sorted(rec["example_ids"])[:5]),
                "source_database": rec["source_database"],
                "kingdom": rec["kingdom"],
                "super_class": rec["super_class"],
                "chemical_class": rec["chemical_class"],
                "sub_class": rec["sub_class"],
                "direct_parent": rec["direct_parent"],
                "biospecimens": "|".join(sorted(rec["biospecimens"])),
                "sources": rec["sources"],
            }
        )

    chemical_rows = list(chemicals.values())
    pathway_rows = list(pathways.values())
    disease_rows = list(diseases.values())

    tables = {
        "metabolites": pd.DataFrame(metabolite_rows),
        "chemicals": pd.DataFrame(chemical_rows),
        "pathways": pd.DataFrame(pathway_rows),
        "diseases": pd.DataFrame(disease_rows),
    }

    summary = {}
    for kind, df in tables.items():
        if df.empty:
            continue
        if "annotation_count" in df.columns:
            df["annotation_count"] = df["annotation_count"].fillna(0).astype(int)
            df = df.sort_values(["annotation_count", "label"], ascending=[False, True])
        else:
            df = df.sort_values("label")
        out = output_dir / f"LLM_categorization_{kind}_global_candidates.csv"
        df.to_csv(out, index=False)
        template = df[["label"]].copy()
        for col in [
            "keep_for_food_card",
            "primary_concept_group",
            "secondary_concept_groups",
            "embedding_phrase",
            "task_relevance",
            "specificity_level",
            "reason",
        ]:
            template[col] = ""
        template.to_csv(output_dir / f"LLM_categorization_{kind}_global_review_template.csv", index=False)
        summary[kind] = {"n_candidates": int(len(df)), "file": str(out)}

    summary_path = output_dir / "LLM_categorization_global_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _keyword_group(label: str, rules: list[tuple[str, str, str]]) -> tuple[str, str]:
    lower = label.lower()
    for pattern, group, phrase in rules:
        if re.search(pattern, lower):
            return group, phrase
    return "general biology annotation", label


CHEMICAL_RULES = [
    (r"caffeine|xanthine|theobromine|theophylline|alkaloid", "alkaloid and methylxanthine chemistry", "alkaloid-like and methylxanthine small-molecule chemistry"),
    (r"flavonoid|phenylpropanoid|polyphenol|benzenoid|coumarin|stilbene|tannin|cinnamic|phenolic", "polyphenol and plant secondary metabolite chemistry", "polyphenol-like plant secondary metabolite chemistry"),
    (r"fatty|lipid|glycerolipid|glycerophospholipid|sphingolipid|sterol|prenol|eicosanoid|linoleic", "lipid and fatty-acid chemistry", "fatty-acid, sterol, and lipid-related chemistry"),
    (r"carbohydrate|sugar|glycoside|glucoside|sucrose|fructose|glucose", "carbohydrate and glycoside chemistry", "carbohydrate, sugar, and glycoside chemistry"),
    (r"amino acid|peptide|protein|histidine|arginine|glycine|serine|threonine|tryptophan|tyrosine", "amino-acid and peptide chemistry", "amino-acid and peptide-related chemistry"),
    (r"organic acid|carboxylic|keto acid|hydroxy acid|pyruv|lactate|citrate", "organic-acid and central-carbon chemistry", "organic-acid and central-carbon metabolite chemistry"),
    (r"vitamin|tocopherol|retinol|folate|riboflavin|niacin|thiamine|biotin|cobalamin", "vitamin and micronutrient chemistry", "vitamin and micronutrient-related chemistry"),
    (r"metal|mineral|calcium|magnesium|iron|zinc|sodium|potassium|selenium|copper", "mineral and inorganic chemistry", "mineral and inorganic compound annotation"),
    (r"sulfur|thiol|sulf", "organosulfur chemistry", "organosulfur compound chemistry"),
    (r"nitrogen|amine|pyridine|pteridine|diazine|nucleotide|nucleoside", "nitrogen heterocycle and nucleotide chemistry", "nitrogen-containing heterocycle, nucleotide, and nucleoside chemistry"),
]

PATHWAY_RULES = [
    (r"caffeine|xanthine", "caffeine and methylxanthine metabolism", "caffeine, xanthine, and methylxanthine metabolism"),
    (r"purine|pyrimidine|nucleotide|nucleoside|adenosine|guanine", "purine, pyrimidine, and nucleotide metabolism", "purine, pyrimidine, nucleotide, and nucleoside metabolism"),
    (r"glycine|serine|threonine|arginine|proline|tryptophan|tyrosine|histidine|alanine|aspartate|glutamate|methionine|cysteine|lysine|leucine|isoleucine|valine|amino", "amino-acid metabolism", "amino-acid metabolism"),
    (r"fatty|lipid|linole|linolen|arachidon|sphingo|glycerolipid|bile|cholesterol|steroid", "lipid, fatty-acid, bile-acid, and steroid metabolism", "lipid, fatty-acid, bile-acid, and steroid metabolism"),
    (r"glucose|glycolysis|gluconeogenesis|pyruvate|citrate|krebs|tca|warburg|energy|carbon", "central carbon and energy metabolism", "central carbon, pyruvate, TCA, and energy metabolism"),
    (r"xenobiotic|drug|action pathway|cytochrome|cyp|detox|disulfiram|ethanol", "xenobiotic and drug metabolism", "xenobiotic, drug-action, and hepatic biotransformation pathway annotation"),
    (r"oxidative|glutathione|reactive oxygen|inflamm|immune", "oxidative stress and immune-inflammatory signaling", "oxidative stress, glutathione, and immune-inflammatory signaling"),
    (r"microbial|bacterial|gut|short chain|butyrate|propionate", "gut microbial metabolism", "gut microbial and short-chain-fatty-acid metabolism"),
    (r"transcription|translation|rna|dna|protein synthesis", "gene expression and protein synthesis annotation", "gene expression, transcription, translation, and protein-synthesis annotation"),
]

DISEASE_RULES = [
    (r"anxiety|depress|schizophrenia|autism|bipolar|psychiatric|mental|sleep", "mental health and neuropsychiatric phenotype", "mental health, sleep, and neuropsychiatric phenotype annotation"),
    (r"alzheimer|dementia|parkinson|neurodegeneration|cognitive|brain", "neurodegeneration and cognitive aging", "neurodegeneration and cognitive-aging phenotype annotation"),
    (r"crohn|colitis|irritable bowel|bowel|intestinal|gastro|eosinophilic esophagitis", "gastrointestinal inflammation and gut phenotype", "gastrointestinal inflammation, bowel disease, and gut phenotype annotation"),
    (r"diabetes|obesity|metabolic syndrome|insulin|hypergly|lipid|fatty liver|cardio|blood pressure|hypertension|atherosclerosis", "cardiometabolic disease", "cardiometabolic, obesity, diabetes, lipid, and blood-pressure phenotype annotation"),
    (r"cancer|carcinoma|melanoma|leukemia|tumou?r|neoplasm|lymphoma", "cancer and tumor biology", "cancer and tumor-biology annotation"),
    (r"pregnancy|preeclampsia|antenatal|neonatal|fetal", "pregnancy and early-life context", "pregnancy, fetal, neonatal, and early-life annotation context"),
    (r"kidney|renal|uremia|nephro|urine|stone", "kidney and urinary disease", "kidney, renal, and urinary phenotype annotation"),
    (r"liver|hepatic|cholest|cirrhosis|hepat", "liver and hepatobiliary disease", "liver and hepatobiliary phenotype annotation"),
    (r"immune|inflamm|infection|arthritis|asthma|allerg|autoimmune", "immune and inflammatory disease", "immune, inflammatory, allergy, and autoimmune phenotype annotation"),
    (r"deficiency|inborn error|syndrome|hyper|hypo|aciduria|emia|uria", "inborn-error and deficiency phenotype", "inborn-error, deficiency, and metabolic-disorder annotation"),
]


def build_seed_categorizations(output_dir: Path = CATEGORIZATION_DIR) -> dict:
    """Create deterministic seed groupings for the global candidate lists."""
    output_dir.mkdir(parents=True, exist_ok=True)
    configs = {
        "metabolites": CHEMICAL_RULES,
        "chemicals": CHEMICAL_RULES,
        "pathways": PATHWAY_RULES,
        "diseases": DISEASE_RULES,
    }
    summary = {}
    for kind, rules in configs.items():
        path = output_dir / f"LLM_categorization_{kind}_global_candidates.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        rows = []
        for _, row in df.iterrows():
            label = _clean_label(row.get("label"))
            group, phrase = _keyword_group(label, rules)
            if kind in {"metabolites", "chemicals"} and group == "general biology annotation":
                for col in ["super_class", "chemical_class", "sub_class", "direct_parent"]:
                    value = _clean_label(row.get(col))
                    if value:
                        group, phrase = _keyword_group(value, rules)
                        if group != "general biology annotation":
                            break
                if group == "general biology annotation":
                    superclass = _clean_label(row.get("super_class"))
                    chem_class = _clean_label(row.get("chemical_class"))
                    group = superclass or chem_class or "uncategorized chemical or metabolite"
                    phrase = f"{group} annotation"
            keep = "yes"
            specificity = "moderate"
            if re.fullmatch(r"(type \d+[a-z]?|neonatal|antenatal|with .+|and .+)", label.lower()):
                keep = "no"
                specificity = "fragment_or_bad_label"
                group = "fragmented label"
                phrase = "discard fragmented label"
            elif group.startswith("general") or group.startswith("uncategorized"):
                specificity = "generic"
            elif any(token in label.lower() for token in ["metabolism", "disease", "cancer", "acid", "lipid", "caffeine"]):
                specificity = "specific"
            task = "general_biology"
            if "mental" in group or "neuro" in group:
                task = "mental_health"
            elif "cardiometabolic" in group or "energy" in group or "lipid" in group:
                task = "cardiometabolic"
            elif "microbial" in group or "gastrointestinal" in group:
                task = "microbiome"
            elif "metabolism" in group or kind == "metabolites":
                task = "metabolomics"
            elif "cancer" in group:
                task = "cancer"
            elif "immune" in group or "inflammatory" in group:
                task = "immune_inflammation"
            rows.append(
                {
                    "label": label,
                    "keep_for_food_card": keep,
                    "primary_concept_group": group,
                    "secondary_concept_groups": "",
                    "embedding_phrase": phrase,
                    "task_relevance": task,
                    "specificity_level": specificity,
                    "reason": "deterministic seed grouping from source taxonomy and biomedical keywords; intended for later LLM/expert review",
                }
            )
        out = output_dir / f"LLM_categorization_{kind}_global_seed_reviewed.csv"
        pd.DataFrame(rows).to_csv(out, index=False)
        summary[kind] = {"n_seed_rows": len(rows), "file": str(out)}
    (output_dir / "LLM_categorization_seed_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def _load_category_map(kind: str, categorization_dir: Path = CATEGORIZATION_DIR) -> dict[str, dict]:
    reviewed = categorization_dir / f"LLM_categorization_{kind}_global_reviewed.csv"
    seed = categorization_dir / f"LLM_categorization_{kind}_global_seed_reviewed.csv"
    path = reviewed if reviewed.exists() else seed
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    out = {}
    for _, row in df.iterrows():
        label = _clean_label(row.get("label"))
        if not label:
            continue
        keep = _clean_label(row.get("keep_for_food_card")).lower()
        if keep and keep not in {"yes", "maybe", "true", "1"}:
            continue
        out[label.lower()] = {
            "group": _clean_label(row.get("primary_concept_group")) or label,
            "phrase": _clean_label(row.get("embedding_phrase")) or label,
            "task_relevance": _clean_label(row.get("task_relevance")),
            "specificity_level": _clean_label(row.get("specificity_level")),
        }
    return out


def _categorize_label(label: object, maps: list[dict[str, dict]]) -> tuple[str, str]:
    label = _clean_label(label)
    if not label:
        return "", ""
    for mapping in maps:
        rec = mapping.get(label.lower())
        if rec:
            return rec["group"], rec["phrase"]
    return label, label


def _top_counter(counter: Counter[str], limit: int) -> list[str]:
    return [item for item, _ in counter.most_common(limit) if item]


def _top_informative(counter: Counter[str], limit: int) -> list[str]:
    items = [item for item, _ in counter.most_common() if item and item.lower() not in GENERIC_PHRASES]
    if len(items) >= limit:
        return items[:limit]
    seen = {item.lower() for item in items}
    for item, _ in counter.most_common():
        if item and item.lower() not in seen:
            items.append(item)
            seen.add(item.lower())
        if len(items) >= limit:
            break
    return items[:limit]


def _evidence_weight(value: object) -> float:
    if value is None or pd.isna(value):
        return 1.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 1.0
    if numeric <= 0:
        return 0.25
    return 1.0 + min(math.log1p(numeric), 8.0)


def _aggregate_chemical_evidence(
    canonical_ids: set[str],
    chemical_map: dict[str, dict],
    metabolite_map: dict[str, dict],
) -> dict[str, dict]:
    evidence = defaultdict(lambda: {"theme_counts": Counter(), "examples": Counter(), "source_rows": 0})
    foodb_path = PROJECT_ROOT / "outputs" / "reference" / "canonical_food_foodb_compound_reference.csv"
    if foodb_path.exists():
        usecols = [
            "canonical_food_id",
            "compound_name",
            "standard_content",
            "chemical_class",
            "chemical_superclass",
            "annotation_quality",
        ]
        for chunk in pd.read_csv(foodb_path, usecols=usecols, chunksize=250000):
            chunk = chunk[chunk["canonical_food_id"].isin(canonical_ids)]
            chunk = chunk.dropna(subset=["compound_name", "chemical_class", "chemical_superclass"], how="all")
            for _, row in chunk.iterrows():
                canonical = row["canonical_food_id"]
                evidence[canonical]["source_rows"] += 1
                name = _clean_label(row.get("compound_name"))
                weight = _evidence_weight(row.get("standard_content"))
                if name:
                    evidence[canonical]["examples"][name] += weight
                labels = [row.get("compound_name"), row.get("chemical_class"), row.get("chemical_superclass")]
                for label in labels:
                    group, phrase = _categorize_label(label, [chemical_map, metabolite_map])
                    if phrase:
                        evidence[canonical]["theme_counts"][phrase] += weight
    foodatlas_path = PROJECT_ROOT / "outputs" / "reference" / "canonical_food_compound_reference.csv"
    if foodatlas_path.exists():
        for chunk in pd.read_csv(foodatlas_path, chunksize=100000):
            chunk = chunk[chunk["canonical_food_id"].isin(canonical_ids)]
            for _, row in chunk.iterrows():
                canonical = row["canonical_food_id"]
                evidence[canonical]["source_rows"] += 1
                name = _clean_label(row.get("compound_name"))
                if name:
                    evidence[canonical]["examples"][name] += 1
                    _, phrase = _categorize_label(name, [chemical_map, metabolite_map])
                    if phrase:
                        evidence[canonical]["theme_counts"][phrase] += 1
                compound_type = _clean_label(row.get("compound_entity_type"))
                if compound_type:
                    _, phrase = _categorize_label(compound_type, [chemical_map])
                    if phrase:
                        evidence[canonical]["theme_counts"][phrase] += 1
    return evidence


def _aggregate_metabolite_evidence(canonical_ids: set[str], metabolite_map: dict[str, dict]) -> dict[str, dict]:
    evidence = defaultdict(
        lambda: {
            "theme_counts": Counter(),
            "examples": Counter(),
            "biospecimens": Counter(),
            "source_rows": 0,
        }
    )
    path = PROJECT_ROOT / "outputs" / "reference" / "canonical_food_hmdb_metabolite_edges.csv"
    if not path.exists():
        return evidence
    usecols = [
        "canonical_food_id",
        "compound_name",
        "hmdb_name",
        "biospecimen",
        "super_class",
        "class",
        "sub_class",
        "direct_parent",
    ]
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=200000):
        chunk = chunk[chunk["canonical_food_id"].isin(canonical_ids)]
        for _, row in chunk.iterrows():
            canonical = row["canonical_food_id"]
            evidence[canonical]["source_rows"] += 1
            hmdb_name = _clean_label(row.get("hmdb_name"))
            if hmdb_name:
                evidence[canonical]["examples"][hmdb_name] += 1
            biospecimen = _clean_label(row.get("biospecimen"))
            if biospecimen:
                evidence[canonical]["biospecimens"][biospecimen] += 1
            for label in [
                row.get("hmdb_name"),
                row.get("direct_parent"),
                row.get("sub_class"),
                row.get("class"),
                row.get("super_class"),
            ]:
                _, phrase = _categorize_label(label, [metabolite_map])
                if phrase:
                    evidence[canonical]["theme_counts"][phrase] += 1
    return evidence


def _load_scenario_tables(scenario_dir: Path) -> dict[str, pd.DataFrame]:
    tables = {
        "nutrients": pd.read_csv(scenario_dir / "hpp_nutrient_reference_per_100g.csv"),
    }
    layer_dir = scenario_dir / "layer_tables"
    for layer, name in [
        ("product", "layer2_product_processing_reference.csv"),
        ("chemical", "layer3_food_chemical_reference.csv"),
        ("metabolomics", "layer4_human_metabolomics_reference.csv"),
        ("disease_pathway", "layer5_disease_pathway_reference.csv"),
    ]:
        path = layer_dir / name
        tables[layer] = pd.read_csv(path) if path.exists() else pd.DataFrame()
    return tables


def _merge_layer_tables(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base = tables["nutrients"].copy()
    keys = [
        "hpp_food_id",
        "hpp_food_name",
        "hpp_product_name",
        "hpp_short_description",
        "hpp_hebrew_name",
        "hpp_category",
        "number_loggings",
        "canonical_food_id",
        "canonical_name",
        "canonical_category",
        "canonical_assignment_method",
    ]
    keep_keys = [k for k in keys if k in base.columns]
    out = base
    for name in ["product", "chemical", "metabolomics", "disease_pathway"]:
        df = tables.get(name, pd.DataFrame())
        if df.empty:
            continue
        value_cols = [c for c in df.columns if c.startswith("canonical_inherited__")]
        out = out.merge(df[["hpp_food_id"] + value_cols], on="hpp_food_id", how="left")
    return out


def _nutrient_sentence(row: pd.Series) -> tuple[str, int]:
    parts = []
    for nutrient in CORE_NUTRIENTS:
        if nutrient not in row.index:
            continue
        value = row.get(nutrient)
        if pd.isna(value):
            continue
        try:
            if float(value) == 0:
                continue
        except (TypeError, ValueError):
            continue
        unit = "kcal" if nutrient == "Energy" else "g or source-native unit"
        if any(token in nutrient.lower() for token in ["sodium", "potassium", "calcium", "magnesium", "iron", "zinc", "caffeine", "theobromine", "niacin", "riboflavin", "thiamin", "vitamin", "folate", "choline"]):
            unit = "mg or source-native micronutrient unit"
        if nutrient == "Water":
            unit = "g"
        parts.append(f"{nutrient} {_fmt_number(value)} {unit}")
    return _join(parts, CARD_TOP_K["nutrients"]), len(parts)


def _product_sentence(row: pd.Series) -> tuple[str, int]:
    fields = {
        "OpenFoodFacts product": "canonical_inherited__openfoodfacts_product_name",
        "match confidence": "canonical_inherited__openfoodfacts_confidence",
        "brand": "canonical_inherited__brands",
        "country": "canonical_inherited__countries_en",
        "ingredients": "canonical_inherited__ingredients_text",
        "additives": "canonical_inherited__additives_tags",
        "labels": "canonical_inherited__labels_en",
        "Nutri-Score": "canonical_inherited__nutriscore_grade",
        "NOVA class": "canonical_inherited__nova_group",
        "PNNS group": "canonical_inherited__pnns_groups_1",
    }
    parts = []
    for label, col in fields.items():
        value = _clean_label(row.get(col))
        if value and value.lower() != "unknown":
            parts.append(f"{label}: {value}")
    if not parts:
        return "product and processing annotations are unavailable or sparse for this food", 0
    return _join(parts, 8), len(parts)


def _themes_from_pipe(value: object, cmap: dict[str, dict], limit: int) -> list[str]:
    counter = Counter()
    for item in _pipe_items(value):
        _, phrase = _categorize_label(item, [cmap])
        if phrase:
            counter[phrase] += 1
    return _top_counter(counter, limit)


def _full_food_card_text(
    row: pd.Series,
    scenario: str,
    chemical_evidence: dict,
    metabolite_evidence: dict,
    chemical_map: dict[str, dict],
    disease_map: dict[str, dict],
    pathway_map: dict[str, dict],
) -> dict:
    nutrient_text, nutrient_count = _nutrient_sentence(row)
    product_text, product_count = _product_sentence(row)
    canonical_id = _clean_label(row.get("canonical_food_id"))
    chem = chemical_evidence.get(canonical_id, {})
    met = metabolite_evidence.get(canonical_id, {})

    layer_chem_themes = []
    for col in [
        "canonical_inherited__foodb_top_chemical_classes",
        "canonical_inherited__foodb_top_chemical_superclasses",
    ]:
        layer_chem_themes.extend(_themes_from_pipe(row.get(col), chemical_map, 12))
    chemical_themes = _join(
        _top_informative(chem.get("theme_counts", Counter()), CARD_TOP_K["chemical_themes"]) + layer_chem_themes,
        CARD_TOP_K["chemical_themes"],
    )
    chemical_examples = _join(
        _top_informative(chem.get("examples", Counter()), CARD_TOP_K["chemical_examples"]),
        CARD_TOP_K["chemical_examples"],
    )

    metabolite_themes = _join(
        _top_informative(met.get("theme_counts", Counter()), CARD_TOP_K["metabolite_themes"]),
        CARD_TOP_K["metabolite_themes"],
    )
    metabolite_examples = _join(
        _top_informative(met.get("examples", Counter()), CARD_TOP_K["metabolite_examples"]),
        CARD_TOP_K["metabolite_examples"],
    )
    biospecimens = _join(_top_counter(met.get("biospecimens", Counter()), 8), 8)

    disease_themes = _join(
        _themes_from_pipe(row.get("canonical_inherited__hmdb_top_diseases"), disease_map, CARD_TOP_K["disease_themes"]),
        CARD_TOP_K["disease_themes"],
    )
    pathway_themes = _join(
        _themes_from_pipe(row.get("canonical_inherited__hmdb_top_pathways"), pathway_map, CARD_TOP_K["pathway_themes"]),
        CARD_TOP_K["pathway_themes"],
    )

    hpp_name = _clean_label(row.get("hpp_food_name")) or _clean_label(row.get("hpp_short_description"))
    category = _clean_label(row.get("hpp_category"))
    product = _clean_label(row.get("hpp_product_name"))
    hebrew = _clean_label(row.get("hpp_hebrew_name"))
    canonical_name = _clean_label(row.get("canonical_name"))
    logs = _clean_label(row.get("number_loggings"))

    identity = (
        f"Food: {hpp_name}. HPP food id {row.get('hpp_food_id')}. "
        f"The HPP description is {product or hpp_name}"
        f"{f', with Hebrew name {hebrew}' if hebrew else ''}. "
        f"This item belongs to the HPP {category or 'unknown'} category"
        f"{f' and was logged {logs} times' if logs else ''}. "
        f"It maps to the canonical helper food concept {canonical_name or canonical_id}."
    )
    nutrition = f"Per 100 g reference nutrient profile: {nutrient_text}."
    product_section = f"Product and processing evidence: {product_text}."
    chemistry = (
        f"Food chemistry themes: {chemical_themes}. "
        f"Representative compound names from FooDB/FoodAtlas evidence include {chemical_examples}. "
        f"Chemical evidence rows linked through the canonical helper: {chem.get('source_rows', 0)}."
    )
    metabolomics = (
        f"Metabolomic themes: {metabolite_themes}. "
        f"Representative HMDB-linked metabolite names include {metabolite_examples}. "
        f"Observed or annotated biospecimen contexts include {biospecimens}. "
        f"Metabolite evidence rows linked through the canonical helper: {met.get('source_rows', 0)}."
    )
    disease_pathway = (
        f"Disease and phenotype neighborhood themes: {disease_themes}. "
        f"Pathway themes: {pathway_themes}. "
        f"FoodAtlas disease edges include {_safe_int(row.get('canonical_inherited__foodatlas_disease_edge_count'))} total edges, "
        f"with {_safe_int(row.get('canonical_inherited__foodatlas_positive_disease_edge_count'))} positive and "
        f"{_safe_int(row.get('canonical_inherited__foodatlas_negative_disease_edge_count'))} negative association edges when available. "
        f"HMDB summaries include {_safe_int(row.get('canonical_inherited__hmdb_disease_count'))} disease annotations and "
        f"{_safe_int(row.get('canonical_inherited__hmdb_pathway_count'))} pathway annotations."
    )
    caveat = (
        "These chemical, metabolite, disease, and pathway links are database-derived reference graph annotations "
        "for representation learning, downstream prediction, and hypothesis discovery; they are not causal estimates "
        "or measured post-ingestion amounts."
    )
    nutrition_core = " ".join([identity, nutrition, product_section])
    chemistry_metabolomics = " ".join([nutrition_core, chemistry, metabolomics, caveat])
    full_biology = " ".join([chemistry_metabolomics, disease_pathway])
    return {
        "nutrition_core_text": nutrition_core,
        "chemistry_metabolomics_text": chemistry_metabolomics,
        "full_biology_text": full_biology,
        "nutrient_count": nutrient_count,
        "product_processing_count": product_count,
        "chemical_theme_count": len(_top_informative(chem.get("theme_counts", Counter()), 1000)),
        "chemical_example_count": len(chem.get("examples", {})),
        "metabolite_theme_count": len(_top_informative(met.get("theme_counts", Counter()), 1000)),
        "metabolite_example_count": len(met.get("examples", {})),
        "disease_theme_text": disease_themes,
        "pathway_theme_text": pathway_themes,
    }


def build_food_cards(
    scenarios: Iterable[str] = ("denovo", "nutrimatch_based"),
    output_dir: Path = OUTPUT_DIR,
) -> dict:
    """Build deterministic food-card text for every HPP food in active scenarios."""
    output_dir.mkdir(parents=True, exist_ok=True)
    chemical_map = _load_category_map("chemicals")
    metabolite_map = _load_category_map("metabolites")
    disease_map = _load_category_map("diseases")
    pathway_map = _load_category_map("pathways")

    scenario_tables = {scenario: _merge_layer_tables(_load_scenario_tables(SCENARIOS[scenario])) for scenario in scenarios}
    canonical_ids = {
        _clean_label(cid)
        for df in scenario_tables.values()
        for cid in df.get("canonical_food_id", pd.Series(dtype=str)).dropna().unique()
        if _clean_label(cid)
    }
    chemical_evidence = _aggregate_chemical_evidence(canonical_ids, chemical_map, metabolite_map)
    metabolite_evidence = _aggregate_metabolite_evidence(canonical_ids, metabolite_map)

    summary = {
        "inputs": {
            "scenarios": list(scenarios),
            "categorization_dir": str(CATEGORIZATION_DIR),
            "chemical_categorization_count": len(chemical_map),
            "metabolite_categorization_count": len(metabolite_map),
            "disease_categorization_count": len(disease_map),
            "pathway_categorization_count": len(pathway_map),
        },
        "outputs": {},
    }
    all_rows = []
    for scenario, df in scenario_tables.items():
        rows = []
        for _, row in df.iterrows():
            card = _full_food_card_text(
                row,
                scenario,
                chemical_evidence,
                metabolite_evidence,
                chemical_map,
                disease_map,
                pathway_map,
            )
            base = {
                "scenario": scenario,
                "hpp_food_id": row.get("hpp_food_id"),
                "hpp_food_name": row.get("hpp_food_name"),
                "hpp_product_name": row.get("hpp_product_name"),
                "hpp_hebrew_name": row.get("hpp_hebrew_name"),
                "hpp_category": row.get("hpp_category"),
                "number_loggings": row.get("number_loggings"),
                "canonical_food_id": row.get("canonical_food_id"),
                "canonical_name": row.get("canonical_name"),
                "canonical_assignment_method": row.get("canonical_assignment_method"),
                **card,
            }
            rows.append(base)
            all_rows.append(base)
        scenario_dir = output_dir / scenario
        scenario_dir.mkdir(parents=True, exist_ok=True)
        out_df = pd.DataFrame(rows)
        csv_path = scenario_dir / "hpp_food_cards.csv"
        jsonl_path = scenario_dir / "hpp_food_cards.jsonl"
        embed_path = scenario_dir / "hpp_food_card_embedding_input.jsonl"
        out_df.to_csv(csv_path, index=False)
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for rec in rows:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with embed_path.open("w", encoding="utf-8") as handle:
            for rec in rows:
                handle.write(
                    json.dumps(
                        {
                            "id": f"{scenario}:{rec['hpp_food_id']}",
                            "scenario": scenario,
                            "hpp_food_id": rec["hpp_food_id"],
                            "text": rec["full_biology_text"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        summary["outputs"][scenario] = {
            "food_count": int(len(out_df)),
            "csv": str(csv_path),
            "jsonl": str(jsonl_path),
            "embedding_input_jsonl": str(embed_path),
            "mean_chemical_examples": float(out_df["chemical_example_count"].mean()),
            "mean_metabolite_examples": float(out_df["metabolite_example_count"].mean()),
        }
    combined = pd.DataFrame(all_rows)
    combined_path = output_dir / "hpp_food_cards_all_scenarios.csv"
    combined.to_csv(combined_path, index=False)
    summary["outputs"]["combined_csv"] = str(combined_path)
    summary_path = output_dir / "food_card_build_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _openai_client(force_prompt: bool = True):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required to build food-card embeddings.") from exc
    api_key = "" if force_prompt else os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        api_key = getpass.getpass("Paste OpenAI API key for this run only. It will not be saved: ").strip()
    if not api_key:
        raise RuntimeError("No OpenAI API key provided; food-card embeddings were not run.")
    return OpenAI(api_key=api_key)


def _embed_texts_openai(
    texts: list[str],
    model: str = DEFAULT_FOOD_CARD_EMBEDDING_MODEL,
    batch_size: int = 64,
    force_prompt: bool = True,
) -> list[list[float]]:
    client = _openai_client(force_prompt=force_prompt)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend([item.embedding for item in response.data])
    return vectors


def build_food_card_embeddings(
    scenarios: Iterable[str] = ("denovo", "nutrimatch_based"),
    text_column: str = "full_biology_text",
    model: str = DEFAULT_FOOD_CARD_EMBEDDING_MODEL,
    batch_size: int = 64,
    force_prompt: bool = True,
) -> dict:
    """Embed deterministic HPP food-card text for all active scenarios."""
    summary = {
        "model": model,
        "text_column": text_column,
        "batch_size": batch_size,
        "outputs": {},
        "api_key_policy": "API key is read from prompt/environment for this run only and is not saved.",
    }
    for scenario in scenarios:
        scenario_dir = OUTPUT_DIR / scenario
        cards_path = scenario_dir / "hpp_food_cards.csv"
        if not cards_path.exists():
            raise FileNotFoundError(f"Food cards not found: {cards_path}. Run build-food-cards first.")
        cards = pd.read_csv(cards_path)
        if text_column not in cards.columns:
            raise ValueError(f"Column {text_column!r} not found in {cards_path}.")
        texts = cards[text_column].fillna("").astype(str).tolist()
        vectors = _embed_texts_openai(texts, model=model, batch_size=batch_size, force_prompt=force_prompt)
        vector_df = pd.DataFrame(vectors, columns=[f"embedding_{i}" for i in range(len(vectors[0]))])
        meta_cols = [
            "scenario",
            "hpp_food_id",
            "hpp_food_name",
            "hpp_product_name",
            "hpp_hebrew_name",
            "hpp_category",
            "number_loggings",
            "canonical_food_id",
            "canonical_name",
            "canonical_assignment_method",
            "nutrient_count",
            "product_processing_count",
            "chemical_theme_count",
            "chemical_example_count",
            "metabolite_theme_count",
            "metabolite_example_count",
            "disease_theme_text",
            "pathway_theme_text",
        ]
        meta = cards[[col for col in meta_cols if col in cards.columns]].copy()
        meta["embedding_text_column"] = text_column
        meta["embedding_model"] = model
        out = pd.concat([meta.reset_index(drop=True), vector_df], axis=1)
        embeddings_dir = scenario_dir / "embeddings"
        embeddings_dir.mkdir(parents=True, exist_ok=True)
        safe_text = re.sub(r"[^a-zA-Z0-9_]+", "_", text_column).strip("_")
        safe_model = re.sub(r"[^a-zA-Z0-9_]+", "_", model).strip("_")
        parquet_path = embeddings_dir / f"hpp_food_card_embeddings_{safe_text}_{safe_model}.parquet"
        meta_path = embeddings_dir / f"hpp_food_card_embedding_metadata_{safe_text}_{safe_model}.csv"
        out.to_parquet(parquet_path, index=False)
        meta.to_csv(meta_path, index=False)
        summary["outputs"][scenario] = {
            "food_count": int(len(cards)),
            "embedding_dimensions": int(len(vectors[0])),
            "embeddings_parquet": str(parquet_path),
            "metadata_csv": str(meta_path),
        }
    summary_path = OUTPUT_DIR / "food_card_embedding_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    summary = {
        "global_candidates": build_global_categorization_candidates(),
        "seed_categorizations": build_seed_categorizations(),
        "food_cards": build_food_cards(),
    }
    print(json.dumps(summary, indent=2))
