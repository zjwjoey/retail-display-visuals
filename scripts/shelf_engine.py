#!/usr/bin/env python3
"""Shelf template compiler: geometry, semantic masks, jobs and drift signals.
Pillow is used to draw NEW masks and inspect pixels, never to retouch source photos.
No API calls or credentials; tool_request is consumed by the host image tool.
"""
import argparse
import base64
import binascii
import hashlib
import html
import io
import json
import math
import re
import shutil
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageStat

VERSION = "0.2"
SCHEMA = "shelf-template/1.0"

class EngineError(ValueError):
    pass

def need(ok, message):
    if not ok:
        raise EngineError(message)

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def number(x):
    return type(x) in (int, float) and math.isfinite(x)

def polygon(poly, label):
    need(isinstance(poly, list) and len(poly) == 4, label + ": four corners required")
    for point in poly:
        need(isinstance(point, list) and len(point) == 2
             and all(number(x) and 0 <= x <= 1 for x in point),
             label + ": normalized finite coordinates required")
    crosses = []
    for i in range(4):
        a, b, c = poly[i], poly[(i+1) % 4], poly[(i+2) % 4]
        crosses.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
    need(all(v > 1e-8 for v in crosses) or all(v < -1e-8 for v in crosses),
         label + ": polygon must be convex, nonzero and not self-crossing")

def raster(poly, size):
    w, h = size
    return [(round(x*(w-1)), round(y*(h-1))) for x, y in poly]

def resolve(profile_path, value):
    return (Path(profile_path).resolve().parent / value).resolve()


def import_template(bundle_path, library):
    """Register an exported custom template, retaining original image bytes."""
    bundle, library = read(bundle_path), Path(library).resolve()
    need(bundle.get("schema_version") == "shelf-template-bundle/1.0", "unsupported bundle schema")
    profile = bundle["profile"]
    tid = profile.get("template_id", "")
    need(re.fullmatch(r"CUST_[A-Za-z0-9_-]{1,58}", tid) is not None, "custom ID must start CUST_ and use safe characters")
    need(isinstance(profile.get("name"), str) and profile["name"].strip(), "custom template name required")
    try:
        pixels = base64.b64decode(bundle["image"]["data_base64"], validate=True)
    except (binascii.Error, ValueError) as error:
        raise EngineError("invalid image base64") from error
    need(hashlib.sha256(pixels).hexdigest() == profile["image"]["sha256"], "bundle image hash mismatch")
    with Image.open(io.BytesIO(pixels)) as image:
        media = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg"), "WEBP": ("image/webp", ".webp")}.get(image.format)
        need(media is not None and media[0] == bundle["image"]["media_type"], "unsupported or mismatched image format")
        need(image.size == (profile["image"]["width"], profile["image"]["height"]), "bundle image dimensions mismatch")
        image.verify()
    profile["image"]["path"] = "../images/" + tid + media[1]
    profile.setdefault("scope", "用户自定义的可见标定范围")
    profile.setdefault("kind", "custom_fixture")
    validate_template(profile, check_image=False)
    catalog_path = library / "catalog.json"
    catalog = read(catalog_path) if catalog_path.exists() else {"schema_version": "shelf-catalog/1.0", "engine_version": VERSION, "templates": []}
    need(catalog.get("schema_version") == "shelf-catalog/1.0", "unsupported custom catalog")
    need(all(item["id"] != tid for item in catalog["templates"]), "custom ID exists; save a new copy instead of overwriting")
    target, image_path = library/"templates"/(tid+".json"), library/"images"/(tid+media[1])
    need(not target.exists() and not image_path.exists(), "custom files exist; choose a new ID")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(pixels)
    write(target, profile)
    catalog["engine_version"] = VERSION
    catalog["templates"].append({"id": tid, "name": profile["name"], "kind": profile["kind"], "profile": "templates/"+tid+".json",
        "slots": len(profile["slots"]), "calibration": profile["calibration"], "scope": profile["scope"]})
    write(catalog_path, catalog)
    return {"profile": str(target), "catalog": str(catalog_path), "image": str(image_path), "template_id": tid}

