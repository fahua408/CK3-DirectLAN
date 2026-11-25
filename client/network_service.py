#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CK3-DirectLAN · 6 步自建 ZeroTier Planet 虚拟专网、电脑对电脑直连与唯一昵称锁核心引擎
====================================================================================
开源独立版网络引擎，不含任何第三方私有服务器地址或在线自动更新逻辑。
支持两种联机拓扑：
1. 【连接自建云服务器 / 房主节点】：玩家在界面填写自己搭建的云服务器 IP（或房主电脑 IP）与端口，
   自动执行 6 步虚拟局域网握手（同步自建 Planet -> 部署 zttap300 -> 启动本地 ZeroTier -> 入网 -> Controller 自动授权 -> WinIPBroadcast 广播转发与网卡 Metric=1）。
2. 【玩家电脑对电脑直连开服 (Host-to-Peer)】：房主无需购买云服务器，直接在客户端一键拉起本机内置的
   lan_server.py (--spawn-zt)，将房主自己的电脑变为 Planet 主节点，朋友填入房主电脑 IP 即可直连！
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_AUTH_PORT = 12030
DEFAULT_ZT_SERVER_PORT = 12020
ZT_LOCAL_PORT = 56814
DEFAULT_ADMIN_TOKEN = "ck3_open_admin"
ZT_PROGRAM_DATA = Path(r"C:\ProgramData\ZeroTier\One")


def get_project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PROJECT_ROOT = get_project_root()
ZERO_DIR = Path(PROJECT_ROOT) / "bin" / "zero"
if not ZERO_DIR.is_dir():
    ZERO_DIR = Path(PROJECT_ROOT) / "zero"
SERVER_SCRIPT = Path(PROJECT_ROOT) / "server" / "lan_server.py"
CONFIG_FILE = os.path.join(PROJECT_ROOT, "client_config.json")
DEBUG_LOG_DIR = Path(PROJECT_ROOT) / "debug_logs"
DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_LOG_FILE = DEBUG_LOG_DIR / "client_debug.log"


