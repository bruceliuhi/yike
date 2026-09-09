"use strict";
const state={pages:[],index:-1,tiles:[]};
const el=id=>document.getElementById(id);
function show(index,moveFocus=true){
  const previousIndex=state.index;
  const valid=Number.isInteger(index)&&index>=0&&index<state.pages.length;
  state.index=valid?index:-1;
  el("single").hidden=!valid;el("grid").hidden=valid;
  el("previous").disabled=!valid||index===0;
  el("next").disabled=valid&&index===state.pages.length-1;
  el("original").hidden=!valid;
  document.querySelectorAll("#pages button").forEach((button,i)=>{
    if(i===state.index)button.setAttribute("aria-current","page");else button.removeAttribute("aria-current");
  });
  window.scrollTo({top:0,behavior:"instant"});
  if(valid){
    const page=state.pages[index];
    el("title").textContent=page.id+" · "+page.title;
    el("position").textContent=(index+1)+" / "+state.pages.length+" · 待确认";
    el("image-error").hidden=true;
    el("screen").src=page.image;el("screen").alt=page.id+" "+page.title+"设计预览";
    el("original").href=page.image;history.replaceState(null,"","#"+page.id);
    if(moveFocus)el("title").focus({preventScroll:true});
  }else{
    history.replaceState(null,"",location.pathname);
    if(moveFocus)(state.tiles[previousIndex]||el("overview")).focus();
  }
}
el("screen").addEventListener("error",()=>{el("image-error").hidden=false;});
el("overview").addEventListener("click",()=>show(-1));
el("previous").addEventListener("click",()=>show(state.index-1));
el("next").addEventListener("click",()=>show(state.index+1));
document.addEventListener("keydown",event=>{
  if(event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return;
  if(event.key==="ArrowRight"&&state.index<state.pages.length-1){event.preventDefault();show(state.index+1);}
  if(event.key==="ArrowLeft"&&state.index>0){event.preventDefault();show(state.index-1);}
  if(event.key==="Escape")show(-1);
});
fetch("manifest.json").then(response=>{if(!response.ok)throw new Error("manifest unavailable");return response.json();}).then(data=>{
  state.pages=data.pages;
  el("summary").textContent="R1 · "+state.pages.length+" 页 · 等待你的确认";
  for(const [index,page]of state.pages.entries()){
    const nav=document.createElement("button");nav.type="button";nav.textContent=page.id+" · "+page.title;nav.addEventListener("click",()=>show(index));el("pages").append(nav);
    const tile=document.createElement("button");tile.type="button";tile.className="thumbnail";tile.addEventListener("click",()=>show(index));
    const image=document.createElement("img");image.src=page.image;image.alt=page.title+"设计缩略图";image.loading="lazy";
    const caption=document.createElement("span");caption.textContent=page.id+" · "+page.title;
    image.addEventListener("error",()=>{image.hidden=true;caption.textContent=page.id+" · "+page.title+"（图片加载失败）";});
    tile.append(image,caption);el("thumbnails").append(tile);state.tiles.push(tile);
  }
  show(state.pages.findIndex(page=>"#"+page.id===location.hash),false);
}).catch(()=>{el("grid").textContent="设计目录加载失败，请通过本地图册服务打开，或直接查看 screens 文件夹。";});
