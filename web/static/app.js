'use strict';
const $ = (s, r = document) => r.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const tr = n => Number(n).toLocaleString('tr-TR');
const api = (u, opt) => fetch(u, opt).then(r => r.json());

let selectedIncident = null;
let incidents = [];

// ---------- Genel bakış ----------
async function loadOverview() {
  const d = await api('/api/overview');
  incidents = d.incidents;

  // KPI
  const k = d.kpis;
  const cards = [
    ['Aktif Arıza', k.aktif_ariza, 'açık olay', true],
    ['Kritik Stok Kalemi', k.kritik_stok, 'emniyet stoğu altında', true],
    ['Bekleyen Sipariş', k.bekleyen_siparis, 'insan onayı bekliyor', false],
    ['Haftalık Duruş', k.haftalik_durus + ' s', 'son 7 gün', false],
    ['MTBF', (k.mtbf_gun != null ? k.mtbf_gun : '—') + ' g', 'arızalar arası ort.', false],
    ['MTTR', (k.mttr_saat != null ? k.mttr_saat : '—') + ' s', 'ort. çözüm süresi', false],
    ['Çözüm Oranı', (k.cozum_orani != null ? k.cozum_orani : 0) + '%', 'çözülen / toplam', false],
  ];
  $('#kpis').innerHTML = '';
  cards.forEach(([l, v, s, red]) => {
    const c = el('div', 'kpi' + (red && Number(String(v)) > 0 ? ' red' : ''));
    c.append(el('div', 'l', l), el('div', 'v', String(v)), el('div', 's', s));
    $('#kpis').append(c);
  });

  $('#navAriza').textContent = k.aktif_ariza;
  $('#navSip').textContent = k.bekleyen_siparis;

  renderIncidents();
  renderBars(d.downtime);
  renderLow(d.low_stock);
}

function renderIncidents() {
  const box = $('#incList'); box.innerHTML = '';
  incidents.forEach(inc => {
    const row = el('div', 'inc-row' + (inc.incident_id === (selectedIncident && selectedIncident.incident_id) ? ' sel' : ''));
    row.append(
      (() => { const t = el('div', 'top'); t.append(el('span', 'ttl', inc.title), el('span', 'tag ' + inc.status, statusLabel(inc.status))); return t; })(),
      el('div', 'code', inc.fault_code + ' · ' + inc.reported_at),
      el('div', 'mac', inc.machine_id)
    );
    row.onclick = () => selectIncident(inc);
    box.append(row);
  });
}
const statusLabel = s => ({ yeni: 'Yeni', isleniyor: 'İşleniyor', cozuldu: 'Çözüldü' }[s] || s);

function selectIncident(inc) {
  selectedIncident = inc;
  renderIncidents();
  $('#diagBody').innerHTML =
    `<p class="val"><b>${inc.machine_id}</b> · ${inc.fault_code}<br>${inc.title}</p>
     <button class="btn primary" id="runBtn" style="margin-top:12px">▶ Ajanı Çalıştır</button>`;
  $('#runBtn').onclick = () => runDiagnosis(inc);
}

// ---------- Teşhis ----------
async function runDiagnosis(inc) {
  $('#diagSpin').innerHTML = '<span class="spin"></span>';
  $('#runBtn').disabled = true;
  const r = await api('/api/diagnose', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ incident_id: inc.incident_id })
  });
  $('#diagSpin').innerHTML = '';
  renderDiagnosis(r);
  renderSubstitutes(r.substitutes);
  renderOrder(r.order_draft);
  loadWorkOrders();
  loadOverview();
}

function renderDiagnosis(r) {
  const conf = r.confidence;
  const cc = conf >= 90 ? 'var(--ok)' : conf >= 80 ? 'var(--warn)' : 'var(--crit)';
  const ev = (r.evidence || []).map(e => `<li>${e}</li>`).join('');
  const src = (r.sources || []).map(s => `<div class="src">📖 ${s}</div>`).join('');
  const traceTxt = (r.trace || []).map((t, i) => `${i + 1}. ${t.tool}(${Object.keys(t.input).join(', ')})`).join('\n');
  $('#diagBody').innerHTML = `
    <div class="row"><div class="lbl">Kök Neden</div><div class="val">${r.root_cause}</div>
      <div class="conf"><div class="confbar"><i style="width:${conf}%;background:${cc}"></i></div>
      <span style="font-size:12px;font-weight:700;color:${cc}">Güven %${conf}</span></div></div>
    <div class="row"><div class="lbl">Kanıtlar (sensör/analiz)</div><ul class="evidence">${ev}</ul>${src}</div>
    <div class="row"><div class="lbl">İlgili Parça</div><div class="val"><b>${r.part.part_code}</b> · ${r.part.name}<br>
      <span class="muted-note">Stok: ${r.stock.on_hand}/${r.stock.safety_stock} ${r.stock.below_safety ? '⚠️ emniyet stoğu altında' : '✓ yeterli'}</span></div></div>
    <div class="row"><div class="lbl">Onarım Adımları (İş Emri ${r.work_order ? r.work_order.work_order_id : ''})</div>
      <ul class="steps">${(r.work_order ? r.work_order.steps : []).map(s => `<li><span class="mk">${'•'}</span><span>${s}</span></li>`).join('')}</ul></div>
    <div class="row"><div class="lbl">Ajan araç zinciri (tool-use)</div><div class="trace">${traceTxt}</div></div>`;
}

