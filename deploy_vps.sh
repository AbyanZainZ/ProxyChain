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
mkdir -p "$INSTALL_DIR"

# Jika dijalankan di dalam folder clone
if [ -f "app.py" ] && [ -d "static" ]; then
    echo -e "${CYAN}Menyalin file dari direktori saat ini...${NC}"
    cp -r ./* "$INSTALL_DIR/" 2>/dev/null || cp -r * "$INSTALL_DIR/"
else
    # Jika dijalankan via curl langsung dari GitHub
    REPO_URL="${1}"
    if [ -z "$REPO_URL" ]; then
        read -p "Masukkan URL GitHub Repository Anda (cth: https://github.com/username/ProxyChain.git): " REPO_URL
    fi
    echo -e "${YELLOW}Mengunduh source code dari ${REPO_URL}...${NC}"
    rm -rf /tmp/proxychain_tmp
    git clone "$REPO_URL" /tmp/proxychain_tmp
    cp -r /tmp/proxychain_tmp/* "$INSTALL_DIR/"
    rm -rf /tmp/proxychain_tmp
fi

cd "$INSTALL_DIR"

echo -e "${GREEN}[3/5] Menyiapkan Python Virtual Environment & Library...${NC}"
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo -e "${GREEN}[4/5] Mengonfigurasi Firewall (UFW) untuk Port Dashboard & Proxy...${NC}"
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
