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
  ];
  $('#kpis').innerHTML = '';
  cards.forEach(([l, v, s, red]) => {
    const c = el('div', 'kpi' + (red && Number(String(v)) > 0 ? ' red' : ''));
    c.append(el('div', 'l', l), el('div', 'v', String(v)), el('div', 's', s));
    $('#kpis').append(c);
  });

  renderIncidents();
  renderBars(d.downtime);
  renderLow(d.low_stock);
}

let incidentsExpanded = false;
const INCIDENTS_LIMIT = 4;

function renderIncidents() {
  const box = $('#incList'); box.innerHTML = '';
  const visible = incidentsExpanded ? incidents : incidents.slice(0, INCIDENTS_LIMIT);
  visible.forEach(inc => {
    const row = el('div', 'inc-row' + (inc.incident_id === (selectedIncident && selectedIncident.incident_id) ? ' sel' : ''));
    row.append(
      (() => { const t = el('div', 'top'); t.append(el('span', 'ttl', inc.title), el('span', 'tag ' + inc.status, statusLabel(inc.status))); return t; })(),
      el('div', 'code', inc.fault_code + ' · ' + inc.reported_at),
      el('div', 'mac', inc.machine_id)
    );
    row.onclick = () => selectIncident(inc);
    box.append(row);
  });
  if (incidents.length > INCIDENTS_LIMIT) {
    const btn = el('button', 'btn', incidentsExpanded ? '▲ Daha az göster' : `▼ Tümünü göster (${incidents.length})`);
    btn.style.cssText = 'width:100%;margin-top:8px;font-size:12px;padding:8px';
    btn.onclick = () => { incidentsExpanded = !incidentsExpanded; renderIncidents(); };
    box.append(btn);
  }
}
const statusLabel = s => ({ yeni: 'Yeni', isleniyor: 'İşleniyor', cozuldu: 'Çözüldü' }[s] || s);

