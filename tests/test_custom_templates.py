import base64
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("engine",ROOT/"scripts/shelf_engine.py")
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
ASSETS=ROOT/"assets/shelf-templates"

class CustomTemplateTests(unittest.TestCase):
    def setUp(self):
        self.profile=engine.read(ASSETS/"templates/N01.json")
        self.profile["template_id"]="CUST_fixture_test"
        self.profile["name"]="My own fixture"
        # Embedded paths are advisory, never destinations for importer writes.
        self.profile["image"]["path"]="../../outside.png"
        self.original=ASSETS/"images/N01_front_two_bay.png"
        self.bundle={"schema_version":"shelf-template-bundle/1.0","profile":self.profile,
                     "image":{"media_type":"image/png","data_base64":base64.b64encode(self.original.read_bytes()).decode()}}

    def import_into(self,folder):
        bundle=folder/"bundle.json";engine.write(bundle,self.bundle)
        return engine.import_template(bundle,folder/"custom-library")

    def test_import_preserves_exact_image_bytes_and_can_compile_real_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);result=self.import_into(folder)
            self.assertEqual(Path(result["image"]).read_bytes(),self.original.read_bytes())
            self.assertTrue(Path(result["image"]).is_relative_to(folder/"custom-library"))
            engine.validate_template(engine.read(result["profile"]),result["profile"])
            plan=engine.read(ASSETS/"examples/N01_halloween.json")
            plan["template_id"]=self.profile["template_id"]
            for p in plan["products"].values():
                p["reference_path"]=str(engine.resolve(ASSETS/"examples/N01_halloween.json",p["reference_path"]))
            engine.write(folder/"plan.json",plan)
            job=engine.compile_job(result["profile"],folder/"plan.json",folder/"job")
            self.assertEqual(job["active_slots"],["A/L1","A/L2","A/L3"])

    def test_duplicate_import_refuses_to_overwrite_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);result=self.import_into(folder);before=Path(result["catalog"]).read_bytes()
            self.bundle["profile"]["name"]="Replacement"
            with self.assertRaisesRegex(engine.EngineError,"ID exists"):
                self.import_into(folder)
            self.assertEqual(Path(result["catalog"]).read_bytes(),before)

    def test_tampered_hash_and_dimensions_are_rejected_without_creating_library(self):
        for field,value in [("sha256","0"*64),("width",42)]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                initial=copy.deepcopy(self.bundle);self.bundle["profile"]["image"][field]=value
                folder=Path(tmp)
                with self.assertRaisesRegex(engine.EngineError,"hash|dimensions"):
                    self.import_into(folder)
                self.assertFalse((folder/"custom-library").exists());self.bundle=initial

    def test_invalid_base64_and_mime_are_rejected(self):
        for field,value in [("data_base64","not valid b64!"),("media_type","image/svg+xml")]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                initial=copy.deepcopy(self.bundle);self.bundle["image"][field]=value
                with self.assertRaises(engine.EngineError):self.import_into(Path(tmp))
                self.bundle=initial

    def test_path_like_custom_ids_are_rejected(self):
        self.bundle["profile"]["template_id"]="CUST_../../escape"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(engine.EngineError,"custom ID"):
                self.import_into(Path(tmp))

    def test_uncalibrated_or_duplicate_protection_not_accepted(self):
        for mutation in ["empty","duplicate"]:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                initial=copy.deepcopy(self.bundle)
                if mutation=="empty":self.bundle["profile"]["slots"]=[]
                else:self.bundle["profile"]["protected_regions"].append(copy.deepcopy(self.bundle["profile"]["protected_regions"][0]))
                with self.assertRaises(engine.EngineError):self.import_into(Path(tmp))
                self.bundle=initial

    def test_custom_catalog_merges_without_modifying_foundation_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);result=self.import_into(folder);base=ASSETS/"catalog.json";before=base.read_bytes()
            engine.gallery(base,folder/"console",result["catalog"])
            self.assertEqual(base.read_bytes(),before)
            self.assertTrue((folder/"console/CUST_fixture_test.html").is_file())
            self.assertTrue((folder/"console/custom.html").is_file())
            self.assertTrue((folder/"console/custom-store.js").is_file())
            self.assertTrue((folder/"console/custom-config.js").is_file())

    def test_same_ids_across_catalogs_stop_gallery_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"console"
            with self.assertRaisesRegex(engine.EngineError,"duplicate template ID"):
                engine.gallery(ASSETS/"catalog.json",out,ASSETS/"catalog.json")
            self.assertFalse(out.exists())

if __name__=="__main__":unittest.main()
