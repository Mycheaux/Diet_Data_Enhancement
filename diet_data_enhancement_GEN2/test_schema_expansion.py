"""Check selection, missingness, identity interpretation and exported lineage."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from . import independent_pilot as pilot
from .expand_step1 import ALIASES, REPRESENTATIONS, DESCRIPTORS, OUT, descriptor_frames, read_source, select_catalog
from .export_nutrimatch_base import OUT as BASELINE, METADATA


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.foods = [{"hpp_food_id": "a", "primary_fdc_id": 1, "amino_acid_proxy_fdc_id": 3},
                      {"hpp_food_id": "b", "primary_fdc_id": 2}]
        values = {1003: {1: 2., 2: 1., 3: 1.}, 1008: {1: 10., 2: 20.},
                  1062: {1: 41.84, 2: 83.68}, 1104: {1: 100., 2: 50.}, 1110: {1: 4., 2: 8.},
                  1114: {1: .1, 2: .2}, 1213: {2: .1, 3: .05},
                  1259: {1: 0., 2: 0.}, 1265: {1: .5}, 1408: {1: .01, 2: .02}}
        self.nutrients = pd.DataFrame([{"id": n, "name": f"Nutrient {n}", "unit_name": "G"} for n in values]).set_index("id")
        rows = [{"fdc_id": f, "nutrient_id": n, "amount": v, "id": i}
                for i, (n, f, v) in enumerate((n, f, v) for n, foods in values.items() for f, v in foods.items())]
        self.amounts = pd.DataFrame(rows)

    def test_zero_is_recorded_but_absence_is_not_zero(self):
        registry, evidence = select_catalog(self.nutrients, self.amounts, self.foods)
        status = registry.set_index("usda_nutrient_id").status
        self.assertEqual(status[1259], "included")
        self.assertEqual(status[1265], "completion_pending")
        absent = evidence.loc[evidence.hpp_food_id.eq("b") & evidence.usda_nutrient_id.eq(1265)].iloc[0]
        self.assertTrue(pd.isna(absent.value))
        self.assertEqual(absent.method, "unresolved")

    def test_only_explicit_unit_aliases_are_excluded(self):
        registry, _ = select_catalog(self.nutrients, self.amounts, self.foods)
        aliases = registry.loc[registry.status.eq("unit_alias")]
        self.assertEqual(set(aliases.usda_nutrient_id), {1062, 1110})
        self.assertAlmostEqual(ALIASES[1062]["factor"] * 4.184, 1.)
        self.assertAlmostEqual(ALIASES[1110]["factor"] * 40, 1.)
        self.assertNotIn(1104, ALIASES)
        self.assertIsNone(REPRESENTATIONS[1104]["factor"])
        self.assertEqual(registry.set_index("usda_nutrient_id").loc[1104, "status"], "alternate_activity_convention")

    def test_ambiguous_source_identity_is_not_silently_renamed(self):
        registry, _ = select_catalog(self.nutrients, self.amounts, self.foods)
        self.assertEqual(registry.set_index("usda_nutrient_id").loc[1408, "status"], "source_label_review")

    def test_previously_reviewed_proxy_scales_by_protein(self):
        registry, evidence = select_catalog(self.nutrients, self.amounts, self.foods)
        self.assertEqual(registry.set_index("usda_nutrient_id").loc[1213, "status"], "included")
        proxy = evidence.loc[evidence.hpp_food_id.eq("a") & evidence.usda_nutrient_id.eq(1213)].iloc[0]
        self.assertAlmostEqual(proxy.value, .1)
        self.assertEqual(proxy.scale_factor, 2.)
        self.assertEqual(proxy.donor_fdc_id, 3)
        self.assertEqual(proxy.method, "protein_scaled_brewed_coffee_proxy")

    def test_no_proxy_without_positive_denominator(self):
        self.amounts.loc[self.amounts.fdc_id.eq(3) & self.amounts.nutrient_id.eq(1003), "amount"] = 0
        registry, _ = select_catalog(self.nutrients, self.amounts, self.foods)
        self.assertEqual(registry.set_index("usda_nutrient_id").loc[1213, "status"], "completion_pending")

    def test_duplicate_records_rejected(self):
        with self.assertRaises(ValueError):
            select_catalog(self.nutrients, pd.concat([self.amounts, self.amounts.iloc[[0]]]), self.foods)

    def test_nonfinite_and_negative_values_not_counted_as_coverage(self):
        for invalid in [np.nan, np.inf, -1.]:
            with self.subTest(value=invalid):
                amounts = self.amounts.copy()
                amounts.loc[amounts.fdc_id.eq(1) & amounts.nutrient_id.eq(1259), "amount"] = invalid
                registry, _ = select_catalog(self.nutrients, amounts, self.foods)
                self.assertEqual(registry.set_index("usda_nutrient_id").loc[1259, "status"], "completion_pending")


class DescriptorTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(DESCRIPTORS.read_text())
        self.identities = pd.DataFrame([{"hpp_food_id": f["hpp_food_id"], "product_name": f["expected_product_name"]}
                                        for f in self.config["foods"]])

    def test_unknown_is_explicit_and_not_known_absence(self):
        matrix, prov, dictionary = descriptor_frames(self.identities, self.config)
        self.assertEqual(len(dictionary), 4)
        self.assertEqual(int((~prov.known_value).sum()), 7)
        self.assertTrue(prov.loc[~prov.known_value, "value"].eq("not_stated").all())
        spinach = matrix.set_index("hpp_food_id").loc["1009997"]
        self.assertEqual(spinach.identity_preparation_evidence, "cooked_method_unspecified")
        self.assertEqual(spinach.identity_fermentation_evidence, "not_stated")

    def test_changed_identity_rejected(self):
        self.identities.loc[0, "product_name"] = "Decaf instant coffee"
        with self.assertRaises(ValueError):
            descriptor_frames(self.identities, self.config)

    def test_unregistered_category_rejected(self):
        self.config["foods"][0]["identity_fermentation_evidence"] = "unfermented"
        with self.assertRaises(ValueError):
            descriptor_frames(self.identities, self.config)


class CheckpointIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (OUT / "food_features.csv").exists() or not (BASELINE / "food_features.csv").exists():
            raise unittest.SkipTest("Build both Step 1 checkpoint branches before integration tests.")
        cls.matrix = pd.read_csv(OUT / "food_features.csv", dtype={"hpp_food_id": str}).set_index("hpp_food_id")
        cls.dictionary = pd.read_csv(OUT / "feature_dictionary.csv")
        cls.prov = pd.read_csv(OUT / "cell_provenance.csv", dtype={"hpp_food_id": str})
        cls.summary = json.loads((OUT / "summary.json").read_text())

    def test_approved_values_unchanged(self):
        approved = pd.read_csv(pilot.OUT / "independent_pilot_features.csv", dtype={"hpp_food_id": str}).set_index("hpp_food_id")
        pd.testing.assert_frame_equal(self.matrix[approved.columns], approved)

    def test_nutrient_cell_provenance_matches_raw_source(self):
        _, amounts = read_source()
        source = amounts.set_index("id")
        lookup = self.dictionary.set_index("feature_name")
        for row in self.prov.loc[self.prov.method.isin(["primary_donor_transfer", "protein_scaled_brewed_coffee_proxy"])].itertuples():
            ids = json.loads(row.source_food_nutrient_row_ids)
            record = source.loc[ids[0]]
            self.assertEqual(record.fdc_id, row.donor_fdc_id)
            self.assertEqual(record.nutrient_id, lookup.loc[row.feature_name, "usda_nutrient_id"])
            self.assertAlmostEqual(float(row.value), record.amount * row.scale_factor)
            self.assertAlmostEqual(self.matrix.loc[row.hpp_food_id, row.feature_name], float(row.value))

    def test_candidate_accounting_and_unknowns(self):
        registry = pd.read_csv(OUT / "nutrient_registry.csv")
        evidence = pd.read_csv(OUT / "candidate_evidence_long.csv")
        self.assertEqual(len(registry), 149)
        self.assertEqual(registry.status.value_counts().to_dict(), {"included": 86, "completion_pending": 59, "unit_alias": 2, "source_label_review": 1, "alternate_activity_convention": 1})
        self.assertEqual(len(evidence), 149 * 5)
        self.assertEqual(int(evidence.loc[~evidence.usda_nutrient_id.isin(ALIASES), "value"].isna().sum()), 273)
        self.assertEqual(self.summary["unknown_descriptor_cells"], 7)
        self.assertEqual(len(self.prov), len(self.matrix) * len(self.dictionary))
        self.assertFalse(self.prov.duplicated(["hpp_food_id", "feature_name"]).any())

    def test_comparator_preserves_all_input_values(self):
        source = pd.read_csv(pilot.HPP, dtype={"food_id": str})
        names = [c for c in source.columns if c not in METADATA]
        exported = pd.read_csv(BASELINE / "food_features.csv", dtype={"hpp_food_id": str})
        pd.testing.assert_frame_equal(source[names], exported[names])
        self.assertEqual(source.food_id.tolist(), exported.hpp_food_id.tolist())

    def test_new_output_path_does_not_change_original_builder_values(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder)
            pilot.main(out=path)
            original = pd.read_csv(pilot.OUT / "independent_pilot_features.csv")
            reproduced = pd.read_csv(path / "independent_pilot_features.csv")
            pd.testing.assert_frame_equal(original, reproduced)

    def test_manifest_hashes_and_no_model_claims(self):
        manifest = json.loads((OUT / "run_manifest.json").read_text())
        self.assertFalse(manifest["nutrimatch_values_or_schema_used"])
        self.assertIsNone(manifest["external_api_model"])
        self.assertIsNone(manifest["embedding_model"])
        for name, expected in manifest["output_hashes"].items():
            self.assertEqual(pilot.digest(OUT / name), expected)


if __name__ == "__main__":
    unittest.main()