function selectIncident(inc) {
  selectedIncident = inc;
  renderIncidents();
  $('#diagBody').innerHTML =
    `<div class="diag-sel">
       <div class="diag-sel-h">Seçilen arıza</div>
       <div class="val"><b>${inc.machine_id}</b> · ${inc.fault_code}<br>${inc.title}</div>
       <div class="muted-note" style="margin-top:8px">Ajan; kök neden → parça/stok → muadil → sipariş taslağı → iş emri zincirini çalıştıracak.</div>
       <button class="btn primary" id="runBtn" style="margin-top:14px">▶ Ajanı Çalıştır</button>
     </div>`;
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
  const confLbl = conf >= 90 ? 'Yüksek güven' : conf >= 80 ? 'Orta güven' : 'Düşük güven';
  const ev = (r.evidence || []).map(e => `<li>${e}</li>`).join('');
  const src = (r.sources || []).map(s => `<div class="src">📖 Kaynak: ${s}</div>`).join('');
  const trace = (r.trace || []).map((t, i) =>
    `<div class="trace-step"><span class="ti">${i + 1}</span><code>${t.tool}(${Object.keys(t.input).join(', ')})</code></div>`).join('');
  const below = r.stock.below_safety;
  const woId = r.work_order ? r.work_order.work_order_id : '';
  const steps = (r.work_order ? r.work_order.steps : []);

  // Her adım: numara + başlık + ne yaptığını anlatan kısa açıklama + içerik
  $('#diagBody').innerHTML = `
    <div class="diag-intro">Ajan, seçilen arıza için aşağıdaki adımları <b>otonom</b> olarak yürüttü.
      Kritik karar (sipariş onayı) size bırakılır — ajan kendisi tamamlamaz.</div>

    <div class="dstep">
      <div class="dhead"><span class="dnum">1</span>
        <div class="dttl">Kök Neden<span class="dsub">Arızanın temel sebebi — geçmiş kayıt ve kılavuzlardan çıkarıldı</span></div></div>
      <div class="dbody">
        <div class="val">${r.root_cause}</div>
        <div class="conf"><div class="confbar"><i style="width:${conf}%;background:${cc}"></i></div>
          <span class="conftxt" style="color:${cc}">${confLbl} · %${conf}</span></div>
      </div>
    </div>

    <div class="dstep">
      <div class="dhead"><span class="dnum">2</span>
        <div class="dttl">Kanıtlar<span class="dsub">Bu sonuca dayanak oluşturan sensör verileri ve kaynaklar</span></div></div>
      <div class="dbody">
        <ul class="evidence">${ev}</ul>${src}
      </div>
    </div>

    <div class="dstep">
      <div class="dhead"><span class="dnum">3</span>
        <div class="dttl">İlgili Parça &amp; Stok<span class="dsub">Değişmesi gereken parça ve anlık stok durumu</span></div></div>
      <div class="dbody">
        <div class="val"><b>${r.part.part_code}</b> · ${r.part.name}</div>
        <div class="stockline ${below ? 'low' : 'okk'}">
          ${below ? '⚠️' : '✓'} Stok ${r.stock.on_hand} / ${r.stock.safety_stock} emniyet
          <span>${below ? 'emniyet stoğu altında — muadil/sipariş önerildi' : 'yeterli'}</span>
        </div>
      </div>
    </div>

    <div class="dstep">
      <div class="dhead"><span class="dnum">4</span>
        <div class="dttl">Onarım Adımları<span class="dsub">Teknisyene atanan iş emri${woId ? ' · ' + woId : ''}</span></div></div>
      <div class="dbody">
        <ul class="steps">${steps.map(s => `<li><span class="mk">•</span><span>${s}</span></li>`).join('')}</ul>
      </div>
    </div>

    <div class="dstep">
      <div class="dhead"><span class="dnum">5</span>
        <div class="dttl">Ajan Karar Zinciri<span class="dsub">Sonuca ulaşırken çağrılan araçlar (tool-use)</span></div></div>
      <div class="dbody">
        <div class="trace">${trace}</div>
      </div>
    </div>

    <div class="dstep" style="border-left:3px solid var(--accent);background:rgba(59,130,246,0.03)">
      <div class="dhead"><span class="dnum" style="background:var(--accent)">⚡</span>
        <div class="dttl">İş Emri<span class="dsub">MCP üzerinden dinamik iş emri oluştur</span></div></div>
      <div class="dbody">
        <button class="btn primary" id="createWoBtn" style="width:100%">📋 İş Emri Oluştur (MCP)</button>
        <div id="woCreateResult" style="margin-top:10px"></div>
      </div>
    </div>`;

  document.getElementById('createWoBtn').onclick = () => createWorkOrderFromDiag(r);
}