def validate_template(profile, profile_path=None, check_image=True):
    need(profile.get("schema_version") == SCHEMA, "unsupported template schema")
    need(bool(profile.get("template_id")), "template_id required")
    need(profile.get("calibration") in ("manual_visible_scope", "reviewed_visible_scope"),
         "template must be calibrated before compilation")
    image = profile["image"]
    need(all(type(image.get(x)) is int and image[x] > 0 for x in ("width", "height")),
         "positive image width/height required")
    need(len(image.get("sha256", "")) == 64, "image sha256 required")
    slots = profile.get("slots")
    need(isinstance(slots, list) and slots, "at least one visible calibrated slot required")
    ids = [s["id"] for s in slots]
    need(len(ids) == len(set(ids)), "duplicate slot ID")
    locations = [(s.get("module"), s.get("level")) for s in slots]
    need(len(locations) == len(set(locations)), "duplicate module/level")
    for slot in slots:
        need(slot.get("support") in ("shelf", "peg", "basket", "platform"), "unknown support")
        need(slot.get("module") and slot.get("level"), "module and level required")
        polygon(slot["polygon"], slot["id"])
        need(isinstance(slot.get("support_line"), list) and len(slot["support_line"]) == 2,
             "support_line endpoints required")
        for point in slot["support_line"] + slot.get("anchors", []):
            need(len(point) == 2 and all(number(v) and 0 <= v <= 1 for v in point),
                 "invalid support point")
        bounds = slot.get("physical_cm")
        if bounds:
            need(bounds.get("basis") in ("user_measured", "manufacturer_spec", "concept_assumption"),
                 "physical bounds need a provenance basis")
            for key in ("width", "height", "depth"):
                need(bounds.get(key) is None or (number(bounds[key]) and bounds[key] > 0),
                     "invalid physical bound")
    region_ids = [r["id"] for r in profile.get("protected_regions", [])]
    need(len(region_ids) == len(set(region_ids)), "duplicate protected region ID")
    for region in profile.get("protected_regions", []):
        polygon(region["polygon"], region["id"])
    if check_image:
        need(profile_path is not None, "profile path required")
        path = resolve(profile_path, image["path"])
        need(path.is_file(), "base image missing: " + str(path))
        need(digest(path) == image["sha256"], "base image hash changed; recalibrate template")
        with Image.open(path) as im:
            need(im.size == (image["width"], image["height"]), "base image size changed")
    return profile

def capacity(slot, product, binding):
    orientation = binding["orientation"]
    allowed = slot.get("allowed_orientations", {
        "shelf": ["upright", "stacked_flat"], "peg": ["hanging"],
        "basket": ["binned"], "platform": ["upright", "stacked_flat"]}[slot["support"]])
    need(orientation in allowed, "orientation not supported: " + slot["id"])
    for field in ("front_count", "depth_count"):
        value = binding.get(field, 1)
        need(type(value) is int and value > 0, "positive integer required: " + field)
    if slot["support"] == "peg" and slot.get("anchors"):
        need(binding.get("front_count", 1) <= len(slot["anchors"]),
             "more front facings than calibrated pegs: " + slot["id"])
    bounds = slot.get("physical_cm")
    envelope = product.get("display_envelopes_cm", {}).get(orientation, {})
    gap = binding.get("gap_cm", 0)
    need(number(gap) and gap >= 0, "gap_cm must be nonnegative")
    for axis in ("width", "height", "depth"):
        value = envelope.get(axis)
        need(value is None or (number(value) and value > 0), "invalid product display envelope")
    if not bounds:
        return {"status": "unknown", "reason": "no measured or conceptual fixture bounds"}
    unknown = []
    used = {}
    for axis, count in (("width", binding.get("front_count", 1)),
                        ("height", 1), ("depth", binding.get("depth_count", 1))):
        size, limit = envelope.get(axis), bounds.get(axis)
        if size is None or limit is None:
            unknown.append(axis)
            continue
        total = size*count + gap*(count-1)
        used[axis] = total
        need(total <= limit + 1e-7,
             f"{slot['id']}: {axis} overflow {total:g}cm > {limit:g}cm")
    return {"status": "concept_fit" if bounds["basis"] == "concept_assumption" else
            ("partial_fit" if unknown else "declared_dimensions_fit"),
            "basis": bounds["basis"], "used_cm": used, "unknown_axes": unknown,
            "physical_authenticity_verified": False}

def validate_plan(profile, plan, plan_path=None, check_files=True):
    need(plan.get("schema_version") == "shelf-plan/1.0", "unsupported plan schema")
    need(plan.get("template_id") == profile["template_id"], "plan targets another template")
    products = plan.get("products", {})
    bindings = plan.get("bindings", [])
    need(isinstance(products, dict) and isinstance(bindings, list) and bindings, "products/bindings required")
    slots = {s["id"]: s for s in profile["slots"]}
    seen, fit = set(), {}
    for binding in bindings:
        sid, pid = binding.get("slot_id"), binding.get("product_id")
        need(sid in slots and sid not in seen, "unknown or duplicate bound slot: " + str(sid))
        need(pid in products, "unknown product: " + str(pid))
        seen.add(sid)
        fit[sid] = capacity(slots[sid], products[pid], binding)
    if check_files:
        for product in products.values():
            need(product.get("name") and product.get("reference_path"), "product name/reference required")
            need(resolve(plan_path, product["reference_path"]).is_file(), "product reference missing")
    return fit

