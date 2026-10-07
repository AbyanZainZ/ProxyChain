// ==============================================================================
// PROXYCHAIN WEB DASHBOARD JAVASCRIPT
// ==============================================================================

let currentStatusData = null;
let pollTimer = null;

// DOM ELEMENTS
const valServerIp = document.getElementById('val-server-ip');
const statTotalProxies = document.getElementById('stat-total-proxies');
const statPortsRange = document.getElementById('stat-ports-range');
const statAliveProxies = document.getElementById('stat-alive-proxies');
const statAlivePct = document.getElementById('stat-alive-pct');
const statActiveConns = document.getElementById('stat-active-conns');
const statDataTransfer = document.getElementById('stat-data-transfer');
const statTotalConns = document.getElementById('stat-total-conns');
const tagParseCount = document.getElementById('tag-parse-count');

const cfgUser = document.getElementById('cfg-user');
const cfgPass = document.getElementById('cfg-pass');
const cfgStartPort = document.getElementById('cfg-start-port');
const proxiesTextarea = document.getElementById('proxies-textarea');

const btnSaveApply = document.getElementById('btn-save-apply');
const btnCheckHealth = document.getElementById('btn-check-health');
const btnCopyLive = document.getElementById('btn-copy-live');
const btnCopyEndpoints = document.getElementById('btn-copy-endpoints');
const btnPurgeDead = document.getElementById('btn-purge-dead');
const btnClearText = document.getElementById('btn-clear-text');
const tableFilter = document.getElementById('table-filter');
const portsTbody = document.getElementById('ports-tbody');
const toastEl = document.getElementById('pc-toast');
const healthStatusText = document.getElementById('health-check-status-text');

// FORMAT HELPER
function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function showToast(msg, isError = false) {
    toastEl.textContent = msg;
    toastEl.style.borderColor = isError ? '#ff5252' : '#00e5ff';
    toastEl.style.color = isError ? '#ff5252' : '#00e5ff';
    toastEl.style.display = 'block';
    setTimeout(() => {
        toastEl.style.display = 'none';
    }, 3500);
}

// FETCH INITIAL CONFIG & STATUS
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const data = await res.json();
        currentStatusData = data;
        renderDashboard(data);
    } catch (err) {
        console.error("Error fetching status:", err);
    }
}

// FETCH RAW PROXIES
async function fetchRawProxies() {
    try {
        const res = await fetch('/api/proxies/raw');
        if (res.ok) {
            const txt = await res.text();
            if (proxiesTextarea.value === "") {
                proxiesTextarea.value = txt;
                updateParseCount();
            }
        }
    } catch (e) {}
}

function updateParseCount() {
    const lines = proxiesTextarea.value.split('\n').filter(l => l.trim().length > 0 && !l.trim().startsWith('#'));
    tagParseCount.textContent = `${lines.length} Baris`;
}

proxiesTextarea.addEventListener('input', updateParseCount);

// RENDER DASHBOARD
function renderDashboard(data) {
    const srvIp = data.server_ip || '127.0.0.1';
    valServerIp.textContent = srvIp;

    // Config fields (only update if not focused)
    if (document.activeElement !== cfgUser) cfgUser.value = data.config.client_user || '';
    if (document.activeElement !== cfgPass) cfgPass.value = data.config.client_pass || '';
    if (document.activeElement !== cfgStartPort) cfgStartPort.value = data.config.proxy_start_port || 10001;

    // Metrics
    const total = data.total_proxies || 0;
    const alive = data.alive_proxies || 0;
    statTotalProxies.textContent = total;
    statAliveProxies.textContent = alive;
    const pct = total > 0 ? Math.round((alive / total) * 100) : 0;
    statAlivePct.textContent = `${pct}% Siap Pakai`;

    if (total > 0) {
        const startP = data.config.proxy_start_port || 10001;
        statPortsRange.textContent = `Port ${startP} - ${startP + total - 1}`;
    } else {
        statPortsRange.textContent = `Belum ada port aktif`;
    }

    let activeConns = 0;
    let totalConns = 0;
    let totalBytes = 0;

    data.ports.forEach(p => {
        activeConns += (p.active_conns || 0);
        totalConns += (p.total_conns || 0);
        totalBytes += (p.bytes_in || 0) + (p.bytes_out || 0);
    });

    statActiveConns.textContent = activeConns;
    statTotalConns.textContent = `${totalConns} total koneksi`;
    statDataTransfer.textContent = formatBytes(totalBytes);

    if (data.is_checking) {
        healthStatusText.innerHTML = `<span style="color: #ffd600;">🩺 Sedang memeriksa kesehatan proxy di latar belakang...</span>`;
    } else {
        healthStatusText.textContent = `System ready • Sync tiap 4 detik`;
    }

    renderTable(data.ports, srvIp, data.config.client_user, data.config.client_pass);
}

