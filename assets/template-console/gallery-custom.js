(async()=>{
 const list=document.querySelector("#custom-list"),status=document.querySelector("#custom-status");
 async function refresh(){list.replaceChildren();const templates=await ShelfCustom.list();
  const localIDs=new Set(templates.map(b=>b.profile.template_id));for(const card of document.querySelectorAll("[data-registered-id]"))card.hidden=localIDs.has(card.dataset.registeredId);
  if(!templates.length){list.textContent="还没有浏览器自定义模板。可以导入自己的空架图，或从基础模板另存副本。";return}
  for(const b of templates){const article=document.createElement("article"),a=document.createElement("a"),img=document.createElement("img"),h=document.createElement("h2"),p=document.createElement("p"),link=document.createElement("a");
    a.href="custom.html?id="+encodeURIComponent(b.profile.template_id);img.src=ShelfCustom.imageURL(b);img.loading="lazy";a.append(img);h.textContent=b.profile.name;p.textContent=b.profile.slots.length+"个格位 · "+b.profile.template_id;
    link.href=a.href;link.textContent="编辑模板 / 选择商品上货";article.append(a,h,p,link);list.append(article);}
 }
 try{await refresh()}catch(e){status.textContent="浏览器本地库不可用："+e.message+"。仍可使用基础模板，或切换支持IndexedDB的浏览器。"}
 document.querySelector("#restoreBundle").onchange=async e=>{try{const file=e.target.files[0];if(!file)return;const b=await ShelfCustom.validateBundle(JSON.parse(await file.text()));
  if(await ShelfCustom.get(b.profile.template_id))throw Error("同ID模板已存在；请先在工作台另存副本，避免覆盖");
  await ShelfCustom.put(b);await refresh();status.textContent="模板包已恢复，可在下方选择。";
 }catch(err){status.textContent=err.message}finally{e.target.value=""}};
})();
