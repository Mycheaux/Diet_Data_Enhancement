"""Check the de novo input boundary independently of the source-file contents."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from .independent_pilot import read_identity


class IdentityBoundaryTests(unittest.TestCase):
    def test_nutrient_and_old_llm_values_cannot_enter_identity_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "hpp.csv"
            data = pd.DataFrame({"food_id": ["f1"], "product_name": ["Espresso"],
                                 "hebrew_name": ["original"], "short_name": ["original"],
                                 "Caffeine": [212], "gpt_short_food_name": ["old label"]})
            data.to_csv(path, index=False)
            before = read_identity(path)
            data["Caffeine"] = -999999
            data["gpt_short_food_name"] = "unrelated old model label"
            data.to_csv(path, index=False)
            after = read_identity(path)
            pd.testing.assert_frame_equal(before, after)
            self.assertEqual(list(after.columns), ["hpp_food_id", "product_name", "hebrew_name", "short_name"])

    def test_duplicate_food_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "hpp.csv"
            pd.DataFrame({"food_id": ["f1", "f1"], "product_name": ["a", "b"],
                          "hebrew_name": ["a", "b"], "short_name": ["a", "b"]}).to_csv(path, index=False)
            with self.assertRaises(ValueError):
                read_identity(path)


if __name__ == "__main__":
    unittest.main()