// RENDER TABLE
function renderTable(ports, srvIp, user, pass) {
    const filter = tableFilter.value.toLowerCase().trim();

    if (!ports || ports.length === 0) {
        portsTbody.innerHTML = `<tr><td colspan="7" class="pc-text-center pc-muted">Belum ada port proxy yang aktif. Klik "Simpan & Aktifkan Port" di sebelah kiri.</td></tr>`;
        return;
    }

    const filtered = ports.filter(p => {
        if (!filter) return true;
        const up = p.upstream || {};
        const str = `${p.port} ${up.host} ${up.country} ${up.city} ${up.exit_ip}`.toLowerCase();
        return str.includes(filter);
    });

    if (filtered.length === 0) {
        portsTbody.innerHTML = `<tr><td colspan="7" class="pc-text-center pc-muted">Tidak ada proxy yang cocok dengan filter pencarian "${filter}".</td></tr>`;
        return;
    }

    let html = '';
    filtered.forEach(item => {
        const up = item.upstream || {};
        const port = item.port;
        const endpoint = (user && pass) ? `${srvIp}:${port}:${user}:${pass}` : `${srvIp}:${port}`;

        // Status badge
        let statusBadge = '';
        if (up.is_alive === true) {
            statusBadge = `<span class="pc-badge pc-badge-alive">🟢 ALIVE</span>`;
        } else if (up.is_alive === false) {
            statusBadge = `<span class="pc-badge pc-badge-dead">🔴 DEAD</span>`;
        } else {
            statusBadge = `<span class="pc-badge pc-badge-pending">⚡ PENDING</span>`;
        }

        // Latency
        let latText = '-';
        if (up.latency_ms !== null && up.latency_ms !== undefined) {
            const col = up.latency_ms < 300 ? '#00e676' : (up.latency_ms < 800 ? '#ffd600' : '#ff5252');
            latText = `<span style="color: ${col}; font-weight: bold;">${up.latency_ms} ms</span>`;
        } else if (up.error) {
            latText = `<span style="color: #ff5252; font-size: 10px;">${up.error}</span>`;
        }

        // Location / Exit IP
        let locText = up.exit_ip || up.host || '-';
        if (up.country) {
            locText += ` <span style="color: #90caf9; font-size: 11px;">(${up.country})</span>`;
        }

        // Trafik
        const tf = formatBytes((item.bytes_in || 0) + (item.bytes_out || 0));

        html += `
        <tr>
            <td style="color: #00e5ff; font-weight: bold;">${port}</td>
            <td>
                <div class="pc-endpoint-cell">
                    <span>${endpoint}</span>
                    <span class="pc-copy-icon" title="Salin Endpoint" onclick="copyText('${endpoint}')">📋</span>
                </div>
            </td>
            <td><span style="color: #90caf9;">${up.display || '-'}</span></td>
            <td>${locText}</td>
            <td>${latText}</td>
            <td>${tf}</td>
            <td>${statusBadge}</td>
        </tr>
        `;
    });

    portsTbody.innerHTML = html;
}

tableFilter.addEventListener('input', () => {
    if (currentStatusData) {
        renderTable(currentStatusData.ports, currentStatusData.server_ip, currentStatusData.config.client_user, currentStatusData.config.client_pass);
    }
});

// UNIVERSAL CLIPBOARD HELPER (Works on HTTP & HTTPS)
async function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (e) {}
    }
    // Fallback untuk HTTP IP biasa tanpa SSL
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        return successful;
    } catch (err) {
        document.body.removeChild(textArea);
        return false;
    }
}

// COPY HELPER
window.copyText = async function(text) {
    const ok = await copyToClipboard(text);
    if (ok) {
        showToast(`📋 Berhasil disalin: ${text}`);
    } else {
        showToast(`Gagal menyalin ke clipboard.`, true);
    }
};

