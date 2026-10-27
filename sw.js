'use strict';
const CACHE='bojiboji-shell-mobile-v1';
const SHELL=['/','/index.html','/install','/install.html','/manifest.webmanifest','/game.js','/online.js','/spots.js','/experience.js','/experience.css','/i18n.js','/locales/pcm.js','/mobile/mobile.js','/mobile/mobile.css','/legal/legal.js','/legal/terms.html','/legal/privacy.html','/legal/copyright.html','/assets/boji-mark.svg','/assets/bojiboji-logo.webp','/assets/bojiboji-key-art.webp','/assets/app-icon-180.png','/assets/app-icon-192.png','/assets/app-icon-512.png'];
const PATHS=new Set(SHELL);
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('bojiboji-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('message',event=>{if(event.data?.type==='ACTIVATE_UPDATE')self.skipWaiting()});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 // Never cache room APIs, session tokens, event streams, public config or uploads.
 if(request.method!=='GET'||url.origin!==self.location.origin||!PATHS.has(url.pathname))return;
 event.respondWith((async()=>{let cache=null;try{cache=await caches.open(CACHE)}catch{}try{const response=await fetch(request);if(response.ok&&response.type!=='opaque'&&cache){try{await cache.put(url.pathname,response.clone())}catch{}}if(response.status>=500&&cache){const saved=await cache.match(url.pathname);if(saved)return saved}return response}catch{const saved=cache&&await cache.match(url.pathname);if(saved)return saved;return new Response('Bojiboji offline files are not ready. Reconnect and reload.',{status:503,headers:{'Content-Type':'text/plain'}})}})());
});
