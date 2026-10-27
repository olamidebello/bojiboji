'use strict';
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const nodes=new Map();function element(){return {style:{},classList:{toggle(){}},value:'',checked:false,hidden:false,disabled:false,children:[],addEventListener(){},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},scrollIntoView(){},setPointerCapture(){}}}function el(id){if(!nodes.has(id)){const n=element();n.value=({count:'3',duration:'30',avatar:'fox',theme:'grove',name:'Tester'})[id]||'';nodes.set(id,n)}return nodes.get(id)}
const ctx=new Proxy({},{get:()=>()=>{}});el('game').getContext=()=>ctx;el('game').getBoundingClientRect=()=>({left:0,top:0,width:900,height:600});
const c={document:{getElementById:el,querySelectorAll:()=>[],activeElement:{tagName:'BODY'},createElement:element},window:{addEventListener(){}},requestAnimationFrame(){},setInterval(){},localStorage:{getItem:()=>null,setItem(){}},location:{href:'http://localhost/',search:'?room=ABCDEF'},URL,URLSearchParams,navigator:{},console,Math};c.Event=class{constructor(type){this.type=type}};c.window.dispatchEvent=()=>{};vm.createContext(c);
if(process.argv.includes('--pidgin'))for(const file of ['locales/pcm.js','i18n.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),c,{filename:file});
for(const file of ['game.js','online.js','spots.js','experience.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),c,{filename:file});
vm.runInContext(`
if($('roomCode').value!=='ABCDEF')throw Error('invite parsing');
$('start').onclick();draw(100);window.bojiEffects(100);tick(2.1);tick(4.1);draw(200);window.bojiEffects(200);
players[0].throws=4;players[0].hits=2;players.forEach((p,i)=>p.alive=i===0);newRound();draw(300);window.bojiEffects(300);
if(personal.games!==1||personal.wins!==1||personal.hits!==2||$('results').hidden)throw Error('result statistics');window.bojiEffects(350);if(personal.games!==1)throw Error('duplicate stats');
session={id:0};window.bojiRoomUI({host:0,phase:'idle',members:[{id:0,ready:true},{id:1,ready:false}],players:[{id:0,name:'Alice'},{id:1,name:'Bob'}]});if($('roomMembers').children.length!==2)throw Error('room roster');window.bojiRoomUI(null);
`,c);assert.equal(el('statWins').textContent,1);console.log('PASS: scripts load, invite code, canvas rendering, avatars, results, session statistics, duplicate protection, lobby controls');
