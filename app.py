import os
import json
import time
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
PROXIES_ACTIVE_PATH = BASE_DIR / "proxies_active.txt"
PROXIES_STAGING_PATH = BASE_DIR / "proxies_staging.txt"
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

# =============================================================================
# FILE STORAGE HELPERS (BOX 1 ACTIVE vs BOX 2 STAGING)
# =============================================================================
def load_active_proxies_file() -> str:
    if PROXIES_ACTIVE_PATH.exists():
        with open(PROXIES_ACTIVE_PATH, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if PROXIES_PATH.exists():
        with open(PROXIES_PATH, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""

def save_active_proxies_file(content: str):
    with open(PROXIES_ACTIVE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    with open(PROXIES_PATH, "w", encoding="utf-8") as f:
        f.write(content)

def load_staging_proxies_file() -> str:
    if PROXIES_STAGING_PATH.exists():
        with open(PROXIES_STAGING_PATH, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""

def save_staging_proxies_file(content: str):
    with open(PROXIES_STAGING_PATH, "w", encoding="utf-8") as f:
        f.write(content)

# =============================================================================
# PUBLIC IP AUTO-DETECTION
# =============================================================================
_cached_public_ip = None

def get_server_ip() -> str:
    global _cached_public_ip
    if _cached_public_ip:
        return _cached_public_ip

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
# APP LIFECYCLE & STATE
# =============================================================================
config = load_config()
relay_manager = RelayManager(
    start_port=config.get("proxy_start_port", 10001),
    client_user=config.get("client_user", "gemini"),
    client_pass=config.get("client_pass", "gemini"),
    bind_host=config.get("host", "0.0.0.0")
)

# Box 1: Production Relay Pool
active_proxies: List[ProxyItem] = []
is_checking_active = False

# Box 2: Scrape Testing Lab (Staging)
staging_proxies: List[ProxyItem] = []
is_checking_staging = False
staging_summary = {
    "total": 0,
    "alive": 0,
    "dead": 0,
    "status": "idle",
    "last_checked": None
}

async def run_active_check_task():
    global is_checking_active, active_proxies
    if is_checking_active or not active_proxies:
        return
    is_checking_active = True
    try:
        active_proxies = await check_all_proxies(active_proxies, max_concurrency=15, timeout=config.get("check_timeout", 6.0))
    finally:
        is_checking_active = False

async def run_staging_check_task(auto_transfer: bool = False):
    global is_checking_staging, staging_proxies, staging_summary
    if is_checking_staging or not staging_proxies:
        return
    is_checking_staging = True
    staging_summary["status"] = "testing"
    staging_summary["total"] = len(staging_proxies)
    try:
        staging_proxies = await check_all_proxies(staging_proxies, max_concurrency=20, timeout=5.0)
        alive_count = sum(1 for p in staging_proxies if p.is_alive is True)
        dead_count = sum(1 for p in staging_proxies if p.is_alive is False)
        staging_summary["alive"] = alive_count
        staging_summary["dead"] = dead_count
        staging_summary["status"] = "completed"
        staging_summary["last_checked"] = time.time()

        if auto_transfer and alive_count > 0:
            await do_transfer_staging_to_active(apply_relay=False)
    finally:
        is_checking_staging = False

async def do_transfer_staging_to_active(apply_relay: bool = False) -> dict:
    global active_proxies, staging_proxies
    live_staging = [p for p in staging_proxies if p.is_alive is True]
    if not live_staging:
        return {"success": False, "transferred": 0, "message": "Tidak ada proxy ALIVE di Box 2 untuk dipindahkan."}

    existing_keys = {(p.protocol, p.host, p.port, p.user) for p in active_proxies}
    new_items = []
    for p in live_staging:
        key = (p.protocol, p.host, p.port, p.user)
        if key not in existing_keys:
            existing_keys.add(key)
            new_items.append(p)

    if not new_items:
        return {
            "success": True,
            "transferred": 0,
            "total_active": len(active_proxies),
            "new_active_raw": "\n".join(p.raw for p in active_proxies if p.raw),
            "message": f"Semua ({len(live_staging)}) proxy ALIVE sudah ada di Box 1 (duplikat dilewati)."
        }

    active_proxies.extend(new_items)
    new_active_raw = "\n".join(p.raw for p in active_proxies if p.raw)
    save_active_proxies_file(new_active_raw)

    if apply_relay:
        await relay_manager.sync_proxies(active_proxies)

    return {
        "success": True,
        "transferred": len(new_items),
        "total_active": len(active_proxies),
        "new_active_raw": new_active_raw,
        "message": f"🎉 Berhasil memindahkan {len(new_items)} proxy ALIVE ke Box 1!"
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    global active_proxies, staging_proxies
    # Load Box 1 (Active)
    raw_active = load_active_proxies_file()
    active_proxies = parse_proxies_text(raw_active)
    if active_proxies:
        await relay_manager.sync_proxies(active_proxies)
        asyncio.create_task(run_active_check_task())

    # Load Box 2 (Staging)
    raw_staging = load_staging_proxies_file()
    staging_proxies = parse_proxies_text(raw_staging)
    staging_summary["total"] = len(staging_proxies)

    yield

    await relay_manager.stop_all()


app = FastAPI(title="ProxyChain Gateway v2", lifespan=lifespan)

# Mount static folder
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# =============================================================================
# REQUEST MODELS
# =============================================================================
class ActiveApplyRequest(BaseModel):
    raw_text: str

class StagingTestRequest(BaseModel):
    raw_text: Optional[str] = None
    auto_transfer: bool = False

class StagingSaveRequest(BaseModel):
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
    return "<h1>ProxyChain Gateway v2 is Running</h1><p>static/index.html not found.</p>"

@app.get("/api/status")
async def get_status():
    stats = relay_manager.get_all_stats()
    alive_active_count = sum(1 for p in active_proxies if p.is_alive is True)
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
        "box1_active": {
            "total": len(active_proxies),
            "alive": alive_active_count,
            "is_checking": is_checking_active
        },
        "box2_staging": {
            "total": len(staging_proxies),
            "alive": staging_summary.get("alive", 0),
            "dead": staging_summary.get("dead", 0),
            "status": staging_summary.get("status", "idle"),
            "is_checking": is_checking_staging
        },
        "ports": stats
    }

# =============================================================================
# BOX 1 (ACTIVE RELAY POOL) ROUTES
# =============================================================================
@app.get("/api/active/raw", response_class=PlainTextResponse)
async def get_active_raw():
    return load_active_proxies_file()

@app.post("/api/active/save")
async def save_active(payload: ActiveApplyRequest):
    save_active_proxies_file(payload.raw_text)
    return {"success": True, "message": "Box 1 berhasil disimpan."}

@app.post("/api/active/apply")
async def apply_active_relay(payload: ActiveApplyRequest, bg_tasks: BackgroundTasks):
    global active_proxies
    save_active_proxies_file(payload.raw_text)
    active_proxies = parse_proxies_text(payload.raw_text)
    await relay_manager.sync_proxies(active_proxies)
    bg_tasks.add_task(run_active_check_task)
    return {
        "success": True,
        "count": len(active_proxies),
        "message": f"🚀 Relay Berhasil Diaktifkan! {len(active_proxies)} port dibuka di VPS."
    }

@app.post("/api/active/check")
async def trigger_active_check(bg_tasks: BackgroundTasks):
    global is_checking_active
    if is_checking_active:
        return {"success": False, "message": "Pemeriksaan kesehatan Box 1 sedang berjalan."}
    bg_tasks.add_task(run_active_check_task)
    return {"success": True, "message": "Pemeriksaan kesehatan Box 1 dimulai di latar belakang!"}

@app.post("/api/active/purge-dead")
async def purge_dead_active():
    global active_proxies
    alive_only = [p for p in active_proxies if p.is_alive is True]
    removed_count = len(active_proxies) - len(alive_only)
    if removed_count == 0:
        return {"success": False, "removed": 0, "message": "Tidak ada proxy DEAD di Box 1."}

    new_raw_lines = [p.raw for p in alive_only if p.raw]
    new_raw_text = "\n".join(new_raw_lines)
    save_active_proxies_file(new_raw_text)

    active_proxies = alive_only
    await relay_manager.sync_proxies(active_proxies)

    return {
        "success": True,
        "removed": removed_count,
        "remaining": len(active_proxies),
        "new_raw_text": new_raw_text,
        "message": f"Berhasil menghapus {removed_count} proxy DEAD dari Box 1! Tersisa {len(active_proxies)} proxy ALIVE."
    }

# =============================================================================
# BOX 2 (SCRAPE TESTING LAB / STAGING) ROUTES
# =============================================================================
@app.get("/api/staging/raw", response_class=PlainTextResponse)
async def get_staging_raw():
    return load_staging_proxies_file()

@app.post("/api/staging/save")
async def save_staging(payload: StagingSaveRequest):
    global staging_proxies
    save_staging_proxies_file(payload.raw_text)
    staging_proxies = parse_proxies_text(payload.raw_text)
    staging_summary["total"] = len(staging_proxies)
    return {"success": True, "total": len(staging_proxies), "message": "Box 2 berhasil disimpan."}

@app.post("/api/staging/test")
async def trigger_staging_test(payload: StagingTestRequest, bg_tasks: BackgroundTasks):
    global staging_proxies, is_checking_staging
    if is_checking_staging:
        return {"success": False, "message": "Pengujian proxy di Box 2 sedang berjalan di latar belakang."}

    if payload.raw_text is not None and payload.raw_text.strip():
        save_staging_proxies_file(payload.raw_text)
        staging_proxies = parse_proxies_text(payload.raw_text)

    if not staging_proxies:
        return {"success": False, "message": "Box 2 masih kosong! Tempel proxy hasil scrape terlebih dahulu."}

    staging_summary["total"] = len(staging_proxies)
    staging_summary["alive"] = 0
    staging_summary["dead"] = 0
    bg_tasks.add_task(run_staging_check_task, payload.auto_transfer)
    return {
        "success": True,
        "total": len(staging_proxies),
        "message": f"🩺 Memulai pengujian {len(staging_proxies)} proxy hasil scrape di Box 2..."
    }

@app.get("/api/staging/status")
async def get_staging_status():
    return {
        "is_checking": is_checking_staging,
        "summary": staging_summary,
        "total": len(staging_proxies),
        "alive_proxies": [p.to_dict() for p in staging_proxies if p.is_alive is True],
        "dead_proxies": [p.to_dict() for p in staging_proxies if p.is_alive is False]
    }

@app.post("/api/staging/transfer-live")
async def transfer_staging_live():
    res = await do_transfer_staging_to_active(apply_relay=False)
    return res

@app.post("/api/staging/clear")
async def clear_staging():
    global staging_proxies
    staging_proxies.clear()
    save_staging_proxies_file("")
    staging_summary["total"] = 0
    staging_summary["alive"] = 0
    staging_summary["dead"] = 0
    staging_summary["status"] = "idle"
    return {"success": True, "message": "Box 2 (Scrape Lab) telah dikosongkan."}

# =============================================================================
# EXPORT & CONFIG ROUTES (BACKWARD COMPATIBLE)
# =============================================================================
@app.get("/api/export", response_class=PlainTextResponse)
async def export_endpoints(alive_only: bool = True):
    srv_ip = get_server_ip()
    lines = []
    stats = relay_manager.get_all_stats()
    u = relay_manager.client_user
    p = relay_manager.client_pass

    for s in stats:
        up = s.get("upstream", {})
        if alive_only and up.get("is_alive") is not True:
            continue
        port = s["port"]
        if u and p:
            lines.append(f"{srv_ip}:{port}:{u}:{p}")
        else:
            lines.append(f"{srv_ip}:{port}")

    return "\n".join(lines)

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

# Backward compatible legacy routes
@app.get("/api/proxies/raw", response_class=PlainTextResponse)
async def legacy_get_raw():
    return load_active_proxies_file()

@app.post("/api/proxies")
async def legacy_update_proxies(payload: ActiveApplyRequest, bg_tasks: BackgroundTasks):
    return await apply_active_relay(payload, bg_tasks)

@app.post("/api/check")
async def legacy_check(bg_tasks: BackgroundTasks):
    return await trigger_active_check(bg_tasks)

@app.post("/api/proxies/purge-dead")
async def legacy_purge_dead():
    return await purge_dead_active()


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run("app:app", host=cfg.get("host", "0.0.0.0"), port=cfg.get("dashboard_port", 8080), reload=False)
