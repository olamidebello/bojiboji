const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements={};const el=id=>elements[id]??={value:id==='count'?'5':id==='duration'?'30':'Tester',style:{},textContent:'',replaceChildren(){},tagName:'BODY'};
const context=new Proxy({},{get:()=>()=>{}});el('game').getContext=()=>context;
const c={document:{getElementById:el,querySelectorAll:()=>[],activeElement:{tagName:'BODY'},createElement:()=>({style:{}})},window:{addEventListener(){}},requestAnimationFrame(){},Math,console};vm.createContext(c);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'..','game.js'),'utf8'),c);
vm.runInContext(`
$('start').onclick();if(alive().length!==5||phase!=='toss')throw Error('start');tick(2.1);if(phase!=='hide'||!holder)throw Error('toss');tick(4.1);if(phase!=='play')throw Error('hide');
players.forEach((p,i)=>{p.x=50+i*60;p.y=50});holder=players[1];lock=0;throwBall(holder,-1,0);for(let i=0;i<10;i++)tick(.015);if(holder!==players[0])throw Error('hit transfer');
left=.001;let loser=holder;tick(.01);if(loser.alive||phase!=='result')throw Error('elimination');tick(3.1);if(round!==2||alive().length!==4)throw Error('next round');
players.forEach((p,i)=>p.alive=i===0);newRound();if(phase!=='over')throw Error('winner');
$('start').onclick();paused=true;let before=phaseTime;tick(1);if(phaseTime!==before)throw Error('pause');
`,c);console.log('PASS: start, toss, hide, hit transfer, elimination, next round, winner, pause');
