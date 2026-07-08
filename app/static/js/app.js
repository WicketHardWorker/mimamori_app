const API_BASE = '/api';

async function fetchJSON(endpoint) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        return null;
    }
}

async function loadSummary() {
    const data = await fetchJSON('/summary');
    if (!data) return;
    const banner = document.getElementById('status-banner');
    const indicator = document.getElementById('status-indicator');
    const statusTitle = document.getElementById('status-title');
    const statusDesc = document.getElementById('status-desc');

    if (data.active_alerts > 0) {
        banner.className = 'status-banner alert';
        indicator.className = 'status-indicator alert';
        indicator.textContent = '⚠️';
        statusTitle.textContent = 'アラートがあります';
        statusDesc.textContent = `${data.active_alerts}件の未確認アラート`;
    } else if (data.is_active) {
        banner.className = 'status-banner active';
        indicator.className = 'status-indicator active';
        indicator.textContent = '✅';
        statusTitle.textContent = '活動中です';
        statusDesc.textContent = `最後の検知: ${data.last_activity_time || '--:--'} (${data.last_activity_device || ''})`;
    } else {
        banner.className = 'status-banner inactive';
        indicator.className = 'status-indicator inactive';
        indicator.textContent = '💤';
        statusTitle.textContent = '現在は静かです';
        statusDesc.textContent = data.last_activity_time
            ? `最後の活動: ${data.last_activity_time} (${data.last_activity_device || ''})`
            : 'まだ活動が記録されていません';
    }

    document.getElementById('motion-count').textContent = data.today_motion_count;
    document.getElementById('plug-count').textContent = data.today_plug_count;
    document.getElementById('alert-count').textContent = data.active_alerts;
    document.getElementById('device-count').textContent = `${data.devices_online}/${data.devices_total}`;
    const alertValue = document.getElementById('alert-count');
    alertValue.className = data.active_alerts > 0 ? 'card-value danger' : 'card-value success';
}

let timelineChart = null;
async function loadTimeline() {
    const data = await fetchJSON('/timeline');
    if (!data) return;
    const ctx = document.getElementById('timeline-canvas');
    if (!ctx) return;
    if (timelineChart) timelineChart.destroy();
    timelineChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.timeline.map(t => t.label),
            datasets: [
                { label: '動き検知', data: data.timeline.map(t => t.motion_count), backgroundColor: 'rgba(74,144,217,0.6)', borderColor: 'rgba(74,144,217,1)', borderWidth: 1 },
                { label: '電気ケトル', data: data.timeline.map(t => t.plug_count), backgroundColor: 'rgba(39,174,96,0.6)', borderColor: 'rgba(39,174,96,1)', borderWidth: 1 },
            ],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: { x: { ticks: { maxRotation: 0 } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } } },
    });
}

async function loadEvents() {
    const data = await fetchJSON('/events?limit=20');
    if (!data) return;
    const container = document.getElementById('event-list');
    if (data.length === 0) { container.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><p>まだイベントがありません</p></div>'; return; }
    const icons = { 'motion_detected': {icon:'🚶',cls:'motion',label:'動き検知'}, 'plug_on': {icon:'🔌',cls:'plug-on',label:'電源ON'}, 'plug_off': {icon:'⭕',cls:'plug-off',label:'電源OFF'} };
    container.innerHTML = data.map(e => { const i = icons[e.event_type]||{icon:'📋',cls:'',label:e.event_type}; const t = e.timestamp.split(' ')[1]||e.timestamp; return `<li class="event-item"><div class="event-icon ${i.cls}">${i.icon}</div><div class="event-info"><div class="event-name">${i.label}</div><div class="event-device">${e.device_name}</div></div><div class="event-time">${t}</div></li>`; }).join('');
}

async function loadDevices() {
    const data = await fetchJSON('/devices');
    if (!data) return;
    const container = document.getElementById('device-list');
    if (data.length === 0) { container.innerHTML = '<div class="empty-state"><div class="empty-icon">📡</div><p>デバイスが見つかりません</p></div>'; return; }
    const types = {'hub':'ハブ','sensor':'モーションセンサー','plug':'スマートプラグ'};
    container.innerHTML = data.map(d => `<div class="device-item"><div class="device-dot ${d.is_online?'online':'offline'}"></div><div class="device-info"><div class="device-name">${d.device_name}</div><div class="device-type">${types[d.device_type]||d.device_type}${d.ip_address?' / '+d.ip_address:''}</div></div></div>`).join('');
}

async function loadAlerts() {
    const data = await fetchJSON('/alerts?limit=10');
    if (!data) return;
    const container = document.getElementById('alert-list');
    if (data.length === 0) { container.innerHTML = '<div class="empty-state"><div class="empty-icon">✅</div><p>アラートはありません</p></div>'; return; }
    const types = {'morning_no_activity':'🌅 朝の確認','long_inactivity':'⚠️ 長時間不活動','device_offline':'📡 オフライン'};
    container.innerHTML = data.map(a => { const btn = a.status==='triggered'?`<button class="btn-small" onclick="ackAlert(${a.id})">確認</button>`:''; return `<div class="alert-item ${a.status}"><div class="alert-content"><div class="alert-message">${types[a.alert_type]||a.alert_type}: ${a.message}</div><div class="alert-time">${a.triggered_at}</div></div><div class="alert-action">${btn}</div></div>`; }).join('');
}

async function ackAlert(id) {
    await fetch(`${API_BASE}/alerts/${id}/acknowledge`, {method:'POST'});
    await loadAlerts(); await loadSummary();
}

async function loadDailySummary() {
    const data = await fetchJSON('/daily-summary?days=7');
    if (!data) return;
    const container = document.getElementById('summary-table-body');
    if (data.length === 0) { container.innerHTML = '<tr><td colspan="5">データがありません</td></tr>'; return; }
    container.innerHTML = data.map(s => `<tr><td>${s.date}</td><td>${s.first_activity_time||'-'} 〜 ${s.last_activity_time||'-'}</td><td>${s.motion_count}</td><td>${s.plug_on_count}</td><td>${s.max_inactivity_minutes.toFixed(0)}分</td></tr>`).join('');
}

async function loadAll() {
    document.getElementById('last-update').textContent = `最終更新: ${new Date().toLocaleTimeString('ja-JP')}`;
    await Promise.all([loadSummary(), loadTimeline(), loadEvents(), loadDevices(), loadAlerts(), loadDailySummary()]);
}

document.addEventListener('DOMContentLoaded', () => { loadAll(); setInterval(loadAll, 60000); });
function refreshDashboard() { loadAll(); }