// BUTTON ACTIONS
btnSaveApply.addEventListener('click', async () => {
    const raw = proxiesTextarea.value.trim();
    if (!raw) {
        showToast("⚠️ Daftar proxy masih kosong!", true);
        return;
    }

    btnSaveApply.disabled = true;
    btnSaveApply.innerHTML = `<span>⏳ Menyimpan & Membuka Port...</span>`;

    try {
        // 1. Save config first
        await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                client_user: cfgUser.value.trim(),
                client_pass: cfgPass.value.trim(),
                proxy_start_port: parseInt(cfgStartPort.value) || 10001
            })
        });

        // 2. Save proxies and trigger re-sync
        const res = await fetch('/api/proxies', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ raw_text: raw })
        });
        const result = await res.json();
        showToast(result.message || "Berhasil diaktifkan!");
        await fetchStatus();
    } catch (e) {
        showToast("Terjadi kendala koneksi ke server.", true);
    } finally {
        btnSaveApply.disabled = false;
        btnSaveApply.innerHTML = `<span>🚀 SIMPAN & AKTIFKAN PORT</span>`;
    }
});

btnCheckHealth.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/check', { method: 'POST' });
        const data = await res.json();
        showToast(data.message);
        await fetchStatus();
    } catch (e) {
        showToast("Gagal memicu health-check.", true);
    }
});

if (btnCopyLive) {
    btnCopyLive.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/export?alive_only=true');
            if (!res.ok) {
                showToast("Gagal mengambil data live proxy dari server.", true);
                return;
            }
            const txt = await res.text();
            if (!txt || txt.trim() === "") {
                showToast("⚠️ Belum ada proxy berstatus ALIVE yang siap disalin.", true);
                return;
            }
            const ok = await copyToClipboard(txt);
            if (ok) {
                const count = txt.split('\n').filter(Boolean).length;
                showToast(`📋 Berhasil menyalin ${count} LIVE PROXY ke Clipboard!`);
            } else {
                showToast("Browser memblokir akses clipboard.", true);
            }
        } catch (e) {
            showToast("Gagal menyalin live proxy.", true);
        }
    });
}

btnCopyEndpoints.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/export');
        if (!res.ok) {
            showToast("Gagal mengambil data endpoint dari server.", true);
            return;
        }
        const txt = await res.text();
        if (!txt || txt.trim() === "") {
            showToast("Belum ada endpoint proxy aktif untuk disalin.", true);
            return;
        }
        const ok = await copyToClipboard(txt);
        if (ok) {
            const count = txt.split('\n').filter(Boolean).length;
            showToast(`📋 ${count} Endpoint berhasil disalin ke Clipboard!`);
        } else {
            showToast("Browser memblokir akses clipboard.", true);
        }
    } catch (e) {
        showToast("Gagal menyalin endpoint.", true);
    }
});

if (btnPurgeDead) {
    btnPurgeDead.addEventListener('click', async () => {
        if (!confirm("Hapus semua proxy yang berstatus DEAD (merah)?\n\nPort yang mati akan dinonaktifkan dan daftar proxy akan otomatis diperbarui.")) {
            return;
        }

        btnPurgeDead.disabled = true;
        btnPurgeDead.innerHTML = `<span>⏳ Menghapus...</span>`;

        try {
            const res = await fetch('/api/proxies/purge-dead', { method: 'POST' });
            if (!res.ok) {
                const errTxt = await res.text();
                showToast(`Gagal: ${errTxt || 'Server error'}`, true);
                return;
            }
            const data = await res.json();
            showToast(data.message, !data.success);
            if (data.success && data.new_raw_text !== undefined) {
                proxiesTextarea.value = data.new_raw_text;
                updateParseCount();
                await fetchStatus();
            }
        } catch (e) {
            showToast("Gagal membuang proxy dead.", true);
        } finally {
            btnPurgeDead.disabled = false;
            btnPurgeDead.innerHTML = `<span>🗑️ DELETE ALL DEAD PROXY</span>`;
        }
    });
}

btnClearText.addEventListener('click', () => {
    if (confirm("Kosongkan kotak teks proxy?")) {
        proxiesTextarea.value = '';
        updateParseCount();
        showToast("Kotak teks telah dikosongkan.");
    }
});

// START POLLING
fetchRawProxies();
fetchStatus();
pollTimer = setInterval(fetchStatus, 4000);
