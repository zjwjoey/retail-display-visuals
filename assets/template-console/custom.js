/* Custom shelf authoring; annotations are SVG, never painted into the source image. */
const customAPI=window.ShelfCustom,byID=id=>document.getElementById(id),svg=byID("canvas");
let bundle=null,drag=null,selected={kind:"slots",index:0};
const planDraft=new Map(),ns="http://www.w3.org/2000/svg";
function message(value){byID("status").textContent=value}
function item(){return bundle?.profile[selected.kind]?.[selected.index]}
function pointList(){return item()?.[byID("part").value]||[]}
function option(select,value,label){const o=document.createElement("option");o.value=value;o.textContent=label;select.append(o)}
function svgElement(tag,attrs){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);svg.append(e);return e}
function names(){if(!bundle)return;bundle.profile.name=byID("name").value.trim();bundle.profile.kind=byID("kind").value;document.title=bundle.profile.name+" · 自定义模板"}
function updateFields(){const s=item(),isSlot=selected.kind==="slots";byID("slotFields").hidden=!s||!isSlot;
 if(!s)return;byID("part").value="polygon";
 if(isSlot){for(const key of ["module","level","support"])byID(key).value=s[key];
  for(const key of ["width","height","depth"])byID(key).value=s.physical_cm?.[key]??"";
  byID("basis").value=s.physical_cm?.basis||"";}
}
function menu(){const pick=byID("pick");pick.replaceChildren();if(!bundle)return;
 for(const key of ["slots","protected_regions"])bundle.profile[key].forEach((s,i)=>option(pick,key+":"+i,(key==="slots"?"格位 ":"保护 ")+s.id));
 const valid=bundle.profile[selected.kind]?.[selected.index];if(!valid)selected=bundle.profile.slots.length?{kind:"slots",index:0}:{kind:"protected_regions",index:0};
 pick.value=selected.kind+":"+selected.index;updateFields();
}
function paint(){svg.replaceChildren();if(!bundle)return;
 const p=bundle.profile,W=p.image.width,H=p.image.height;svg.hidden=false;byID("empty").hidden=true;
 svg.setAttribute("viewBox","0 0 "+W+" "+H);svg.setAttribute("preserveAspectRatio","xMidYMid meet");svg.style.aspectRatio=W+"/"+H;
 const scale=svg.getScreenCTM()?.a||1;
 svgElement("image",{href:customAPI.imageURL(bundle),width:W,height:H});
 for(const key of ["slots","protected_regions"])p[key].forEach((s,i)=>{
  const active=selected.kind===key&&selected.index===i,color=key==="slots"?"#10d8ed":"#ff556e";
  const shape=svgElement("polygon",{points:s.polygon.map(q=>[q[0]*W,q[1]*H].join(",")).join(" "),fill:color,"fill-opacity":active ? .25 : .1,stroke:active?"white":color,"stroke-width":Math.max(W/650,1)});
  shape.onpointerdown=()=>{selected={kind:key,index:i};menu();paint()};
  if(key==="slots"||active){const label=svgElement("text",{x:s.polygon[0][0]*W+6,y:s.polygon[0][1]*H+22,fill:"white","font-size":Math.max(12/scale,W/65)});label.textContent=s.id;}
 });
 const s=item();if(!s)return;
 if(s.support_line)svgElement("line",{x1:s.support_line[0][0]*W,y1:s.support_line[0][1]*H,x2:s.support_line[1][0]*W,y2:s.support_line[1][1]*H,stroke:"#ffdf69","stroke-width":Math.max(W/400,2)});
 for(const q of s.anchors||[])svgElement("circle",{cx:q[0]*W,cy:q[1]*H,r:Math.max(W/170,5),fill:"#ff982b"});
 pointList().forEach((q,i)=>{const dot=svgElement("circle",{cx:q[0]*W,cy:q[1]*H,r:Math.max(W/95,7/scale),fill:"white",stroke:"#056d91","stroke-width":2/scale});
  dot.onpointerdown=e=>{e.stopPropagation();drag=i;svg.setPointerCapture(e.pointerId)}});
}
svg.onpointermove=e=>{if(drag===null||!bundle)return;const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const q=pt.matrixTransform(svg.getScreenCTM().inverse()),p=bundle.profile;
 pointList()[drag]=[Math.max(0,Math.min(1,q.x/p.image.width)),Math.max(0,Math.min(1,q.y/p.image.height))];paint()};
