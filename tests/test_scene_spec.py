import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location("scene_spec", ROOT / "scripts/scene_spec.py")
contract = importlib.util.module_from_spec(loader)
loader.loader.exec_module(contract)

class SceneContractTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "references/scene-spec.example.json").read_text(encoding="utf-8"))

    def test_detail_exports_four_levels_without_merging(self):
        contract.validate(self.spec)
        rows = [line for line in contract.render(self.spec, "V03_DETAIL").splitlines()
                if line.startswith("W01/")]
        self.assertEqual([line.split(" support=")[0] for line in rows],
                         ["W01/A/L1", "W01/A/L2", "W01/A/L3", "W01/A/L4"])
        for row, pid in zip(rows, ["PLATE", "PLATE", "GOBLET", "GOBLET"]):
            self.assertIn('"product_id": "' + pid + '"', row)

    def test_same_fixture_rejects_layer_reorder(self):
        self.spec["views"]["V03_DETAIL"]["level_selection"]["A"] = ["L1", "L3", "L2", "L4"]
        with self.assertRaisesRegex(contract.SpecError, "reorder"):
            contract.validate(self.spec)

    def test_same_fixture_rejects_different_fixture(self):
        self.spec["fixtures"]["W02"] = copy.deepcopy(self.spec["fixtures"]["W01"])
        self.spec["views"]["V03_DETAIL"]["fixture_id"] = "W02"
        with self.assertRaisesRegex(contract.SpecError, "changed fixture"):
            contract.validate(self.spec)

    def test_same_scene_allows_separate_fixture_layout(self):
        self.spec["fixtures"]["W02"] = copy.deepcopy(self.spec["fixtures"]["W01"])
        view = self.spec["views"]["V03_DETAIL"]
        view.update(relation="same_scene", fixture_id="W02", level_selection={"A": ["L1", "L2"]})
        contract.validate(self.spec)

    def test_independent_photo_keeps_its_own_scene(self):
        contract.validate(self.spec)
        self.assertEqual(self.spec["views"]["V04_EDIT"]["scene_id"], "STORE_ST008")

    def test_missing_product_is_rejected(self):
        del self.spec["products"]["GOBLET"]
        with self.assertRaisesRegex(contract.SpecError, "unknown product"):
            contract.validate(self.spec)

    def test_nonphysical_dimensions_are_rejected(self):
        self.spec["products"]["GOBLET"]["dimensions_cm"]["height"] = 0
        with self.assertRaisesRegex(contract.SpecError, "positive"):
            contract.validate(self.spec)

    def test_edit_without_preserve_regions_is_rejected(self):
        self.spec["views"]["V04_EDIT"]["preserve_regions"] = []
        with self.assertRaisesRegex(contract.SpecError, "preserve"):
            contract.validate(self.spec)

    def test_cycle_is_rejected(self):
        self.spec["views"]["V01"]["anchor_view"] = "V02"
        with self.assertRaisesRegex(contract.SpecError, "cyclic"):
            contract.validate(self.spec)

    def test_optional_file_check_rejects_missing_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(contract.SpecError, "missing"):
                contract.validate(self.spec, folder, check_files=True)

if __name__ == "__main__":
    unittest.main()
