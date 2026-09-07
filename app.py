"""
METNMAT BMS - single-file Flask telemetry server + dashboard for Render.
Visual design cloned from the ASTERIQUE BMS dashboard (navy control-room
theme, KPI strip, live tiles, trend chart).

Endpoints:
  POST /api/telemetry  <- pollers push here. Accepts BOTH schemas:
       {"sensor_id":"FRZ-01-T1","ts":...,"temp_c":-17.7,"raw":-177,"status":"ok"}
       {"device":"PLC001","temperature_C":-18.2,"status":"LIVE"}
  GET  /api/data       -> latest + history JSON
  GET  /               -> dashboard

Storage: SQLite (ephemeral on Render free tier - history resets on
redeploy/sleep; upgrade path is Render Postgres).
"""

import os
import time
import sqlite3
from flask import Flask, request, jsonify, Response, g

DB_PATH = os.environ.get("DB_PATH", "telemetry.db")
HISTORY_POINTS = 600
OFFLINE_AFTER_S = 60

# Per-sensor display config: label, location and alarm limits.
# Sensors not listed appear automatically with defaults.
SENSOR_CFG = {
    "FRZ-01-T1": {
        "name": "Freezer 1 - Air",
        "location": "Plant room A",
        "low": -25.0,
        "high": -15.0
    },

    "FRZ-02-T1": {
        "name": "Freezer 2 - Air",
        "location": "Plant room A",
        "low": -25.0,
        "high": -15.0
    },

    "PLC001": {
        "name": "Freezer 1 - Air",
        "location": "Plant room A",
        "low": -25.0,
        "high": -15.0
    },

    "PLC002": {
        "name": "Freezer 2 - Air",
        "location": "Plant room A",
        "low": -25.0,
        "high": -15.0
    },
}
DEFAULT_CFG = {"name": "Sensor", "location": "Site", "low": -25.0, "high": -15.0}

app = Flask(__name__)

# ------------------------------ database ------------------------------

def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.execute("""CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT NOT NULL,
            ts INTEGER NOT NULL,
            temp_c REAL,
            raw INTEGER,
            status TEXT NOT NULL DEFAULT 'ok')""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_sensor_ts
                      ON telemetry (sensor_id, ts)""")
        db.commit()
    return db

@app.teardown_appcontext
def close_db(_exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

# ------------------------------ API ------------------------------

@app.route("/api/telemetry", methods=["POST"])
def ingest():
    try:
        d = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400

    sensor_id = str(d.get("sensor_id") or d.get("device") or "UNKNOWN")
    ts = int(d.get("ts") or time.time())
    temp_c = d.get("temp_c", d.get("temperature_C"))
    temp_c = float(temp_c) if temp_c is not None else None
    raw = d.get("raw")
    raw = int(raw) if raw is not None else None
    status = str(d.get("status") or "ok").lower()
    if status == "live":
        status = "ok"
    if status not in ("ok", "sensor_fault", "comm_fault"):
        status = "ok"

    db = get_db()
    db.execute("INSERT INTO telemetry (sensor_id, ts, temp_c, raw, status) "
               "VALUES (?,?,?,?,?)", (sensor_id, ts, temp_c, raw, status))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/data")
def data():
    db = get_db()
    now = int(time.time())
    out = {}
    # Always expose all 10 configured freezers.
    # A freezer with no telemetry is shown as OFFLINE instead of disappearing.
    db_ids = [r[0] for r in db.execute("SELECT DISTINCT sensor_id FROM telemetry")]
    ids = list(SENSOR_CFG.keys()) + [sid for sid in db_ids if sid not in SENSOR_CFG]

    for sid in ids:
        rows = db.execute(
            "SELECT ts, temp_c, raw, status FROM telemetry "
            "WHERE sensor_id=? ORDER BY ts DESC LIMIT ?",
            (sid, HISTORY_POINTS)).fetchall()
        rows.reverse()
        last = rows[-1] if rows else None
        cfg = SENSOR_CFG.get(sid, DEFAULT_CFG)
        out[sid] = {
            "name": cfg["name"], "location": cfg["location"],
            "low": cfg["low"], "high": cfg["high"],
            "online": bool(last and (now - last[0]) <= OFFLINE_AFTER_S),
            "last": {"ts": last[0], "temp_c": last[1],
                     "raw": last[2], "status": last[3]} if last else None,
            "history": [{"ts": r[0], "temp_c": r[1], "status": r[3]}
                        for r in rows],
        }
    return jsonify({"now": now, "sensors": out})

# ------------------------------ dashboard ------------------------------

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>METNMAT · Temperature Monitoring BMS</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#0a0e18; --bg-grad:radial-gradient(1200px 620px at 78% -14%,#141d33 0%,#0a0e18 62%);
  --surface:#111726; --surface-2:#161d2f; --surface-3:#1f2739;
  --line:#1e2637; --line-strong:#2c3750;
  --ink:#f2f5fb; --ink-2:#a9b3c9; --ink-3:#6a7590;
  --accent:#5b9cf0; --accent-soft:rgba(91,156,240,.12);
  --gold:#e9bc57; --crit:#f2777a; --crit-soft:rgba(242,119,122,.12);
  --warn:#e5ab45; --warn-soft:rgba(229,171,69,.13);
  --ok:#3ecfa0; --ok-soft:rgba(62,207,160,.11);
  --r-sm:6px; --r-md:9px; --r-lg:12px; color-scheme:dark;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;
 background:var(--bg);color:var(--ink);font-size:12.5px;line-height:1.42;
 -webkit-font-smoothing:antialiased}
