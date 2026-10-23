/* Local browser template library. Image bytes are stored unchanged. */
window.ShelfCustom = (() => {
  function open() { return new Promise((resolve,reject) => {
    const req=indexedDB.open("retail-shelf-custom-v1",1);
    req.onupgradeneeded=()=>req.result.createObjectStore("templates",{keyPath:"profile.template_id"});
    req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);
  });}
  async function transaction(mode,fn) { const db=await open();return new Promise((resolve,reject)=>{
    const tx=db.transaction("templates",mode),store=tx.objectStore("templates");let value;
    const req=fn(store);req.onsuccess=()=>{value=req.result};
    tx.oncomplete=()=>{db.close();resolve(value)};tx.onerror=()=>{db.close();reject(tx.error)};tx.onabort=()=>{db.close();reject(tx.error)};
  });}
  function download(value,name) { const a=document.createElement("a");
    a.href=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+"\n"],{type:"application/json"}));
    a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
  }
  function imageURL(bundle){return "data:"+bundle.image.media_type+";base64,"+bundle.image.data_base64}
  async function hash(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(x=>x.toString(16).padStart(2,"0")).join("")}
  function convex(poly){if(!Array.isArray(poly)||poly.length!==4)throw Error("区域需要4个角点");
    for(const p of poly)if(!Array.isArray(p)||p.length!==2||p.some(v=>!Number.isFinite(v)||v<0||v>1))throw Error("坐标必须在0到1之间");
    const cs=poly.map((a,i)=>{const b=poly[(i+1)%4],c=poly[(i+2)%4];return (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])});
    if(!cs.every(v=>v>1e-8)&&!cs.every(v=>v< -1e-8))throw Error("四角不能交叉或压成直线");
  }
  function validateProfile(p){if(p.schema_version!=="shelf-template/1.0"||!/^CUST_[A-Za-z0-9_-]{1,58}$/.test(p.template_id))throw Error("自定义模板ID需以CUST_开头");
    if(!p.name?.trim()||!p.slots?.length)throw Error("请填写名称并添加至少一个格位");
    const ids=new Set(),positions=new Set();
    for(const s of p.slots){convex(s.polygon);const key=s.module+"/"+s.level;
      if(!s.module||!s.level||ids.has(s.id)||positions.has(key))throw Error("格位编号或模块/层位重复");ids.add(s.id);positions.add(key);
      if(!["shelf","peg","basket","platform"].includes(s.support))throw Error("支撑方式无效");
      for(const point of [...(s.support_line||[]),...(s.anchors||[])])if(point.length!==2||point.some(v=>!Number.isFinite(v)||v<0||v>1))throw Error("支撑线/挂点无效");
      if(s.support_line?.length!==2)throw Error("需要支撑线两个端点");
      if(s.physical_cm){if(!["user_measured","manufacturer_spec","concept_assumption"].includes(s.physical_cm.basis))throw Error("尺寸需要来源");
        for(const k of ["width","height","depth"])if(s.physical_cm[k]!=null&&(!Number.isFinite(s.physical_cm[k])||s.physical_cm[k]<=0))throw Error("尺寸必须为正数或留空");}
    }
    for(const r of p.protected_regions||[])convex(r.polygon);
  }
  async function validateBundle(b){if(b.schema_version!=="shelf-template-bundle/1.0")throw Error("不支持的模板包版本");validateProfile(b.profile);
    if(!["image/png","image/jpeg","image/webp"].includes(b.image?.media_type))throw Error("只支持PNG、JPEG、WebP");
    const bin=atob(b.image.data_base64),bytes=Uint8Array.from(bin,c=>c.charCodeAt(0));
    if(await hash(bytes)!==b.profile.image.sha256)throw Error("原图哈希不匹配");
    const img=new Image();await new Promise((yes,no)=>{img.onload=yes;img.onerror=()=>no(Error("图片无法解码"));img.src=imageURL(b)});
    if(img.naturalWidth!==b.profile.image.width||img.naturalHeight!==b.profile.image.height)throw Error("图片尺寸不匹配");return b;
  }
  function newID(){return "CUST_"+Date.now().toString(36)+"_"+crypto.randomUUID().slice(0,8)}
  async function clone(profile,uri){const copy=structuredClone(profile),id=newID();copy.template_id=id;copy.name+=" · 自定义";
    copy.calibration="manual_visible_scope";copy.image.path="../images/"+id+".png";
    copy.provenance={kind:"custom_copy",parent_template_id:profile.template_id,verified_real_measurements:false};
    const media=uri.slice(5,uri.indexOf(";")),data=uri.slice(uri.indexOf(",")+1);
    const b={schema_version:"shelf-template-bundle/1.0",profile:copy,image:{media_type:media,data_base64:data}};
    await validateBundle(b);await put(b);return id;
  }
  async function put(b){return transaction("readwrite",s=>s.put(b))}
  return {list:()=>transaction("readonly",s=>s.getAll()),get:id=>transaction("readonly",s=>s.get(id)),put,download,imageURL,hash,convex,validateProfile,validateBundle,newID,clone};
})();
