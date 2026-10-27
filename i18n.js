'use strict';
(()=>{
 const catalog=window.bojiPcm||{},storageKey='boji-language-v1',supported=['pcm','en'];
 const reverse=new Map(Object.entries(catalog).map(([key,value])=>[value.trim(),key]));
 const rendered=new Map(),textNodes=[],attributes=[];let language='pcm';
 try{const saved=localStorage.getItem(storageKey);if(supported.includes(saved))language=saved}catch{}
 const canonical=value=>Object.hasOwn(catalog,value)?value:(reverse.get(value.trim())||value);
 function t(key,values={}){key=String(key);const previous=rendered.get(key);if(previous&&Object.keys(values).length===0){key=previous.key;values=previous.values}else key=canonical(key);const template=language==='pcm'?(catalog[key]||key):key;const output=template.replace(/\{(\w+)\}/g,(_,name)=>String(values[name]??'{'+name+'}'));rendered.set(output,{key,values:{...values}});if(rendered.size>500)rendered.delete(rendered.keys().next().value);return output}
 if(document.createTreeWalker){const walker=document.createTreeWalker(document.body,4);let node;while((node=walker.nextNode())){if(node.parentElement?.closest('script,style,[data-no-i18n]'))continue;const text=node.nodeValue.trim(),key=canonical(text);if(Object.hasOwn(catalog,key)){const prefix=node.nodeValue.match(/^\s*/)[0],suffix=node.nodeValue.match(/\s*$/)[0];textNodes.push({node,key,prefix,suffix})}}}
 for(const element of document.querySelectorAll('[placeholder],[aria-label],[alt]'))for(const name of ['placeholder','aria-label','alt']){const value=element.getAttribute(name);if(value){const key=canonical(value);if(Object.hasOwn(catalog,key))attributes.push({element,name,key})}}
 function apply(){if(document.documentElement)document.documentElement.lang=language;for(const item of textNodes)if(item.node.isConnected!==false)item.node.nodeValue=item.prefix+t(item.key).trim()+item.suffix;for(const item of attributes)item.element.setAttribute(item.name,t(item.key));const picker=document.getElementById('language');if(picker)picker.value=language;for(const element of document.querySelectorAll('[data-locale]'))element.hidden=element.getAttribute('data-locale')!==language;
  for(const id of ['spotStatus','spotPosition','banner','roomStatus','pause','sound','startRoom','winnerName','winnerMessage','clearSavedStatus']){const element=document.getElementById(id),old=element&&rendered.get(element.textContent);if(old)element.textContent=t(old.key,old.values)}
 }
 function setLanguage(next,persist=true){language=supported.includes(next)?next:'pcm';if(persist)try{localStorage.setItem(storageKey,language)}catch{}apply();window.dispatchEvent(new Event('boji-language-changed'))}
 window.bojiI18n={t,setLanguage,get language(){return language},defaultLanguage:'pcm',supported:[...supported]};apply();
 document.getElementById('language')?.addEventListener('change',event=>setLanguage(event.target.value));
 window.addEventListener('boji-saves-cleared',()=>setLanguage('pcm',false));
 window.addEventListener('storage',event=>{if(event.key===storageKey)setLanguage(event.newValue,false)});
})();