def detect_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("223.5.5.5", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def load_config_dict() -> dict:
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config_dict(cfg: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_client_id() -> str:
    cfg = load_config_dict()
    if "client_id" not in cfg or not cfg["client_id"]:
        cfg["client_id"] = str(uuid.uuid4())[:8]
        save_config_dict(cfg)
    return cfg["client_id"]


def load_saved_username() -> str:
    cid = load_client_id()
    saved = (load_config_dict().get("username") or "").strip()
    if not saved or saved.lower() == "anon":
        saved = f"Player_{cid[:4]}"
        save_username(saved)
    return saved


def save_username(name: str) -> None:
    cfg = load_config_dict()
    cid = cfg.get("client_id") or str(uuid.uuid4())[:8]
    cfg["client_id"] = cid
    clean = (name or "").strip()
    if not clean or clean.lower() == "anon":
        clean = f"Player_{cid[:4]}"
    cfg["username"] = clean
    save_config_dict(cfg)


def compute_deterministic_ip(client_id: str, subnet_prefix: str = "10.155.155") -> str:
    """根据客户端唯一 ID 计算固定虚拟 IP (10.155.155.10 ~ 10.155.155.249)"""
    crc = zlib.crc32(client_id.encode("utf-8")) & 0xFFFFFFFF
    last_octet = 10 + (crc % 240)
    return f"{subnet_prefix}.{last_octet}"


class NetworkService:
    def __init__(self, is_admin: bool = False, log_cb: Optional[Callable[[str], None]] = None):
        self.is_admin = is_admin
        self.log_cb = log_cb
        cfg = load_config_dict()

        self.server_host = (cfg.get("server_host") or DEFAULT_SERVER_HOST).strip()
        self.auth_port = int(cfg.get("auth_port", DEFAULT_AUTH_PORT))
        self.zt_server_port = int(cfg.get("zt_server_port", DEFAULT_ZT_SERVER_PORT))
        self.admin_token = (cfg.get("admin_token") or DEFAULT_ADMIN_TOKEN).strip()

        self.client_id = load_client_id()
        self.username = load_saved_username()
        self.force_tcp = bool(cfg.get("force_tcp", False))
        self.use_force_bind = bool(cfg.get("use_force_bind", True))
        self.use_relay_shield = bool(cfg.get("use_relay_shield", True))

        self.zt_proc: Optional[subprocess.Popen] = None
        self.winip_proc: Optional[subprocess.Popen] = None
        self.iperf_proc: Optional[subprocess.Popen] = None
        self.self_server_proc: Optional[subprocess.Popen] = None
        self.is_running = False

        self.nwid = cfg.get("nwid", "")
        self.zt_address = ""
        self.virtual_ip = "10.155.155.2" if is_admin else compute_deterministic_ip(self.client_id)
        self.host_ip = "10.155.155.2"
        self.is_allowed = is_admin
        self.name_conflict = False
        self.conflict_msg = ""
        self.ping_ms: Optional[float] = None
        self.link_mode = "准备就绪"
        self.nat_type = "未检测"
        self.nat_text = ""
        self.status_text = "未连接"
        self.light_color = "gray"
        self.peer_ips: List[str] = []

        self._auth_token = ""
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def log(self, msg: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        try:
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        if self.log_cb:
            try:
                self.log_cb(line)
            except Exception:
                pass

    def save_preferences(self) -> None:
        cfg = load_config_dict()
        cfg.update(
            {
                "client_id": self.client_id,
                "username": self.username,
                "server_host": self.server_host,
                "auth_port": self.auth_port,
                "zt_server_port": self.zt_server_port,
                "admin_token": self.admin_token,
                "force_tcp": self.force_tcp,
                "use_force_bind": self.use_force_bind,
                "use_relay_shield": self.use_relay_shield,
                "nwid": self.nwid,
            }
        )
        save_config_dict(cfg)

    def set_server_endpoint(self, host: str, auth_port: int = 12030, zt_port: int = 12020, admin_token: str = "") -> None:
        clean_host = (host or "").strip().replace("http://", "").replace("https://", "").rstrip("/")
        if ":" in clean_host:
            parts = clean_host.split(":", 1)
            clean_host = parts[0]
            if parts[1].isdigit():
                auth_port = int(parts[1])
        self.server_host = clean_host or DEFAULT_SERVER_HOST
        self.auth_port = int(auth_port or DEFAULT_AUTH_PORT)
        self.zt_server_port = int(zt_port or DEFAULT_ZT_SERVER_PORT)
        if admin_token:
            self.admin_token = admin_token.strip()
        self.save_preferences()

    def set_username(self, name: str) -> None:
        clean = (name or "").strip() or f"Player_{self.client_id[:4]}"
        self.username = clean
        self.save_preferences()

    @property
    def base_http_url(self) -> str:
        return f"http://{self.server_host}:{self.auth_port}"

    # =========================================================================
    # 玩家电脑对电脑直连模式 (房主本机一键开启 Planet + Controller 服务端)
    # =========================================================================
    def is_self_hosted_running(self) -> bool:
        return self.self_server_proc is not None and self.self_server_proc.poll() is None

    def start_self_hosted_node(self, public_ip: str = "", auth_port: int = 12030, zt_port: int = 12020, admin_token: str = "") -> Tuple[bool, str]:
        """在房主本机电脑直接拉起自建 Planet + Controller + 准入服务端 (免云服务器直连模式)"""
        if self.is_self_hosted_running():
            return True, "本机直连主节点已在运行中"

        if not SERVER_SCRIPT.is_file():
            return False, f"未找到内置服务端脚本: {SERVER_SCRIPT}"

        host_ip = (public_ip or "").strip() or detect_local_ip()
        token = (admin_token or "").strip() or self.admin_token or DEFAULT_ADMIN_TOKEN
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        py_exe = sys.executable if not getattr(sys, "frozen", False) else "python"

        cmd = [
            py_exe,
            str(SERVER_SCRIPT),
            "--public-ip",
            host_ip,
            "--auth-port",
            str(auth_port),
            "--zt-port",
            str(zt_port),
            "--admin-token",
            token,
            "--init-planet",
            "--spawn-zt",
        ]
        try:
            self.self_server_proc = subprocess.Popen(
                cmd,
                cwd=str(SERVER_SCRIPT.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
            self.set_server_endpoint(host_ip, auth_port=auth_port, zt_port=zt_port, admin_token=token)
            self.log(f"[SELF_HOST] 已在本机启动直连主节点: IP={host_ip}, 控制端口={auth_port}, 专网端口={zt_port}")
            return (
                True,
                f"本机联机主节点已启动！\n"
                f"• 朋友连接地址: {host_ip} (端口 {auth_port})\n"
                f"• 专网通信端口: UDP/TCP {zt_port} (请确保路由器/防火墙已放行)",
            )
        except Exception as e:
            return False, f"启动本机主节点失败: {e}"

    def stop_self_hosted_node(self) -> None:
        if self.self_server_proc:
            try:
                self.self_server_proc.terminate()
                self.self_server_proc.wait(timeout=3)
            except Exception:
                pass
            self.self_server_proc = None
            self.log("[SELF_HOST] 已关闭本机直连主节点")

    def test_server_reachability(self) -> Tuple[bool, dict, str]:
        """测试当前配置的自建服务器或房主电脑主节点是否连通"""
        try:
            req = urllib.request.Request(f"{self.base_http_url}/api/info", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                info = json.loads(resp.read().decode("utf-8", errors="ignore"))
                return True, info, "连接成功"
        except Exception as e:
            return False, {}, str(e)

    # =========================================================================
    # 唯一联机昵称校验与锁定
    # =========================================================================
    def check_and_reserve_username(self, name: str) -> Tuple[bool, str]:
        clean = (name or "").strip()
        if not clean:
            return False, "联机昵称不能为空！"
        if clean.lower() == "anon":
            return False, "请勿使用公共默认名【anon】，请设置你专属的英文或数字昵称！"

        url = f"{self.base_http_url}/api/check_name"
        req_data = {"player_id": self.client_id, "username": clean}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(req_data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ok = bool(data.get("ok", False))
                msg = data.get("message", "")
                if ok:
                    self.set_username(clean)
                    self.name_conflict = False
                    self.conflict_msg = ""
                    self.log(f"[NICKNAME_LOCK] 成功锁定唯一昵称: {clean} (client_id={self.client_id})")
                else:
                    self.log(f"[NICKNAME_CONFLICT] 昵称冲突被拒绝: {clean} -> {msg}")
                return ok, msg
        except Exception as e:
            self.set_username(clean)
            self.log(f"[NICKNAME_LOCAL] 服务端暂未连接，已先保存至本地 ({e})")
            return True, f"昵称【{clean}】已保存至本地（连入自建服务器/房主节点时将自动锁定唯一性）"

    # =========================================================================
    # 本地命令与 ZeroTier 控制平面 (127.0.0.1:56814)
    # =========================================================================
    def _run_cmd(self, cmd: List[str], timeout: int = 12) -> subprocess.CompletedProcess:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        return subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags)

    def _decode(self, raw: bytes) -> str:
        for enc in ("utf-8", "gbk", "cp936"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode("utf-8", errors="ignore")

    def _kill_exe(self, exe_name: str) -> None:
        if os.name == "nt":
            self._run_cmd(["taskkill", "/F", "/IM", exe_name, "/T"])

    def _get_zt_token(self) -> str:
        t_path = ZT_PROGRAM_DATA / "authtoken.secret"
        if t_path.exists():
            self._auth_token = t_path.read_text(encoding="utf-8", errors="ignore").strip()
        return self._auth_token

    def zt_api(self, path: str, method: str = "GET", body: Optional[dict] = None, timeout: int = 8) -> Any:
        token = self._get_zt_token()
        url = f"http://127.0.0.1:{ZT_LOCAL_PORT}{path}"
        headers = {"X-ZT1-Auth": token, "Content-Type": "application/json"}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            return json.loads(raw) if raw else {}

    # =========================================================================
    # 6 步核心虚拟局域网连接流水线
    # =========================================================================
    def start_tunnel(self) -> Tuple[bool, str]:
        if self.is_running:
            return True, "专网已在运行中"

        zt_exe = ZERO_DIR / "zerotier-one_x64.exe"
        if not zt_exe.is_file():
            return False, f"未找到 ZeroTier 核心组件: {zt_exe}"

        ok_srv, srv_info, err_srv = self.test_server_reachability()
        if not ok_srv:
            return (
                False,
                f"无法连接到目标服务器/房主节点 ({self.base_http_url})！\n"
                f"错误详情: {err_srv}\n\n"
                f"提示：\n"
                f"• 如果你是普通玩家，请在顶部填写房主提供的服务器 IP 或房主电脑 IP；\n"
                f"• 如果你是房主且没有云服务器，可在房主端点击【🖥️ 本机一键开服】。",
            )

        if srv_info.get("defaultNwid"):
            self.nwid = srv_info["defaultNwid"]
        if srv_info.get("ztPort"):
            self.zt_server_port = int(srv_info["ztPort"])
        self.save_preferences()

        ok_name, msg_name = self.check_and_reserve_username(self.username)
        if not ok_name:
            self.light_color = "red"
            self.name_conflict = True
            self.conflict_msg = msg_name
            self.status_text = f"🔴 昵称冲突：{msg_name}"
            return False, msg_name

        self.is_running = True
        self.light_color = "yellow"
        self.status_text = "[1/6] 正在同步自建 Planet 节点..."
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._connect_and_monitor_loop, daemon=True)
        self._thread.start()
        return True, f"正在连接专网节点 {self.server_host} (专属昵称: {self.username}, 虚拟 IP: {self.virtual_ip})..."

    def stop_tunnel(self) -> None:
        self._stop_event.set()
        self.is_running = False
        try:
            if self.nwid:
                self.zt_api(f"/network/{self.nwid}", method="DELETE", timeout=3)
        except Exception:
            pass
        for exe in ("zerotier-one_x64.exe", "WinIPBroadcast.exe", "iperf3.exe"):
            if not self.is_self_hosted_running() or exe != "zerotier-one_x64.exe":
                self._kill_exe(exe)
        self.light_color = "gray"
        self.status_text = "已断开连接"
        self.ping_ms = None
        self.log("[STOP_TUNNEL] 已断开专网连接")

    def _connect_and_monitor_loop(self) -> None:
        try:
            # ---------------- [1/6] 从自建服务器/房主节点同步 planet ----------------
            self.light_color = "yellow"
            self.status_text = f"[1/6] 正在从节点 ({self.server_host}) 获取 Planet..."
            self.log(f"[1/6] 正在从 {self.base_http_url}/planet 同步根节点配置...")

            ZT_PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
            planet_dst = ZT_PROGRAM_DATA / "planet"
            planet_bak = ZT_PROGRAM_DATA / "planet.orig.bak"
            if planet_dst.exists() and not planet_bak.exists():
                try:
                    shutil.copy2(planet_dst, planet_bak)
                except Exception:
                    pass

            if not self.is_self_hosted_running():
                self._kill_exe("zerotier-one_x64.exe")
            self._run_cmd(["net", "stop", "ZeroTierOneService"])

            self._run_cmd(["icacls", str(ZT_PROGRAM_DATA), "/inheritance:e", "/t"])
            self._run_cmd(["icacls", str(ZT_PROGRAM_DATA), "/grant", "everyone:(oi)(ci)(F)", "/t"])
            self._run_cmd(["netsh", "advfirewall", "set", "allprofiles", "state", "off"])

            with urllib.request.urlopen(f"{self.base_http_url}/planet", timeout=10) as resp:
                planet_bytes = resp.read()
            planet_dst.write_bytes(planet_bytes)
            self.log(f"[1/6] 成功同步自建 Planet ({len(planet_bytes)} 字节)")

            relay_str = f"{self.server_host}/{self.zt_server_port}"
            local_conf = {
                "settings": {
                    "softwareUpdate": "disable",
                    "primaryPort": ZT_LOCAL_PORT,
                    "tcpFallbackRelay": relay_str,
                }
            }
            if self.force_tcp:
                local_conf["settings"]["forceTcpRelay"] = True
            (ZT_PROGRAM_DATA / "local.conf").write_text(json.dumps(local_conf, indent=2), encoding="utf-8")

            # ---------------- [2/6] 部署虚拟网卡驱动与清理缓存 ----------------
            self.status_text = "[2/6] 正在部署虚拟网卡驱动 (zttap300)..."
            self.log("[2/6] 检查并部署 zttap300 虚拟网卡驱动...")
            for drv in ("zttap300.cat", "zttap300.inf", "zttap300.sys"):
                src = ZERO_DIR / drv
                if src.is_file():
                    try:
                        shutil.copy2(src, ZT_PROGRAM_DATA / drv)
                    except Exception:
                        pass

            for subdir in ("peers.d", "moons.d"):
                sd = ZT_PROGRAM_DATA / subdir
                if sd.exists():
                    shutil.rmtree(sd, ignore_errors=True)
                sd.mkdir(parents=True, exist_ok=True)

            # ---------------- [3/6] 启动本地 ZeroTier 客户端与测速服务 ----------------
            self.status_text = "[3/6] 正在启动 ZeroTier 虚拟网卡服务..."
            self.log("[3/6] 启动 zerotier-one_x64.exe -C -p56814...")
            zt_exe = ZERO_DIR / "zerotier-one_x64.exe"
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.zt_proc = subprocess.Popen(
                [str(zt_exe), "-C", f"-p{ZT_LOCAL_PORT}"],
                cwd=str(ZERO_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=flags,
            )

            zt_ready = False
            for _ in range(30):
                if self._stop_event.is_set():
                    return
                try:
                    st = self.zt_api("/status")
                    if isinstance(st, dict) and st.get("address"):
                        self.zt_address = st["address"]
                        zt_ready = True
                        break
                except Exception:
                    pass
                time.sleep(0.4)

            if not zt_ready:
                raise RuntimeError("ZeroTier 核心服务启动超时，请确保以管理员权限运行！")

            self.log(f"[3/6] 本机 ZeroTier 节点已启动! 节点 ID: {self.zt_address}")

            try:
                old_nets = self.zt_api("/network")
                if isinstance(old_nets, list):
                    for net in old_nets:
                        old_id = net.get("nwid")
                        if old_id and old_id != self.nwid:
                            self.zt_api(f"/network/{old_id}", method="DELETE")
            except Exception:
                pass

            iperf_exe = ZERO_DIR / "iperf3.exe"
            if iperf_exe.is_file():
                self._kill_exe("iperf3.exe")
                self.iperf_proc = subprocess.Popen(
                    [str(iperf_exe), "-s", "-p", "23456"],
                    cwd=str(ZERO_DIR),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )

            # ---------------- [4/6] 加入虚拟局域网 (nwid) ----------------
            self.status_text = f"[4/6] 正在加入虚拟局域网 ({self.nwid})..."
            self.log(f"[4/6] 加入虚拟网络 NWID: {self.nwid}...")
            self.zt_api(
                f"/network/{self.nwid}",
                method="POST",
                body={
                    "allowDNS": False,
                    "allowDefault": False,
                    "allowManaged": True,
                    "allowGlobal": False,
                    "netconfRevision": 1,
                },
                timeout=15,
            )

            # ---------------- [5/6] 上报服务端 Controller 进行唯一昵称核验、准入授权与 IP 绑定 ----------------
            self.status_text = "[5/6] 正在向服务端 Controller 申请节点授权与唯一昵称绑定..."
            self.log(f"[5/6] 上报节点 {self.zt_address} (昵称: {self.username}) 申请准入与绑定 IP ({self.virtual_ip})...")
            auth_ok, allowed, peer_ips = self._report_heartbeat()
            self.is_allowed = allowed
            self.peer_ips = peer_ips

            if allowed:
                for _ in range(16):
                    if self._stop_event.is_set():
                        return
                    try:
                        net_info = self.zt_api(f"/network/{self.nwid}")
                        addrs = net_info.get("assignedAddresses") or []
                        if addrs:
                            got_ip = addrs[0].split("/")[0]
                            if got_ip:
                                self.virtual_ip = got_ip
                                break
                    except Exception:
                        pass
                    time.sleep(0.5)

            # ---------------- [6/6] 启动 WinIPBroadcast 广播转发与设置虚拟网卡跃点数 metric=1 ----------------
            self.status_text = "[6/6] 正在优化 CK3 局域网广播与网卡优先级 (Metric=1)..."
            self.log("[6/6] 启动 WinIPBroadcast 并设置 ZeroTier 虚拟网卡跃点数 Metric=1...")
            self.start_winip_broadcast()
            self.optimize_zerotier_adapter_metric()
            if peer_ips:
                self._update_broadcasts(peer_ips)

            self.log(f"✅ 6 步虚拟专网连接完成！专属昵称: {self.username} | 本机虚拟 IP: {self.virtual_ip}")

            self._monitor_loop()

        except Exception as e:
            self.log(f"❌ 专网启动异常: {e}")
            self.is_running = False
            self.light_color = "red"
            self.status_text = f"启动失败: {e}"

    def start_winip_broadcast(self) -> None:
        winip_exe = ZERO_DIR / "WinIPBroadcast.exe"
        if not winip_exe.is_file():
            return
        self._kill_exe("WinIPBroadcast.exe")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.winip_proc = subprocess.Popen(
            [str(winip_exe), "run"],
            cwd=str(ZERO_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )

    def optimize_zerotier_adapter_metric(self) -> List[str]:
        optimized = []
        for iface in self.get_network_interfaces():
            desc = (iface.get("description") or "").lower()
            name = iface.get("name") or ""
            if "zerotier" in desc or "zttap" in desc or "zerotier" in name.lower():
                self._run_cmd(
                    [
                        "netsh",
                        "interface",
                        "ipv4",
                        "set",
                        "interface",
                        name,
                        "metric=1",
                        "forwarding=enabled",
                        "store=active",
                    ]
                )
                optimized.append(name)

        p_bat = ZERO_DIR / "priority.bat"
        if p_bat.is_file():
            self._run_cmd(["cmd.exe", "/c", str(p_bat)])
        return optimized

    def _monitor_loop(self) -> None:
        metric_optimized_once = False
        while not self._stop_event.is_set():
            if not self.zt_proc or self.zt_proc.poll() is not None:
                self.is_running = False
                self.light_color = "red"
                self.status_text = "ZeroTier 专网核心进程已退出"
                break

            try:
                net_info = self.zt_api(f"/network/{self.nwid}")
                addrs = net_info.get("assignedAddresses") or []
                if addrs:
                    got_ip = addrs[0].split("/")[0]
                    if got_ip and got_ip != self.virtual_ip:
                        self.virtual_ip = got_ip
                    if not metric_optimized_once:
                        self.optimize_zerotier_adapter_metric()
                        metric_optimized_once = True
            except Exception:
                pass

            auth_ok, allowed, peer_ips = self._report_heartbeat()
            self.is_allowed = allowed if auth_ok else False
            self.peer_ips = peer_ips

            if self.is_allowed and peer_ips:
                self._update_broadcasts(peer_ips)

            target_test_ip = "10.155.155.1" if self.is_admin else self.host_ip
            latency = self._ping_test(target_test_ip)
            if latency is None and not self.is_admin:
                latency = self._ping_test("10.155.155.1")
            self.ping_ms = latency
            self._check_p2p_mode()

            if self.name_conflict:
                self.light_color = "red"
                self.status_text = f"🔴 昵称冲突：{self.conflict_msg}"
            elif self.is_allowed:
                self.light_color = "green"
                if latency is not None:
                    self.status_text = f"🟢 通行正常 ({self.link_mode} | 延迟: {int(latency)} ms | 账号: {self.username} | IP: {self.virtual_ip})"
                else:
                    self.status_text = f"🟢 通行正常 ({self.link_mode} | 账号: {self.username} | IP: {self.virtual_ip})"
            else:
                self.light_color = "red"
                self.status_text = "🔴 阻断状态：等待房主放行许可 (Controller 未授权，请提醒房主审核)"

            for _ in range(30):
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)

    def _check_p2p_mode(self) -> None:
        try:
            peers = self.zt_api("/peer")
            if isinstance(peers, list):
                leafs = [p for p in peers if p.get("role") == "LEAF"]
                if any(not p.get("tunneled") and (p.get("paths") or []) for p in leafs):
                    self.link_mode = "P2P直连"
                    return
                elif leafs:
                    self.link_mode = "节点中转"
                    return
                planets = [p for p in peers if p.get("role") == "PLANET"]
                if planets and (planets[0].get("paths") or []):
                    self.link_mode = "已连Planet主节点"
                    return
        except Exception:
            pass
        self.link_mode = "强制TCP中继" if self.force_tcp else "P2P直连就绪"

    def _report_heartbeat(self) -> Tuple[bool, bool, List[str]]:
        url = f"{self.base_http_url}/api/heartbeat"
        req_data = {
            "player_id": self.client_id,
            "username": self.username,
            "virtual_ip": self.virtual_ip,
            "zt_address": self.zt_address,
            "nwid": self.nwid,
            "is_admin": self.is_admin,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(req_data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("nwid") and data["nwid"] != self.nwid:
                    self.nwid = data["nwid"]
                self.name_conflict = bool(data.get("name_conflict", False))
                self.conflict_msg = data.get("conflict_msg", "")
                return True, data.get("allowed", False), data.get("peer_ips", [])
        except Exception:
            return False, False, []

    def _update_broadcasts(self, peer_ips: List[str]) -> None:
        import patch_manager

        game_path = patch_manager.find_steam_ck3_path()
        if not game_path or not patch_manager.verify_ck3_path(game_path):
            return

        bin_dir = patch_manager.get_binaries_path(game_path)
        settings_dir = os.path.join(bin_dir, "steam_settings")
        if not os.path.isdir(settings_dir):
            return

        b_file = os.path.join(settings_dir, "custom_broadcasts.txt")
        lines = ["10.155.155.255", "10.155.155.1", "10.155.155.2", "255.255.255.255", "127.0.0.1"]
        for ip in peer_ips:
            if ip and ip != self.virtual_ip and ip not in lines:
                lines.append(ip)

        try:
            with open(b_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass

    def _ping_test(self, target_ip: str) -> Optional[float]:
        if not target_ip:
            return None
        try:
            res = self._run_cmd(["ping", "-n", "1", "-w", "800", target_ip], timeout=3)
            out = self._decode(res.stdout)
            if "TTL=" in out.upper() or "时间" in out or "time" in out.lower():
                m = re.search(r"[=<](\d+)\s*ms", out, re.IGNORECASE)
                if m:
                    return float(m.group(1))
                return 10.0
            return None
        except Exception:
            return None

    # =========================================================================
    # 网卡管理与 NAT 类型检测
    # =========================================================================
    def detect_nat_type(self) -> Tuple[str, str]:
        nat_exe = ZERO_DIR / "NATTest.exe"
        if not nat_exe.is_file():
            return ("未知", "未找到 NATTest.exe")
        try:
            res = self._run_cmd([str(nat_exe), "-H", "stun.miwifi.com", "-P", "3478"], timeout=10)
            out = self._decode(res.stdout)
            nat_type = "Unknown"
            for line in out.splitlines():
                if line.strip().startswith("NAT Type:"):
                    nat_type = line.split(":", 1)[1].strip()
                    break
            desc_map = {
                "Full Cone": "全锥形 NAT（无限制，适合作为电脑对电脑直连主节点）",
                "Restric NAT": "受限锥形 NAT（限制较少，优质 P2P 主机）",
                "Port Restricted Cone": "端口受限锥形 NAT（家庭宽带常见类型，支持 P2P 打洞直连）",
                "Symmetric NAT": "对称型 NAT（限制严格，无法打洞时将自动通过自建服务器中转）",
            }
            self.nat_type = nat_type
            self.nat_text = desc_map.get(nat_type, f"{nat_type}（普通主机）")
            return (self.nat_type, self.nat_text)
        except Exception as e:
            return ("检测失败", str(e))

    def get_network_interfaces(self) -> List[dict]:
        if os.name != "nt":
            return []
        interfaces: List[dict] = []
        try:
            r_res = self._run_cmd(["route", "print", "-4"])
            r_out = self._decode(r_res.stdout)
            desc_by_idx: Dict[str, str] = {}
            in_list = False
            for line in r_out.splitlines():
                if "接口列表" in line or "Interface List" in line:
                    in_list = True
                    continue
                if in_list and ("====" in line and len(desc_by_idx) > 0):
                    break
                if in_list and "..." in line:
                    parts = line.split("...")
                    idx = parts[0].strip()
                    desc = parts[-1].strip()
                    if idx.isdigit():
                        desc_by_idx[idx] = desc

            n_res = self._run_cmd(["netsh", "interface", "ipv4", "show", "interface"])
            n_out = self._decode(n_res.stdout)
            ipv4_by_name: Dict[str, dict] = {}
            for line in n_out.splitlines()[2:]:
                line_s = line.strip()
                if not line_s or "---" in line_s or "状态" in line_s or "State" in line_s:
                    continue
                cols = re.split(r"\s+", line_s, maxsplit=4)
                if len(cols) >= 5 and cols[0].isdigit():
                    idx, met, mtu, state, name = cols
                    ipv4_by_name[name] = {
                        "id": idx,
                        "metric": met,
                        "mtu": mtu,
                        "status": state,
                        "name": name,
                        "description": desc_by_idx.get(idx, ""),
                    }

            s_res = self._run_cmd(["netsh", "interface", "show", "interface"])
            s_out = self._decode(s_res.stdout)
            for line in s_out.splitlines()[2:]:
                line_s = line.strip()
                if not line_s or "---" in line_s or "管理员状态" in line_s or "Admin State" in line_s:
                    continue
                cols = re.split(r"\s+", line_s, maxsplit=3)
                if len(cols) >= 4:
                    admin_state, conn_state, _, name = cols
                    item = ipv4_by_name.get(
                        name,
                        {
                            "id": "",
                            "metric": "-",
                            "mtu": "-",
                            "status": conn_state,
                            "name": name,
                            "description": "",
                        },
                    )
                    item["admin_state"] = admin_state
                    interfaces.append(item)
            if not interfaces:
                for item in ipv4_by_name.values():
                    item["admin_state"] = "已启用"
                    interfaces.append(item)
        except Exception:
            pass
        return interfaces

    def set_interface_enabled(self, interface_name: str, enabled: bool) -> bool:
        state_str = "enabled" if enabled else "disabled"
        res = self._run_cmd(["netsh", "interface", "set", "interface", interface_name, state_str])
        return res.returncode == 0

    # =========================================================================
    # 管理员专用 API
    # =========================================================================
    def admin_get_players(self) -> Tuple[bool, list, str]:
        url = f"{self.base_http_url}/api/admin/players"
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.admin_token}"}, method="GET")
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return True, list(data.get("players", [])), data.get("mode", "auto")
        except Exception as e:
            return False, [], str(e)

    def admin_toggle_player(self, player_id: str, allow: bool) -> bool:
        url = f"{self.base_http_url}/api/admin/toggle"
        req_data = {"player_id": player_id, "action": "allow" if allow else "block"}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(req_data).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.admin_token}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                return resp.status == 200
        except Exception:
            return False

    def admin_release_player_name(self, player_id: str = "", username: str = "") -> bool:
        url = f"{self.base_http_url}/api/admin/release_name"
        req_data = {"player_id": player_id, "username": username}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(req_data).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.admin_token}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                return resp.status == 200
        except Exception:
            return False

    def admin_set_mode(self, mode: str) -> bool:
        url = f"{self.base_http_url}/api/admin/set_mode"
        req_data = {"mode": mode}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(req_data).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.admin_token}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                return resp.status == 200
        except Exception:
            return False