def make_mask(profile, slot_ids, size=None):
    size = size or (profile["image"]["width"], profile["image"]["height"])
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for slot in profile["slots"]:
        if slot["id"] in slot_ids:
            draw.polygon(raster(slot["polygon"], size), fill=255)
    for region in profile.get("protected_regions", []):
        draw.polygon(raster(region["polygon"], size), fill=0)
    return mask

def batches(profile, plan, max_images=5):
    need(type(max_images) is int and 3 <= max_images <= 5,
         "current adapter supports 3..5 images: base + semantic mask + products")
    bound = {b["slot_id"]: b for b in plan["bindings"]}
    result, current, refs = [], [], set()
    for slot in profile["slots"]:
        if slot["id"] not in bound:
            continue
        binding = bound[slot["id"]]
        path = plan["products"][binding["product_id"]]["reference_path"]
        if current and len(refs | {path}) > max_images-2:
            result.append(current)
            current, refs = [], set()
        current.append(binding)
        refs.add(path)
    if current:
        result.append(current)
    return result

def scene_spec(profile, plan):
    bindings = {x["slot_id"]: x for x in plan["bindings"]}
    products = {pid: {"name": p["name"], "reference_path": p["reference_path"],
                     "dimensions_cm": p.get("dimensions_cm", {}),
                     "identity_constraints": p.get("identity_constraints", [])}
                for pid, p in plan["products"].items()}
    products["KEEP_BASE"] = {"name": "保持底图原有状态；可能空置或已有商品，本计划未重新指定", "dimensions_cm": {}}
    order, modules = [], {}
    for slot in profile["slots"]:
        mid = slot["module"]
        if mid not in modules:
            order.append(mid)
            modules[mid] = {"levels_top_to_bottom": []}
        binding = bindings.get(slot["id"])
        modules[mid]["levels_top_to_bottom"].append({
            "id": slot["level"], "support": slot["support"],
            "items": [{"product_id": binding["product_id"] if binding else "KEEP_BASE",
                       "orientation": binding["orientation"] if binding else "unchanged"}]})
    fid = profile["template_id"]
    return {"schema_version": "1.1", "scene_id": plan.get("scene_id", fid),
            "business": plan.get("business", {}), "assets": {},
            "products": products, "fixtures": {fid: {"kind": profile["kind"],
            "placement": profile.get("placement", {}), "module_order": order, "modules": modules}},
            "views": {"TEMPLATE_VIEW": {"mode": "full_wall", "relation": "anchor",
             "scene_id": plan.get("scene_id", fid), "fixture_id": fid, "level_selection": "all"}},
            "calibrated_scope_only": True}