async function createWorkOrderFromDiag(diagResult) {
  const btn = document.getElementById('createWoBtn');
  const resultDiv = document.getElementById('woCreateResult');
  btn.disabled = true;
  btn.textContent = '⏳ MCP ile iş emri oluşturuluyor...';

  try {
    const r = await api('/api/work_order/create_from_diag', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fault_code: diagResult.fault_code,
        machine_id: diagResult.machine_id,
        root_cause: diagResult.root_cause,
        part_code: diagResult.part ? diagResult.part.part_code : '',
      }),
    });
    if (r.error) {
      resultDiv.innerHTML = `<div class="alt warn"><div class="note">❌ ${r.error}</div></div>`;
      btn.disabled = false;
      btn.textContent = '📋 İş Emri Oluştur (MCP)';
    } else {
      const toolsHtml = (r.tools_called || []).map(t => `🔧 ${t}`).join('<br>');
      resultDiv.innerHTML = `
        <div class="alt ok">
          <div class="h"><span class="c">${r.work_order_id}</span><span class="apill" style="background:var(--okbg);color:var(--ok)">Oluşturuldu</span></div>
          <div class="note">Teknisyen: <b>${r.technician}</b> · Parça: <b>${r.part_code}</b></div>
          <ul class="steps">${(r.steps || []).map(s => '<li><span class="mk">•</span><span>' + s + '</span></li>').join('')}</ul>
          ${toolsHtml ? '<div class="muted-note" style="margin-top:8px">📡 MCP Tool Çağrıları:<br>' + toolsHtml + '</div>' : ''}
        </div>`;
      btn.textContent = '✓ İş Emri Oluşturuldu';
      loadWorkOrders();
    }
  } catch (e) {
    resultDiv.innerHTML = `<div class="alt warn"><div class="note">❌ ${e.message}</div></div>`;
    btn.disabled = false;
    btn.textContent = '📋 İş Emri Oluştur (MCP)';
  }
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
  box.innerHTML = '';
  wos.forEach(w => {
    const steps = w.steps || [];
    const card = el('div', 'wo-card');
    card.innerHTML = `
      <div class="wo-head">
        <span class="c">${w.work_order_id}</span>
        <span class="nm">${w.part_code} · Teknisyen: ${w.technician}</span>
        <span class="apill" style="background:var(--okbg);color:var(--ok)">${w.status}</span>
        <span class="wo-caret">›</span>
      </div>
      <div class="wo-sub">${steps.length} adım · Olay: ${w.fault_id} · ${w.created_at}</div>`;
    card.querySelector('.wo-head').onclick = () => openWorkOrderModal(w);
    box.append(card);
  });
}

function openWorkOrderModal(w) {
  const steps = w.steps || [];
  closeWorkOrderModal();   // varsa önceki modalı kapat
  const overlay = el('div', 'wo-modal-overlay');
  overlay.id = 'woModal';
  overlay.innerHTML = `
    <div class="wo-modal" role="dialog" aria-modal="true" aria-label="İş emri detayı">
      <button class="wo-modal-close" aria-label="Kapat">&times;</button>
      <div class="wo-modal-head">
        <span class="c">${w.work_order_id}</span>
        <span class="apill" style="background:var(--okbg);color:var(--ok)">${w.status}</span>
      </div>
      <div class="wo-modal-body">
        <div class="wo-row"><div class="lbl">Kök Neden</div><div class="val">${w.root_cause || '—'}</div></div>
        <div class="wo-row"><div class="lbl">Onarım Adımları</div>
          <ul class="steps">${steps.map(s => `<li><span class="mk">•</span><span>${s}</span></li>`).join('') || '<li>—</li>'}</ul></div>
        <div class="wo-metarow">
          <span>Olay: <b>${w.fault_id}</b></span><span>Parça: <b>${w.part_code}</b></span>
          <span>Teknisyen: <b>${w.technician}</b></span><span>Durum: <b>${w.status}</b></span>
          <span>Oluşturma: <b>${w.created_at}</b></span>
        </div>
      </div>
    </div>`;
  // Kapatma: × butonu, arka plana tıklama, Esc
  overlay.querySelector('.wo-modal-close').onclick = closeWorkOrderModal;
  overlay.onclick = (e) => { if (e.target === overlay) closeWorkOrderModal(); };
  document.body.append(overlay);
  document.addEventListener('keydown', _woEscHandler);
}

function closeWorkOrderModal() {
  const m = $('#woModal');
  if (m) m.remove();
  document.removeEventListener('keydown', _woEscHandler);
}

