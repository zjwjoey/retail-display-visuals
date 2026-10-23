import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/"scripts"/(name+".py"))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj
engine, scene = module("shelf_engine"), module("scene_spec")
ASSETS = ROOT/"assets/shelf-templates"

class ShelfEngineTests(unittest.TestCase):
    def setUp(self):
        self.profile_path=ASSETS/"templates/N01.json"
        self.plan_path=ASSETS/"examples/N01_halloween.json"
        self.profile=engine.read(self.profile_path)
        self.plan=engine.read(self.plan_path)

    def test_all_catalog_profiles_match_source_hash_and_dimensions(self):
        catalog=engine.read(ASSETS/"catalog.json")
        self.assertEqual(len(catalog["templates"]),11)
        total=0
        for item in catalog["templates"]:
            p=ASSETS/item["profile"]
            profile=engine.validate_template(engine.read(p),p)
            total+=len(profile["slots"])
        self.assertEqual(total,38)

    def test_rejects_self_crossing_or_nonfinite_geometry(self):
        for poly in ([[0,0],[1,1],[1,0],[0,1]],
                     [[0,0],[1,0],[1,float("nan")],[0,1]]):
            with self.assertRaises(engine.EngineError):
                engine.polygon(poly,"bad")

    def test_rejects_duplicate_module_level_even_when_id_differs(self):
        self.profile["slots"][1]["module"]=self.profile["slots"][0]["module"]
        self.profile["slots"][1]["level"]=self.profile["slots"][0]["level"]
        with self.assertRaisesRegex(engine.EngineError,"module/level"):
            engine.validate_template(self.profile,check_image=False)

    def test_tall_upright_plate_rejected_but_flat_stack_fits_concept(self):
        b=copy.deepcopy(self.plan["bindings"][0])
        product=self.plan["products"][b["product_id"]]
        self.assertEqual(engine.capacity(self.profile["slots"][0],product,b)["status"],"concept_fit")
        b["orientation"]="upright"
        with self.assertRaisesRegex(engine.EngineError,"height overflow"):
            engine.capacity(self.profile["slots"][0],product,b)

    def test_missing_fixture_dimensions_stays_unknown(self):
        p=engine.read(ASSETS/"templates/E008.json")
        plan=engine.read(ASSETS/"examples/E008_bin.json")
        self.assertEqual(engine.validate_plan(p,plan,check_files=False)["A/L1"]["status"],"unknown")

    def test_rejects_more_facings_than_actual_calibrated_pegs(self):
        p=engine.read(ASSETS/"templates/N02.json")
        plan=engine.read(ASSETS/"examples/N02_mixed.json")
        b=plan["bindings"][0];b["front_count"]=5
        with self.assertRaisesRegex(engine.EngineError,"pegs"):
            engine.capacity(p["slots"][0],plan["products"][b["product_id"]],b)

    def test_support_and_counts_are_checked(self):
        b=copy.deepcopy(self.plan["bindings"][0])
        b["orientation"]="hanging"
        product=self.plan["products"][b["product_id"]]
        with self.assertRaisesRegex(engine.EngineError,"orientation"):
            engine.capacity(self.profile["slots"][0],product,b)
        b.update(orientation="stacked_flat",front_count=True)
        with self.assertRaisesRegex(engine.EngineError,"integer"):
            engine.capacity(self.profile["slots"][0],product,b)

    def test_masks_subtract_protected_structure_and_unselected_bays(self):
        mask=engine.make_mask(self.profile,["A/L1"],(200,150))
        self.assertEqual(mask.getpixel((50,45)),255)
        self.assertEqual(mask.getpixel((150,45)),0)
        self.assertEqual(mask.getpixel((100,45)),0)
        self.assertEqual(mask.getpixel((50,10)),0)

    def test_reference_limit_splits_four_products_and_rejects_six(self):
        batches=engine.batches(self.profile,self.plan)
        self.assertEqual([len(x) for x in batches],[3,1])
        with self.assertRaisesRegex(engine.EngineError,"3..5"):
            engine.batches(self.profile,self.plan,6)

    def test_export_works_with_existing_scene_validator(self):
        data=engine.scene_spec(self.profile,self.plan)
        scene.validate(data)
        self.assertTrue(data["calibrated_scope_only"])
        self.assertEqual(data["fixtures"]["N01"]["module_order"],["A","B"])
        kept=data["fixtures"]["N01"]["modules"]["B"]["levels_top_to_bottom"][0]["items"][0]
        self.assertEqual(kept["product_id"],"KEEP_BASE")
        self.assertEqual(kept["orientation"],"unchanged")

    def test_stage_two_requires_explicit_base_and_outputs_never_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/"job"
            with self.assertRaisesRegex(engine.EngineError,"later stage"):
                engine.compile_job(self.profile_path,self.plan_path,out,stage=2)
            job=engine.compile_job(self.profile_path,self.plan_path,out)
            self.assertEqual(len(job["tool_request"]["referenced_image_paths"]),5)
            self.assertEqual(job["mask_enforcement"],"reference_only")
            scene.validate(engine.read(out/"scene-spec.json"))
            with self.assertRaisesRegex(engine.EngineError,"output exists"):
                engine.compile_job(self.profile_path,self.plan_path,out)
            resumed=engine.compile_job(self.profile_path,self.plan_path,Path(folder)/"next",
                stage=2,base=job["tool_request"]["referenced_image_paths"][0])
            self.assertEqual(resumed["active_slots"],["A/L4"])

    def test_wrong_aspect_is_blocked_before_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)/"square.png";Image.new("RGB",(100,100)).save(base)
            out=Path(folder)/"job"
            with self.assertRaisesRegex(engine.EngineError,"aspect"):
                engine.compile_job(self.profile_path,self.plan_path,out,base=base)
            self.assertFalse(out.exists())

    def test_base_hash_change_requires_recalibration(self):
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/"base.png";Image.new("RGB",(100,100)).save(image)
            p=copy.deepcopy(self.profile);p["image"]["path"]=str(image)
            with self.assertRaisesRegex(engine.EngineError,"hash changed"):
                engine.validate_template(p,Path(folder)/"profile.json")

    def test_locked_slot_difference_detects_small_local_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            job=engine.compile_job(self.profile_path,self.plan_path,folder/"job")
            base=job["tool_request"]["referenced_image_paths"][0]
            with Image.open(base) as im:
                altered=im.convert("RGB")
            draw=ImageDraw.Draw(altered)
            draw.polygon(engine.raster(self.profile["slots"][4]["polygon"],altered.size),fill="white")
            output=folder/"output.png";altered.save(output)
            report=engine.compare(folder/"job/job.json",output,folder/"report.json")
            self.assertEqual(report["drift_signal"],"high")
            self.assertGreater(report["mean_absolute_rgb_difference_0_255"]["locked_slot:B/L1"],12)
            self.assertEqual(report["visual_verdict"],"requires_review")

    def test_identity_pixels_still_do_not_auto_approve_visuals(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            job=engine.compile_job(self.profile_path,self.plan_path,folder/"job")
            report=engine.compare(folder/"job/job.json",
                job["tool_request"]["referenced_image_paths"][0],folder/"report.json")
            self.assertEqual(report["drift_signal"],"low")
            self.assertFalse(report["pixel_identity_verified"])
            self.assertEqual(report["visual_verdict"],"requires_review")

    def test_profile_snapshot_is_frozen_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            job=engine.compile_job(self.profile_path,self.plan_path,folder/"job")
            p=Path(job["profile_snapshot_path"])
            self.assertEqual(engine.digest(p),job["profile_sha256"])
            p.write_text("{}",encoding="utf-8")
            with self.assertRaisesRegex(engine.EngineError,"snapshot changed"):
                engine.compare(folder/"job/job.json",
                    job["tool_request"]["referenced_image_paths"][0],folder/"report.json")

    def test_all_sample_plans_validate_against_profiles(self):
        for name,tid in [("N01_halloween","N01"),("N01_plate_correction","N01"),
                         ("N02_mixed","N02"),("E008_bin","E008")]:
            engine.validate_plan(engine.read(ASSETS/"templates"/(tid+".json")),
                engine.read(ASSETS/"examples"/(name+".json")),
                ASSETS/"examples"/(name+".json"))

    def test_gallery_copies_original_pixels_and_generates_both_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/"gallery"
            engine.gallery(ASSETS/"catalog.json",out)
            self.assertEqual(engine.digest(out/"images/N01.png"),self.profile["image"]["sha256"])
            self.assertTrue((out/"N01.html").is_file())
            self.assertTrue((out/"N01-plan.html").is_file())
            self.assertTrue((out/"index.html").is_file())

if __name__=="__main__":
    unittest.main()
