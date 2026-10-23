#!/usr/bin/env python3
"""Validate scene contracts and render fixed merchandising; does not inspect images."""
import argparse
import json
from pathlib import Path

class SpecError(ValueError):
    pass

def need(condition, message):
    if not condition:
        raise SpecError(message)

def selection(spec, view):
    fixture = spec["fixtures"].get(view.get("fixture_id"))
    if fixture is None:
        return []
    chosen = view.get("level_selection", "all")
    if chosen == "all":
        return [(m, level) for m in fixture["module_order"]
                for level in fixture["modules"][m]["levels_top_to_bottom"]]
    need(isinstance(chosen, dict) and chosen, "level_selection must be all or a nonempty module map")
    need(set(chosen) <= set(fixture["module_order"]), "unknown selected module")
    result = []
    for module in fixture["module_order"]:
        if module not in chosen:
            continue
        levels = fixture["modules"][module]["levels_top_to_bottom"]
        ids = [level["id"] for level in levels]
        pick = chosen[module]
        need(isinstance(pick, list) and pick and len(pick) == len(set(pick)),
             "selected levels must be a nonempty unique list")
        need(set(pick) <= set(ids), "unknown selected level")
        need(pick == [i for i in ids if i in pick], "selected levels reorder the fixture")
        result.extend((module, level) for level in levels if level["id"] in pick)
    return result

def validate(spec, base=None, check_files=False):
    need(spec.get("schema_version") == "1.1", "schema_version must be 1.1")
    need(bool(spec.get("scene_id")), "scene_id required")
    for key in ("business", "assets", "products", "fixtures", "views"):
        need(isinstance(spec.get(key), dict), key + " must be an object")
    products, fixtures, views = (spec[k] for k in ("products", "fixtures", "views"))
    need(bool(views), "at least one view required")
    for pid, product in products.items():
        need(isinstance(product, dict) and bool(product.get("name")), "product name required: " + pid)
        dims = product.get("dimensions_cm", {})
        need(isinstance(dims, dict), "dimensions_cm must be an object: " + pid)
        for axis, value in dims.items():
            need(value is None or (type(value) in (int, float) and value > 0),
                 "dimension must be positive or null: " + pid + "/" + axis)
    for fid, fixture in fixtures.items():
        modules, order = fixture["modules"], fixture["module_order"]
        need(isinstance(order, list) and order and len(order) == len(set(order))
             and set(order) == set(modules), "module_order must name every module once: " + fid)
        for mid in order:
            levels = modules[mid]["levels_top_to_bottom"]
            need(isinstance(levels, list) and levels, "levels required: " + fid + "/" + mid)
            level_ids = [x["id"] for x in levels]
            need(all(isinstance(x, str) and x for x in level_ids)
                 and len(level_ids) == len(set(level_ids)), "duplicate/empty level ID: " + fid + "/" + mid)
            for level in levels:
                need(level.get("support") in ("shelf", "peg", "basket", "platform"),
                     "unknown support: " + fid + "/" + mid + "/" + level["id"])
                need(isinstance(level.get("items"), list) and level["items"], "items required")
                for item in level["items"]:
                    need(item.get("product_id") in products, "unknown product in " + fid + "/" + mid)
                    need(bool(item.get("orientation")), "item orientation required")
    for vid, view in views.items():
        relation = view.get("relation")
        need(relation in ("anchor", "same_fixture", "same_scene", "independent"), "unknown relation: " + vid)
        need(view.get("mode") in ("full_wall", "wide", "detail", "local_edit"), "unknown mode: " + vid)
        need(bool(view.get("scene_id")), "view scene_id required: " + vid)
        fid = view.get("fixture_id")
        need(fid is None or fid in fixtures, "unknown fixture: " + vid)
        if "asset_id" in view:
            need(view["asset_id"] in spec["assets"], "unknown asset_id: " + vid)
        if fid is None:
            need(relation == "independent", "linked view requires fixture_id: " + vid)
        if relation in ("anchor", "same_fixture", "same_scene"):
            need(view["scene_id"] == spec["scene_id"], "linked view has different scene_id: " + vid)
        if relation in ("same_fixture", "same_scene"):
            aid = view.get("anchor_view")
            need(aid in views and aid != vid, "missing/invalid anchor_view: " + vid)
            anchor = views[aid]
            need(anchor.get("scene_id") == view["scene_id"], "anchor scene mismatch: " + vid)
            if relation == "same_fixture":
                need(anchor.get("fixture_id") == fid, "same_fixture changed fixture: " + vid)
            seen = {vid}
            while aid:
                need(aid not in seen, "cyclic anchor_view: " + vid)
                seen.add(aid)
                aid = views[aid].get("anchor_view")
                need(aid is None or aid in views, "unknown anchor chain: " + vid)
        if view["mode"] == "local_edit":
            need(view.get("base_asset") in spec["assets"], "edit base_asset required: " + vid)
            need(bool(view.get("edit_region")) and bool(view.get("preserve_regions")),
                 "edit and preserve regions required: " + vid)
        selection(spec, view)
    if check_files:
        base = Path(base or ".")
        paths = [p.get("reference_path") for p in products.values()]
        paths += [a.get("path") for a in spec["assets"].values()]
        for value in paths:
            need(isinstance(value, str) and value, "reference path required for file check")
            need((base / value).is_file(), "reference file missing: " + value)
    return spec

def render(spec, view_id):
    need(view_id in spec["views"], "unknown view: " + view_id)
    view = spec["views"][view_id]
    rows = [f"scene={view['scene_id']} view={view_id} relation={view['relation']}",
            "business=" + json.dumps(spec["business"], ensure_ascii=False)]
    anchor = spec["views"][view.get("anchor_view", view_id)]
    asset = spec["assets"].get(anchor.get("asset_id"))
    if asset:
        rows.append("anchor_approval=" + json.dumps(asset, ensure_ascii=False))
    if view.get("fixture_id"):
        fixture = spec["fixtures"][view["fixture_id"]]
        rows.append("placement=" + json.dumps(fixture.get("placement", {}), ensure_ascii=False))
    for module, level in selection(spec, view):
        contents = []
        for item in level["items"]:
            product = spec["products"][item["product_id"]]
            contents.append(json.dumps({"product_id": item["product_id"], "name": product["name"],
                "orientation": item["orientation"], "variant_order": item.get("variant_order"),
                "dimensions_cm": product.get("dimensions_cm", {}),
                "identity": product.get("identity_constraints", []),
                "packaging_status": product.get("packaging_status", "unknown")}, ensure_ascii=False))
        rows.append(f"{view['fixture_id']}/{module}/{level['id']} support={level['support']}: " + "; ".join(contents))
    for key in ("anchor_view", "allowed_changes", "locked", "edit_region", "preserve_regions"):
        if key in view:
            rows.append(key + "=" + json.dumps(view[key], ensure_ascii=False))
    rows.append("Configuration only; actual generated image still requires visual inspection.")
    return "\n".join(rows)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "render"):
        child = sub.add_parser(command)
        child.add_argument("spec", type=Path)
        child.add_argument("--check-files", action="store_true")
        if command == "render":
            child.add_argument("--view", required=True)
    args = parser.parse_args()
    try:
        spec = validate(json.loads(args.spec.read_text(encoding="utf-8")),
                        args.spec.parent, args.check_files)
        print(render(spec, args.view) if args.command == "render"
              else "Scene contract valid; image consistency NOT assessed.")
        return 0
    except (SpecError, KeyError, TypeError, AttributeError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f"Invalid scene spec: {error}\n")

if __name__ == "__main__":
    raise SystemExit(main())