// ---------- Muadiller ----------
function renderSubstitutes(subs) {
  const box = $('#altBody');
  if (!subs || !subs.length) { box.innerHTML = '<p class="muted-note">Stok yeterli — muadil gerekmedi.</p>'; return; }
  box.innerHTML = '';
  subs.forEach(s => {
    const lvl = s.approved ? 'ok' : (/(adaptör|şartlı|mühendislik)/i.test(s.compatibility_note) ? 'warn' : 'no');
    const pill = s.approved ? 'Onaylı · Uyumlu' : (lvl === 'warn' ? 'Şartlı uyumlu' : 'Uyumlu değil');
    const a = el('div', 'alt ' + lvl);
    a.innerHTML = `<div class="h"><span class="c">${s.substitute_code}</span><span class="nm">${s.name}</span><span class="apill">${pill}</span></div>
      <div class="note">${s.compatibility_note}</div>
      <div class="stk">Stok: ${s.on_hand != null ? s.on_hand + ' adet' : '—'}</div>`;
    box.append(a);
  });
}

// ---------- Sipariş ----------
function renderOrder(o) {
  const box = $('#orderBody');
  if (!o) { box.innerHTML = '<p class="muted-note">Mevcut stok yeterli — sipariş taslağı gerekmedi.</p>'; return; }
  drawOrder(o);
}
function drawOrder(o) {
  const box = $('#orderBody');
  const cls = o.status === 'approved' ? 'approved' : o.status === 'rejected' ? 'rejected' : 'pending';
  let acts = '';
  if (o.status === 'pending_approval') {
    acts = `<div class="acts"><button class="btn ok" id="appBtn">✓ Onayla</button><button class="btn danger" id="rejBtn">✕ Reddet</button></div>`;
  }
  const warn = o.requires_manager_approval ? `<div class="warnbox">⚠️ Tutar eşiğin üzerinde — YÖNETİCİ onayı şart.</div>` : '';
  const finalMsg = o.status === 'approved' ? `<div class="status-final" style="color:var(--ok)">✓ Onaylandı — ${o.approved_by || ''}</div>`
    : o.status === 'rejected' ? `<div class="status-final" style="color:var(--crit)">✕ Reddedildi — ${o.approved_by || ''}</div>` : '';
  box.innerHTML = `<div class="order ${cls}">
      <div class="ttl">🧾 ${o.draft_id}</div>
      <div class="meta"><b>${o.part_code}</b> · ${o.name || ''}<br>
        Adet: <b>${o.quantity}</b> · Tahmini tutar: <b>${tr(o.est_cost)} TL</b><br>
        Durum: <b>${o.status === 'pending_approval' ? 'İnsan onayı bekliyor' : o.status}</b></div>
      ${warn}${finalMsg}${acts}
      <div class="muted-note" style="margin-top:10px">⛔ Bu taslak ajan tarafından onaylanmaz. Karar bakım planlama sorumlusuna aittir.</div>
    </div>`;
  if (o.status === 'pending_approval') {
    $('#appBtn').onclick = () => decideOrder(o.draft_id, true);
    $('#rejBtn').onclick = () => decideOrder(o.draft_id, false);
  }
}
async function decideOrder(id, approved) {
  const o = await api(`/api/order/${id}/decide`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved, approver: 'Elif Demirtaş' })
  });
  drawOrder(o);
  loadOverview();
}

// ---------- İş emirleri ----------
async function loadWorkOrders() {
  const wos = await api('/api/work_orders');
  const box = $('#woBody');
  if (!wos.length) { box.innerHTML = '<p class="muted-note">Henüz iş emri yok.</p>'; return; }
  box.innerHTML = wos.map(w => `<div class="alt ok" style="background:#fff;border-color:var(--line)">
      <div class="h"><span class="c">${w.work_order_id}</span><span class="nm">${w.part_code} · Teknisyen: ${w.technician}</span>
        <span class="apill" style="background:var(--okbg);color:var(--ok)">${w.status}</span></div>
      <div class="note">${(w.steps || []).length} adım · Olay: ${w.fault_id} · ${w.created_at}</div></div>`).join('');
}

