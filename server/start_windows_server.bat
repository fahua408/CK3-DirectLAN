@echo off
chcp 65001 >nul
title CK3-DirectLAN · Windows 自建联机服务端 (ZeroTier Planet + Controller + 准入控制)

cd /d "%~dp0"
echo ====================================================================
echo   CK3-DirectLAN · Windows 一键开服脚本 (支持云服务器或玩家电脑直连)
echo ====================================================================
echo.
set /p PUB_IP=请输入本机的公网 IP 或局域网 IP (直接回车则自动检测本机 IP): 
set /p ADMIN_PWD=请设置房主管理密码 (直接回车默认 ck3_open_admin): 
set /p AUTH_PORT=请输入准入控制与 Planet 分发端口 (直接回车默认 12030): 
set /p ZT_PORT=请输入服务端 ZeroTier Planet 端口 (直接回车默认 12020): 

if "%ADMIN_PWD%"=="" set ADMIN_PWD=ck3_open_admin
if "%AUTH_PORT%"=="" set AUTH_PORT=12030
if "%ZT_PORT%"=="" set ZT_PORT=12020

if "%PUB_IP%"=="" (
    python "%~dp0lan_server.py" --auth-port %AUTH_PORT% --zt-port %ZT_PORT% --admin-token "%ADMIN_PWD%" --init-planet --spawn-zt
) else (
    python "%~dp0lan_server.py" --public-ip %PUB_IP% --auth-port %AUTH_PORT% --zt-port %ZT_PORT% --admin-token "%ADMIN_PWD%" --init-planet --spawn-zt
)
pause
