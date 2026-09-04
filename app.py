"""
METNMAT Freezer Monitoring - single-file Flask app for Render.

Endpoints:
  POST /api/telemetry   <- pollers push JSON here
        {"sensor_id": "FRZ-01-T1", "ts": 1756900000,
         "temp_c": -17.7, "raw": -177, "status": "ok"}
        status: "ok" | "sensor_fault" | "comm_fault" | "LIVE" (treated as ok)
  GET  /api/data        -> latest reading + recent history per sensor (JSON)
  GET  /                -> live dashboard page

Storage: SQLite file. NOTE: on Render free tier the filesystem is
ephemeral - history resets on redeploy/restart. Fine for a trial;
move to Render Postgres for permanence.
"""

import os
import json
import time
import sqlite3
from flask import Flask, request, jsonify, Response, g

DB_PATH = os.environ.get("DB_PATH", "telemetry.db")
HISTORY_POINTS = 500          # points per sensor returned to the chart
OFFLINE_AFTER_S = 60          # no data for this long => sensor shown OFFLINE

app = Flask(__name__)

# ---------------- database ----------------

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

# ---------------- API ----------------

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
    sensors = {}
    ids = [r[0] for r in db.execute(
        "SELECT DISTINCT sensor_id FROM telemetry")]
    for sid in ids:
        rows = db.execute(
            "SELECT ts, temp_c, raw, status FROM telemetry "
            "WHERE sensor_id=? ORDER BY ts DESC LIMIT ?",
            (sid, HISTORY_POINTS)).fetchall()
        rows.reverse()
        last = rows[-1] if rows else None
        online = bool(last and (now - last[0]) <= OFFLINE_AFTER_S)
        sensors[sid] = {
            "online": online,
            "last": {"ts": last[0], "temp_c": last[1],
                     "raw": last[2], "status": last[3]} if last else None,
            "history": [{"ts": r[0], "temp_c": r[1], "status": r[3]}
                        for r in rows],
        }
    return jsonify({"now": now, "sensors": sensors})

# ---------------- dashboard ----------------

PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>METNMAT Freezer Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body{font-family:system-ui,sans-serif;background:#141414;color:#eee;
       margin:0;padding:20px}
  h1{color:#C41F1E;font-size:1.3em;margin:0 0 4px}
  .sub{color:#888;font-size:.85em;margin-bottom:18px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));
        gap:16px}
  .card{background:#212121;border-radius:12px;padding:18px;
        border-top:4px solid #C41F1E}
  .sid{font-size:.95em;color:#aaa}
  .temp{font-size:2.4em;font-weight:600;margin:6px 0}
  .badge{display:inline-block;padding:2px 10px;border-radius:10px;
         font-size:.8em;font-weight:600}
  .ok{background:#123f1f;color:#5fdc82}
  .off{background:#3f1212;color:#ff7b7b}
  .fault{background:#3f2f12;color:#ffc95f}
  .meta{color:#777;font-size:.8em;margin-top:6px}
  canvas{margin-top:12px;max-height:220px}
</style>
</head>
<body>
<h1>METNMAT Freezer Monitor</h1>
<div class="sub">Live PLC telemetry &mdash; auto-refreshes every 5 s</div>
<div class="grid" id="grid"></div>
<script>
const charts = {};
function fmtAge(s){ if(s<60) return s+"s"; if(s<3600) return Math.floor(s/60)+"m";
                    return Math.floor(s/3600)+"h"; }
async function poll(){
  try{
    const r = await fetch('/api/data'); const j = await r.json();
    const grid = document.getElementById('grid');
    for(const [sid, s] of Object.entries(j.sensors)){
      let card = document.getElementById('card-'+sid);
      if(!card){
        card = document.createElement('div');
        card.className='card'; card.id='card-'+sid;
        card.innerHTML =
          `<div class="sid">${sid}</div>
           <div class="temp" id="t-${sid}">--</div>
           <span class="badge" id="b-${sid}"></span>
           <div class="meta" id="m-${sid}"></div>
           <canvas id="c-${sid}"></canvas>`;
        grid.appendChild(card);
        charts[sid] = new Chart(document.getElementById('c-'+sid), {
          type:'line',
          data:{labels:[],datasets:[{data:[],borderColor:'#C41F1E',
                borderWidth:2,pointRadius:0,tension:.25}]},
          options:{plugins:{legend:{display:false}},
            scales:{x:{ticks:{color:'#666',maxTicksLimit:6},grid:{color:'#2a2a2a'}},
                    y:{ticks:{color:'#666'},grid:{color:'#2a2a2a'}}}}
        });
      }
      const t = document.getElementById('t-'+sid),
            b = document.getElementById('b-'+sid),
            m = document.getElementById('m-'+sid);
      const last = s.last;
      if(last && last.temp_c !== null && last.status === 'ok'){
        t.textContent = last.temp_c.toFixed(1) + ' \u00B0C';
      } else if(last && last.status === 'sensor_fault'){
        t.textContent = 'SENSOR FAULT';
      } else if(last && last.status === 'comm_fault'){
        t.textContent = 'NO COMMS';
      }
      if(!s.online){ b.textContent='OFFLINE'; b.className='badge off'; }
      else if(last.status==='ok'){ b.textContent='ONLINE'; b.className='badge ok'; }
      else { b.textContent=last.status.replace('_',' ').toUpperCase();
             b.className='badge fault'; }
      if(last) m.textContent = 'last update ' + fmtAge(j.now-last.ts) +
                               ' ago' + (last.raw!==null? '  |  raw '+last.raw:'');
      const ch = charts[sid];
      const pts = s.history.filter(h=>h.temp_c!==null);
      ch.data.labels = pts.map(h=>{
        const d = new Date(h.ts*1000);
        return d.getHours().toString().padStart(2,'0')+':'+
               d.getMinutes().toString().padStart(2,'0');});
      ch.data.datasets[0].data = pts.map(h=>h.temp_c);
      ch.update('none');
    }
  }catch(e){ console.log(e); }
  setTimeout(poll, 5000);
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
