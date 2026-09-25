"""Dashboard HTML — visualización de datos históricos Centinela Vial."""
from http.server import BaseHTTPRequestHandler

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Centinela Vial — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}
  header{background:#1a1f2e;border-bottom:1px solid #2d3748;padding:16px 24px;display:flex;align-items:center;gap:12px}
  header h1{font-size:1.25rem;font-weight:700;color:#f97316}
  header span{color:#94a3b8;font-size:.875rem}
  .badge{background:#f97316;color:#fff;font-size:.7rem;padding:2px 8px;border-radius:99px;font-weight:600}
  main{padding:24px;max-width:1400px;margin:0 auto}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px}
  .card{background:#1e2130;border:1px solid #2d3748;border-radius:12px;padding:20px}
  .card .num{font-size:2rem;font-weight:700;color:#f97316;line-height:1}
  .card .lbl{font-size:.8rem;color:#94a3b8;margin-top:6px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
  .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px}
  .panel{background:#1e2130;border:1px solid #2d3748;border-radius:12px;padding:20px}
  .panel h2{font-size:.9rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:16px}
  #map{height:340px;border-radius:8px}
  table{width:100%;border-collapse:collapse;font-size:.8rem}
  th{text-align:left;padding:8px 12px;color:#64748b;border-bottom:1px solid #2d3748;font-weight:500}
  td{padding:8px 12px;border-bottom:1px solid #1a1f2e;color:#cbd5e1}
  tr:hover td{background:#252a3a}
  .tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.7rem;font-weight:600}
  .tag-cierre{background:#7f1d1d;color:#fca5a5}
  .tag-accidente{background:#78350f;color:#fde68a}
  .tag-peligro{background:#1e3a5f;color:#93c5fd}
  .tag-flujo{background:#134e4a;color:#6ee7b7}
  .spin{display:inline-block;width:18px;height:18px;border:2px solid #f97316;border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  .loading{display:flex;align-items:center;gap:8px;color:#64748b;font-size:.85rem}
  #last-update{font-size:.75rem;color:#475569;margin-top:4px}
  @media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <span style="font-size:1.5rem">🛣</span>
  <div>
    <h1>Centinela Vial <span class="badge">TESIS</span></h1>
    <div id="last-update">Cargando datos...</div>
  </div>
  <button onclick="loadData()" style="margin-left:auto;background:#f97316;border:none;color:#fff;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:.85rem">↻ Actualizar</button>
</header>

<main>
  <!-- Tarjetas resumen -->
  <div class="cards" id="cards">
    <div class="card"><div class="loading"><span class="spin"></span> Cargando...</div></div>
  </div>

  <!-- Fila 1: tipo + hora -->
  <div class="grid2">
    <div class="panel">
      <h2>Incidentes por tipo</h2>
      <canvas id="chartTipo" height="220"></canvas>
    </div>
    <div class="panel">
      <h2>Distribución por hora del día</h2>
      <canvas id="chartHora" height="220"></canvas>
    </div>
  </div>

  <!-- Fila 2: carretera + día semana + flujo -->
  <div class="grid3">
    <div class="panel">
      <h2>Top carreteras</h2>
      <canvas id="chartCarretera" height="260"></canvas>
    </div>
    <div class="panel">
      <h2>Incidentes por día</h2>
      <canvas id="chartDow" height="260"></canvas>
    </div>
    <div class="panel">
      <h2>Flujo vial — ciudades más lentas</h2>
      <canvas id="chartFlujo" height="260"></canvas>
    </div>
  </div>

  <!-- Mapa -->
  <div class="panel" style="margin-bottom:16px">
    <h2>Mapa de incidentes</h2>
    <div id="map"></div>
  </div>

  <!-- Tabla recientes -->
  <div class="panel">
    <h2>Últimos incidentes registrados</h2>
    <div style="overflow-x:auto">
      <table id="tablaRecientes">
        <thead><tr><th>Tipo</th><th>Carretera</th><th>Tramo</th><th>Descripción</th><th>Hora</th><th>Fecha</th></tr></thead>
        <tbody><tr><td colspan="6"><div class="loading"><span class="spin"></span> Cargando...</div></td></tr></tbody>
      </table>
    </div>
  </div>
</main>

<script>
const COLORS = {
  orange: '#f97316', blue: '#3b82f6', green: '#10b981',
  red: '#ef4444', purple: '#8b5cf6', yellow: '#eab308',
  teal: '#14b8a6', pink: '#ec4899',
};
const CHART_DEFAULTS = {
  plugins:{legend:{display:false}},
  scales:{x:{ticks:{color:'#64748b'},grid:{color:'#1e2130'}},
          y:{ticks:{color:'#64748b'},grid:{color:'#2d3748'}}},
};
let charts = {};
let map;

function destroyChart(id){if(charts[id]){charts[id].destroy();delete charts[id];}}

function tagTipo(tipo){
  if(!tipo)return'<span class="tag" style="background:#1e293b;color:#94a3b8">—</span>';
  if(tipo.includes('cerrada'))return`<span class="tag tag-cierre">${tipo}</span>`;
  if(tipo.includes('Accidente'))return`<span class="tag tag-accidente">${tipo}</span>`;
  if(tipo.includes('peligro')||tipo.includes('Condición'))return`<span class="tag tag-peligro">${tipo}</span>`;
  return`<span class="tag tag-flujo">${tipo}</span>`;
}

async function loadData(){
  document.getElementById('last-update').textContent='Actualizando...';
  try{
    const res = await fetch('/api/stats');
    const d   = await res.json();
    if(d.error)throw new Error(d.error);
    renderCards(d.resumen, d.por_tipo, d.flujo_resumen);
    renderTipo(d.por_tipo);
    renderHora(d.por_hora);
    renderCarretera(d.por_carretera);
    renderDow(d.por_dow);
    renderFlujo(d.flujo_resumen);
    renderMapa(d.mapa);
    renderTabla(d.recientes);
    document.getElementById('last-update').textContent=
      'Última actualización: '+new Date().toLocaleTimeString('es-MX');
  }catch(e){
    document.getElementById('last-update').textContent='Error: '+e.message;
  }
}

function renderCards(res, tipos, flujo){
  const lento = flujo.filter(f=>f.ratio<0.65).length;
  document.getElementById('cards').innerHTML=`
    <div class="card"><div class="num">${(res.total_incidentes||0).toLocaleString()}</div><div class="lbl">Total incidentes</div></div>
    <div class="card"><div class="num">${tipos.length}</div><div class="lbl">Tipos distintos</div></div>
    <div class="card"><div class="num">${lento}</div><div class="lbl">Ciudades con flujo lento</div></div>
    <div class="card"><div class="num">55</div><div class="lbl">Ciudades monitoreadas</div></div>
    <div class="card"><div class="num">3x</div><div class="lbl">Harvests por día</div></div>
    <div class="card"><div class="num">${res.primer_dia||'—'}</div><div class="lbl">Primer registro</div></div>
  `;
}

function renderTipo(datos){
  destroyChart('tipo');
  const ctx = document.getElementById('chartTipo').getContext('2d');
  charts.tipo = new Chart(ctx,{
    type:'bar',
    data:{
      labels: datos.map(d=>d.tipo),
      datasets:[{data:datos.map(d=>d.total),
        backgroundColor:[COLORS.orange,COLORS.red,COLORS.yellow,COLORS.purple,
          COLORS.blue,COLORS.green,COLORS.teal,COLORS.pink,'#6b7280','#a78bfa'],
        borderRadius:4}]
    },
    options:{...CHART_DEFAULTS,indexAxis:'y',
      scales:{x:{...CHART_DEFAULTS.scales.x},y:{...CHART_DEFAULTS.scales.y,ticks:{color:'#94a3b8',font:{size:11}}}}}
  });
}

function renderHora(datos){
  destroyChart('hora');
  const ctx = document.getElementById('chartHora').getContext('2d');
  charts.hora = new Chart(ctx,{
    type:'line',
    data:{
      labels: datos.map(d=>d.hora+'h'),
      datasets:[{data:datos.map(d=>d.total),
        borderColor:COLORS.blue,backgroundColor:'rgba(59,130,246,.15)',
        fill:true,tension:.4,pointRadius:3,pointBackgroundColor:COLORS.blue}]
    },
    options:{...CHART_DEFAULTS}
  });
}

function renderCarretera(datos){
  destroyChart('carr');
  const ctx = document.getElementById('chartCarretera').getContext('2d');
  charts.carr = new Chart(ctx,{
    type:'bar',
    data:{
      labels: datos.map(d=>d.carretera),
      datasets:[{data:datos.map(d=>d.total),
        backgroundColor:COLORS.green,borderRadius:4}]
    },
    options:{...CHART_DEFAULTS,indexAxis:'y'}
  });
}

function renderDow(datos){
  destroyChart('dow');
  const ctx = document.getElementById('chartDow').getContext('2d');
  charts.dow = new Chart(ctx,{
    type:'bar',
    data:{
      labels: datos.map(d=>d.dia),
      datasets:[{data:datos.map(d=>d.total),
        backgroundColor:COLORS.purple,borderRadius:4}]
    },
    options:{...CHART_DEFAULTS}
  });
}

function renderFlujo(datos){
  destroyChart('flujo');
  const ctx = document.getElementById('chartFlujo').getContext('2d');
  const colors = datos.map(d=>d.ratio<0.40?COLORS.red:d.ratio<0.65?COLORS.yellow:COLORS.green);
  charts.flujo = new Chart(ctx,{
    type:'bar',
    data:{
      labels: datos.map(d=>d.ciudad.replace('_',' ')),
      datasets:[{data:datos.map(d=>Math.round(d.ratio*100)),
        backgroundColor:colors,borderRadius:4}]
    },
    options:{...CHART_DEFAULTS,indexAxis:'y',
      scales:{...CHART_DEFAULTS.scales,
        x:{...CHART_DEFAULTS.scales.x,max:100,
           ticks:{...CHART_DEFAULTS.scales.x.ticks,callback:v=>v+'%'}}}}
  });
}

function renderMapa(puntos){
  if(!map){
    map = L.map('map').setView([23.0,-102.0],5);
    L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
      {attribution:'© Stadia Maps © OpenMapTiles © OpenStreetMap',maxZoom:18}).addTo(map);
  }
  map.eachLayer(l=>{if(l instanceof L.CircleMarker)map.removeLayer(l);});
  const typeColor={'Carretera cerrada':'#ef4444','Accidente':'#f97316',
    'Condiciones peligrosas':'#eab308','Inundación':'#3b82f6'};
  puntos.forEach(p=>{
    if(!p.coords_lat||!p.coords_lon)return;
    const color=typeColor[p.tipo]||'#8b5cf6';
    L.circleMarker([p.coords_lat,p.coords_lon],
      {radius:6,fillColor:color,color:'#fff',weight:1,fillOpacity:.85})
      .bindPopup(`<b>${p.tipo||'Incidente'}</b><br>${p.carretera||''}<br><small>${p.descripcion||''}</small>`)
      .addTo(map);
  });
}

function renderTabla(datos){
  const tbody=document.querySelector('#tablaRecientes tbody');
  if(!datos||!datos.length){tbody.innerHTML='<tr><td colspan="6" style="color:#64748b">Sin datos</td></tr>';return;}
  tbody.innerHTML=datos.map(r=>`
    <tr>
      <td>${tagTipo(r.tipo)}</td>
      <td style="color:#f97316;font-weight:600">${r.carretera||'—'}</td>
      <td style="color:#94a3b8">${r.origen&&r.destino?r.origen+'→'+r.destino:'—'}</td>
      <td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.descripcion||'—'}</td>
      <td>${r.hora_del_dia!=null?r.hora_del_dia+'h':'—'}</td>
      <td style="color:#64748b">${r.fecha||'—'}</td>
    </tr>`).join('');
}

loadData();
</script>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
