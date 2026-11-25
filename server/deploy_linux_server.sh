#!/usr/bin/env bash
# ============================================================================
# CK3-DirectLAN · Linux 云服务器一键自建部署脚本
# 支持系统: Ubuntu / Debian / CentOS / Rocky / AlmaLinux
# 用法:
#   chmod +x deploy_linux_server.sh
#   sudo ./deploy_linux_server.sh <你的服务器公网IP> [管理密码:默认ck3_open_admin] [控制端口:默认12030] [专网端口:默认12020]
# ============================================================================
set -e

PUBLIC_IP="${1:-}"
ADMIN_TOKEN="${2:-ck3_open_admin}"
AUTH_PORT="${3:-12030}"
ZT_PORT="${4:-12020}"
INSTALL_DIR="/opt/ck3-directlan"

if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP=$(curl -s4 ifconfig.me || curl -s4 icanhazip.com || hostname -I | awk '{print $1}')
fi

echo "============================================================"
echo " 正在部署 CK3-DirectLAN 自建 ZeroTier Planet 联机主节点"
echo " 服务器公网 IP : $PUBLIC_IP"
echo " 准入控制端口  : $AUTH_PORT (TCP)"
echo " ZeroTier 端口 : $ZT_PORT (UDP & TCP)"
echo " 房主管理密码  : $ADMIN_TOKEN"
echo "============================================================"

# 1. 安装 python3 与 zerotier-one
if ! command -v python3 >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update && apt-get install -y python3 curl
    elif command -v yum >/dev/null 2>&1; then
        yum install -y python3 curl
    fi
fi

if ! command -v zerotier-one >/dev/null 2>&1; then
    echo "[*] 正在安装 ZeroTier One..."
    curl -s https://install.zerotier.com | bash
fi

# 2. 配置 ZeroTier 监听端口与 TCP 中继回退支持
mkdir -p /var/lib/zerotier-one
cat >/var/lib/zerotier-one/local.conf <<EOF
{
  "settings": {
    "primaryPort": ${ZT_PORT},
    "secondaryPort": 9993,
    "allowTcpFallbackRelay": true
  }
}
EOF

systemctl enable zerotier-one || true
systemctl restart zerotier-one || true
sleep 2

# 3. 准备服务端程序并生成自建 Planet
mkdir -p "$INSTALL_DIR/server"
cp -f "$(dirname "$0")/lan_server.py" "$INSTALL_DIR/server/lan_server.py"

echo "[*] 正在生成自建加密签名 Planet 文件..."
python3 "$INSTALL_DIR/server/lan_server.py" \
    --public-ip "$PUBLIC_IP" \
    --auth-port "$AUTH_PORT" \
    --zt-port "$ZT_PORT" \
    --admin-token "$ADMIN_TOKEN" \
    --zt-home "/var/lib/zerotier-one" \
    --init-planet &
PID=$!
sleep 3
kill $PID 2>/dev/null || true

if [ -f "$INSTALL_DIR/server/data/planet_dist/planet" ]; then
    cp -f "$INSTALL_DIR/server/data/planet_dist/planet" /var/lib/zerotier-one/planet
    systemctl restart zerotier-one
    sleep 2
    echo "[+] 已应用自建 Planet 并重启 ZeroTier One！"
fi

# 4. 放行系统防火墙端口
if command -v ufw >/dev/null 2>&1; then
    ufw allow "${AUTH_PORT}/tcp" >/dev/null 2>&1 || true
    ufw allow "${ZT_PORT}/udp" >/dev/null 2>&1 || true
    ufw allow "${ZT_PORT}/tcp" >/dev/null 2>&1 || true
elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port="${AUTH_PORT}/tcp" >/dev/null 2>&1 || true
    firewall-cmd --permanent --add-port="${ZT_PORT}/udp" >/dev/null 2>&1 || true
    firewall-cmd --permanent --add-port="${ZT_PORT}/tcp" >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
fi

# 5. 注册并启动 systemd 守护服务
cat >/etc/systemd/system/ck3-directlan.service <<EOF
[Unit]
Description=CK3-DirectLAN Self-Hosted ZeroTier Planet & Auth Server
After=network.target zerotier-one.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}/server
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/server/lan_server.py --public-ip ${PUBLIC_IP} --auth-port ${AUTH_PORT} --zt-port ${ZT_PORT} --admin-token ${ADMIN_TOKEN} --zt-home /var/lib/zerotier-one
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ck3-directlan
systemctl restart ck3-directlan

echo "============================================================"
echo "✅ 部署完成！服务已启动并设为开机自启。"
echo "👉 请确保在云服务器安全组/防火墙放行以下端口："
echo "   1) TCP ${AUTH_PORT} (准入控制 & Planet 自动分发)"
echo "   2) UDP ${ZT_PORT}   (ZeroTier Planet 核心握手中继端口 - 必开!)"
echo "   3) TCP ${ZT_PORT}   (ZeroTier TCP 增强连接支持)"
echo ""
echo "👉 在客户端填入以下信息即可联机："
echo "   • 服务器地址: ${PUBLIC_IP}"
echo "   • 控制端口  : ${AUTH_PORT}"
echo "   • 专网端口  : ${ZT_PORT}"
echo "   • 房主密码  : ${ADMIN_TOKEN}"
echo "============================================================"