def editor(profile, image_path, out_path, custom_url=None):
    # Browser-native SVG geometry editing; the original image bytes are embedded unchanged.
    picture = base64.b64encode(Path(image_path).read_bytes()).decode()
    with Image.open(image_path) as source:
        media = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(source.format, "image/png")
    payload = json.dumps(profile, ensure_ascii=False).replace("<", "\\u003c")
    page = r"""<!doctype html><meta charset="utf-8"><title>Shelf slot editor</title>
<style>body{font:15px system-ui;margin:20px;background:#141b25;color:#edf3fa}
aside{width:310px;float:right}main{max-width:calc(100vw - 380px)}
svg{max-height:88vh;max-width:100%;background:#111;touch-action:none}
select,button{padding:9px;margin:4px}pre{white-space:pre-wrap}circle{cursor:move}
.note{color:#9fb0c5}</style>
<aside><h2>货架格位标定</h2><select id="pick"></select>
<select id="part"><option value="polygon">可编辑范围</option><option value="support_line">支撑线</option><option value="anchors">挂点</option></select>
<button id="save">下载配置JSON</button><p>选格位，拖动四角。蓝色为可编辑格位，红色为结构保护区。非选定格位在本次任务中保持原样。</p>
<p class="note">坐标是图像标定，不是实测尺寸。白点可拖动，黄线为支撑线，橙点为挂点。三者独立编辑。下载后保存回原配置目录，保持image.path可解析，再运行validate。</p><pre id="info"></pre></aside>
<main><svg id="canvas" xmlns="http://www.w3.org/2000/svg"></svg></main>
<script>
const data=__DATA__, uri="data:image/png;base64,__IMAGE__";
const ns="http://www.w3.org/2000/svg",svg=document.querySelector("#canvas");
const W=data.image.width,H=data.image.height;
svg.setAttribute("viewBox","0 0 "+W+" "+H);
svg.setAttribute("width",W);svg.setAttribute("height",H);
svg.setAttribute("preserveAspectRatio","xMidYMid meet");
svg.style.aspectRatio=data.image.width+"/"+data.image.height;
const pick=document.querySelector("#pick");
const part=document.querySelector("#part");
data.slots.forEach((s,i)=>{let o=document.createElement("option");o.value=i;o.textContent=s.id;pick.append(o)});
function el(tag,attrs){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);svg.append(e);return e}
let drag=null;
function paint(){
svg.replaceChildren();el("image",{href:uri,width:W,height:H,preserveAspectRatio:"none"});
for(const r of data.protected_regions||[])el("polygon",{points:r.polygon.map(p=>[p[0]*W,p[1]*H].join(",")).join(" "),fill:"#fa4865","fill-opacity":.23,stroke:"#ff4262","stroke-width":2});
data.slots.forEach((s,i)=>{const pts=s.polygon.map(p=>[p[0]*W,p[1]*H].join(",")).join(" ");
el("polygon",{points:pts,fill:"#00c7ec","fill-opacity":i==pick.value ? .25 : .06,stroke:i==pick.value?"#fff":"#00c7ec","stroke-width":2});
const t=el("text",{x:s.polygon[0][0]*W+4,y:s.polygon[0][1]*H+19,fill:"white","font-size":17});t.textContent=s.id;
});
const s=data.slots[+pick.value||0];
el("line",{x1:s.support_line[0][0]*W,y1:s.support_line[0][1]*H,x2:s.support_line[1][0]*W,y2:s.support_line[1][1]*H,stroke:"#ffe466","stroke-width":4});
(s.anchors||[]).forEach(p=>el("circle",{cx:p[0]*W,cy:p[1]*H,r:6,fill:"#ff8c35"}));
(s[part.value]||[]).forEach((p,i)=>{const h=el("circle",{cx:p[0]*W,cy:p[1]*H,r:9,fill:"#fff",stroke:"#006f8d","stroke-width":3});h.onpointerdown=e=>{drag=i;svg.setPointerCapture(e.pointerId)}});
document.querySelector("#info").textContent=JSON.stringify(s,null,2);
}
svg.onpointermove=e=>{if(drag===null)return;const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;
const q=p.matrixTransform(svg.getScreenCTM().inverse());data.slots[+pick.value||0][part.value][drag]=[Math.max(0,Math.min(1,q.x/W)),Math.max(0,Math.min(1,q.y/H))];paint()};
svg.onpointerup=()=>{drag=null};svg.onpointercancel=()=>{drag=null};pick.onchange=paint;
part.onchange=paint;
document.querySelector("#save").onclick=()=>{const blob=new Blob([JSON.stringify(data,null,2)+"\n"],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=data.template_id+".json";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
paint();
</script>"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    page = page.replace("data:image/png;base64,", "data:"+media+";base64,")
    if custom_url:
        page = page.replace('<button id="save">', '<button id="clone">另存为自定义模板</button><button id="save">', 1)
        page = page.replace('<script>', '<script src="custom-store.js"></script><script>', 1)
        action = 'document.querySelector("#clone").onclick=async()=>{try{const id=await ShelfCustom.clone(data,uri);location.href='+json.dumps(custom_url)+'+"?id="+encodeURIComponent(id)}catch(e){document.querySelector("#info").textContent=e.message}};'
        position = page.rfind('</script>')
        page = page[:position]+action+'\n'+page[position:]
    Path(out_path).write_text(page.replace("__DATA__", payload).replace("__IMAGE__", picture), encoding="utf-8")

def compile_job(profile_path, plan_path, out, stage=1, base=None, max_images=5):
    profile_path, plan_path, out = Path(profile_path), Path(plan_path), Path(out)
    profile, plan = read(profile_path), read(plan_path)
    validate_template(profile, profile_path)
    fit = validate_plan(profile, plan, plan_path)
    stages = batches(profile, plan, max_images)
    need(1 <= stage <= len(stages), "stage outside generated batch range")
    need(stage == 1 or base, "later stage requires --base from prior reviewed output")
    original = resolve(profile_path, profile["image"]["path"])
    base = Path(base).resolve() if base else original
    need(base.is_file(), "stage base missing")
    with Image.open(base) as im:
        expected = profile["image"]["width"]/profile["image"]["height"]
        need(abs(im.width/im.height/expected-1) < .02, "base camera/aspect changed; review before continuing")
    need(not out.exists(), "output exists; choose a versioned directory")
    selected = stages[stage-1]
    active = [x["slot_id"] for x in selected]
    mask = make_mask(profile, active)
    need(mask.getbbox() is not None, "empty edit mask")
    out.mkdir(parents=True)
    mask.save(out/"edit-mask.png")
    reference_paths, entries = [], []
    slots = {s["id"]: s for s in profile["slots"]}
    for binding in selected:
        product = plan["products"][binding["product_id"]]
        reference = str(resolve(plan_path, product["reference_path"]))
        if reference not in reference_paths:
            reference_paths.append(reference)
        slot = slots[binding["slot_id"]]
        entries.append({"slot_id": slot["id"], "support": slot["support"],
            "polygon_norm": slot["polygon"], "support_line": slot["support_line"],
            "anchors": slot.get("anchors", []), "physical_cm": slot.get("physical_cm"),
            "product_image_number": 3+reference_paths.index(reference), "product": product,
            "binding": binding, "capacity": fit[slot["id"]]})
    locked = [s["id"] for s in profile["slots"] if s["id"] not in active]
    placement_lines = []
    w, h = profile["image"]["width"], profile["image"]["height"]
    for entry in entries:
        corners = raster(entry["polygon_norm"], (w, h))
        line = (f"{entry['slot_id']}: image {entry['product_image_number']}; "
                f"EXACTLY {entry['binding'].get('front_count',1)} front positions; "
                f"orientation={entry['binding']['orientation']}; allowed product polygon in pixels={corners}.")
        placement_lines.append(line)
    prompt = (
        "Use case: precise-object-edit. Edit image 1, the actual empty/partly stocked shelf base. "
        "Keep camera, perspective, posts, exact shelf/hook count, board heights, background, ceiling and floor. "
        "Image 2 is a SEMANTIC REFERENCE MASK: white marks only the permitted product insertion interiors, "
        "black must retain the base. It is a guide image, not a native enforced inpainting mask. "
        "Do not render the mask itself, labels, IDs, colored polygons or measurements. "
        "Images 3 onward are product identity references; ignore catalog page layout, people and arrows. "
        "Only populate active slots listed below. Put bases on the support_line, hanging goods on the listed pegs; "
        "respect orientation, front_count, depth_count and product envelopes. No product may cross a shelf/post. "
        "stacked_flat means horizontal plate faces parallel to the shelf, a short stack seen mostly edge-on, "
        "NEVER propped upright facing the camera. Hanging goods must end inside their assigned polygon; "
        "shrink their display scale to fit instead of consuming the next hook row. "
        "Do not merge, add or shift shelves. Unselected slots, including existing products from a prior stage, "
        "must remain as in image 1. Keep original light, texture, white balance and sharpness. "
        "Use no new logos or price numbers. Output one photo with the SAME framing/aspect as image 1. "
        "If a placement cannot fit, leave space rather than distort the product or move the fixture.\n"
        f"IMAGE CANVAS: {w}x{h}. Placement summary:\n"+'\n'.join(placement_lines)+
        "\nACTIVE SLOT CONTRACT:\n"+json.dumps(entries,ensure_ascii=False,indent=2)+
        "\nLOCKED SLOTS: "+json.dumps(locked,ensure_ascii=False)+
        "\nPROTECTED STRUCTURE: "+json.dumps(profile.get("protected_regions",[]),ensure_ascii=False)+
        "\nThis is stage "+str(stage)+"/"+str(len(stages))+
        ". Physical bounds with concept_assumption are design hypotheses, not verified real measurements."
    )
    request = {"prompt": prompt, "referenced_image_paths": [str(base), str((out/"edit-mask.png").resolve())]
               + reference_paths, "transparent_background": False}
    job = {"engine_version": VERSION, "template_id": profile["template_id"],
        "profile_path": str(profile_path.resolve()), "plan_path": str(plan_path.resolve()),
        "profile_snapshot_path": str((out/"profile-snapshot.json").resolve()),
        "profile_sha256": digest(profile_path), "base_sha256": digest(base),
        "stage": stage, "total_stages": len(stages), "active_slots": active,
        "mask_semantics": "white_edit_black_keep", "mask_enforcement": "reference_only",
        "capacity": {sid:fit[sid] for sid in active}, "tool_request": request}
    (out/"profile-snapshot.json").write_bytes(profile_path.read_bytes())
    write(out/"job.json", job)
    scene = scene_spec(profile, plan)
    for pid, product in scene["products"].items():
        if pid != "KEEP_BASE":
            product["reference_path"] = str(resolve(plan_path, product["reference_path"]))
    scene["products"]["KEEP_BASE"].update(reference_path=str(base),
        reference_role="base_context_not_a_product")
    scene["assets"] = {"template_base": {"path": str(original), "role": "fixed_camera_layout", "approval": "geometry_scope_only"}}
    scene["views"]["TEMPLATE_VIEW"]["asset_id"] = "template_base"
    scene["views"]["TEMPLATE_VIEW"]["mode"] = "wide" if "aisle" in profile["kind"] else "detail"
    scene["generation_progress"] = {"stage": stage, "total_stages": len(stages),
        "active_slots": active, "scene_spec_role": "requested_final_plan_not_verified_output"}
    write(out/"scene-spec.json", scene)
    (out/"prompt.txt").write_text(prompt+"\n",encoding="utf-8")
    editor(profile, base, out/"slot-editor.html")
    return job


def plan_editor(profile, products, out_path):
    payload=json.dumps({"profile":profile,"products":products},ensure_ascii=False).replace("<","\\u003c")
    page=r'''<!doctype html><meta charset="utf-8"><title>上货计划</title>
<style>body{font:16px system-ui;max-width:1120px;margin:32px auto;background:#142030;color:#edf4ff}table{width:100%;border-collapse:collapse}td,th{padding:12px;text-align:left;border-bottom:1px solid #456}select,input,button{padding:9px;font:inherit}input{width:60px}p{line-height:1.8}button{margin-top:20px;background:#74d9ff;border:0;border-radius:7px}</style>
<h1 id="title"></h1><p>选择格位、商品、姿态和正面数量。空置格位将保持底图原样。这里只导出计划；尺寸检查与生图任务由Python编译器执行。</p>
<table><thead><tr><th>格位</th><th>商品</th><th>姿态</th><th>正面数量</th><th>纵深数量</th></tr></thead><tbody id="rows"></tbody></table>
<button id="save">下载上货计划JSON</button><p id="status"></p><p>导出文件使用当前机器的商品路径。换机器后重新生成模板库即可。依赖资料中的尺寸与身份来自商品参考，未知尺寸保持未知。</p>
<script>const data=__DATA__,profile=data.profile,products=data.products;
document.querySelector('#title').textContent=profile.template_id+' · '+profile.name+' 上货计划';
function option(select,value,label){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o)}
const rows=profile.slots.map(s=>{const tr=document.createElement('tr');document.querySelector('#rows').append(tr);
const label=document.createElement('td');label.textContent=s.id;tr.append(label);
const p=document.createElement('select');option(p,'','保持原样');for(const[id,v]of Object.entries(products))option(p,id,v.name);
const orientation=document.createElement('select');
const supported=s.allowed_orientations||({shelf:['upright','stacked_flat'],peg:['hanging'],basket:['binned'],platform:['upright','stacked_flat']}[s.support]);
function refresh(){orientation.replaceChildren();for(const v of supported){if(!p.value||products[p.value].display_envelopes_cm[v])option(orientation,v,({upright:'直立',stacked_flat:'平放叠放',hanging:'悬挂',binned:'筐装'})[v])}}
p.onchange=refresh;refresh();
const count=document.createElement('input'),depth=document.createElement('input');for(const i of [count,depth]){i.type='number';i.min='1';i.step='1';i.value='1'}
for(const el of [p,orientation,count,depth]){const cell=document.createElement('td');cell.append(el);tr.append(cell)}
return {s,p,orientation,count,depth}});
document.querySelector('#save').onclick=()=>{try{const bindings=[];const used={};for(const r of rows){if(!r.p.value)continue;const front=Number(r.count.value),depth=Number(r.depth.value);if(!r.orientation.value||!Number.isInteger(front)||front<1||!Number.isInteger(depth)||depth<1)throw Error(r.s.id+'：请检查姿态和数量');bindings.push({slot_id:r.s.id,product_id:r.p.value,orientation:r.orientation.value,front_count:front,depth_count:depth,gap_cm:0});used[r.p.value]=products[r.p.value]}
if(!bindings.length)throw Error('至少选择一个格位');const plan={schema_version:'shelf-plan/1.0',template_id:profile.template_id,scene_id:profile.template_id+'_CUSTOM',products:used,bindings};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(plan,null,2)+'\n'],{type:'application/json'}));a.download=profile.template_id+'-plan.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);document.querySelector('#status').textContent='计划已导出，尚未校验尺寸或生成图片。'}catch(e){document.querySelector('#status').textContent=e.message}};
</script>'''
    Path(out_path).write_text(page.replace('__DATA__',payload),encoding='utf-8')


def gallery(catalog_path, out, custom_catalog=None):
    """Portable local catalog, source copies and self-contained slot editors."""
    out = Path(out)
    need(not out.exists(), "gallery output exists; choose a versioned directory")
    catalog=read(catalog_path)
    products={}
    if catalog.get('product_library'):
        library_path=resolve(catalog_path,catalog['product_library'])
        products=read(library_path)['products']
        for value in products.values():
            value['reference_path']=str(resolve(library_path,value['reference_path']))
    entries, seen = [], set()
    catalogs = [(catalog_path, catalog, "basic")]
    if custom_catalog:
        catalogs.append((custom_catalog, read(custom_catalog), "custom"))
    for origin, source_catalog, group in catalogs:
        for item in source_catalog["templates"]:
            profile_path = resolve(origin, item["profile"])
            profile = validate_template(read(profile_path), profile_path)
            tid=profile["template_id"]
            need(tid not in seen, "duplicate template ID across catalogs: "+tid)
            need(re.fullmatch(r"[A-Za-z0-9_-]{1,64}",tid) is not None, "unsafe template ID")
            seen.add(tid)
            entries.append((profile, resolve(profile_path, profile["image"]["path"]), group))
    (out / "images").mkdir(parents=True)
    ui = Path(__file__).resolve().parents[1]/"assets/template-console"
    for resource in ui.iterdir():
        if resource.is_file():
            shutil.copyfile(resource, out/resource.name)
    (out/"custom-config.js").write_text("window.SHELF_PRODUCTS="+json.dumps(products,ensure_ascii=False).replace("<","\\u003c")+";\n",encoding="utf-8")
    cards = {"basic":[], "custom":[]}
    for profile, source, group in entries:
        tid = profile["template_id"]
        need(tid.isascii() and all(c.isalnum() or c in "_-" for c in tid), "unsafe template ID")
        shutil.copyfile(source, out / "images" / (tid + source.suffix))
        editor(profile, source, out / (tid + ".html"), custom_url="custom.html")
        plan_link=''
        if products:
            plan_editor(profile,products,out/(tid+'-plan.html'))
            plan_link=' · <a href="'+tid+'-plan.html">选择商品上货</a>'
        registered = ' data-registered-id="'+tid+'"' if group == "custom" else ''
        cards[group].append('<article'+registered+'><a href="'+tid+'.html"><img loading="lazy" src="images/'+tid+source.suffix+'"></a><h2>'+html.escape(tid+' · '+profile['name'])+'</h2><p>'+html.escape(profile['scope'])+'</p><p>'+str(len(profile['slots']))+'个标定格位 · <a href="'+tid+'.html">打开标定器 / 另存自定义</a>'+plan_link+'</p></article>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>货架模板库 · 基础与自定义</title><style>
body{background:#101b2b;color:#eef4ff;font:16px system-ui;margin:32px}a{color:#72dbff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}article{background:#1d2c40;border-radius:14px;padding:16px}img{width:100%;height:290px;object-fit:contain;background:#0b1420}p{line-height:1.7}article h2{font-size:19px}.hero{padding:26px;background:#203750;border-radius:16px;margin-bottom:26px}.actions{display:flex;flex-wrap:wrap;gap:14px;align-items:center}.button{padding:12px 20px;border-radius:8px;background:#8fe4ff;color:#102133;text-decoration:none;font-weight:700}label{padding:10px;background:#2d4865;border-radius:8px}h2.section{margin-top:38px}.muted{color:#adc0d4}
</style><h1>货架模板引擎</h1><section class="hero"><h2>选基础模板，也能建立自己的模板库</h2><p>导入空货架图，自定义格位、支撑线、挂点和保护区；或从现有模板另存副本。保存后可重复选择商品上货。</p><div class="actions"><a class="button" id="new-template" href="custom.html">＋ 新建自定义模板</a><a href="#basics">浏览基础模板</a><a href="#mine">我的自定义模板</a><label>恢复模板包 <input id="restoreBundle" type="file" accept=".json"></label></div></section>
<h2 class="section" id="mine">我的自定义模板</h2><p class="muted">本机已注册模板与当前浏览器保存的模板均可选择。浏览器模板可导出包含原图的模板包，交给Codex注册到生成引擎。</p><p id="custom-status" role="status"></p><section class="grid">'''+''.join(cards["custom"])+'''</section><section class="grid" id="custom-list"></section>
<h2 class="section" id="basics">基础模板 · '''+str(len(cards["basic"]))+'''组</h2><p>这些是起始选择，可以直接上货，也可以打开标定器“另存为自定义模板”。标注仅覆盖已标定范围，不代表实测尺寸。</p><section class="grid">'''+''.join(cards["basic"])+'''</section><script src="custom-store.js"></script><script src="gallery-custom.js"></script></html>'''
    (out/'index.html').write_text(page,encoding='utf-8')
    return out/'index.html'

def compare(job_path, output_path, out_path):
    job = read(job_path)
    profile_path = job.get("profile_snapshot_path", job["profile_path"])
    profile = read(profile_path)
    need(digest(profile_path) == job["profile_sha256"], "profile snapshot changed since compilation")
    base = job["tool_request"]["referenced_image_paths"][0]
    need(digest(base) == job["base_sha256"], "stage base changed since compilation")
    with Image.open(base) as im:
        a = im.convert("RGB")
    with Image.open(output_path) as im:
        actual_size = list(im.size)
        b = im.convert("RGB").resize(a.size, Image.Resampling.BILINEAR)
    ratio_delta = abs((actual_size[0]/actual_size[1])/(a.width/a.height)-1)
    allowed = make_mask(profile, job["active_slots"], a.size)
    protected = ImageChops.invert(allowed)
    diff = ImageChops.difference(a,b)
    metrics = {"outside_edit_region": sum(ImageStat.Stat(diff,protected).mean)/3}
    for region in profile.get("protected_regions",[]):
        mask=Image.new("L",a.size,0)
        ImageDraw.Draw(mask).polygon(raster(region["polygon"],a.size),fill=255)
        metrics[region["id"]]=sum(ImageStat.Stat(diff,mask).mean)/3
    for slot in profile["slots"]:
        if slot["id"] not in job["active_slots"]:
            mask=Image.new("L",a.size,0)
            ImageDraw.Draw(mask).polygon(raster(slot["polygon"],a.size),fill=255)
            metrics["locked_slot:"+slot["id"]]=sum(ImageStat.Stat(diff,mask).mean)/3
    report={"template_id":job["template_id"],"stage":job["stage"],"output_path":str(Path(output_path).resolve()),
        "output_sha256":digest(output_path),"output_size":actual_size,"aspect_relative_delta":ratio_delta,
        "mean_absolute_rgb_difference_0_255":metrics,
        "drift_signal":"high" if ratio_delta>.02 or max(metrics.values())>12 else "low",
        "threshold_status":"heuristic_not_calibrated","alignment":"resize_only_no_geometric_registration",
        "visual_verdict":"requires_review","pixel_identity_verified":False,
        "note":"Low difference does not prove geometry, SKU identity or correct placement. No photo pixels restored."}
    write(out_path,report)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("list");p.add_argument("catalog",type=Path)
    p=sub.add_parser("gallery");p.add_argument("catalog",type=Path);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--custom-catalog",type=Path)
    p=sub.add_parser("import-template");p.add_argument("bundle",type=Path);p.add_argument("--library",type=Path,required=True)
    p=sub.add_parser("validate");p.add_argument("profile",type=Path);p.add_argument("--plan",type=Path)
    p=sub.add_parser("editor");p.add_argument("profile",type=Path);p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("compile");p.add_argument("profile",type=Path);p.add_argument("plan",type=Path)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--stage",type=int,default=1)
    p.add_argument("--base",type=Path);p.add_argument("--max-images",type=int,default=5)
    p=sub.add_parser("compare");p.add_argument("job",type=Path);p.add_argument("image",type=Path)
    p.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=="list":
            print(json.dumps(read(args.catalog),ensure_ascii=False,indent=2))
        elif args.command=="gallery":
            print(gallery(args.catalog,args.out,args.custom_catalog))
        elif args.command=="import-template":
            print(json.dumps(import_template(args.bundle,args.library),ensure_ascii=False,indent=2))
        elif args.command=="validate":
            profile=validate_template(read(args.profile),args.profile)
            fit=validate_plan(profile,read(args.plan),args.plan) if args.plan else {}
            print(json.dumps({"valid":True,"template_id":profile["template_id"],"capacity":fit},ensure_ascii=False,indent=2))
        elif args.command=="editor":
            profile=validate_template(read(args.profile),args.profile)
            editor(profile,resolve(args.profile,profile["image"]["path"]),args.out)
            print(args.out)
        elif args.command=="compile":
            job=compile_job(args.profile,args.plan,args.out,args.stage,args.base,args.max_images)
            print(json.dumps({"job":str(args.out/"job.json"),"stage":job["stage"],
                              "total_stages":job["total_stages"],"active_slots":job["active_slots"]},ensure_ascii=False))
        else:
            result=compare(args.job,args.image,args.out)
            print(json.dumps(result,ensure_ascii=False,indent=2))
    except (EngineError,KeyError,TypeError,OSError,ValueError) as error:
        parser.exit(1,f"Shelf engine: {error}\n")

if __name__=="__main__":
    main()