// ---------- Grafik / stok ----------
function renderBars(data) {
  const max = Math.max(...data.map(d => d[1]));
  $('#bars').innerHTML = '';
  data.forEach(([day, h]) => {
    const isMax = h === max;
    const b = el('div', 'bar' + (isMax ? ' max' : ''));
    b.innerHTML = `<div class="h">${String(h).replace('.', ',')}</div><div class="col" style="height:${Math.round(h / (max + .8) * 100)}%"></div><div class="d">${day}</div>`;
    $('#bars').append(b);
  });
}
function renderLow(low) {
  $('#low').innerHTML = '';
  low.forEach(p => {
    const ratio = p.on_hand / p.safety_stock;
    const col = ratio < .5 ? 'var(--crit)' : 'var(--warn)';
    const d = el('div', 'ls');
    d.innerHTML = `<div class="top"><span class="c">${p.part_code}</span><span class="q" style="color:${col}">${p.on_hand} / ${p.safety_stock}</span></div>
      <div class="nm">${p.name}</div><div class="track"><i style="width:${Math.max(6, Math.round(ratio * 100))}%;background:${col}"></i></div>`;
    $('#low').append(d);
  });
}

// ---------- Önleyici bakım (UC-06) ----------
async function loadPreventive() {
  const d = await api('/api/preventive');
  const alerts = d.alerts || [];
  renderAlerts(alerts);
  renderRecurring(d.recurring_faults || []);
  renderShortage(d.part_shortages || []);
  $('#navOnleyici').textContent = alerts.length;
  $('#alertCount').textContent = alerts.length + ' uyarı';
}
function lvlColors(level) {
  if (level === 'kritik' || level === 'yüksek') return ['var(--crit)', 'var(--critbg)'];
  if (level === 'uyari' || level === 'orta') return ['var(--warn)', 'var(--warnbg)'];
  return ['var(--ok)', 'var(--okbg)'];
}
function renderAlerts(alerts) {
  const box = $('#alertBody');
  if (!alerts.length) { box.innerHTML = '<p class="muted-note">Aktif önleyici uyarı yok.</p>'; return; }
  box.innerHTML = '';
  alerts.forEach(a => {
    const [col, bg] = lvlColors(a.level);
    const lbl = a.level === 'kritik' ? 'KRİTİK' : a.level === 'uyari' ? 'UYARI' : 'BİLGİ';
    const d = el('div', 'alt'); d.style.borderLeft = '3px solid ' + col;
    d.innerHTML = `<div class="h"><span class="apill" style="background:${bg};color:${col}">${lbl}</span>
      <span class="nm" style="font-weight:600;color:var(--ink)">${a.title}</span></div>
      <div class="note">${a.detail}</div>`;
    box.append(d);
  });
}
function renderRecurring(list) {
  const box = $('#recurBody');
  if (!list.length) { box.innerHTML = '<p class="muted-note">Tekrar eden arıza yok.</p>'; return; }
  box.innerHTML = '';
  list.forEach(f => {
    const lvl = f.severity === 'yüksek' ? 'warn' : 'ok';
    const mtbf = f.mtbf_days != null ? ('MTBF ~' + f.mtbf_days + ' gün') : 'MTBF —';
    const d = el('div', 'alt ' + lvl);
    d.innerHTML = `<div class="h"><span class="c">${f.fault_code}</span><span class="nm">${f.occurrences}× · ${mtbf}</span>
      <span class="apill">${f.repeated_machine ? ('⟳ ' + f.repeated_machine) : 'çok makineli'}</span></div>
      <div class="note">${f.last_root_cause || ''}</div>
      <div class="stk">Makineler: ${(f.machines || []).join(', ')}${f.part_used ? (' · Parça: ' + f.part_used) : ''}</div>`;
    box.append(d);
  });
}
function renderShortage(list) {
  const box = $('#shortageBody');
  if (!list.length) { box.innerHTML = '<p class="muted-note">Çapraz-varyant açık riski yok.</p>'; return; }
  box.innerHTML = '';
  list.forEach(s => {
    const [col, bg] = lvlColors(s.shortage_risk);
    const d = el('div', 'alt'); d.style.borderLeft = '3px solid ' + col;
    d.innerHTML = `<div class="h"><span class="c">${s.part_code}</span><span class="nm">${s.name}</span>
      <span class="apill" style="background:${bg};color:${col}">Risk: ${s.shortage_risk}</span></div>
      <div class="note">${s.recommendation}</div>
      <div class="stk">Stok: ${s.on_hand}/${s.safety_stock} · ${s.variant_count} makine · Önerilen: ${s.recommended_qty} adet</div>`;
    box.append(d);
  });
}

