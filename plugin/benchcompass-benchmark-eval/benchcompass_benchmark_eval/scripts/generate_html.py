"""JSON sonuçlarından self-contained interaktif HTML raporu üretir.

Özellikler:
  - Veri sayfaya gömülür -> internet olmadan da çalışır.
  - Hybrid grafik: Chart.js CDN'i yüklenirse onu kullanır; yüklenmezse
    elle SVG/Canvas çizime düşer (offline fallback).
  - Bölümler: Genel Bakış / Testler & Koşullar / Sonuçlar / Grafikler /
    İyileştirmeler / Veri.

Deterministik: aynı girdi -> aynı çıktı.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import config, history, llmfit_data
from ..scripts.generate_md import IMPROVEMENTS

HTML_TEMPLATE = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLMFit Benchmark Eval — İnteraktif Rapor</title>
<style>
:root{
  --bg:#0b0e14; --panel:#11151f; --panel2:#161b28; --border:#232a3a;
  --text:#d7dce6; --muted:#7a8599; --mono:"Consolas","Cascadia Mono",monospace;
  --success:#22c55e; --warn:#f59e0b; --bad:#ef4444; --accent:#60a5fa;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:13px/1.55 "Segoe UI",system-ui,sans-serif;padding:18px;max-width:1280px;margin:0 auto}
h1{font-size:20px;letter-spacing:.05em;text-transform:uppercase}
h2{font-family:var(--mono);font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);margin:0 0 12px}
.sub{color:var(--muted);font-size:12px;margin-top:4px}
nav{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0 18px}
nav button{background:var(--panel);color:var(--muted);border:1px solid var(--border);padding:7px 14px;cursor:pointer;font:11px var(--mono);letter-spacing:.04em;text-transform:uppercase}
nav button.active{background:var(--accent);color:#0b0e14;border-color:var(--accent)}
section.view{display:none}
section.view.active{display:block}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.kpi{background:var(--panel);border:1px solid var(--border);padding:14px}
.kpi .label{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em}
.kpi .value{font-family:var(--mono);font-size:24px;margin-top:6px;color:var(--text)}
.kpi .value small{font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{border:1px solid var(--border);padding:6px 8px;text-align:left}
th{background:var(--panel2);cursor:pointer;user-select:none;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
tr:nth-child(even){background:#10141e}
.ok{color:var(--success)} .no{color:var(--bad)} .warn{color:var(--warn)}
.tag{display:inline-block;padding:1px 6px;border:1px solid var(--border);border-radius:3px;font-size:10px;font-family:var(--mono);color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--border);padding:16px;margin-bottom:16px}
.panel p{margin-bottom:8px}
code,pre{font-family:var(--mono);background:var(--panel2);border:1px solid var(--border);padding:1px 4px;font-size:11px}
pre{display:block;padding:12px;overflow:auto;max-height:420px;white-space:pre}
.chart{background:var(--panel);border:1px solid var(--border);padding:14px;margin-bottom:16px}
.chart h3{font-family:var(--mono);font-size:11px;text-transform:uppercase;color:var(--muted);letter-spacing:.06em;margin-bottom:10px}
.chart canvas{width:100%;max-height:340px}
.badge{display:inline-block;padding:2px 8px;border-radius:3px;font:11px var(--mono)}
.badge.good{background:#0f2e1b;color:var(--success);border:1px solid var(--success)}
.badge.mid{background:#33270a;color:var(--warn);border:1px solid var(--warn)}
.badge.bad{background:#351312;color:var(--bad);border:1px solid var(--bad)}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center}
.toolbar input,.toolbar select{background:var(--panel2);border:1px solid var(--border);color:var(--text);padding:6px 8px;font:12px var(--mono)}
details{border:1px solid var(--border);background:var(--panel);padding:8px 12px;margin-bottom:6px}
summary{cursor:pointer;font-weight:600}
.fail{color:var(--bad)} .pass{color:var(--success)}
@media(max-width:720px){th,td{padding:4px}}
</style>
</head>
<body>
<h1>LLMFit Benchmark Eval</h1>
<div class="sub">İnteraktif yerel model raporu — <span id="gen-date"></span> · veri gömülü (offline)</div>

<nav id="tabs">
  <button data-view="overview" class="active">Genel Bakış</button>
  <button data-view="tests">Testler &amp; Koşullar</button>
  <button data-view="results">Sonuçlar</button>
  <button data-view="quants">Quant</button>
  <button data-view="context">Context</button>
  <button data-view="retrieval">Retrieval</button>
  <button data-view="community">Community</button>
  <button data-view="charts">Grafikler</button>
  <button data-view="improvements">İyileştirmeler</button>
  <button data-view="data">Veri</button>
</nav>

<section id="overview" class="view active">
  <div class="kpis" id="kpis"></div>
  <div class="panel" id="hardware-panel"></div>
</section>

<section id="tests" class="view">
  <div class="panel" id="conditions"></div>
  <div class="panel">
    <h2>Görev Matrisi</h2>
    <table id="task-table"></table>
  </div>
</section>

<section id="results" class="view">
  <div class="toolbar">
    <input id="q" type="search" placeholder="Model ara..." oninput="renderSummary()">
  </div>
  <div class="panel">
    <h2>Özet Tablo <small class="sub">(sütun başlığına tıkla sıralar)</small></h2>
    <table id="summary-table"></table>
  </div>
  <div class="panel">
    <h2>Per-Görev Geçti/Kaldı</h2>
    <table id="task-pass-table"></table>
  </div>
</section>

<section id="quants" class="view">
  <div class="panel">
    <h2>Quant Karşılaştırma (B1)</h2>
    <p class="sub">Aynı model ailesinin farklı quant'ları yan yana — hız/doğruluk trade-off'u.</p>
    <div id="quant-panel"></div>
  </div>
</section>

<section id="context" class="view">
  <div class="panel">
    <h2>Context Stres Testi (B2)</h2>
    <p class="sub">Needle-in-haystack: gizli kod uzun metnin %50 derinliğinde; prefill tok/s + hatırlama.</p>
    <div id="context-panel"></div>
  </div>
</section>

<section id="retrieval" class="view">
  <div class="panel">
    <h2>Retrieval / Embedding Kalitesi (B4)</h2>
    <p class="sub">Sorgu için doğru doküman en üstte mi? (cosine benzerliği)</p>
    <div id="retrieval-panel"></div>
  </div>
</section>

<section id="community" class="view">
  <div class="panel">
    <h2>Community Karşılaştırma Panosu (B5)</h2>
    <p class="sub">Kendi ölçümleriniz vs llmfit community benchmark_cache.</p>
    <div id="community-panel"></div>
  </div>
  <div class="panel">
    <h2>Geçmiş / Zaman Serisi (B5)</h2>
    <p class="sub">Parent benchmark_history.db'deki per-model trend.</p>
    <div id="history-panel"></div>
  </div>
</section>

<section id="charts" class="view">
  <div class="chart"><h3>Generation Hızı (tok/s)</h3><canvas id="c-speed"></canvas></div>
  <div class="chart"><h3>Kalite Skoru (%)</h3><canvas id="c-quality"></canvas></div>
  <div class="chart"><h3>Hız x Kalite (verimlilik scatter)</h3><canvas id="c-scatter"></canvas></div>
  <div class="chart"><h3>TTFT (ms)</h3><canvas id="c-ttft"></canvas></div>
  <div class="sub" id="chart-mode"></div>
</section>

<section id="improvements" class="view">
  <div class="panel">
    <h2>Öneriler</h2>
    <table id="improve-table"></table>
  </div>
</section>

<section id="data" class="view">
  <div class="panel">
    <h2>Ham Sonuç JSON</h2>
    <pre id="raw-data"></pre>
  </div>
</section>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
"use strict";
var DATA = __DATA_JSON__;
var IMPROVEMENTS = __IMPROVEMENTS_JSON__;
var chartjs = typeof Chart !== "undefined";

function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function fmt(v,d){if(v==null)return "-";d=d||1;return typeof v==="number"?v.toFixed(d):v;}

document.getElementById("tabs").addEventListener("click",function(e){
  var b=e.target.closest("button"); if(!b) return;
  var btns=document.querySelectorAll("nav button");
  for(var i=0;i<btns.length;i++)btns[i].classList.remove("active");
  b.classList.add("active");
  var vs=document.querySelectorAll("section.view");
  for(var j=0;j<vs.length;j++)vs[j].classList.remove("active");
  document.getElementById(b.dataset.view).classList.add("active");
});

function renderKpis(){
  var models=DATA.models||[]; var el=document.getElementById("kpis");
  if(!models.length){el.innerHTML="<div class='sub'>Veri yok</div>";return;}
  var speeds=[],quals=[],i,m;
  for(i=0;i<models.length;i++){m=models[i];if((m.speed||{}).gen_tps)speeds.push(m.speed.gen_tps);if(m.quality&&m.quality.score!=null)quals.push(m.quality.score);}
  var bestS=Math.max.apply(null,speeds), bestQ=Math.max.apply(null,quals);
  var avgS=(speeds.reduce(function(a,b){return a+b;},0)/speeds.length).toFixed(1);
  var cards=[["Model sayısı",models.length],["En hızlı",bestS+" tok/s"],["Ort. hız",avgS+" tok/s"],["En yüksek kalite",bestQ+" %"]];
  var html="";
  for(i=0;i<cards.length;i++){html+='<div class="kpi"><div class="label">'+cards[i][0]+'</div><div class="value">'+cards[i][1]+'</div></div>';}
  el.innerHTML=html;
}
function renderHardware(){
  var hw=DATA.hardware||{},cond=DATA.conditions||{};
  var rows=[["GPU",hw.gpu||"-"],["VRAM",fmt(hw.vram_gb)+" GB"],["RAM",fmt(hw.ram_gb)+" GB"],["CPU",hw.cpu||"-"],["Ollama",hw.ollama_version||"-"],["Sıcaklık",cond.temperature==null?"-":cond.temperature],["think",cond.think==null?"-":cond.think],["Hız tekrarı",cond.speed_runs==null?"-":cond.speed_runs],["Kalite token bütçesi",cond.quality_num_predict==null?"-":cond.quality_num_predict],["Üretim",DATA.generated_at||"-"],["llmfit modu",DATA.llmfit_mode||"none"]];
  var html="<h2>Donanım &amp; Koşullar</h2><table>";
  for(var i=0;i<rows.length;i++){html+="<tr><th style='width:240px'>"+rows[i][0]+"</th><td>"+esc(rows[i][1])+"</td></tr>";}
  html+="</table>"; document.getElementById("hardware-panel").innerHTML=html;
}
function renderConditions(){
  var cond=DATA.conditions||{};
  var items=[["Ölçüm yöntemi","tok/s = eval_count/eval_duration (Ollama resmi metriği). TTFT akışlı istekle ilk token zamanı (bayt bayt okuma). Kalite: sıcaklık 0.0, kod görevleri exec + birim test."],["Ollama URL",cond.ollama_url||"-"],["Sıcaklık",cond.temperature],["think modu",cond.think],["Hız tekrar sayısı",cond.speed_runs],["Kalite token bütçesi",cond.quality_num_predict],["Hız testi çıktı uzunluğu",cond.speed_num_predict]];
  var html="<h2>Test &amp; Ölçüm Koşulları</h2><table>";
  for(var i=0;i<items.length;i++){html+="<tr><th style='width:240px'>"+items[i][0]+"</th><td>"+esc(items[i][1])+"</td></tr>";}
  html+="</table>"; document.getElementById("conditions").innerHTML=html;
}
function renderTaskTable(){
  var tasks=DATA.tasks||[]; var rows=[["ID","Tip","Dil","Zorluk","Kategori","Beklenen"]];
  var i,t;
  for(i=0;i<tasks.length;i++){t=tasks[i];rows.push([t.id,t.type,t.lang||"en",t.difficulty||"-",t.category||"-",esc(String(t.expected==null?"":t.expected).slice(0,50))]);}
  var html="";
  for(i=0;i<rows.length;i++){html+="<tr>";for(var j=0;j<rows[i].length;j++){html+= i===0?"<th>"+rows[i][j]+"</th>":"<td>"+rows[i][j]+"</td>";}html+="</tr>";}
  document.getElementById("task-table").innerHTML=html;
}
var sortKey="gen_tps",sortDir=-1;
function renderSummary(){
  var q=document.getElementById("q").value.toLowerCase();
  var models=(DATA.models||[]).filter(function(m){return q===""||m.model.toLowerCase().indexOf(q)>=0;});
  models.sort(function(a,b){var av=a.speed?.[sortKey]||0,bv=b.speed?.[sortKey]||0;return (av-bv)*sortDir;});
  var head=["Model","Boyut","tok/s","prefill","TTFT(ms)","Kalite","EN","TR","Değerlendirme"];
  var rows=[head];
  var i,m,s,qu,score,badge;
  for(i=0;i<models.length;i++){m=models[i];s=m.speed||{};qu=m.quality||{};score=qu.score==null?0:qu.score;
    var byL=qu.by_lang||{},enS=byL.en&&byL.en.score,trS=byL.tr&&byL.tr.score;
    badge=score>=85?"good":score>=70?"mid":"bad";
    rows.push([m.model,fmt(m.size_gb)+"GB",fmt(s.gen_tps),fmt(s.prefill_tps,0),fmt(s.ttft_ms,0),(qu.passed||0)+"/"+(qu.total||0),enS==null?"-":enS+"%",trS==null?"-":trS+"%",'<span class="badge '+badge+'">'+(score>=85?"İYİ":score>=70?"ORTA":"ZAYIF")+"</span>"]);}
  var cols=["model","size_gb","gen_tps","prefill_tps","ttft_ms","","","",""];
  var html="<thead><tr>";
  for(i=0;i<head.length;i++){var k=cols[i]||"gen_tps";html+='<th onclick="sortKey=\\''+k+'\\';sortDir=-sortDir;renderSummary()">'+head[i]+"</th>";}
  html+="</tr></thead><tbody>";
  for(i=1;i<rows.length;i++){html+="<tr>";for(var j=0;j<rows[i].length;j++)html+="<td>"+rows[i][j]+"</td>";html+="</tr>";}
  html+="</tbody>"; document.getElementById("summary-table").innerHTML=html;
}
function renderTaskPass(){
  var models=DATA.models||[],tasks=DATA.tasks||[];
  if(!models.length||!tasks.length){document.getElementById("task-pass-table").innerHTML="<div class='sub'>Veri yok</div>";return;}
  var html="<tr><th>Model</th>";var i,t,m,by;
  for(i=0;i<tasks.length;i++){t=tasks[i];html+="<th title='"+esc(t.id)+"'>"+t.id+"</th>";}
  html+="</tr>";
  for(i=0;i<models.length;i++){m=models[i];by={};var dl=(m.quality&&m.quality.details)||[];for(var k=0;k<dl.length;k++)by[dl[k].id]=dl[k].pass;
    html+="<tr><td>"+m.model+"</td>";
    for(var j=0;j<tasks.length;j++){var p=by[tasks[j].id];html+="<td>"+(p===true?'<span class="pass">✅</span>':p===false?'<span class="fail">❌</span>':"•")+"</td>";}
    html+="</tr>";}
  document.getElementById("task-pass-table").innerHTML=html;
}
function fallbackBar(id,labels,values,color){
  var c=document.getElementById(id); if(!c) return;
  var max=Math.max.apply(null,values.concat([1])),n=labels.length,W=Math.max(300,n*40),H=260,x,w,h,v,i;
  var s='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%">';
  w=W/n-16;
  for(i=0;i<n;i++){v=values[i];h=(v/max)*180;x=i*(W/n)+8;
    s+='<rect x="'+x+'" y="'+(230-h)+'" width="'+w+'" height="'+h+'" fill="'+color+'" opacity="0.85"/>';
    s+='<text x="'+(x+w/2)+'" y="'+(225-h)+'" fill="#d7dce6" font-size="11" text-anchor="middle">'+v+"</text>";
    s+='<text x="'+(x+w/2)+'" y="245" fill="#7a8599" font-size="9" text-anchor="middle">'+esc(String(labels[i]).slice(0,14))+"</text>";}
  s+="</svg>"; c.outerHTML="<div>"+s+"</div>";
}
function fallbackScatter(id,points){
  var c=document.getElementById(id); if(!c) return;
  var W=Math.max(400,points.length*70),H=280,pad=46,maxX=1,maxY=1,i,p,x,y;
  for(i=0;i<points.length;i++){if(points[i].x>maxX)maxX=points[i].x;if(points[i].y>maxY)maxY=points[i].y;}
  maxX*=1.1;maxY*=1.1;
  var s='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%">';
  for(i=0;i<points.length;i++){p=points[i];x=pad+(p.x/maxX)*(W-pad*2);y=H-pad-(p.y/maxY)*(H-pad*2);
    s+='<circle cx="'+x+'" cy="'+y+'" r="7" fill="#60a5fa" opacity="0.85"/>';
    s+='<text x="'+x+'" y="'+(y-10)+'" fill="#d7dce6" font-size="10" text-anchor="middle">'+esc(String(p.label).slice(0,12))+"</text>";}
  s+='<text x="'+(W/2)+'" y="'+(H-6)+'" fill="#7a8599" font-size="10" text-anchor="middle">hız (tok/s)</text>';
  s+="</svg>"; c.outerHTML="<div>"+s+"</div>";
}
function renderCharts(){
  var models=DATA.models||[]; if(!models.length)return;
  var i,m,labels=[],speeds=[],quals=[],ttfts=[],scatter=[];
  for(i=0;i<models.length;i++){m=models[i];labels.push(m.model);speeds.push((m.speed&&m.speed.gen_tps)||0);quals.push((m.quality&&m.quality.score)||0);ttfts.push((m.speed&&m.speed.ttft_ms)||0);scatter.push({x:(m.speed&&m.speed.gen_tps)||0,y:(m.quality&&m.quality.score)||0,label:m.model});}
  document.getElementById("chart-mode").textContent=chartjs?"[ grafik motoru: Chart.js (CDN) ]":"[ grafik motoru: offline SVG fallback ]";
  if(chartjs){
    function mk(id,type,label,data,color){new Chart(document.getElementById(id),{type:type,data:{labels:labels,datasets:[{label:label,data:data,backgroundColor:color,borderColor:color}]},options:{responsive:true,plugins:{legend:{labels:{color:"#d7dce6"}}},scales:{x:{ticks:{color:"#7a8599"}},y:{ticks:{color:"#7a8599"}}}}});}
    mk("c-speed","bar","tok/s",speeds,"#60a5fa");
    mk("c-quality","bar","%",quals,"#22c55e");
    mk("c-ttft","bar","ms",ttfts,"#f59e0b");
    new Chart(document.getElementById("c-scatter"),{type:"scatter",data:{datasets:[{label:"hız x kalite",data:scatter.map(function(p){return {x:p.x,y:p.y};}),backgroundColor:"#60a5fa"}]},options:{responsive:true,plugins:{legend:{labels:{color:"#d7dce6"}}},scales:{x:{title:{display:true,text:"tok/s",color:"#7a8599"},ticks:{color:"#7a8599"}},y:{title:{display:true,text:"kalite %",color:"#7a8599"},ticks:{color:"#7a8599"}}}}});
  }else{
    fallbackBar("c-speed",labels,speeds,"#60a5fa");
    fallbackBar("c-quality",labels,quals,"#22c55e");
    fallbackBar("c-ttft",labels,ttfts,"#f59e0b");
    fallbackScatter("c-scatter",scatter);
  }
}
function renderImprovements(){
  var rows=[["Öncelik","Başlık","Detay"]];
  var i;
  for(i=0;i<IMPROVEMENTS.length;i++){rows.push([IMPROVEMENTS[i].oncelik,IMPROVEMENTS[i].madde,esc(IMPROVEMENTS[i].detay)]);}
  var html="";
  for(i=0;i<rows.length;i++){html+="<tr>";for(var j=0;j<rows[i].length;j++)html+= i===0?"<th>"+rows[i][j]+"</th>":"<td>"+rows[i][j]+"</td>";html+="</tr>";}
  document.getElementById("improve-table").innerHTML=html;
}
function renderQuants(){
  var groups=DATA.quant_compare||[]; var el=document.getElementById("quant-panel");
  if(!groups.length){el.innerHTML="<div class='sub'>Bu koşuda aynı modelin birden çok quant'ı ölçülmedi — ör. <code>--models qwen3:8b-q4_K_M qwen3:8b-q8_0</code></div>";return;}
  var html="",g,i,j,rows,e,best;
  for(g=0;g<groups.length;g++){
    var grp=groups[g];
    best=0;for(i=0;i<grp.entries.length;i++){if((grp.entries[i].gen_tps||0)>best)best=grp.entries[i].gen_tps;}
    rows=[["Quant","tok/s","prefill tok/s","TTFT(ms)","Kalite",""]];
    for(i=0;i<grp.entries.length;i++){e=grp.entries[i];var mark=(e.gen_tps||0)>=best?"← en hızlı":"";
      rows.push([e.quant,fmt(e.gen_tps),fmt(e.prefill_tps,0),fmt(e.ttft_ms,0),(e.score==null?"-":e.score+"%"),mark]);}
    html+="<h3>"+esc(grp.family)+"</h3><table>";
    for(i=0;i<rows.length;i++){html+="<tr>";for(j=0;j<rows[i].length;j++)html+=i===0?"<th>"+rows[i][j]+"</th>":"<td>"+esc(rows[i][j])+"</td>";html+="</tr>";}
    html+="</table>";
  }
  el.innerHTML=html;
}
function renderContext(){
  var data=DATA.context_stress||{}; var el=document.getElementById("context-panel");
  var keys=Object.keys(data);
  if(!keys.length){el.innerHTML="<div class='sub'>Bu koşuda context stres çalıştırılmadı — <code>--context-stress 32k,64k,128k</code></div>";return;}
  var cols=[];var i,k,r;
  for(i=0;i<keys.length;i++){for(k=0;k<data[keys[i]].length;k++){r=data[keys[i]][k];if(r.ctx_tokens!=null&&cols.indexOf(r.ctx_tokens)<0)cols.push(r.ctx_tokens);}}
  cols.sort(function(a,b){return a-b;});
  var head=["Model"];for(i=0;i<cols.length;i++)head.push((cols[i]/1000)+"K");
  var html="<table><thead><tr>";for(i=0;i<head.length;i++)html+="<th>"+head[i]+"</th>";html+="</tr></thead><tbody>";
  for(k=0;k<keys.length;k++){
    var by={};for(i=0;i<data[keys[k]].length;i++)by[data[keys[k]][i].ctx_tokens]=data[keys[k]][i];
    html+="<tr><td>"+esc(keys[k])+"</td>";
    for(i=0;i<cols.length;i++){
      var row=by[cols[i]]||{};
      if(row.error){html+="<td class='no'>hata</td>";continue;}
      var rec=row.recall==null?"?":row.recall?"hatırladı":"hatırlamadı";
      var pre=row.prefill_tps==null?"-":Math.round(row.prefill_tps);
      html+="<td>"+pre+" tok/s · "+(row.recall?'<span class="ok">':'<span class="no">')+rec+"</span></td>";
    }
    html+="</tr>";
  }
  html+="</tbody></table>"; el.innerHTML=html;
}
function renderRetrieval(){
  var data=DATA.retrieval||{}; var keys=Object.keys(data); var el=document.getElementById("retrieval-panel");
  if(!keys.length){el.innerHTML="<div class='sub'>Bu koşuda retrieval çalıştırılmadı — <code>--retrieval</code></div>";return;}
  var html="<table><thead><tr><th>Model</th><th>Doğruluk</th><th>Detay</th></tr></thead><tbody>";
  for(var k=0;k<keys.length;k++){
    var r=data[keys[k]];
    if(r.error){html+="<tr><td>"+esc(keys[k])+"</td><td class='no'>hata</td><td>"+esc(String(r.error).slice(0,80))+"</td></tr>";continue;}
    var det=[];
    for(var i=0;i<r.queries.length;i++){det.push(esc(String(r.queries[i].query).slice(0,40))+" -> "+(r.queries[i].pass?'<span class="ok">':'<span class="no">')+esc(r.queries[i].top||"?")+"</span>");}
    html+="<tr><td>"+esc(keys[k])+"</td><td>"+r.passed+"/"+r.total+"</td><td>"+det.join("; ")+"</td></tr>";
  }
  html+="</tbody></table>"; el.innerHTML=html;
}
function renderCommunity(){
  var el=document.getElementById("community-panel");
  var presets=DATA.community_presets||{}; var names=Object.keys(presets);
  var html="";
  for(var p=0;p<names.length;p++){
    var name=names[p], rows=presets[name]||[];
    var htmlRows="<tr><th>Yerel model</th><th>Yerel tok/s</th><th>Community tok/s</th><th>Fark (%)</th></tr>";
    var models=DATA.models||[],mm,found=0,i,j,m,s,best;
    for(i=0;i<models.length;i++){m=models[i];s=m.speed||{};if(!s.gen_tps)continue;
      var base=String(m.model).split(":")[0].toLowerCase().replace(/[\\s\\-_]/g,"").trim();
      var tag=String(m.model).split(":")[1]||"";var sizeM=tag.match(/(\\d+(?:\\.\\d+)?)b/i);var size=sizeM?sizeM[1]:"";
      best=null;
      for(j=0;j<rows.length;j++){var rr=rows[j]||{},rrm=rr.model||{};var nm=String(rrm.displayName||rrm.hfId||"").toLowerCase().replace(/[\\s\\-_]/g,"");
        if(nm.indexOf(base)>=0&&(!size||nm.indexOf(size)>=0)){if(!best||(rr.tokSOut||0)>(best.tokSOut||0))best=rr;}}
      if(best){var cv=best.tokSOut||0;var diff=cv?((s.gen_tps/cv-1)*100).toFixed(1)+"%":"-";
        htmlRows+="<tr><td>"+esc(m.model)+"</td><td>"+s.gen_tps.toFixed(1)+"</td><td>"+cv.toFixed(1)+"</td><td>"+diff+"</td></tr>";found++;}
    }
    html+="<h3>Community: "+esc(name)+"</h3><table>"+htmlRows+"</table>";
    if(!found)html+="<div class='sub'>Eşleşen model yok.</div>";
  }
  el.innerHTML=html||"<div class='sub'>llmfit verisi yok — community panosu atlandı.</div>";
}
function renderHistory(){
  var el=document.getElementById("history-panel");
  var hist=DATA.history||{}; var keys=Object.keys(hist);
  if(!keys.length){el.innerHTML="<div class='sub'>Parent benchmark_history.db yok — standalone mod.</div>";return;}
  var html="<table><thead><tr><th>Model</th><th>Ölçüm</th><th>Son tok/s</th><th>Trend</th></tr></thead><tbody>";
  for(var i=0;i<keys.length;i++){var h=hist[keys[i]];
    html+="<tr><td>"+esc(keys[i])+"</td><td>"+h.measurements+"</td><td>"+fmt(h.last_tps)+"</td><td>"+esc(h.trend)+"</td></tr>";}
  html+="</tbody></table>"; el.innerHTML=html;
}
function renderData(){document.getElementById("raw-data").textContent=JSON.stringify(DATA,null,2);}

document.getElementById("gen-date").textContent=DATA.generated_at||"-";
renderKpis();renderHardware();renderConditions();renderTaskTable();renderSummary();renderTaskPass();
renderQuants();renderContext();renderRetrieval();renderCommunity();renderHistory();renderCharts();renderImprovements();renderData();
</script>
</body>
</html>
"""


def generate_html(input_path: str | Path) -> Path:
    """results JSON'dan reports/index.html üretir ve yolunu döndürür."""
    inp = Path(input_path)
    run = json.loads(inp.read_text(encoding="utf-8"))
    llmfit = llmfit_data.resolve()
    run["llmfit_mode"] = llmfit.mode
    # B5: geçmiş/zaman serisi + community preset verisi sayfaya gömülür (offline)
    run["history"] = history.summarize_history(history.load_history())
    run["community_presets"] = llmfit.speed_presets(
        ["RTX 4070 Ti (12 GB)", "RTX 3060 (12 GB)"]
    )

    html = HTML_TEMPLATE.replace(
        "__DATA_JSON__", json.dumps(run, ensure_ascii=False)
    ).replace("__IMPROVEMENTS_JSON__", json.dumps(IMPROVEMENTS, ensure_ascii=False))
    out = config.REPORTS_DIR / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="JSON -> interaktif HTML rapor")
    p.add_argument("--input", required=True, help="Sonuç JSON")
    args = p.parse_args(argv or sys.argv[1:])
    path = generate_html(args.input)
    print(f"HTML rapor yazıldı: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