svg.onpointerup=()=>drag=null;svg.onpointercancel=()=>drag=null;
byID("pick").onchange=()=>{const[k,n]=byID("pick").value.split(":");selected={kind:k,index:+n};updateFields();paint()};
byID("part").onchange=paint;
function stock(){const host=byID("stockRows");host.replaceChildren();if(!bundle)return;
 const products=window.SHELF_PRODUCTS||{},table=document.createElement("table"),head=document.createElement("tr");
 for(const text of ["格位","商品","姿态","正面数量","纵深数量"]){const th=document.createElement("th");th.textContent=text;head.append(th)}table.append(head);
 for(const s of bundle.profile.slots){
  const row=document.createElement("tr"),label=document.createElement("td");label.textContent=s.id;row.append(label);
  const product=document.createElement("select"),orientation=document.createElement("select"),front=document.createElement("input"),depth=document.createElement("input");
  option(product,"","保持底图");for(const[pid,p]of Object.entries(products))option(product,pid,p.name);
  const draft=planDraft.get(s.id)||{product_id:"",front_count:1,depth_count:1};product.value=draft.product_id;
  function orientations(){orientation.replaceChildren();const allowed={shelf:["upright","stacked_flat"],peg:["hanging"],basket:["binned"],platform:["upright","stacked_flat"]}[s.support];
   for(const v of allowed)if(!product.value||products[product.value]?.display_envelopes_cm?.[v])option(orientation,v,{upright:"直立",stacked_flat:"平放叠放",hanging:"悬挂",binned:"筐装"}[v]);
   if([...orientation.options].some(x=>x.value===draft.orientation))orientation.value=draft.orientation;}
  orientations();for(const input of [front,depth]){input.type="number";input.min="1";input.step="1"}front.value=draft.front_count;depth.value=draft.depth_count;
  function capture(){planDraft.set(s.id,{product_id:product.value,orientation:orientation.value,front_count:Number(front.value),depth_count:Number(depth.value)})}
  product.onchange=()=>{orientations();capture()};orientation.onchange=capture;front.onchange=capture;depth.onchange=capture;
  for(const el of [product,orientation,front,depth]){const td=document.createElement("td");td.append(el);row.append(td)}table.append(row);capture();
 }host.append(table);
}
function show(value){bundle=value;selected={kind:"slots",index:0};planDraft.clear();byID("name").value=value.profile.name;
 if(![...byID("kind").options].some(o=>o.value===value.profile.kind))option(byID("kind"),value.profile.kind,value.profile.kind);
 byID("kind").value=value.profile.kind;menu();paint();stock();document.title=value.profile.name+" · 自定义模板";}
function requireImage(){if(!bundle)throw Error("请先导入空架图片")}
function readFileURL(file){return new Promise((yes,no)=>{const reader=new FileReader();reader.onload=()=>yes(reader.result);reader.onerror=()=>no(reader.error);reader.readAsDataURL(file)})}
function guarded(fn){return async(...args)=>{try{await fn(...args)}catch(e){message(e.message)}}}
byID("imageFile").onchange=guarded(async e=>{const file=e.target.files[0];if(!file)return;
 if(!["image/png","image/jpeg","image/webp"].includes(file.type))throw Error("只支持PNG、JPEG、WebP图片");
 const uri=await readFileURL(file),img=new Image();await new Promise((yes,no)=>{img.onload=yes;img.onerror=()=>no(Error("图片无法打开"));img.src=uri});
 const id=customAPI.newID(),profile={schema_version:"shelf-template/1.0",template_id:id,name:file.name.replace(/\.[^.]+$/,""),kind:"custom_fixture",calibration:"manual_visible_scope",scope:"用户手动标定的可见范围",
 image:{path:"../images/"+id+"."+({ "image/png":"png","image/jpeg":"jpg","image/webp":"webp"}[file.type]),width:img.naturalWidth,height:img.naturalHeight,sha256:await customAPI.hash(await file.arrayBuffer())},
 provenance:{kind:"user_custom_template",source_filename:file.name,verified_real_measurements:false},placement:{camera:"fixed_to_template_image",same_scene_with_other_templates:"not_established"},slots:[],protected_regions:[]};
 show({schema_version:"shelf-template-bundle/1.0",profile,image:{media_type:file.type,data_base64:uri.slice(uri.indexOf(",")+1)}});
 message("原图已载入。请添加格位，拖动范围与支撑线，再保存。实际尺寸未知时留空。");e.target.value="";});
byID("bundleFile").onchange=guarded(async e=>{const file=e.target.files[0];if(!file)return;const b=await customAPI.validateBundle(JSON.parse(await file.text()));show(b);message("模板包已载入，修改后点击保存。");e.target.value=""});
byID("name").onchange=names;byID("kind").onchange=names;
byID("addSlot").onclick=guarded(()=>{requireImage();const p=bundle.profile;let n=1;while(p.slots.some(s=>s.id==="A/L"+n))n++;
 const y=.2+((n-1)%5)*.12,poly=[[.2,y],[.8,y],[.8,y+.1],[.2,y+.1]];
 p.slots.push({id:"A/L"+n,module:"A",level:"L"+n,support:"shelf",polygon:poly,support_line:[structuredClone(poly[3]),structuredClone(poly[2])]});
 selected={kind:"slots",index:p.slots.length-1};menu();paint();stock();});