#app{display:flex;height:100vh;overflow:hidden}
aside{width:196px;min-width:196px;background:linear-gradient(180deg,var(--surface) 0%,#0f1522 100%);
 border-right:1px solid var(--line);display:flex;flex-direction:column}
.brand{padding:14px 12px 12px;border-bottom:1px solid var(--line)}
.brand h1{font-size:14px;letter-spacing:.5px;line-height:1.2}
.wordmark{font-family:Georgia,'Times New Roman',serif;font-weight:600;letter-spacing:.22em;
 background:linear-gradient(90deg,var(--gold) 0%,#f3d98b 45%,#a8c4e0 100%);
 -webkit-background-clip:text;background-clip:text;color:transparent}
.brand small{color:var(--ink-3);font-size:9.5px;display:block;margin-top:2px}
nav{flex:1;padding:8px 7px}
.navgroup{font-size:8.5px;font-weight:700;letter-spacing:.13em;color:var(--ink-3);
 padding:9px 8px 3px;text-transform:uppercase}
.navbtn{display:flex;align-items:center;gap:9px;width:100%;background:none;border:none;
 color:var(--ink-2);padding:6px 8px;text-align:left;font-size:12px;font-weight:500;
 border-radius:var(--r-sm);margin-bottom:1px}
.navbtn.active{background:var(--accent-soft);color:var(--accent);font-weight:600}
.userbox{border-top:1px solid var(--line);padding:10px 12px;font-size:11px;color:var(--ink-3)}
.userbox b{color:var(--ink);font-weight:600;font-size:12px;display:block}
main{flex:1;overflow-y:auto;padding:14px 18px;background:var(--bg-grad)}
.pagehead{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}
.pagehead h2{font-size:16px;font-weight:600}
.pagehead .sub{color:var(--ink-3);font-size:11px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
 padding:13px 15px;box-shadow:0 1px 2px rgba(0,0,0,.30);margin-bottom:14px}
.card h3{font-size:11px;color:var(--ink-2);font-weight:600;letter-spacing:.04em;
 text-transform:uppercase;margin-bottom:10px}
.kpistrip{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0;padding:0;overflow:hidden}
.kpi{position:relative;display:flex;align-items:center;gap:11px;padding:11px 13px;border-left:1px solid var(--line)}
.kpi:first-child{border-left:none}
.kpi::before{content:'';position:absolute;left:0;top:10px;bottom:10px;width:2px;border-radius:2px;background:var(--ink-3);opacity:.5}
.kpi.crit::before{background:var(--crit);opacity:1}.kpi.warn::before{background:var(--warn);opacity:1}.kpi.ok::before{background:var(--ok);opacity:.85}
.kico{width:30px;height:30px;flex:none;border-radius:8px;display:flex;align-items:center;justify-content:center;background:var(--surface-3);color:var(--ink-3);font-size:14px}
.kpi.crit .kico{background:var(--crit-soft);color:var(--crit)}.kpi.warn .kico{background:var(--warn-soft);color:var(--warn)}.kpi.ok .kico{background:var(--ok-soft);color:var(--ok)}
.kpi .v{font-size:21px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.08}
.kpi .l{font-size:10.3px;color:var(--ink-3);margin-top:1px;font-weight:500}
.kpi.crit .v{color:var(--crit)}.kpi.warn .v{color:var(--warn)}.kpi.ok .v{color:var(--ok)}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(178px,1fr));gap:10px}
.tile{background:linear-gradient(180deg,var(--surface-2) 0%,#131a2b 100%);
 border:1px solid var(--line);border-radius:var(--r-md);padding:10px 11px 11px;
 position:relative;cursor:pointer;overflow:hidden;transition:border-color .16s,transform .16s,box-shadow .16s}
.tile::after{content:'';position:absolute;left:0;right:0;bottom:0;height:2px;background:var(--ok);opacity:.5}
.tile.warnstate::after{background:var(--warn);opacity:.9}.tile.alarm::after{background:var(--crit);opacity:1}
.tile.failstate::after{background:var(--ink-3);opacity:.6}
.tile.alarm{border-color:#5b3040}.tile.selected{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),0 6px 18px rgba(91,156,240,.12)}
.tile:hover{border-color:var(--line-strong);transform:translateY(-1.5px);box-shadow:0 8px 20px rgba(0,0,0,.28)}
.tile .sid{font-size:9.3px;color:var(--ink-3);font-weight:500;letter-spacing:.04em;text-transform:uppercase}
.tile .nm{font-size:11.5px;font-weight:600;margin:1px 0 5px}
.tile .val{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.03em}
.tile .val small{font-size:11px;color:var(--ink-3);font-weight:500}.tile .lim{font-size:9.5px;color:var(--ink-3);margin-top:4px}
.dot{position:absolute;top:11px;right:11px;width:8px;height:8px;border-radius:50%}
.dot.ok{background:var(--ok);box-shadow:0 0 0 3px var(--ok-soft)}.dot.warn{background:var(--warn);box-shadow:0 0 0 3px var(--warn-soft)}
.dot.crit{background:var(--crit);box-shadow:0 0 0 3px var(--crit-soft);animation:blink 1s infinite}.dot.fail{background:var(--ink-3)}
@keyframes blink{50%{opacity:.3}}
.selectbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
.selectinfo{color:var(--ink-3);font-size:10.5px}
.actionbtn{border:1px solid var(--line-strong);background:var(--surface-3);color:var(--ink-2);
 border-radius:6px;padding:5px 9px;font-size:10px;cursor:pointer}
.actionbtn:hover{border-color:var(--accent);color:var(--accent)}
.graphgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:12px}
.graphcard{background:var(--surface-2);border:1px solid var(--line);border-radius:9px;padding:10px 11px}
.graphhead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}
.graphname{font-size:12px;font-weight:600}.graphmeta{color:var(--ink-3);font-size:9.5px}
.trendwrap{height:245px;position:relative}
.badge{display:inline-block;padding:1.5px 9px;border-radius:10px;font-size:9.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.badge.ok{background:var(--ok-soft);color:var(--ok)}.badge.off{background:var(--crit-soft);color:var(--crit)}.badge.fault{background:var(--warn-soft);color:var(--warn)}
.muted{color:var(--ink-3);font-size:10.5px}
.emptygraph{height:245px;display:flex;align-items:center;justify-content:center;color:var(--ink-3);font-size:11px;border:1px dashed var(--line-strong);border-radius:7px}
@media(max-width:900px){.graphgrid{grid-template-columns:1fr}}
@media(max-width:760px){aside{display:none}main{padding:10px}.graphgrid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div id="app">
<aside>
  <div class="brand"><h1><span class="wordmark">METNMAT</span></h1><small>Temperature Monitoring BMS</small></div>
  <nav>
    <div class="navgroup">Monitoring</div>
    <div class="navbtn active">▦&nbsp; Dashboard</div>
    <div class="navbtn">📈&nbsp; Trends</div>
    <div class="navgroup">System</div>
    <div class="navbtn">⚙&nbsp; Sensors</div>
  </nav>
  <div class="userbox"><b>Plant Gateway</b>Raspberry Pi · Modbus ASCII</div>
</aside>
<main>
  <div class="pagehead"><h2>Live status</h2><span class="sub" id="updated">connecting…</span></div>
  <div class="card kpistrip" id="kpis"></div>

  <div class="card">
    <div class="selectbar">
      <h3 style="margin:0">Freezer status</h3>
      <div>
        <span class="selectinfo" id="selectinfo">Select at least 2 freezers</span>
        <button class="actionbtn" onclick="selectOnline()">Select online</button>
      </div>
    </div>
    <div class="tiles" id="tiles"></div>
  </div>

  <div class="card">
    <div class="selectbar">
      <h3 style="margin:0">Temperature trends</h3>
      <span class="muted">One graph per selected freezer</span>
    </div>
    <div class="graphgrid" id="graphs"></div>
  </div>
</main>
</div>

<script>
let selected = new Set();
let charts = {};
let lastData = null;
let initialized = false;

const fmt = (v,d=1)=> v==null ? '—' : (+v).toFixed(d);
const fmtAge = s => s<60 ? Math.max(0,Math.floor(s))+'s' :
                    s<3600 ? Math.floor(s/60)+'m' : Math.floor(s/3600)+'h';

function sensorState(s){
  if(!s.online) return 'fail';
  if(!s.last) return 'fail';
  if(s.last.status==='sensor_fault'||s.last.status==='comm_fault') return 'crit';
  const v=s.last.temp_c;
  if(v==null) return 'fail';
  if(v>s.high || v<s.low) return 'crit';
  const m=(s.high-s.low)*0.1;
  if(v>s.high-m || v<s.low+m) return 'warn';
  return 'ok';
}

function kpiHTML(icon,tone,value,label){
  return `<div class="kpi ${tone}"><span class="kico">${icon}</span>
    <span><div class="v">${value}</div><div class="l">${label}</div></span></div>`;
}

function tileHTML(sid,s){
  const st=sensorState(s);
  const cls=st==='crit'?'alarm':st==='warn'?'warnstate':st==='fail'?'failstate':'';
  const v=s.last && s.last.status==='ok' ? `${fmt(s.last.temp_c)}<small> °C</small>` :
          s.last && s.last.status==='sensor_fault' ? 'FAULT' :
          s.last && s.last.status==='comm_fault' ? 'NO COMMS' : '—';
  const onlineText=s.online ? 'ONLINE' : 'NOT CONNECTED';
  return `<div class="tile ${cls} ${selected.has(sid)?'selected':''}" data-sid="${sid}" title="${onlineText}">
    <span class="dot ${st==='fail'?'fail':st}"></span>
    <div class="sid">${sid} · ${s.location}</div>
    <div class="nm">${s.name}</div>
    <div class="val">${v}</div>
    <div class="lim">${onlineText} · Limits ${fmt(s.low)} … ${fmt(s.high)} °C</div>
  </div>`;
}

function makeGraphCard(sid,s){
  return `<div class="graphcard" id="graphcard-${sid}">
    <div class="graphhead">
      <div><div class="graphname">${s.name} · ${sid}</div>
      <div class="graphmeta">${s.last ? 'last '+fmtAge(lastData.now-s.last.ts)+' ago' : 'No telemetry received'}</div></div>
      <span class="badge ${s.online?'ok':'off'}">${s.online?'ONLINE':'OFFLINE'}</span>
    </div>
    <div class="trendwrap"><canvas id="chart-${sid}"></canvas>
      ${!s.history.some(h=>h.temp_c!=null) ? '<div class="emptygraph">No temperature data yet</div>' : ''}</div>
  </div>`;
}

function drawChart(sid){
  const s=lastData.sensors[sid];
  if(!s) return;
  const card=document.getElementById('graphcard-'+sid);
  if(!card) return;
  const pts=s.history.filter(h=>h.temp_c!=null);
  if(!pts.length) return;
  const labels=pts.map(h=>{
    const d=new Date(h.ts*1000);
    return d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0')+':'+d.getSeconds().toString().padStart(2,'0');
  });
  const vals=pts.map(h=>h.temp_c);

  if(charts[sid]){
    charts[sid].data.labels=labels;
    charts[sid].data.datasets[0].data=vals;
    charts[sid].options.scales.y.suggestedMin=s.low;
    charts[sid].options.scales.y.suggestedMax=s.high;
    charts[sid].update('none');
    return;
  }

  const canvas=document.getElementById('chart-'+sid);
  if(!canvas) return;
  charts[sid]=new Chart(canvas,{
    type:'line',
    data:{labels,datasets:[{label:s.name,data:vals,borderColor:'#5b9cf0',borderWidth:2,
      pointRadius:0,tension:.3,fill:{target:'origin',above:'rgba(91,156,240,.05)'}}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        x:{ticks:{color:'#6a7590',maxTicksLimit:8},grid:{color:'#1e2637'}},
        y:{ticks:{color:'#6a7590'},grid:{color:'#1e2637'},
           suggestedMin:s.low,suggestedMax:s.high}
      }
    }
  });
}

function renderGraphs(){
  const ids=[...selected].filter(id=>lastData.sensors[id]);
  const graphs=document.getElementById('graphs');

  // Keep chart objects only for selected sensors.
  Object.keys(charts).forEach(id=>{
    if(!selected.has(id)){
      charts[id].destroy();
      delete charts[id];
    }
  });

  graphs.innerHTML=ids.map(id=>makeGraphCard(id,lastData.sensors[id])).join('') ||
    '<span class="muted">Select at least 2 freezers to display their graphs.</span>';

  ids.forEach(drawChart);
  document.getElementById('selectinfo').textContent =
    `${ids.length} selected · ${ids.length < 2 ? 'select at least 2' : 'graphs shown'}`;
}

function toggleSensor(sid){
  if(selected.has(sid)){
    if(selected.size<=2){
      // Keep minimum two selected.
      return;
    }
    selected.delete(sid);
  }else{
    selected.add(sid);
  }
  renderTiles();
  renderGraphs();
}

function renderTiles(){
  const ids=Object.keys(lastData.sensors);
  document.getElementById('tiles').innerHTML=ids.map(id=>tileHTML(id,lastData.sensors[id])).join('');
  document.querySelectorAll('.tile').forEach(t=>{
    t.onclick=()=>toggleSensor(t.dataset.sid);
  });
}

function selectOnline(){
  const ids=Object.keys(lastData.sensors);
  const online=ids.filter(id=>lastData.sensors[id].online);
  const chosen=online.length>=2 ? online.slice(0,10) : ids.slice(0,2);
  selected=new Set(chosen);
  renderTiles();
  renderGraphs();
}

async function poll(){
  try{
    const r=await fetch('/api/data');
    lastData=await r.json();
    const ids=Object.keys(lastData.sensors);

    if(!initialized){
      // Start with the first two freezers, preferring online units.
      const online=ids.filter(id=>lastData.sensors[id].online);
      const initial=online.length>=2 ? online.slice(0,2) : ids.slice(0,2);
      selected=new Set(initial);
      initialized=true;
    }else{
      // Preserve user selection. If a selected freezer goes offline, keep its graph.
      selected=new Set([...selected].filter(id=>lastData.sensors[id]));
      if(selected.size<2){
        ids.slice(0,2).forEach(id=>selected.add(id));
      }
    }

    let crit=0,warn=0,comm=0;
    ids.forEach(id=>{
      const st=sensorState(lastData.sensors[id]);
      if(st==='crit')crit++;
      if(st==='warn')warn++;
      if(!lastData.sensors[id].online)comm++;
    });

    document.getElementById('kpis').innerHTML =
      kpiHTML('🔔',crit?'crit':'ok',crit,'Active alarms')+
      kpiHTML('⚡',warn?'warn':'ok',warn,'Warning states')+
      kpiHTML('🖧',comm?'crit':'ok',(ids.length-comm)+'/'+ids.length,'Sensors communicating')+
      kpiHTML('🗄','ok',ids.length,'Monitored units');

    renderTiles();
    renderGraphs();
    document.getElementById('updated').textContent='updated '+new Date().toLocaleTimeString();
  }catch(e){
    console.log(e);
    document.getElementById('updated').textContent='connection error';
  }
  setTimeout(poll,1000);
}
poll();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
