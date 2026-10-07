import os
import json
import asyncio
import socket
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from checker import ProxyItem, parse_proxies_text, check_all_proxies
from relay_engine import RelayManager

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
PROXIES_PATH = BASE_DIR / "proxies.txt"
STATIC_DIR = BASE_DIR / "static"

# =============================================================================
# DEFAULT CONFIG LOADER & SAVER
# =============================================================================
DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "dashboard_port": 8080,
    "proxy_start_port": 10001,
    "client_user": "gemini",
    "client_pass": "gemini",
    "check_target_url": "http://api.ipify.org",
    "check_timeout": 6.0,
    "auto_check_interval_minutes": 15
}

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {**DEFAULT_CONFIG, **cfg}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def load_proxies_file() -> str:
    if PROXIES_PATH.exists():
        with open(PROXIES_PATH, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""

def save_proxies_file(content: str):
    with open(PROXIES_PATH, "w", encoding="utf-8") as f:
        f.write(content)

_cached_public_ip = None

def get_server_ip() -> str:
    global _cached_public_ip
    if _cached_public_ip:
        return _cached_public_ip

    # 1. Prioritaskan deteksi Public IP asli jika berada di VPS / Cloud (Tencent, AWS, GCP, Oracle)
    import urllib.request
    endpoints = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com"
    ]
    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.88.1"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                detected = resp.read().decode("utf-8").strip()
                if detected and not detected.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168.", "127.")):
                    _cached_public_ip = detected
                    return detected
        except Exception:
            pass

    # 2. Fallback ke IP LAN jika offline atau di Localhost murni
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# =============================================================================
# APP LIFECYCLE
# =============================================================================
config = load_config()
relay_manager = RelayManager(
    start_port=config.get("proxy_start_port", 10001),
    client_user=config.get("client_user", "gemini"),
    client_pass=config.get("client_pass", "gemini"),
    bind_host=config.get("host", "0.0.0.0")
)
active_proxies: List[ProxyItem] = []
is_checking = False

async def run_health_check_task():
    global is_checking, active_proxies
    if is_checking or not active_proxies:
        return
    is_checking = True
    try:
        active_proxies = await check_all_proxies(active_proxies, max_concurrency=12, timeout=config.get("check_timeout", 6.0))
    finally:
        is_checking = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    global active_proxies
    raw_text = load_proxies_file()
    active_proxies = parse_proxies_text(raw_text)
    if active_proxies:
        await relay_manager.sync_proxies(active_proxies)
        # Run initial health check in background
        asyncio.create_task(run_health_check_task())

    yield

    await relay_manager.stop_all()


app = FastAPI(title="ProxyChain Gateway", lifespan=lifespan)

# Mount static folder
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# =============================================================================
# MODELS
# =============================================================================
class ProxiesUpdateRequest(BaseModel):
    raw_text: str

class ConfigUpdateRequest(BaseModel):
    client_user: str
    client_pass: str
    proxy_start_port: int


# =============================================================================
# ROUTES
# =============================================================================
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return "<h1>ProxyChain Gateway is Running</h1><p>static/index.html not found yet.</p>"

@app.get("/api/status")
async def get_status():
    stats = relay_manager.get_all_stats()
    alive_count = sum(1 for p in active_proxies if p.is_alive is True)
    return {
        "status": "online",
        "server_ip": get_server_ip(),
        "config": {
            "client_user": relay_manager.client_user,
            "client_pass": relay_manager.client_pass,
            "proxy_start_port": relay_manager.start_port,
            "bind_host": relay_manager.bind_host,
            "dashboard_port": config.get("dashboard_port", 8080)
        },
        "total_proxies": len(active_proxies),
        "alive_proxies": alive_count,
        "is_checking": is_checking,
        "ports": stats
    }

@app.get("/api/proxies/raw", response_class=PlainTextResponse)
async def get_raw_proxies():
    return load_proxies_file()

@app.post("/api/proxies")
async def update_proxies(payload: ProxiesUpdateRequest, bg_tasks: BackgroundTasks):
    global active_proxies
    save_proxies_file(payload.raw_text)
    active_proxies = parse_proxies_text(payload.raw_text)
    await relay_manager.sync_proxies(active_proxies)
    bg_tasks.add_task(run_health_check_task)
    return {
        "success": True,
        "count": len(active_proxies),
        "message": f"Berhasil memuat dan mengaktifkan {len(active_proxies)} proxy!"
    }

@app.post("/api/config")
async def update_config(payload: ConfigUpdateRequest):
    global config
    config["client_user"] = payload.client_user.strip()
    config["client_pass"] = payload.client_pass.strip()
    config["proxy_start_port"] = max(1024, min(65000, payload.proxy_start_port))
    save_config(config)

    relay_manager.client_user = config["client_user"]
    relay_manager.client_pass = config["client_pass"]
    relay_manager.start_port = config["proxy_start_port"]

    if active_proxies:
        await relay_manager.sync_proxies(active_proxies)

    return {"success": True, "config": config}

@app.post("/api/check")
async def trigger_check(bg_tasks: BackgroundTasks):
    global is_checking
    if is_checking:
        return {"success": False, "message": "Pengecekan kesehatan proxy sedang berjalan."}
    bg_tasks.add_task(run_health_check_task)
    return {"success": True, "message": "Proses health-check dimulai di latar belakang!"}

@app.post("/api/proxies/purge-dead")
async def purge_dead_proxies():
    global active_proxies
    alive_only = [p for p in active_proxies if p.is_alive is True]
    removed_count = len(active_proxies) - len(alive_only)
    if removed_count == 0:
        return {"success": False, "removed": 0, "message": "Tidak ada proxy DEAD yang ditemukan."}

    new_raw_lines = [p.raw_line for p in alive_only]
    new_raw_text = "\n".join(new_raw_lines)
    save_proxies_file(new_raw_text)

    active_proxies = alive_only
    await relay_manager.sync_proxies(active_proxies)

    return {
        "success": True,
        "removed": removed_count,
        "remaining": len(active_proxies),
        "new_raw_text": new_raw_text,
        "message": f"Berhasil membuang {removed_count} proxy DEAD! Tersisa {len(active_proxies)} proxy ALIVE."
    }

@app.get("/api/export", response_class=PlainTextResponse)
async def export_endpoints():
    srv_ip = get_server_ip()
    lines = []
    stats = relay_manager.get_all_stats()
    u = relay_manager.client_user
    p = relay_manager.client_pass

    for s in stats:
        port = s["port"]
        if u and p:
            lines.append(f"{srv_ip}:{port}:{u}:{p}")
        else:
            lines.append(f"{srv_ip}:{port}")

    return "\n".join(lines)


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run("app:app", host=cfg.get("host", "0.0.0.0"), port=cfg.get("dashboard_port", 8080), reload=False)
