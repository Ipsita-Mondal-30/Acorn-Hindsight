// ---- pixel sprites: grid strings -> crisp SVG ----
const PAL={k:'#1a1a1a',B:'#7a4118',b:'#a8602a',t:'#e8b366',w:'#fff3c9',y:'#f3f08a',Y:'#dfd85f',o:'#e8a33d',g:'#5aa13a',G:'#7fcf55',u:'#3a86ff',l:'#9bd0ff',r:'#ff6b5e',W:'#ffffff',s:'#c8ccd4',m:'#7b5ea7'};
const SPR={
acorn:[".....kk.....","....kBBk....","..kkkkkkkk..",".kBbBbBbBBk.","kBbBbBbBbBBk","kBBBBBBBBBBk","kkkkkkkkkkkk",".kttttttttk.",".kttwttttttk",".kttttttttk.","..kttttttk..","...kttttk...","....kkkk...."],
sparkle:["...u...","...u...","..uuu..","uulllUU".replace(/U/g,"u"),"..uuu..","...u...","...u..."],
coin:["..kkkk..",".kyyyyyk","kyyyooyk","kyyoooyk","kyyoooyk","kyyyooyk",".kyyyyk.","..kkkk.."],
folder:[".kkkkkk.......","kyyyyyykkkkkk.","kyyyyyyyyyyyyk","kkkkkkkkkkkkkk","kyYyYyYyYyYyYk","kYyYyYyYyYyYyk","kyYyYyYyYyYyYk","kYyYyYyYyYyYyk","kyYyYyYyYyYyYk","kkkkkkkkkkkkkk"],
flower:["..kyyyk..",".kyyyyyk.","kyyBBByyk","kyBbbbByk","kyBbbbByk","kyyBBByyk",".kyyyyyk.","..kkgkk..","....g....","..gg.g...",".ggg.g...","...g.gg..","....ggg..","....g....","....g...."],
ghost:["...kkkk...","..kllllk..",".kllllllk.",".klkklkklk",".klkklkklk",".klllllllk",".klllllllk",".klllllllk",".klkllklllk","..k.kk.k.."],
siren:["...kk...","..krrk..",".krWrrk.",".krWrrk.","krrrrrrk","kkkkkkkk","kssssskk"],
check:["......kk",".....kGk","k...kGk.","kk.kGk..","kGkGk...",".kGk....","..k....."],
hex:["...kkkkkk...","..krrrrrrk..",".krrrWWrrrk.","krrrrWWrrrrk","krrrrWWrrrrk","krrrrWWrrrrk","krrrrrrrrrrk","krrrrWWrrrrk",".krrrrrrrrk.","..kkkkkkkk.."]
};
function px(name,size=4){const g=SPR[name],h=g.length,w=Math.max(...g.map(r=>r.length));let r='';
  g.forEach((row,y)=>[...row].forEach((c,x)=>{if(PAL[c])r+=`<rect x="${x}" y="${y}" width="1.02" height="1.02" fill="${PAL[c]}"/>`}));
  return `<svg class="px" width="${w*size}" height="${h*size}" viewBox="0 0 ${w} ${h}">${r}</svg>`}
const $=s=>document.querySelector(s);
$('#logo').innerHTML=px('acorn',5);$('#d1').innerHTML=px('sparkle',5);$('#d2').innerHTML=px('sparkle',4);

const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const md=s=>esc(s).replace(/^#{1,6}\s*(.+)$/gm,'<b>$1</b>').replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/^\s*[*-]\s+/gm,'▪ ');
const winHtml=(cls,title,body)=>`<div class="win ${cls}"><div class="bar"><i class="dot r"></i><i class="dot"></i><i class="dot"></i><span class="pf">${title}</span></div><div class="body">${body}</div></div>`;
function toast(m,err){const t=$('#toast');t.innerHTML=winHtml(err?'bad':'green',err?'error.exe':'done.app',`<span class="bob">${px(err?'hex':'coin',4)}</span><div class="ans" style="font-size:21px">${err?'<b>ERROR!</b> ':''}${esc(m)}</div>`);t.style.display='block';clearTimeout(toast.h);toast.h=setTimeout(()=>t.style.display='none',4200)}
let inflight=0;const setBusy=d=>{inflight+=d;document.body.classList.toggle('busy',inflight>0)};
async function api(p,o){setBusy(1);try{const r=await fetch(p,o&&{method:o.method||'POST',headers:{'content-type':'application/json'},body:JSON.stringify(o.body||{})});if(!r.ok)throw new Error((await r.text()).slice(0,200));return await r.json()}finally{setBusy(-1)}}
const busy=async(b,fn)=>{b.disabled=true;try{return await fn()}catch(e){toast(e.message,true)}finally{b.disabled=false}};
const ago=iso=>{const d=Math.round((Date.now()-new Date(iso))/864e5);return d<=0?'today':d+'d ago'};
const facts=fs=>fs&&fs.length?`<div class="facts"><div class="pf">MEMORIES USED (${fs.length})</div>${fs.slice(0,8).map(f=>`<div class="fact"><i>${esc(f.type||'fact')}</i>${esc(f.text)}</div>`).join('')}</div>`:'';

