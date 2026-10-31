/* Graphiques Trailpace : thème commun + une fonction par graphique. Expose window.Charts. */
(function () {
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const FONT = 'system-ui,"Segoe UI",Roboto,sans-serif';
  const CFG = { displayModeBar: false, responsive: true };
  const C = { green: '#12b76a', amber: '#f79009', red: '#d92d20', blue: '#2e90fa', navy: '#1849a9' };
  const fr = (x, n = 0) => x == null ? '–' : Number(x).toLocaleString('fr-FR', { minimumFractionDigits: n, maximumFractionDigits: n });
  const hm = h => { const m = Math.round(h * 60); return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}`; };
  const pace = v => { const m = Math.floor(v), s = Math.round((v - m) * 60); return s === 60 ? `${m + 1}'00` : `${m}'${String(s).padStart(2, '0')}`; };
  const theme = () => ({ ink: css('--ink'), mute: css('--mute'), line: css('--line'), acc: css('--acc'), card: css('--card'), warn: css('--warn') });

  function layout(extra) {
    const t = theme();
    return Object.assign({
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', separators: ', ',
      font: { family: FONT, size: 12, color: t.ink }, hovermode: 'closest',
      hoverlabel: { bgcolor: t.card, bordercolor: t.line, font: { family: FONT, size: 12, color: t.ink } },
      margin: { l: 58, r: 24, t: 28, b: 48 }, showlegend: false,
    }, extra);
  }
  function axis(extra = {}) {
    const t = theme();
    const o = Object.assign({
      gridcolor: t.line, gridwidth: 1, zeroline: false, showline: false, ticks: 'outside', ticklen: 4,
      tickcolor: t.line, tickfont: { size: 11, color: t.mute }, automargin: true,
    }, extra);
    if (typeof extra.title === 'string') o.title = { text: extra.title, font: { size: 12, color: t.mute }, standoff: 8 };
    return o;
  }
  const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
  const lerp = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const rgb = c => `rgb(${c.join(',')})`;
  const Q = 12;

  const slopeCol = g => {
    const a = Math.abs(g);
    if (a < 2) return 'rgb(18,183,106)';
    const t = Math.round(Math.min((a - 2) / 18, 1) * Q) / Q;
    return g > 0 ? rgb(lerp(hex('#fedf89'), hex('#b42318'), t)) : rgb(lerp(hex('#b2ddff'), hex('#1849a9'), t));
  };
  const techCol = f => {
    const t = Math.round(Math.min(Math.max((f - 1) / 0.5, 0), 1) * Q) / Q;
    return t < 0.5 ? rgb(lerp(hex('#12b76a'), hex('#fdb022'), t * 2)) : rgb(lerp(hex('#fdb022'), hex('#b42318'), (t - 0.5) * 2));
  };

  /* ---------- 1. Profil altimétrique coloré (pente ou technicité) ---------- */
  function profile(c) {
    const p = c.profile, t = theme();
    const aids = c.aid_stations;
    const emin = Math.min(...p.ele), emax = Math.max(...p.ele);
    const bounds = [0, ...aids.map(a => a.km), c.total_km];
    const shapes = [], annotations = [];
    bounds.slice(0, -1).forEach((x0, i) => {
      if (i % 2 === 0) shapes.push({ type: 'rect', xref: 'x', yref: 'paper', x0, x1: bounds[i + 1], y0: 0, y1: 1, fillcolor: rgba('#667085', 0.06), line: { width: 0 }, layer: 'below' });
    });
    aids.forEach((a, i) => {
      shapes.push({ type: 'line', xref: 'x', yref: 'paper', x0: a.km, x1: a.km, y0: 0, y1: 1, line: { color: t.acc, width: 1, dash: 'dot' } });
      annotations.push({ x: a.km, y: 1, yref: 'paper', text: `<b>R${i + 1}</b>`, showarrow: false, yanchor: 'bottom', font: { size: 11, color: t.acc } });
    });
    annotations.push({ x: p.km[p.ele.indexOf(emax)], y: emax, text: `${emax} m`, showarrow: true, arrowhead: 0, arrowcolor: t.mute, ax: 0, ay: -24, font: { size: 11, color: t.mute } });
    const hover = p.km.map((k, i) => `<b>km ${fr(k, 1)}</b><br>${p.ele[i]} m · pente ${fr(p.grade[i], 1)} %` + (p.tech ? `<br>technicité ×${fr(p.tech[i], 2)}` : ''));
    function draw(mode) {
      const colf = mode === 'tech' ? (i => techCol(p.tech[i])) : (i => slopeCol(p.grade[i]));
      const tr = [{ x: p.km, y: p.ele, type: 'scatter', mode: 'lines', fill: 'tozeroy', line: { width: 0 }, fillcolor: rgba('#667085', 0.10), text: hover, hoverinfo: 'text', showlegend: false }];
      let start = 0, cur = colf(1);
      const flush = end => tr.push({ x: p.km.slice(start, end + 1), y: p.ele.slice(start, end + 1), type: 'scatter', mode: 'lines', line: { color: cur, width: 4, shape: 'spline', smoothing: 0.4 }, hoverinfo: 'skip', showlegend: false });
      for (let i = 2; i < p.km.length; i++) { const col = colf(i); if (col !== cur) { flush(i - 1); start = i - 1; cur = col; } }
      flush(p.km.length - 1);
      tr.push({ x: aids.map(a => a.km), y: aids.map(a => a.alt), type: 'scatter', mode: 'markers', marker: { size: 10, color: t.card, line: { color: t.acc, width: 2 } },
        text: aids.map((a, i) => `<b>R${i + 1} · ${a.name}</b><br>km ${fr(a.km, 1)} · ${a.alt} m${a.cutoff ? '<br>barrière ' + a.cutoff : ''}`), hoverinfo: 'text', showlegend: false });
      Plotly.react('prof', tr, layout({ shapes, annotations, margin: { l: 58, r: 24, t: 36, b: 48 },
        xaxis: axis({ title: 'distance (km)', range: [0, c.total_km], showgrid: false, dtick: 10 }),
        yaxis: axis({ title: 'altitude (m)', range: [Math.max(0, emin - 60), emax + 70] }) }), CFG);
      const grad = (f, n = 8) => Array.from({ length: n }, (_, i) => f(i / (n - 1))).join(',');
      document.querySelector('#legend').innerHTML = mode === 'tech'
        ? `<span>×1,0 roulant</span><i style="background:linear-gradient(90deg,${grad(x => techCol(1 + x * 0.5))})"></i><span>×1,5 très technique</span>`
        : `<span>descente raide</span><i style="background:linear-gradient(90deg,${grad(x => slopeCol(-20 + x * 18), 5)},${slopeCol(0)},${grad(x => slopeCol(2 + x * 18), 5)})"></i><span>montée raide</span>`;
    }
    document.querySelectorAll('input[name=pm]').forEach(r => {
      if (r.value === 'tech' && !p.tech) { r.disabled = true; r.parentElement.title = 'Technicité OSM indisponible'; }
      r.onchange = () => draw(r.value);
    });
    draw('slope');
  }

  /* ---------- 2. Répartition de la distance par pente ---------- */
  const CLS = ['Descente raide<br>< −15 %', 'Descente<br>−15 à −8 %', 'Descente douce<br>−8 à −3 %', 'Roulant<br>±3 %', 'Montée douce<br>3 à 8 %', 'Montée<br>8 à 15 %', 'Montée raide<br>> 15 %'];
  const CLSCOL = ['#1849a9', '#2e90fa', '#84caff', '#12b76a', '#fdb022', '#f04438', '#b42318'];
  function classes(c) {
    const v = Object.values(c.dist_by_class), tot = v.reduce((a, b) => a + b, 0), t = theme();
    Plotly.react('cls', [{ x: CLS, y: v, type: 'bar', marker: { color: CLSCOL, line: { width: 0 } }, width: 0.62,
      text: v.map(x => `<b>${fr(x, 1)} km</b><br>${fr(100 * x / tot)} %`), textposition: 'outside', cliponaxis: false,
      textfont: { size: 11, color: t.ink }, hovertemplate: '%{x}<br>%{y:.1f} km<extra></extra>' }],
      layout({ margin: { l: 52, r: 16, t: 40, b: 56 }, bargap: 0.3,
        xaxis: axis({ showgrid: false, ticks: '', tickfont: { size: 11, color: t.mute } }),
        yaxis: axis({ title: 'km', range: [0, Math.max(...v) * 1.25] }) }), CFG);
  }

  /* ---------- 3. Vitesse par pente : observé vs attendu (Minetti) ---------- */
  function slopeSpeed(f) {
    const SL = ['Descente raide<br>< −15 %', 'Descente<br>−15 à −8 %', 'Descente douce<br>−8 à −3 %', 'Roulant<br>±3 %', 'Montée douce<br>3 à 8 %', 'Montée<br>8 à 15 %', 'Montée raide<br>15 à 25 %', 'Très raide<br>> 25 %'];
    const rows = f.grade_profile.map((r, i) => ({ ...r, lab: SL[i] || r.label })).filter(r => r.speed_kmh != null);
    const t = theme();
    Plotly.react('sl', [
      { x: rows.map(r => r.lab), y: rows.map(r => r.expected_kmh), type: 'bar', name: 'Attendu (Minetti)', marker: { color: rgba('#667085', 0.25), line: { color: t.mute, width: 1 } },
        hovertemplate: 'Attendu : %{y:.1f} km/h<extra></extra>' },
      { x: rows.map(r => r.lab), y: rows.map(r => r.speed_kmh), type: 'bar', name: 'Observé', marker: { color: rows.map(r => r.index_rel > 1.05 ? t.acc : r.index_rel < 0.9 ? t.warn : '#667085') },
        text: rows.map(r => `<b>${fr(r.index_rel, 2)}</b>`), textposition: 'outside', cliponaxis: false, textfont: { size: 12, color: t.ink },
        hovertemplate: 'Observé : %{y:.1f} km/h<br>indice relatif %{text}<extra></extra>' },
    ], layout({ barmode: 'group', bargap: 0.28, showlegend: true, legend: { orientation: 'h', y: 1.18, x: 0, font: { color: t.mute } }, margin: { l: 52, r: 16, t: 40, b: 56 },
      xaxis: axis({ showgrid: false, ticks: '' }), yaxis: axis({ title: 'km/h', range: [0, Math.max(...rows.map(r => Math.max(r.expected_kmh, r.speed_kmh))) * 1.2] }) }), CFG);
  }

  /* ---------- 4. Courbes de record + modèle CS/CP + FC ---------- */
  function recordChart(div, durs, vals, hrs, o) {
    const t = theme(), fit = [3, 5, 10, 20, 30];
    const mins = durs.map(d => d / 60);
    const tt = Array.from({ length: 80 }, (_, i) => 120 * Math.pow(7200 / 120, i / 79));
    const inFit = mins.map(m => fit.includes(m));
    const main = [
      { x: tt.map(x => x / 60), y: tt.map(x => o.model(x)), xaxis: 'x', yaxis: 'y', mode: 'lines', line: { color: o.color, width: 2, dash: 'dot' }, hoverinfo: 'skip' },
      { x: [1, 120], y: [o.crit, o.crit], xaxis: 'x', yaxis: 'y', mode: 'lines', line: { color: o.color, width: 1.2 }, hoverinfo: 'skip' },
      { x: mins.filter((_, i) => !inFit[i]), y: vals.filter((_, i) => !inFit[i]), xaxis: 'x', yaxis: 'y', mode: 'markers', marker: { size: 10, color: t.card, line: { color: o.color, width: 2 } },
        hovertemplate: '%{x:.0f} min<br>%{y:.1f} ' + o.unit + '<extra>hors modèle</extra>' },
      { x: mins.filter((_, i) => inFit[i]), y: vals.filter((_, i) => inFit[i]), xaxis: 'x', yaxis: 'y', mode: 'markers', marker: { size: 11, color: o.color, line: { color: t.card, width: 2 } },
        hovertemplate: '%{x:.0f} min<br>%{y:.1f} ' + o.unit + '<extra>ajusté</extra>' },
      { x: mins, y: hrs, xaxis: 'x2', yaxis: 'y2', mode: 'lines+markers', line: { color: C.red, width: 1.5 }, marker: { size: 7, color: C.red, line: { color: t.card, width: 1 } },
        hovertemplate: '%{x:.0f} min<br>%{y:.0f} bpm<extra>FC</extra>' },
    ];
    const ticks = [1, 2, 3, 5, 10, 20, 30, 60, 120];
    const xa = extra => axis(Object.assign({ type: 'log', range: [Math.log10(0.85), Math.log10(140)], tickvals: ticks, ticktext: ticks.map(String), showgrid: true }, extra));
    const lo = Math.min(...hrs.filter(Boolean)) - 8, hi = Math.max(o.hrmax || 0, ...hrs.filter(Boolean)) + 6;
    Plotly.react(div, main, layout({
      margin: { l: 62, r: 100, t: 20, b: 52 },
      xaxis: xa({ domain: [0, 1], anchor: 'y', showticklabels: false }),
      xaxis2: xa({ domain: [0, 1], anchor: 'y2', title: 'durée de l\'effort (min)' }),
      yaxis: axis({ domain: [0.34, 1], anchor: 'x', title: o.ytitle, range: o.yrange }),
      yaxis2: axis({ domain: [0, 0.24], anchor: 'x2', title: 'FC (bpm)', range: [lo, hi] }),
      shapes: [
        { type: 'rect', xref: 'x', yref: 'paper', x0: 3, x1: 30, y0: 0.34, y1: 1, fillcolor: rgba(o.color, 0.07), line: { width: 0 }, layer: 'below' },
        ...(o.hrmax ? [{ type: 'line', xref: 'x2', yref: 'y2', x0: 1, x1: 120, y0: o.hrmax, y1: o.hrmax, line: { color: t.mute, width: 1, dash: 'dash' } }] : []),
      ],
      annotations: [
        { xref: 'paper', x: 1.01, xanchor: 'left', y: o.crit, yref: 'y', text: `<b>${o.critLabel}</b>`, showarrow: false, font: { color: o.color, size: 12 } },
        { xref: 'x', x: Math.log10(9.5), xanchor: 'center', yref: 'paper', y: 1.02, yanchor: 'bottom', text: 'zone d\'ajustement du modèle (3 – 30 min)', showarrow: false, font: { size: 10.5, color: t.mute } },
        ...(o.hrmax ? [{ xref: 'paper', x: 1.01, xanchor: 'left', yref: 'y2', y: o.hrmax, text: 'FCmax<br>estimée', showarrow: false, font: { size: 10.5, color: t.mute } }] : []),
      ],
    }), CFG);
  }
  function critical(f) {
    const durs = Object.keys(f.mean_max_gap_kmh).map(Number).sort((a, b) => a - b);
    const cs = f.cs_kmh / 3.6, D = f.d_prime_m;
    recordChart('mm_v', durs, durs.map(d => f.mean_max_gap_kmh[d]), durs.map(d => f.hr_at_best[d]), {
      color: '#0f6b5c', unit: 'km/h', ytitle: 'vitesse équiv. plat (km/h)', crit: f.cs_kmh, critLabel: `CS<br>${fr(f.cs_kmh, 1)} km/h`,
      model: t => (cs + D / t) * 3.6, hrmax: f.hrmax, yrange: [Math.min(...durs.map(d => f.mean_max_gap_kmh[d])) - 1.5, Math.max(...durs.map(d => f.mean_max_gap_kmh[d])) + 2],
    });
    if (f.cp_w) {
      const pd = Object.keys(f.mean_max_power).map(Number).sort((a, b) => a - b);
      recordChart('mm_p', pd, pd.map(d => f.mean_max_power[d]), pd.map(d => f.hr_at_best_power[d]), {
        color: '#b54708', unit: 'W', ytitle: 'puissance (W)', crit: f.cp_w, critLabel: `CP<br>${fr(f.cp_w)} W`,
        model: t => f.cp_w + f.w_prime_j / t, hrmax: f.hrmax, yrange: [Math.min(...pd.map(d => f.mean_max_power[d])) - 20, Math.max(...pd.map(d => f.mean_max_power[d])) + 25],
      });
    } else document.querySelector('#mm_p').innerHTML = '<p class="mute">Pas de données de puissance.</p>';
  }

  /* ---------- 5. Durabilité : pente Theil-Sen par sortie (forest plot) ---------- */
  function durability(f) {
    const t = theme(), d = f.durability || {};
    const nm = s => s.replace(/^i\d+_/, '').replace(/\.fit$/, '').replace(/_/g, ' ').slice(0, 30);
    const runs = f.durability_runs.slice().sort((a, b) => b.dur_h - a.dur_h);
    const labels = runs.map(r => `${nm(r.file)} · ${fr(r.dur_h, 1)} h`);
    const y = labels.slice(), ys = 'Ensemble des sorties';
    const tr = [{ x: runs.map(r => r.pct_per_h), y: labels, mode: 'markers', marker: { size: 9, color: runs.map(r => r.pct_per_h < 0 ? t.warn : t.acc), line: { color: t.card, width: 1.5 } },
      error_x: { type: 'data', symmetric: false, array: runs.map(r => r.ci_hi - r.pct_per_h), arrayminus: runs.map(r => r.pct_per_h - r.ci_lo), color: t.mute, thickness: 1.5, width: 4 },
      hovertemplate: '%{y}<br>pente %{x:.1f} %/h<extra></extra>' }];
    if (d.pooled_pct_per_h != null) tr.push({ x: [d.pooled_pct_per_h], y: [ys], mode: 'markers', marker: { size: 14, symbol: 'diamond', color: t.ink },
      error_x: { type: 'data', symmetric: false, array: [d.pooled_hi - d.pooled_pct_per_h], arrayminus: [d.pooled_pct_per_h - d.pooled_lo], color: t.ink, thickness: 2.5, width: 6 },
      hovertemplate: 'Ensemble : %{x:.1f} %/h<extra></extra>' });
    Plotly.react('dur', tr, layout({ margin: { l: 210, r: 24, t: 24, b: 52 },
      shapes: [{ type: 'line', xref: 'x', yref: 'paper', x0: 0, x1: 0, y0: 0, y1: 1, line: { color: t.mute, width: 1.5, dash: 'dash' } }],
      annotations: [{ xref: 'x', x: 0, yref: 'paper', y: 1.04, text: 'pas de dérive', showarrow: false, font: { size: 10.5, color: t.mute } }],
      xaxis: axis({ title: 'dérive de l\'efficience vitesse/FC (%/h) — vers la gauche = fatigue', zeroline: false }),
      yaxis: axis({ categoryorder: 'array', categoryarray: [ys, ...labels.slice().reverse()], showgrid: false, ticks: '', automargin: true, tickfont: { size: 11, color: t.ink } }) }), CFG);
  }

  /* ---------- 6. Plan de course : profil + allure ---------- */
  function plan(p) {
    const t = theme(), pf = p.profile, secs = p.sections;
    const ends = secs.slice(0, -1);
    const emin = Math.min(...pf.ele), emax = Math.max(...pf.ele);
    const valid = pf.pace.filter(x => x != null);
    const avg = p.total_s / 60 / pf.km[pf.km.length - 1];
    const movingAvg = (p.total_s - p.stops_s) / 60 / pf.km[pf.km.length - 1];
    const pmin = Math.max(3, Math.floor(Math.min(...valid))), pmax = Math.min(14, Math.ceil(Math.max(...valid)));
    const pts = pf.km.map((k, i) => `<b>km ${fr(k, 1)}</b> · ${pf.ele[i]} m<br>allure ${pf.pace[i] ? pace(pf.pace[i]) : '–'}/km<br>temps écoulé ${hm(pf.t_h[i])}`);
    const tr = [
      { x: pf.km, y: pf.ele, xaxis: 'x', yaxis: 'y', type: 'scatter', mode: 'lines', fill: 'tozeroy', line: { color: t.mute, width: 1.5 }, fillcolor: rgba('#667085', 0.14), text: pts, hoverinfo: 'text' },
      { x: ends.map(s => s.end_km), y: ends.map(s => pf.ele[Math.min(pf.km.length - 1, Math.round(s.end_km / pf.km[pf.km.length - 1] * (pf.km.length - 1)))]), xaxis: 'x', yaxis: 'y', type: 'scatter', mode: 'markers',
        marker: { size: 11, color: t.card, line: { color: t.acc, width: 2 } }, hoverinfo: 'text',
        text: ends.map((s, i) => `<b>R${i + 1} · ${s.to}</b><br>km ${fr(s.end_km, 1)}<br>passage ${s.arrival} (${s.clock})<br>arrêt ${s.stop_min} min` + (s.cutoff ? `<br>barrière ${s.cutoff} · marge ${fr(s.cutoff_margin_min / 60, 1)} h` : '')) },
      { x: pf.km, y: pf.pace.map(x => x == null ? null : Math.min(Math.max(x, pmin), pmax)), xaxis: 'x2', yaxis: 'y2', type: 'scatter', mode: 'lines', line: { color: t.acc, width: 2, shape: 'spline', smoothing: 0.6 },
        text: pts, hoverinfo: 'text' },
    ];
    const shapes = [], annotations = [];
    ends.forEach((s, i) => {
      shapes.push({ type: 'line', xref: 'x', yref: 'paper', x0: s.end_km, x1: s.end_km, y0: 0, y1: 1, line: { color: t.acc, width: 1, dash: 'dot' } });
      annotations.push({ x: s.end_km, xref: 'x', y: 1, yref: 'paper', yanchor: 'bottom', text: `<b>R${i + 1}</b> ${s.clock}`, showarrow: false, font: { size: 10.5, color: t.acc } });
    });
    shapes.push({ type: 'line', xref: 'x2', yref: 'y2', x0: 0, x1: pf.km[pf.km.length - 1], y0: movingAvg, y1: movingAvg, line: { color: t.warn, width: 1.2, dash: 'dash' } });
    annotations.push({ xref: 'paper', x: 1.005, xanchor: 'left', yref: 'y2', y: movingAvg, text: `moy.<br>${pace(movingAvg)}`, showarrow: false, font: { size: 10.5, color: t.warn } });
    const tv = []; for (let v = pmin; v <= pmax; v += 1) tv.push(v);
    // axe du temps prévu : position (km) où le temps écoulé atteint chaque heure, avec l'heure de la journée
    const kmEnd = pf.km[pf.km.length - 1], t0 = new Date(p.params.start), hv = [], ht = [];
    for (let h = 1; h <= Math.floor(pf.t_h[pf.t_h.length - 1]); h++) {
      const j = pf.t_h.findIndex(x => x >= h);
      if (j <= 0) continue;
      const f = (h - pf.t_h[j - 1]) / (pf.t_h[j] - pf.t_h[j - 1] || 1);
      hv.push(pf.km[j - 1] + f * (pf.km[j] - pf.km[j - 1]));
      const clk = new Date(t0.getTime() + h * 3600e3);
      ht.push(`<b>${h}h</b><br>${String(clk.getHours()).padStart(2, '0')}:${String(clk.getMinutes()).padStart(2, '0')}`);
    }
    hv.forEach((k, i) => {
      shapes.push({ type: 'line', xref: 'x', yref: 'paper', x0: k, x1: k, y0: 0, y1: 1, line: { color: rgba('#667085', 0.22), width: 1 }, layer: 'below' });
      annotations.push({ xref: 'x', x: k, yref: 'paper', y: -0.2, yanchor: 'top', text: ht[i], showarrow: false, font: { size: 11, color: t.ink }, align: 'center' });
    });
    annotations.push({ xref: 'paper', x: 0, xanchor: 'right', yref: 'paper', y: -0.2, yanchor: 'top', text: 'temps<br>prévu', showarrow: false, font: { size: 10.5, color: t.mute }, align: 'right' });
    Plotly.react('plan_chart', tr, layout({
      margin: { l: 58, r: 52, t: 40, b: 118 }, shapes, annotations,
      xaxis: axis({ domain: [0, 1], anchor: 'y', range: [0, pf.km[pf.km.length - 1]], showticklabels: false, showgrid: false }),
      xaxis2: axis({ domain: [0, 1], anchor: 'y2', range: [0, pf.km[pf.km.length - 1]], title: 'distance (km)', dtick: 10, showgrid: false }),
      yaxis: axis({ domain: [0.58, 1], anchor: 'x', title: 'altitude (m)', range: [Math.max(0, emin - 60), emax + 60] }),
      yaxis2: axis({ domain: [0, 0.46], anchor: 'x2', title: 'allure (min/km)', range: [pmax, pmin], tickvals: tv, ticktext: tv.map(v => `${v}'00`) }),
    }), CFG);
  }

  window.Charts = { profile, classes, slopeSpeed, critical, durability, plan, fr, hm, pace };
})();
