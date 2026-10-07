# 🌐 PROXYCHAIN — Multi-Port Authenticated Proxy Gateway & Relay
### Universal Proxy Relay, Chaining, Auto-Healthcheck & Cyber Cockpit Web Dashboard

Project Location: `D:\ProjectABYAN\ProxyChain`

---

## 📌 Apa itu ProxyChain?

**ProxyChain** adalah sistem **Proxy Gateway & Forwarding Server** yang mengubah daftar proxy upstream (baik proxy publik gratisan maupun proxy privat berotentikasi) menjadi port-port proxy terpusat dengan format dan otentikasi seragam:

$$\text{Klien / Bot} \longrightarrow \mathbf{HOST:PORT:USER:PASS} \longrightarrow \text{ProxyChain Relay} \longrightarrow \text{Upstream Proxy} \longrightarrow \text{Target Web}$$

* **Target Web** hanya akan melihat IP dari **Upstream Proxy** (bukan IP asli klien, dan bukan IP VPS/Localhost).
* **Format Seragam:** Semua proxy Anda (meskipun format aslinya berantakan) akan diakses dengan kredensial kustom yang Anda tentukan sendiri (misal: `gemini:gemini`).

---

## 🚀 Fitur Utama

1. **Dual Mode Running:**
   * **🖥️ Localhost Mode (Windows):** Berjalan langsung di komputer Anda (`127.0.0.1`) untuk pengujian lokal, bot lokal, atau debugging.
   * **☁️ VPS Linux Mode (Ubuntu/Debian):** Berjalan 24/7 di VPS publik dengan systemd background service.
2. **🎛️ Modern Dark Cyber Cockpit Dashboard (`http://HOST:8080`):**
   * Tema visual gelap elegan (`#070f1a` deep navy dengan aksen neon cyan `#00e5ff`).
   * Kotak teks paste proxy instan (mendukung format `http://`, `socks5://`, `socks5|`, `ip:port:user:pass`, `user:pass@ip:port`).
   * Tombol satu klik **"📋 Salin Semua Endpoint Jadi"** dalam format `HOST:PORT:USER:PASS`.
3. **🩺 Asynchronous Live Health-Check:**
   * Otomatis menguji latency (ping ms) dan mendeteksi IP keluar serta negara (GeoIP) dari masing-masing proxy.
   * Memberikan badge status visual: `🟢 ALIVE` atau `🔴 DEAD`.
4. **🔒 Keamanan Penuh (Client Authentication):**
   * Setiap port dilindungi oleh username & password kustom Anda untuk mencegah akses liar dari bot internet saat di-deploy ke VPS publik.
5. **⚡ High-Performance Asyncio Engine:**
   * Menggunakan Python 3 `asyncio` streams murni (zero-copy socket piping), sangat ringan dan mampu melayani ratusan port simultan dengan penggunaan RAM < 50 MB.

---

## 📁 Struktur File Proyek

```text
D:\ProjectABYAN\ProxyChain/
├── ROADMAP.md              # Dokumentasi lengkap & petunjuk penggunaan
├── config.json             # Konfigurasi sistem (port awal, kredensial, host)
├── proxies.txt             # Daftar upstream proxy yang dimuat
├── requirements.txt        # Dependensi Python (FastAPI, Uvicorn, httpx, dll.)
├── checker.py              # Universal Parser & Async Health Checker
├── relay_engine.py         # Asynchronous Multi-Port Proxy Relay Engine
├── app.py                  # Backend FastAPI & REST API
├── static/
│   ├── index.html          # Web Dashboard Cyber Cockpit
│   ├── style.css           # Styling Dark Cyber Cockpit (#070f1a)
│   └── app.js              # Logika interaktif dashboard & real-time sync
├── run_localhost.bat       # Launcher 1-klik untuk Windows Localhost
└── deploy_vps.sh           # Script 1-baris instalasi otomatis untuk VPS Linux
```

---

## 💻 Cara Menjalankan di Localhost (Windows)

1. Buka folder `D:\ProjectABYAN\ProxyChain`.
2. Klik ganda (double-click) file **`run_localhost.bat`**.
3. Browser Anda akan otomatis terbuka ke alamat:
   👉 **`http://127.0.0.1:8080`**
4. Masukkan username & password yang Anda inginkan (default: `gemini` / `gemini`).
5. Tempel daftar proxy Anda di kotak teks, lalu klik **"🚀 Simpan & Aktifkan Port"**.
6. Uji proxy Anda di browser atau bot dengan format:
   `127.0.0.1:10001` (Username: `gemini`, Password: `gemini`).

---

## ☁️ Cara Deploy ke VPS Linux (Ubuntu / Debian)

Cukup jalankan 1 perintah berikut di terminal SSH VPS Anda:

```bash
curl -sSL https://raw.githubusercontent.com/.../deploy_vps.sh | bash
# atau upload folder ini ke VPS lalu jalankan:
bash deploy_vps.sh
```

Service akan otomatis terdaftar sebagai **`proxychain.service`** di systemd, menyala di latar belakang, dan otomatis aktif kembali saat VPS di-restart. Dashboard dapat diakses langsung via:
👉 **`http://IP_VPS:8080`**

---

## 📋 Catatan Firewall VPS
Pastikan port dibuka pada firewall penyedia VPS (misal Tencent Cloud Lighthouse / Oracle Cloud):
* Port Dashboard: `TCP 8080`
* Rentang Port Proxy: `TCP 10000 - 10500`
