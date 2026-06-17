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
    </div>`;
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
        <span class="wo-caret">▾</span>
      </div>
      <div class="wo-sub">${steps.length} adım · Olay: ${w.fault_id} · ${w.created_at}</div>
      <div class="wo-detail">
        <div class="wo-row"><div class="lbl">Kök Neden</div><div class="val">${w.root_cause || '—'}</div></div>
        <div class="wo-row"><div class="lbl">Onarım Adımları</div>
          <ul class="steps">${steps.map(s => `<li><span class="mk">•</span><span>${s}</span></li>`).join('') || '<li>—</li>'}</ul></div>
        <div class="wo-metarow">
          <span>Olay: <b>${w.fault_id}</b></span><span>Parça: <b>${w.part_code}</b></span>
          <span>Teknisyen: <b>${w.technician}</b></span><span>Durum: <b>${w.status}</b></span>
          <span>Oluşturma: <b>${w.created_at}</b></span>
        </div>
      </div>`;
    card.querySelector('.wo-head').onclick = () => card.classList.toggle('open');
    box.append(card);
  });
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

// Galeri: örnek parçaları yükle
async function loadYoloSamples() {
  const samples = await api('/api/yolo/samples');
  const g = $('#yoloGallery'); g.innerHTML = '';
  samples.forEach(s => {
    const card = el('div', 'yolo-sample');
    card.style.cssText = 'cursor:pointer;border:1px solid var(--line);border-radius:10px;padding:6px;text-align:center;width:120px;transition:all .15s';
    card.innerHTML = `<img src="/api/yolo/sample-image/${s.image}" style="width:100%;height:80px;object-fit:cover;border-radius:6px;margin-bottom:4px">
      <div style="font-size:11px;font-weight:600;color:var(--ink)">${s.label_tr}</div>`;
    card.onmouseenter = () => { card.style.borderColor = 'var(--accent)'; card.style.boxShadow = '0 2px 8px rgba(59,130,246,.15)'; };
    card.onmouseleave = () => { card.style.borderColor = 'var(--line)'; card.style.boxShadow = 'none'; };
    card.onclick = async () => {
      // Resmi fetch edip YOLO'ya gönder
      const resp = await fetch(`/api/yolo/sample-image/${s.image}`);
      const blob = await resp.blob();
      const file = new File([blob], s.image, { type: 'image/jpeg' });
      setYoloFile(file);
      // Otomatik tespit başlat
      $('#yoloDetectBtn').click();
    };
    g.append(card);
  });
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

// ---------- Parça tanıma (eski) ----------
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
loadYoloSamples();
initChat();