function _woEscHandler(e) {
  if (e.key === 'Escape') closeWorkOrderModal();
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

// ---------- YOLO Parça Tespiti ----------
let yoloSelectedFile = null;

$('#yoloDrop').onclick = () => $('#yoloFile').click();
$('#yoloDrop').ondragover = e => { e.preventDefault(); e.currentTarget.style.borderColor = 'var(--ok)'; };
$('#yoloDrop').ondragleave = e => { e.currentTarget.style.borderColor = 'var(--accent)'; };
$('#yoloDrop').ondrop = e => {
  e.preventDefault();
  e.currentTarget.style.borderColor = 'var(--accent)';
  const f = e.dataTransfer.files[0];
  if (f) setYoloFile(f);
};
$('#yoloFile').onchange = e => { const f = e.target.files[0]; if (f) setYoloFile(f); };
$('#yoloClear').onclick = () => clearYoloFile();

function setYoloFile(f) {
  yoloSelectedFile = f;
  $('#yoloPreview').style.display = 'block';
  $('#yoloFileName').textContent = f.name;
  $('#yoloFileSize').textContent = (f.size / 1024 / 1024).toFixed(2) + ' MB';
  if (f.type.startsWith('image/')) {
    const url = URL.createObjectURL(f);
    $('#yoloPreviewImg').src = url;
    $('#yoloPreviewImg').style.display = 'block';
    $('#yoloPreviewVid').style.display = 'none';
  } else if (f.type.startsWith('video/')) {
    const url = URL.createObjectURL(f);
    $('#yoloPreviewVid').src = url;
    $('#yoloPreviewVid').style.display = 'block';
    $('#yoloPreviewImg').style.display = 'none';
  }
  $('#yoloResult').innerHTML = '';
}

function clearYoloFile() {
  yoloSelectedFile = null;
  $('#yoloPreview').style.display = 'none';
  $('#yoloPreviewImg').style.display = 'none';
  $('#yoloPreviewVid').style.display = 'none';
  $('#yoloFile').value = '';
  $('#yoloResult').innerHTML = '';
}

$('#yoloDetectBtn').onclick = async () => {
  if (!yoloSelectedFile) {
    $('#yoloResult').innerHTML = '<div class="alt warn"><div class="note">Lütfen önce bir resim veya video yükleyin.</div></div>';
    return;
  }
  $('#yoloResult').innerHTML = '<span class="spin"></span> Tespit yapılıyor… (orijinal boyutta analiz)';
  $('#yoloDetectBtn').disabled = true;

  const formData = new FormData();
  formData.append('file', yoloSelectedFile);

  try {
    const resp = await fetch('/api/yolo/detect', { method: 'POST', body: formData });
    const r = await resp.json();
    if (r.error) {
      $('#yoloResult').innerHTML = `<div class="alt warn"><div class="note">❌ ${r.message}</div></div>`;
    } else if (r.detections) {
      renderYoloImageResult(r);
    } else if (r.unique_detections !== undefined) {
      renderYoloVideoResult(r);
    }
  } catch (e) {
    $('#yoloResult').innerHTML = `<div class="alt warn"><div class="note">❌ Bağlantı hatası: ${e.message}</div></div>`;
  }
  $('#yoloDetectBtn').disabled = false;
};

function renderYoloImageResult(r) {
  let detsHtml = '';
  if (r.detections.length) {
    detsHtml = r.detections.map(d => {
      const partInfo = d.part_info ? `<div class="stk">Stok: ${d.part_info.on_hand}/${d.part_info.safety_stock} · ${d.part_info.name}</div>` : '';
      return `<div class="alt ok" style="margin-bottom:6px">
        <div class="h"><span class="c">${d.label_tr}</span>
          <span class="apill" style="background:var(--okbg);color:var(--ok)">%${Math.round(d.confidence*100)}</span>
          ${d.part_code ? `<span class="apill">${d.part_code}</span>` : ''}
        </div>
        <div class="note">Bbox: [${d.bbox.join(', ')}]</div>
        ${partInfo}
      </div>`;
    }).join('');
  } else {
    detsHtml = '<div class="alt warn"><div class="note">Parça tespit edilemedi.</div></div>';
  }

  $('#yoloResult').innerHTML = `
    <div style="margin-bottom:10px;font-weight:600;font-size:14px">📊 Sonuç: ${r.summary}</div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:10px">Orijinal boyut: ${r.original_size[0]}×${r.original_size[1]} px</div>
    ${r.annotated_b64 ? `<img src="data:image/jpeg;base64,${r.annotated_b64}" style="max-width:100%;border-radius:8px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.08)">` : ''}
    <div>${detsHtml}</div>`;
}

function renderYoloVideoResult(r) {
  let detsHtml = '';
  if (r.unique_detections.length) {
    detsHtml = r.unique_detections.map(d => {
      const partInfo = d.part_info ? `<div class="stk">Stok: ${d.part_info.on_hand}/${d.part_info.safety_stock} · ${d.part_info.name}</div>` : '';
      return `<div class="alt ok" style="margin-bottom:6px">
        <div class="h"><span class="c">${d.label_tr}</span>
          <span class="apill" style="background:var(--okbg);color:var(--ok)">Maks %${Math.round(d.max_confidence*100)}</span>
          ${d.part_code ? `<span class="apill">${d.part_code}</span>` : ''}
        </div>
        ${partInfo}
      </div>`;
    }).join('');
  } else {
    detsHtml = '<div class="alt warn"><div class="note">Video boyunca parça tespit edilemedi.</div></div>';
  }

  const timelineHtml = r.detections_per_frame.filter(f => f.count > 0).slice(0, 10).map(f =>
    `<div style="font-size:11px;padding:3px 0;border-bottom:1px solid var(--line)">
      ⏱ ${f.time_sec}s (frame ${f.frame_idx}) — ${f.count} tespit: ${f.detections.map(d => d.label_tr).join(', ')}
    </div>`
  ).join('');

  $('#yoloResult').innerHTML = `
    <div style="margin-bottom:10px;font-weight:600;font-size:14px">📊 Sonuç: ${r.summary}</div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:10px">
      Video: ${r.original_size[0]}×${r.original_size[1]} px · ${r.fps} FPS · ${r.total_frames} toplam frame · ${r.frames_analyzed} analiz edildi
    </div>
    ${r.best_frame_b64 ? `<div style="margin-bottom:12px"><div style="font-size:11px;color:var(--muted);margin-bottom:4px">En iyi frame (en çok tespit):</div><img src="data:image/jpeg;base64,${r.best_frame_b64}" style="max-width:100%;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.08)"></div>` : ''}
    <div style="margin-bottom:12px">${detsHtml}</div>
    ${timelineHtml ? `<div style="margin-top:10px"><div style="font-size:12px;font-weight:600;margin-bottom:6px">⏰ Zaman Çizelgesi</div>${timelineHtml}</div>` : ''}`;
}

// ---------- Sohbet ----------
const quickQs = [
  'Kritik stoktaki parçaları ve muadillerini göster',
  'KAYNAK-ROBOT-02 arızasının kök nedenini araştır',
  'HYD-4520-B için sipariş taslağı oluştur',
  'Bu haftaki toplam duruş kaç saat, en kötü gün hangisi?',
  'En sık tekrar eden arıza hangisi, önlem öner',
  'Tesisin genel bakım performansını özetle',
];
function initChat() {
  $('#quick').innerHTML = '';
  quickQs.forEach(q => { const b = el('button', null, q); b.onclick = () => ask(q); $('#quick').append(b); });
  addMsg('ai', 'Merhaba, bakım asistanınızım. Parça, sipariş, iş emri ve stok durumunu sorabilirsiniz.');
}

function parseMd(text) {
  // Basit markdown → HTML dönüştürücü
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Kod blokları (```)
  html = html.replace(/```([^`]*?)```/gs, '<pre><code>$1</code></pre>');
  // Inline kod
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Kalın
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // İtalik
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Başlıklar
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');
  // Tablo satırları
  html = html.replace(/^\|(.+)\|$/gm, (m, row) => {
    const cells = row.split('|').map(c => c.trim());
    if (cells.every(c => /^[-:]+$/.test(c))) return ''; // ayırıcı satır
    return '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
  });
  html = html.replace(/(<tr>.*<\/tr>\s*)+/gs, '<table class="md-table">$&</table>');
  // Liste
  html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\s*)+/gs, '<ul>$&</ul>');
  // Numaralı liste
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Paragraflar (boş satırlar)
  html = html.replace(/\n{2,}/g, '<br><br>');
  html = html.replace(/\n/g, '<br>');
  return html;
}

function addMsg(role, text) { const m = el('div', 'msg ' + role, role === 'ai' ? parseMd(text) : text.replace(/</g, '&lt;')); $('#msgs').append(m); $('#msgs').scrollTop = $('#msgs').scrollHeight; }
async function ask(q) {
  addMsg('user', q); $('#chatInp').value = '';
  const r = await api('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: q }) });
  addMsg('ai', r.answer);
  // Sipariş/iş emri oluşturulduysa panelleri güncelle
  if (r.answer && (r.answer.includes('sipariş') || r.answer.includes('TASLAK') || r.answer.includes('order') || r.answer.includes('iş emri'))) {
    refreshOrders();
    loadWorkOrders();
    loadOverview();
  }
}

async function refreshOrders() {
  const orders = await api('/api/orders');
  const box = $('#orderBody');
  const pending = orders.filter(o => o.status === 'pending_approval');
  if (!pending.length) { box.innerHTML = '<p class="muted-note">Bekleyen sipariş taslağı yok.</p>'; return; }
  // En son 3 siparişi göster (son oluşturulanlar üstte)
  const recent = pending.slice(0, 3);
  box.innerHTML = '';
  recent.forEach(o => {
    const div = el('div', '', '');
    div.style.marginBottom = '12px';
    box.append(div);
    drawOrderInto(div, o);
  });
  if (pending.length > 3) {
    const more = el('div', 'muted-note', `+ ${pending.length - 3} daha eski sipariş taslağı var`);
    more.style.textAlign = 'center';
    more.style.marginTop = '8px';
    box.append(more);
  }
}

function drawOrderInto(container, o) {
  const cls = o.status === 'approved' ? 'approved' : o.status === 'rejected' ? 'rejected' : 'pending';
  let acts = '';
  if (o.status === 'pending_approval') {
    acts = `<div class="acts"><button class="btn ok" data-id="${o.draft_id}" data-action="approve">✓ Onayla</button><button class="btn danger" data-id="${o.draft_id}" data-action="reject">✕ Reddet</button></div>`;
  }
  const warn = o.requires_manager_approval ? `<div class="warnbox">⚠️ Tutar eşiğin üzerinde — YÖNETİCİ onayı şart.</div>` : '';
  const finalMsg = o.status === 'approved' ? `<div class="status-final" style="color:var(--ok)">✓ Onaylandı — ${o.approved_by || ''}</div>`
    : o.status === 'rejected' ? `<div class="status-final" style="color:var(--crit)">✕ Reddedildi — ${o.approved_by || ''}</div>` : '';
  container.innerHTML = `<div class="order ${cls}">
      <div class="ttl">🧾 ${o.draft_id}</div>
      <div class="meta"><b>${o.part_code}</b> · ${o.name || ''}<br>
        Adet: <b>${o.quantity}</b> · Tahmini tutar: <b>${tr(o.est_cost)} TL</b><br>
        Durum: <b>${o.status === 'pending_approval' ? 'İnsan onayı bekliyor' : o.status}</b></div>
      ${warn}${finalMsg}${acts}
      <div class="muted-note" style="margin-top:10px">⛔ Bu taslak ajan tarafından onaylanmaz. Karar bakım planlama sorumlusuna aittir.</div>
    </div>`;
  container.querySelectorAll('[data-action]').forEach(btn => {
    btn.onclick = async () => {
      const approved = btn.dataset.action === 'approve';
      const result = await api(`/api/order/${btn.dataset.id}/decide`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, approver: 'Elif Demirtaş' })
      });
      drawOrderInto(container, result);
      loadOverview();
    };
  });
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
initChat();
