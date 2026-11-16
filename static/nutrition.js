/* Onglet Nutrition : profil, produits, tests de sudation, bilan et plan par section. */
(function () {
  const $ = s => document.querySelector(s);
  const fr = (x, n = 0) => x == null ? '–' : Number(x).toLocaleString('fr-FR', { minimumFractionDigits: n, maximumFractionDigits: n });
  const TYPES = { drink: 'Boisson', gel: 'Gel', chew: 'Gomme / pâte', bar: 'Barre', real: 'Aliment solide', maltodextrin: 'Maltodextrine', electrolyte: 'Électrolytes' };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = v => (v === '' || v == null) ? null : Number(v);
  let prof = null, defaultCarb = null, carbTouched = false, timer = null, loaded = false;

  async function api(url, opt) {
    const r = await fetch(url, opt);
    if (!r.ok) { let d = ''; try { d = (await r.json()).detail; } catch (e) { } throw d || ('erreur ' + r.status); }
    return r.json();
  }
  const say = (sel, msg, ok) => { const el = $(sel); el.className = ok ? 'ok' : 'err'; el.textContent = msg; };

  // ---------------------------------------------------------------- profil, produits, tests
  function fillProfile() {
    $('#n_weight').value = prof.weight_kg ?? ''; $('#n_height').value = prof.height_cm ?? ''; $('#n_age').value = prof.age ?? '';
    $('#n_sex').value = prof.sex ?? ''; $('#n_habit').value = prof.habit_g_h ?? ''; $('#n_gi').value = prof.gi; $('#n_caf').value = prof.caffeine;
    $('#n_na').value = prof.sweat_na_mmol_l ?? '';
    const pr = $('#n_products'); pr.innerHTML = '';
    prof.products.forEach(addProductRow);
    const ts = $('#n_tests'); ts.innerHTML = '';
    prof.tests.forEach(addTestRow);
    shareTotal();
  }
  function addProductRow(p = { name: '', type: 'gel', carbs_g: 25, sodium_mg: 0, volume_ml: 0, fructose_pct: 0, share_pct: 0 }, meta = null) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><input class="tin p_name" value="${esc(p.name)}"></td>
      <td><select class="tin p_type">${Object.entries(TYPES).map(([k, v]) => `<option value="${k}"${k === p.type ? ' selected' : ''}>${v}</option>`).join('')}</select></td>
      <td><input class="tin p_carbs" type="number" min="0" value="${p.carbs_g}"></td><td><input class="tin p_na" type="number" min="0" value="${p.sodium_mg}"></td>
      <td><input class="tin p_vol" type="number" min="0" value="${p.volume_ml}"></td><td><input class="tin p_fru" type="number" min="0" max="60" value="${p.fructose_pct}"></td>
      <td><input class="tin p_share" type="number" min="0" max="100" value="${p.share_pct}"></td><td><button class="btn danger" type="button">✕</button></td>`;
    tr.querySelector('button').onclick = () => { tr.remove(); shareTotal(); };
    tr.querySelector('.p_share').oninput = shareTotal;
    if (meta) {
      const nm = tr.querySelector('.p_name');
      nm.title = (meta.note ? meta.note + '\n' : '') + (meta.source ? 'Source : ' + meta.source : '');
      const map = { carbs: '.p_carbs', sodium: '.p_na', volume: '.p_vol' };
      meta.missing.forEach(k => { const i = tr.querySelector(map[k]); if (i) { i.classList.add('miss'); i.title = 'Non indiqué par la marque : à compléter avec ton emballage'; i.addEventListener('input', () => i.classList.remove('miss')); } });
    }
    $('#n_products').appendChild(tr);
    return tr;
  }
  function shareTotal() {
    const t = [...document.querySelectorAll('.p_share')].reduce((a, i) => a + Number(i.value || 0), 0);
    $('#n_sharetot').textContent = t ? `Total des parts : ${t} %${t !== 100 ? ' (normalisé à 100 % dans le plan)' : ''}` : 'Aucune part définie : renseigne la part des glucides de chaque produit.';
  }
  function testRate(t) {
    const h = t.duration_min / 60;
    return h > 0 ? (t.before - t.after + ((t.fluid || 0) - (t.urine || 0)) / 1000) / h : NaN;
  }
  function addTestRow(t = {}) {
    const tr = document.createElement('tr');
    const v = (k, d = '') => esc(t[k] ?? d);
    tr.innerHTML = `<td><input class="tin t_date" type="date" value="${v('date')}"></td><td><input class="tin t_dur" type="number" min="20" value="${v('duration_min')}"></td>
      <td><input class="tin t_temp" type="number" value="${v('temp_c')}"></td><td><input class="tin t_before" type="number" step="0.05" value="${v('mass_before_kg')}"></td>
      <td><input class="tin t_after" type="number" step="0.05" value="${v('mass_after_kg')}"></td><td><input class="tin t_fluid" type="number" min="0" value="${v('fluid_ml', 0)}"></td>
      <td><input class="tin t_urine" type="number" min="0" value="${v('urine_ml', 0)}"></td><td><input class="tin t_pow" type="number" min="0" value="${v('avg_power_w')}"></td>
      <td class="t_rate mute">–</td><td><button class="btn danger" type="button">✕</button></td>`;
    const upd = () => {
      const r = testRate({ duration_min: num(tr.querySelector('.t_dur').value), before: num(tr.querySelector('.t_before').value), after: num(tr.querySelector('.t_after').value),
        fluid: num(tr.querySelector('.t_fluid').value), urine: num(tr.querySelector('.t_urine').value) });
      tr.querySelector('.t_rate').textContent = isFinite(r) ? fr(r, 2) + ' L/h' : '–';
    };
    tr.querySelectorAll('input').forEach(i => i.oninput = upd);
    tr.querySelector('button').onclick = () => tr.remove();
    $('#n_tests').appendChild(tr); upd();
  }
  function collect() {
    return {
      weight_kg: num($('#n_weight').value), height_cm: num($('#n_height').value), age: num($('#n_age').value), sex: $('#n_sex').value || null,
      habit_g_h: num($('#n_habit').value), gi: $('#n_gi').value, caffeine: $('#n_caf').value, sweat_na_mmol_l: num($('#n_na').value),
      products: [...document.querySelectorAll('#n_products tr')].map(tr => ({
        name: tr.querySelector('.p_name').value, type: tr.querySelector('.p_type').value, carbs_g: num(tr.querySelector('.p_carbs').value) || 0,
        sodium_mg: num(tr.querySelector('.p_na').value) || 0, volume_ml: num(tr.querySelector('.p_vol').value) || 0,
        fructose_pct: num(tr.querySelector('.p_fru').value) || 0, share_pct: num(tr.querySelector('.p_share').value) || 0 })),
      tests: [...document.querySelectorAll('#n_tests tr')].filter(tr => tr.querySelector('.t_dur').value).map(tr => ({
        date: tr.querySelector('.t_date').value, duration_min: num(tr.querySelector('.t_dur').value), temp_c: num(tr.querySelector('.t_temp').value),
        mass_before_kg: num(tr.querySelector('.t_before').value), mass_after_kg: num(tr.querySelector('.t_after').value),
        fluid_ml: num(tr.querySelector('.t_fluid').value) || 0, urine_ml: num(tr.querySelector('.t_urine').value) || 0, avg_power_w: num(tr.querySelector('.t_pow').value) })),
    };
  }
  async function save() {
    try {
      prof = await api('/api/nutrition/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(collect()) });
      fillProfile(); say('#n_msg', 'Profil nutrition enregistré.', true); carbTouched = false; loadPlan();
    } catch (e) { say('#n_msg', String(e), false); }
  }

  // ---------------------------------------------------------------- bilan et plan
  const STATUS = { sous: ['sous la fourchette', 'bad'], dans: ['dans la fourchette', 'good'], 'au-dessus': ['au-dessus de la fourchette', 'bad'] };
  function renderBilan(b) {
    let h = '';
    const t = b.training;
    if (t) {
      h += `<p>Sur les ${t.days} derniers jours d'entraînement : <b>${t.sessions}</b> sorties de course, <b>${fr(t.hours_week, 1)} h/semaine</b>, plus longue ${fr(t.longest_h, 1)} h, ${t.n_2h} sortie(s) de 2 h ou plus.</p>
        <p>Glucides au quotidien : <b>${t.carb_day.lo}–${t.carb_day.hi} g/kg/jour</b> (${t.carb_day.label})${t.carb_day_g ? `, soit environ ${t.carb_day_g.lo}–${t.carb_day_g.hi} g/jour` : ''}.
        <span class="mute">Un apport quotidien d'environ 8 g/kg améliore l'oxydation des glucides ingérés à l'effort ; les régimes très pauvres en glucides sont déconseillés. ${esc(t.carb_day.src)}</span></p>`;
      if (t.kcal_week) h += `<p>Dépense estimée à l'entraînement (course à pied) : environ <b>${fr(t.kcal_week, 0)} kcal/semaine</b> <span class="mute">(modèle de coût de Minetti, à partir de ton poids)</span>.</p>`;
    } else h += '<p class="mute">Pas de sorties de course dans le profil pour établir le bilan d\'entraînement.</p>';
    if (b.items.length) {
      h += '<table><tr><th>Situation</th><th>Repère glucides</th><th>Ton apport habituel</th><th>Écart</th></tr>';
      b.items.forEach(i => { const st = STATUS[i.status] || ['non renseigné', 'mute'];
        h += `<tr><td>${esc(i.what)}</td><td>${i.band.hi ? i.band.lo + '–' + i.band.hi + ' g/h' : 'aucun'}</td><td>${b.habit_g_h != null ? fr(b.habit_g_h) + ' g/h' : '–'}</td><td class="${st[1]}">${st[0]}</td></tr>`; });
      h += '</table>';
    }
    if (b.caffeine_mg) h += `<p>Caféine : 3 à 6 mg/kg, soit <b>${b.caffeine_mg.lo}–${b.caffeine_mg.hi} mg</b> (ISSN 2021) ; à tester à l'entraînement, plutôt en fin de course.</p>`;
    b.notes.forEach(n => h += `<p class="note">${esc(n)}</p>`);
    $('#n_bilan').innerHTML = h;
  }

  function nutQuery() {
    const c = $('#n_carb'), f = $('#n_fluid'), s = $('#n_nasl');
    if (!c) return '';
    return `&carb=${c.value}&fluid_pct=${f.value}&na_pct=${s.value}`;
  }
  window.nutQuery = () => (loaded ? nutQuery() : '');

  async function loadPlan() {
    const out = $('#n_plan');
    try {
      const q = (typeof planQuery === 'function' ? planQuery() : '') + (loaded && carbTouched ? nutQuery() : '');
      const d = await api('/api/nutrition/plan?' + q);
      if (!loaded) { loaded = true; }
      if (defaultCarb == null || !carbTouched) { defaultCarb = d.default_carb; $('#n_carb').value = d.nutrition.carb_g_h; }
      renderBilan(d.bilan); renderPlan(d);
    } catch (e) {
      const m = { no_gpx: 'Dépose d\'abord le GPX de ta course (onglet « Mes données »).', no_archive: 'Dépose d\'abord ton archive d\'activités (onglet « Mes données »).' }[e] || ('Impossible de calculer : ' + esc(e));
      out.innerHTML = `<p class="note">${m}</p>`;
    }
  }

  function renderPlan(d) {
    const n = d.nutrition, t = n.totals, sw = n.sweat, b = n.band;
    $('#n_carb_v').textContent = fr(n.carb_g_h) + ' g/h'; $('#n_fluid_v').textContent = n.fluid_pct + ' % de la sueur'; $('#n_nasl_v').textContent = n.na_pct + ' % des pertes';
    $('#n_band').textContent = b.hi ? `Repère pour ${fr(n.hours, 1)} h (${b.label}) : ${b.lo}–${b.hi} g/h — ${b.note}.` : `Repère pour ${fr(n.hours, 1)} h : ${b.note}.`;
    const kp2 = (v, l) => `<div class="kpi"><b>${v}</b><span>${l}</span></div>`;
    const avgFluid = t.fluid_ml / n.hours;
    let h = `<div class="grid">${kp2(fr(n.carb_g_h) + ' g/h', 'Glucides visés')}${kp2(esc(n.ratio.ratio), 'Ratio glucose:fructose conseillé')}
      ${kp2(t.carbs_g >= 1000 ? fr(t.carbs_g / 1000, 2) + ' kg' : fr(t.carbs_g) + ' g', 'Glucides sur la course')}${kp2(fr(avgFluid) + ' mL/h', 'Liquide moyen · ' + fr(t.fluid_ml / 1000, 1) + ' L au total')}
      ${kp2(fr(t.sodium_target_mg / 1000, 1) + ' g', 'Sodium visé · prévu ' + fr(t.sodium_planned_mg / 1000, 1) + ' g')}${kp2(fr(sw.total_l, 1) + ' L', 'Sueur estimée sur la course')}</div>`;
    n.warnings.forEach(w => h += `<p class="note">⚠ ${esc(w)}</p>`);
    h += `<div class="exports"><span class="mute">Exporter avec la nutrition :</span><a class="btn sec" href="/api/plan/export/pdf?${(typeof planQuery === 'function' ? planQuery() : '')}${nutQuery()}" download>Fiche PDF</a>
      <a class="btn sec" href="/api/plan/export/gpx?${(typeof planQuery === 'function' ? planQuery() : '')}${nutQuery()}" download>GPX</a></div>`;
    h += '<table><tr><th>Section</th><th>Durée</th><th>Temp.</th><th>Glucides</th><th>Produits</th><th>Liquide</th><th>Sodium visé</th><th>Sueur</th></tr>';
    n.sections.forEach(s => {
      const prods = s.products.filter(p => p.servings >= 0.05).map(p => `${fr(p.servings, 1)} × ${esc(p.name)}`);
      if (s.electrolyte_tabs) prods.push(`${fr(s.electrolyte_tabs, 1)} × électrolytes`);
      h += `<tr><td>${esc(s.from)} → ${esc(s.to)}</td><td>${Charts.hm(s.hours)}</td><td>${fr(s.temp)} °C</td><td>${fr(s.carbs_g)} g</td><td style="text-align:left">${prods.join('<br>') || '–'}</td>
        <td>${fr(s.fluid_ml)} mL<br><span class="mute">dont boisson ${fr(s.drink_ml)}</span></td><td>${fr(s.na_target_mg)} mg</td><td>${fr(s.sweat_l_h, 2)} L/h</td></tr>`;
    });
    h += '</table>';
    if (t.products.length) h += `<p><b>À prévoir pour la course :</b> ${t.products.map(p => `${Math.ceil(p.servings)} × ${esc(p.name)}`).join(' · ')}</p>`;
    h += `<p class="mute">Sudation de référence à 20 °C : ${fr(sw.base_20c, 2)} L/h (${sw.from_tests ? sw.n_tests + ' test(s) de sudation' : '<b>valeur de population, à confirmer par un test de sudation</b>'}), ajustée à la température de chaque section
      (hypothèse : environ moitié moins à 0 °C qu'à 25 °C, d'après une étude à effort modéré) et à la puissance prévue si tes tests la mentionnent. Sodium de la sueur : ${fr(sw.na_mmol_l)} mmol/L (${sw.na_default ? 'valeur de population, Baker 2016' : 'valeur saisie'}).
      Le liquide est plafonné à 800 mL/h et ne dépasse jamais la sueur : le consensus recommande de boire à la soif, la surhydratation étant la cause de l'hyponatrémie. La compensation du sodium est facultative (preuves limitées).
      ${t.bm_loss_pct != null ? 'Perte de masse estimée : ' + fr(t.bm_loss_pct, 1) + ' %.' : ''}</p>`;
    $('#n_plan').innerHTML = h;
  }


  // ---------------------------------------------------------------- catalogue des marques (arborescence)
  const CAT_LABEL = { drink: 'Boissons', gel: 'Gels', chew: 'Gommes et pâtes', bar: 'Barres', electrolyte: 'Électrolytes', real: 'Purées et aliments' };
  const CAT_ORDER = ['gel', 'drink', 'chew', 'bar', 'electrolyte', 'real'];
  const CONF = { tableau: ['tableau lu', 't'], fiche: ['fiche produit', 'f'], carte: ['carte d\'accueil', 'c'], generique: ['exemple', ''] };
  let catalog = null;

  function missingOf(p) {
    const m = [];
    if (p.carbs_g == null) m.push('carbs');
    if (p.sodium_mg == null) m.push('sodium');
    if (p.type === 'drink' && !p.volume_ml) m.push('volume');
    return m;
  }
  function addFromCatalog(p) {
    const row = {
      name: p.brand === 'Génériques' ? p.name : `${p.brand} – ${p.name}`, type: p.category, carbs_g: p.carbs_g ?? 0, sodium_mg: p.sodium_mg ?? 0,
      volume_ml: p.volume_ml ?? 0, fructose_pct: p.fructose_pct ?? 0, share_pct: 0,
    };
    const m = missingOf({ ...p, type: p.category });
    const tr = addProductRow(row, { missing: m, note: p.note, source: p.source });
    shareTotal();
    const names = { carbs: 'glucides', sodium: 'sodium', volume: 'volume d\'eau' };
    say('#n_msg', `« ${row.name} » ajouté. ` + (m.length ? `À compléter (cases orange) : ${m.map(k => names[k]).join(', ')}. ` : '') + 'Pense à définir sa part des glucides, puis enregistre.', !m.length);
    tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
  function renderCatalog() {
    const q = $('#n_cat_q').value.trim().toLowerCase();
    const tree = $('#n_cat_tree'); tree.innerHTML = '';
    const byBrand = {};
    catalog.products.forEach(p => { if (!q || (p.brand + ' ' + p.name + ' ' + (p.serving || '') + ' ' + p.category).toLowerCase().includes(q)) (byBrand[p.brand] = byBrand[p.brand] || []).push(p); });
    const brands = Object.keys(catalog.brands).filter(b => byBrand[b] || (!q && catalog.brands[b]));
    brands.forEach(b => {
      const list = byBrand[b] || [], info = catalog.brands[b] || {};
      const d = document.createElement('details'); d.className = 'brand'; d.open = !!q;
      d.innerHTML = `<summary>${esc(b)} <span class="mute">(${list.length} produit${list.length > 1 ? 's' : ''})</span></summary>
        <p class="mute" style="margin:2px 0 2px 10px">${esc(info.coverage || '')}${info.site ? ` <a href="${esc(info.site)}" target="_blank" rel="noopener">site</a>` : ''}</p>`;
      CAT_ORDER.forEach(c => {
        const items = list.filter(p => p.category === c);
        if (!items.length) return;
        const sd = document.createElement('details'); sd.open = !!q;
        sd.innerHTML = `<summary>${CAT_LABEL[c]} <span class="mute">(${items.length})</span></summary>`;
        const tb = document.createElement('table');
        tb.innerHTML = '<tr><th>Produit</th><th>Portion</th><th>Glucides</th><th>Sodium</th><th>Source</th><th></th></tr>';
        items.forEach(p => {
          const tr = document.createElement('tr'); const cf = CONF[p.confidence] || ['', ''];
          tr.innerHTML = `<td title="${esc(p.note || '')}">${esc(p.name)}${p.caffeine_mg ? ` <span class="mute">· ${p.caffeine_mg} mg caféine</span>` : ''}</td><td>${esc(p.serving || '')}</td>
            <td>${p.carbs_g != null ? fr(p.carbs_g, p.carbs_g % 1 ? 1 : 0) + ' g' : '<span class="err">?</span>'}</td><td>${p.sodium_mg != null ? fr(p.sodium_mg) + ' mg' : '<span class="err">?</span>'}</td>
            <td><span class="badge ${cf[1]}">${cf[0]}</span>${p.source ? ` <a href="${esc(p.source)}" target="_blank" rel="noopener">↗</a>` : ''}</td><td><button class="btn sec" type="button">+ Ajouter</button></td>`;
          tr.querySelector('button').onclick = () => addFromCatalog(p);
          tb.appendChild(tr);
        });
        sd.appendChild(tb); d.appendChild(sd);
      });
      tree.appendChild(d);
    });
    if (!tree.children.length) tree.innerHTML = '<p class="mute">Aucun produit trouvé.</p>';
  }
  async function openCatalog() {
    if (catalog) return;
    try {
      catalog = await api('/api/nutrition/catalog');
      $('#n_cat_note').textContent = catalog.note;
      renderCatalog();
    } catch (e) { $('#n_cat_note').textContent = 'Catalogue indisponible : ' + e; }
  }

  function schedule() { clearTimeout(timer); timer = setTimeout(loadPlan, 300); }

  function init() {
    if (!$('#nutrition')) return;
    $('#n_add_prod').onclick = () => addProductRow();
    $('#n_cat').addEventListener('toggle', () => { if ($('#n_cat').open) openCatalog(); });
    $('#n_cat_q').oninput = () => { if (catalog) renderCatalog(); };
    $('#n_add_test').onclick = () => addTestRow({ date: new Date().toISOString().slice(0, 10), duration_min: 60, mass_before_kg: prof && prof.weight_kg || '', fluid_ml: 0, urine_ml: 0 });
    $('#n_save').onclick = save;
    $('#n_reset_prod').onclick = async () => {
      if (!confirm('Remplacer la liste de produits par les exemples génériques ?')) return;
      const d = await api('/api/nutrition/profile'); const fresh = await api('/api/nutrition/defaults');
      prof.products = fresh.products; fillProfile();
    };
    $('#n_carb').oninput = () => { carbTouched = true; schedule(); };
    $('#n_fluid').oninput = () => { carbTouched = true; schedule(); };
    $('#n_nasl').oninput = () => { carbTouched = true; schedule(); };
    api('/api/nutrition/profile').then(p => { prof = p; fillProfile(); });
  }
  window.loadNutritionPlan = () => { if (prof) loadPlan(); else setTimeout(window.loadNutritionPlan, 200); };
  init();
})();