// ---------- Parça tanıma ----------
$('#drop').onclick = () => $('#file').click();
$('#file').onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  const rd = new FileReader();
  // Dosya adını ipucu olarak gönder — offline modda kod eşleşmesi için.
  rd.onload = () => identify(rd.result.split(',')[1], f.name);
  rd.readAsDataURL(f);
};
$('#identBtn').onclick = () => identify(null, $('#hintInp').value.trim());

async function loadParts() {
  const parts = await api('/api/parts');
  const g = $('#partGallery'); g.innerHTML = '';
  parts.forEach(p => {
    const chip = el('button', 'gchip', `<b>${p.part_code}</b><span>${p.name}</span>`);
    chip.onclick = () => identify(null, p.part_code);
    g.append(chip);
  });
}

async function identify(b64, hint) {
  $('#identOut').innerHTML = '<span class="spin"></span> Tanımlanıyor…';
  const r = await api('/api/identify', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_b64: b64, hint })
  });
  const others = (r.candidates || []).filter(c => c.part_code !== r.part_code);
  const candHtml = others.length
    ? `<div class="stk">Diğer adaylar: ${others.map(c => `<button class="cand" data-c="${c.part_code}">${c.part_code} (%${Math.round(c.confidence * 100)})</button>`).join(' ')}</div>`
    : '';
  if (r.part_code) {
    const pi = r.part_info || {};
    $('#identOut').innerHTML = `<div class="alt ok"><div class="h"><span class="c">${r.part_code}</span><span class="nm">${r.name}</span>
        <span class="apill" style="background:var(--okbg);color:var(--ok)">Güven %${Math.round((r.confidence || 0) * 100)}</span></div>
      <div class="note">${pi.specs || ''}</div>
      <div class="stk">Kaynak: ${r.source} · Stok: ${pi.on_hand != null ? pi.on_hand + '/' + pi.safety_stock : '—'}</div>
      ${candHtml}</div>`;
  } else {
    $('#identOut').innerHTML = `<div class="alt warn"><div class="h"><span class="nm" style="font-weight:600;color:var(--ink)">Parça tanınamadı</span></div>
      <div class="note">${r.message || 'Eşleşme bulunamadı. Parça kodu/adı yazın ya da örnek parçalardan seçin.'}</div>${candHtml}</div>`;
  }
  document.querySelectorAll('#identOut .cand').forEach(b => b.onclick = () => identify(null, b.dataset.c));
}

// ---------- Sohbet ----------
const quickQs = ['Bekleyen siparişler neler?', 'HYD-4520-B durumu?', 'Muadil var mı?', 'Bu hafta stok durumu?'];
function initChat() {
  $('#quick').innerHTML = '';
  quickQs.forEach(q => { const b = el('button', null, q); b.onclick = () => ask(q); $('#quick').append(b); });
  addMsg('ai', 'Merhaba, bakım asistanınızım. Parça, sipariş, iş emri ve stok durumunu sorabilirsiniz.');
}
function addMsg(role, text) { const m = el('div', 'msg ' + role, text.replace(/</g, '&lt;')); $('#msgs').append(m); $('#msgs').scrollTop = $('#msgs').scrollHeight; }
async function ask(q) {
  addMsg('user', q); $('#chatInp').value = '';
  const r = await api('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: q }) });
  addMsg('ai', r.answer);
}
$('#chatSend').onclick = () => { const v = $('#chatInp').value.trim(); if (v) ask(v); };
$('#chatInp').onkeydown = e => { if (e.key === 'Enter') { const v = e.target.value.trim(); if (v) ask(v); } };
const toggleChat = () => $('#chat').classList.toggle('open');
$('#fab').onclick = toggleChat; $('#chatX').onclick = toggleChat; $('#navChat').onclick = toggleChat;

// ---------- Nav scroll ----------
document.querySelectorAll('.nav-item[data-target]').forEach(n => {
  n.onclick = () => {
    document.querySelectorAll('.nav-item').forEach(x => x.classList.remove('active'));
    n.classList.add('active');
    const t = document.getElementById(n.dataset.target);
    if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
});

// ---------- Başlat ----------
loadOverview();
loadWorkOrders();
loadPreventive();
loadParts();
initChat();