byID("addProtect").onclick=guarded(()=>{requireImage();const regions=bundle.profile.protected_regions;let n=1;while(regions.some(r=>r.id==="P"+n))n++;
 regions.push({id:"P"+n,polygon:[[.45,.15],[.5,.15],[.5,.85],[.45,.85]]});selected={kind:"protected_regions",index:regions.length-1};menu();paint();});
byID("remove").onclick=guarded(()=>{requireImage();const s=item();if(!s)return;bundle.profile[selected.kind].splice(selected.index,1);planDraft.delete(s.id);selected.index=0;menu();paint();stock();});
for(const[button,delta]of [["moveUp",-1],["moveDown",1]])byID(button).onclick=()=>{if(!bundle)return;const arr=bundle.profile[selected.kind],i=selected.index,j=i+delta;if(j<0||j>=arr.length)return;[arr[i],arr[j]]=[arr[j],arr[i]];selected.index=j;menu();paint();stock()};
for(const key of ["module","level","support","width","height","depth","basis"])byID(key).onchange=guarded(()=>{
 const s=item();if(!s||selected.kind!=="slots")return;const old=s.id;s.module=byID("module").value.trim();s.level=byID("level").value.trim();s.id=s.module+"/"+s.level;s.support=byID("support").value;
 if(planDraft.has(old)&&s.id!==old){planDraft.set(s.id,planDraft.get(old));planDraft.delete(old)}
 const bounds={};for(const dim of ["width","height","depth"])bounds[dim]=byID(dim).value===""?null:Number(byID(dim).value);
 if(Object.values(bounds).some(v=>v!==null)||byID("basis").value)s.physical_cm={...bounds,basis:byID("basis").value};else delete s.physical_cm;
 menu();paint();stock();
});
byID("resetPegs").onclick=guarded(()=>{const s=item();if(!s||s.support!=="peg")throw Error("请先选择挂钩格位");
 const count=Number(byID("pegCount").value);if(!Number.isInteger(count)||count<1||count>40)throw Error("示意挂点数量需为1到40");
 const [a,b]=s.support_line;s.anchors=Array.from({length:count},(_,i)=>{const t=(i+.5)/count;return[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]});byID("part").value="anchors";paint();});
async function checked(){requireImage();names();bundle.profile.calibration="manual_visible_scope";await customAPI.validateBundle(bundle);return bundle}
byID("save").onclick=guarded(async()=>{const b=await checked();await customAPI.put(b);history.replaceState(null,"","custom.html?id="+encodeURIComponent(b.profile.template_id));message("已保存到我的自定义模板："+b.profile.name+"。返回模板库即可再次选择。")});
byID("export").onclick=guarded(async()=>{const b=await checked();customAPI.download(b,b.profile.template_id+".shelf.json");message("模板包已导出，包含未加工原图、格位、支撑线和保护区。可交给Codex注册到引擎。")});
byID("copy").onclick=guarded(async()=>{const b=await checked();bundle=structuredClone(b);const parent=b.profile.template_id;bundle.profile.template_id=customAPI.newID();bundle.profile.name+=" · 副本";bundle.profile.provenance={...bundle.profile.provenance,parent_template_id:parent};bundle.profile.image.path="../images/"+bundle.profile.template_id+".png";
 await customAPI.put(bundle);show(bundle);history.replaceState(null,"","custom.html?id="+encodeURIComponent(bundle.profile.template_id));message("已保存新副本，原模板保持不变。")});
byID("exportPlan").onclick=guarded(async()=>{const b=await checked(),products={},bindings=[];
 for(const s of b.profile.slots){const d=planDraft.get(s.id);if(!d?.product_id)continue;
  if(!d.orientation||!Number.isInteger(d.front_count)||d.front_count<1||!Number.isInteger(d.depth_count)||d.depth_count<1)throw Error(s.id+"：请检查姿态和数量");
  products[d.product_id]=window.SHELF_PRODUCTS[d.product_id];bindings.push({slot_id:s.id,...d,gap_cm:0});}
 if(!bindings.length)throw Error("请至少选择一个格位的商品");
 customAPI.download({schema_version:"shelf-plan/1.0",template_id:b.profile.template_id,scene_id:b.profile.template_id+"_CUSTOM",products,bindings},b.profile.template_id+"-plan.json");
 message("上货计划已导出。请把模板包先注册到引擎，再编译计划；尚未进行尺寸校验或生图。")});
(async()=>{try{const id=new URLSearchParams(location.search).get("id");if(id){const b=await customAPI.get(id);if(!b)throw Error("当前浏览器没有这份模板，请从导出的模板包恢复。");await customAPI.validateBundle(b);show(b);message("已打开自定义模板："+b.profile.name)}}catch(e){message(e.message)}})();
