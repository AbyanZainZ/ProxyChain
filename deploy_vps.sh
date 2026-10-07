#!/usr/bin/env bash
# ==============================================================================
# PROXYCHAIN - ONE-LINE VPS DEPLOYMENT SCRIPT (Ubuntu / Debian)
# ==============================================================================

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}==============================================================================${NC}"
echo -e "${CYAN}       PROXYCHAIN GATEWAY - ONE-LINE VPS INSTALLER (CYBER COCKPIT)           ${NC}"
echo -e "${CYAN}==============================================================================${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Harap jalankan script ini sebagai root (sudo bash deploy_vps.sh)${NC}"
  exit 1
fi

INSTALL_DIR="/opt/proxychain"
echo -e "${GREEN}[1/5] Memperbarui sistem & menginstall dependensi...${NC}"
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git curl ufw

echo -e "${GREEN}[2/5] Menyiapkan direktori proyek di ${INSTALL_DIR}...${NC}"

# Jika dijalankan di dalam folder clone lokal yang sudah ada file app.py
if [ -f "app.py" ] && [ -d "static" ]; then
    echo -e "${CYAN}Menyalin file dari direktori saat ini...${NC}"
    mkdir -p "$INSTALL_DIR"
    cp -a . "$INSTALL_DIR/"
else
    REPO_URL="${1:-https://github.com/AbyanZainZ/ProxyChain.git}"
    echo -e "${YELLOW}Mengunduh source code dari ${REPO_URL}...${NC}"
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo -e "${CYAN}Repository sudah ada di ${INSTALL_DIR}, memperbarui dengan git pull...${NC}"
        git -C "$INSTALL_DIR" pull
    else
        rm -rf "$INSTALL_DIR"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
fi

cd "$INSTALL_DIR"

echo -e "${GREEN}[3/5] Menyiapkan Python Virtual Environment & Library...${NC}"
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo -e "${GREEN}[4/5] Mengonfigurasi Firewall (UFW) untuk Port SSH, Dashboard & Proxy...${NC}"
ufw allow 22/tcp comment "SSH" || true
ufw allow 8080/tcp comment "ProxyChain Dashboard" || true
ufw allow 10000:10500/tcp comment "ProxyChain Proxy Ports" || true
ufw --force enable || true

echo -e "${GREEN}[5/5] Membuat Systemd Background Service (proxychain.service)...${NC}"
cat << 'EOF' > /etc/systemd/system/proxychain.service
[Unit]
Description=ProxyChain Authenticated Multi-Port Proxy Gateway
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/proxychain
ExecStart=/opt/proxychain/venv/bin/python3 /opt/proxychain/app.py
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable proxychain
systemctl restart proxychain

# Detect public IP
SERVER_IP=$(curl -s -4 https://api.ipify.org || curl -s -4 https://ifconfig.me || echo "IP_VPS_ANDA")

echo ""
echo -e "${CYAN}==============================================================================${NC}"
echo -e "${GREEN}🎉 PROXYCHAIN BERHASIL DIINSTALL & DIAKTIFKAN DI VPS!${NC}"
echo -e "${CYAN}==============================================================================${NC}"
echo -e "Web Dashboard  : ${YELLOW}http://${SERVER_IP}:8080${NC}"
echo -e "Default Auth   : ${CYAN}gemini / gemini${NC}"
echo -e "Port Range     : ${CYAN}10001 - 10500${NC}"
echo -e "Status Service : ${GREEN}systemctl status proxychain${NC}"
echo -e "Log Service    : ${GREEN}journalctl -u proxychain -f${NC}"
echo -e "${CYAN}==============================================================================${NC}"
echo -e "Buka browser Anda dan akses: ${YELLOW}http://${SERVER_IP}:8080${NC} untuk mulai mengelola proxy!"
