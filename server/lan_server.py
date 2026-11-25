#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CK3-DirectLAN · 自建 ZeroTier Planet 根服务器 + Controller 准入控制 + 唯一昵称锁服务端
=====================================================================================
开源独立版服务端，支持两种部署运行方式：
1. 【玩家自建云服务器模式】：部署在玩家自己的 Linux / Windows 云服务器上；
2. 【玩家电脑对电脑直连模式】：由房主在自己电脑上通过客户端一键拉起 (--spawn-zt)，朋友直接输入房主电脑 IP 直连！

核心职责：
- 自动根据指定的公网/局域网 IP 生成加密签名的自建 ZeroTier Planet 文件并分发 (/planet)
- 自动对接本机 ZeroTier Controller API 创建虚拟局域网 (10.155.155.0/24)
- 提供全服唯一联机昵称锁 (/api/check_name)，防止免 P 社账号模式下多人重名冲突
- 提供红绿灯准入控制 (/api/heartbeat, /api/admin/players, /api/admin/toggle, /api/admin/set_mode)
"""

import argparse
import hashlib
import http.server
import json
import os
import random
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
PLANET_DIR = DATA_DIR / "planet_dist"
CONFIG_FILE = DATA_DIR / "server_config.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PLANET_DIR.mkdir(parents=True, exist_ok=True)


def detect_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("223.5.5.5", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_default_zt_home(spawn_mode: bool = False) -> Path:
    if os.name == "nt" or spawn_mode:
        return DATA_DIR / "zt_server_home"
    return Path("/var/lib/zerotier-one")


def get_zt_binary() -> str:
    if os.name == "nt":
        for candidate in [
            PROJECT_ROOT / "bin" / "zero" / "zerotier-one_x64.exe",
            PROJECT_ROOT / "zero" / "zerotier-one_x64.exe",
        ]:
            if candidate.is_file():
                return str(candidate)
        return "zerotier-one_x64.exe"
    for candidate in ["/usr/sbin/zerotier-one", "zerotier-one"]:
        if shutil.which(candidate) or os.path.exists(candidate):
            return candidate
    return "zerotier-one"


PUBLIC_IP = os.environ.get("CK3_PUBLIC_IP", "")
LISTEN_PORT = int(os.environ.get("CK3_AUTH_PORT", "12030"))
ZT_PRIMARY_PORT = int(os.environ.get("CK3_ZT_PORT", "12020"))
ZT_SECONDARY_PORT = 9993
ADMIN_TOKEN = os.environ.get("CK3_ADMIN_TOKEN", "ck3_open_admin")
ZT_HOME_DIR = get_default_zt_home()

DEFAULT_CONFIG = {
    "mode": "auto",  # auto: 自由加入模式; whitelist: 房主白名单审核模式
    "host_ip": "10.155.155.2",
    "subnet_prefix": "10.155.155",
    "default_nwid": "",
    "whitelisted_players": [],
    "registered_names": {},
}

PLAYERS: dict[str, dict] = {}
ROOMS: dict[str, dict] = {}
CONFIG = DEFAULT_CONFIG.copy()
LOCK = threading.RLock()


class ZeroTierController:
    """对接本机 ZeroTier One Controller HTTP API"""

    def __init__(self, zt_home: Path | None = None, primary_port: int = 12020):
        self.zt_home = zt_home or ZT_HOME_DIR
        self.primary_port = primary_port
        self._auth_token = ""

    @property
    def auth_token(self) -> str:
        t_file = self.zt_home / "authtoken.secret"
        if t_file.exists():
            self._auth_token = t_file.read_text(encoding="utf-8", errors="ignore").strip()
        return self._auth_token

    @property
    def api_port(self) -> int:
        p_file = self.zt_home / "zerotier-one.port"
        if p_file.exists():
            try:
                return int(p_file.read_text(encoding="utf-8", errors="ignore").strip())
            except Exception:
                pass
        return self.primary_port

    def request(self, path: str, method: str = "GET", body: dict | None = None) -> dict | list:
        last_err = None
        for port in (self.api_port, self.primary_port, ZT_SECONDARY_PORT):
            try:
                url = f"http://127.0.0.1:{port}{path}"
                headers = {
                    "X-ZT1-Auth": self.auth_token,
                    "Content-Type": "application/json",
                }
                data = json.dumps(body).encode("utf-8") if body is not None else None
                req = urllib.request.Request(url, data=data, method=method, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                    return json.loads(raw) if raw else {}
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(f"ZeroTier Controller 请求失败 ({path}): {last_err}")

    def get_address(self) -> str:
        st = self.request("/status")
        return st["address"]

    def ensure_network(self, nwid: str = "", name: str = "CK3_DirectLAN", subnet_prefix: str = "10.155.155") -> str:
        ctrl_addr = self.get_address()
        if nwid and len(nwid) == 16 and nwid.startswith(ctrl_addr):
            try:
                net = self.request(f"/controller/network/{nwid}")
                if isinstance(net, dict) and net.get("nwid") == nwid:
                    return nwid
            except Exception:
                pass

        payload = {
            "name": name[:60],
            "private": True,
            "enableBroadcast": True,
            "multicastLimit": 64,
            "mtu": 2800,
            "v4AssignMode": {"zt": True},
            "ipAssignmentPools": [
                {
                    "ipRangeStart": f"{subnet_prefix}.1",
                    "ipRangeEnd": f"{subnet_prefix}.254",
                }
            ],
            "routes": [
                {
                    "target": f"{subnet_prefix}.0/24",
                    "via": None,
                }
            ],
            "rules": [{"type": "ACTION_ACCEPT"}],
        }
        target_path = (
            f"/controller/network/{nwid}"
            if (nwid and len(nwid) == 16 and nwid.startswith(ctrl_addr))
            else f"/controller/network/{ctrl_addr}______"
        )
        net = self.request(target_path, method="POST", body=payload)
        return net["nwid"]

    def join_local_network(self, nwid: str) -> None:
        try:
            self.request(
                f"/network/{nwid}",
                method="POST",
                body={
                    "allowManaged": True,
                    "allowDNS": False,
                    "allowDefault": False,
                    "allowGlobal": False,
                },
            )
        except Exception:
            pass

    def set_member_auth(self, nwid: str, zt_address: str, authorized: bool, assign_ip: str = "") -> dict:
        if not nwid or not zt_address or len(zt_address) != 10:
            return {}
        body: dict = {
            "authorized": bool(authorized),
            "activeBridge": False,
        }
        if assign_ip:
            body["ipAssignments"] = [assign_ip]
        try:
            return self.request(f"/controller/network/{nwid}/member/{zt_address}", method="POST", body=body)
        except Exception as e:
            print(f"[!] Controller 授权节点 {zt_address} 异常: {e}")
            return {}


CONTROLLER: ZeroTierController | None = None


def check_and_claim_nickname(player_id: str, username: str) -> tuple[bool, str]:
    """全服唯一联机昵称锁（大小写不敏感）"""
    clean_name = (username or "").strip()
    if not clean_name:
        return False, "联机昵称不能为空！"
    if len(clean_name) > 24:
        return False, "联机昵称长度不能超过 24 个字符！"
    if clean_name.lower() == "anon":
        return False, "请勿使用公共默认名【anon】，请修改为你专属的英文或数字昵称！"

    name_key = clean_name.lower()
    reg_map: dict = CONFIG.setdefault("registered_names", {})

    existing = reg_map.get(name_key)
    if existing and existing.get("player_id") != player_id:
        owner_id = existing.get("player_id")
        return False, f"昵称【{clean_name}】已被其他玩家 (ID: {owner_id}) 绑定锁定，请更换一个专属昵称！"

    for pid, pinfo in PLAYERS.items():
        if pid != player_id and (pinfo.get("username") or "").strip().lower() == name_key:
            return False, f"昵称【{clean_name}】当前正被在线玩家 (ID: {pid}) 使用，请更换其他昵称！"

    old_keys = [k for k, v in reg_map.items() if v.get("player_id") == player_id and k != name_key]
    for ok in old_keys:
        reg_map.pop(ok, None)

    reg_map[name_key] = {
        "player_id": player_id,
        "username": clean_name,
        "updated_at": int(time.time()),
    }
    if player_id in PLAYERS:
        PLAYERS[player_id]["username"] = clean_name
        PLAYERS[player_id]["name_conflict"] = False

    save_config()
    return True, f"昵称【{clean_name}】已在服务端为您唯一锁定（他人不可同名，改名时旧名自动释放）！"


def release_nickname_by_player_or_name(player_id: str = "", username: str = "") -> int:
    reg_map: dict = CONFIG.setdefault("registered_names", {})
    removed = 0
    keys_to_del = []
    for k, v in reg_map.items():
        if (player_id and v.get("player_id") == player_id) or (username and k == username.strip().lower()):
            keys_to_del.append(k)
    for k in keys_to_del:
        reg_map.pop(k, None)
        removed += 1
    if removed > 0:
        save_config()
    return removed


def generate_server_planet(public_ip: str, zt_port: int, zt_home: Path, output_dir: Path) -> dict:
    """使用 ZeroTier 内置 idtool 生成指向指定 IP:Port 的加密签名 Planet 与 Moon 文件"""
    output_dir.mkdir(parents=True, exist_ok=True)
    zt_home.mkdir(parents=True, exist_ok=True)
    id_pub = zt_home / "identity.public"
    id_sec = zt_home / "identity.secret"
    zt_bin = get_zt_binary()

    def run_idtool(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
        if shutil.which("zerotier-idtool") and os.name != "nt":
            cmd = ["zerotier-idtool"] + args
        else:
            cmd = [zt_bin, "-i"] + args
        return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=True)

    if not id_pub.exists() or not id_sec.exists():
        run_idtool(["generate", str(id_sec), str(id_pub)])

    endpoints = [f"{public_ip}/{zt_port}"]
    if ZT_SECONDARY_PORT != zt_port:
        endpoints.append(f"{public_ip}/{ZT_SECONDARY_PORT}")

    res = run_idtool(["initmoon", str(id_pub)])
    world_cfg = json.loads(res.stdout)
    world_cfg["roots"][0]["stableEndpoints"] = endpoints
    node_id = world_cfg["id"]

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        moon_cfg = dict(world_cfg)
        moon_cfg["worldType"] = "moon"
        mj = td_path / "moon.json"
        mj.write_text(json.dumps(moon_cfg, indent=2), encoding="utf-8")
        run_idtool(["genmoon", str(mj)], cwd=td_path)
        m_files = list(td_path.glob("*.moon"))
        target_moon = output_dir / m_files[0].name
        shutil.copy2(m_files[0], target_moon)
        m_files[0].unlink()

        planet_cfg = dict(world_cfg)
        planet_cfg["worldType"] = "planet"
        pj = td_path / "planet.json"
        pj.write_text(json.dumps(planet_cfg, indent=2), encoding="utf-8")
        run_idtool(["genmoon", str(pj)], cwd=td_path)
        p_files = list(td_path.glob("*.moon"))
        target_planet = output_dir / "planet"
        shutil.copy2(p_files[0], target_planet)

    meta = {
        "nodeId": node_id,
        "publicIp": public_ip,
        "endpoints": endpoints,
        "planetPath": str(target_planet),
        "moonPath": str(target_moon),
        "generatedAt": int(time.time()),
    }
    (output_dir / "world_config.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def load_config():
    global CONFIG
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            CONFIG.update(saved)
        except Exception as e:
            print(f"[-] 加载配置失败: {e}")

    if "registered_names" not in CONFIG or not isinstance(CONFIG["registered_names"], dict):
        CONFIG["registered_names"] = {}

    try:
        nwid = CONTROLLER.ensure_network(
            nwid=CONFIG.get("default_nwid", ""),
            name="CK3_DirectLAN",
            subnet_prefix=CONFIG.get("subnet_prefix", "10.155.155"),
        )
        if nwid != CONFIG.get("default_nwid"):
            CONFIG["default_nwid"] = nwid
            save_config()

        ctrl_addr = CONTROLLER.get_address()
        CONTROLLER.set_member_auth(nwid, ctrl_addr, True, f"{CONFIG.get('subnet_prefix', '10.155.155')}.1")
        if os.name != "nt":
            CONTROLLER.join_local_network(nwid)
        print(f"[+] 自建 Planet 虚拟局域网已就绪! NWID: {nwid} (Controller 节点: {ctrl_addr})")

        if nwid not in ROOMS:
            ROOMS[nwid] = {
                "id": 1,
                "nwid": nwid,
                "name": "CK3 默认自建专网主房间",
                "game": "Crusader Kings III",
                "owner_uid": "admin",
                "nickname": "Host",
                "password": "",
                "hasPassword": False,
                "remark": "长效自建联机房间",
                "subnet_prefix": CONFIG.get("subnet_prefix", "10.155.155"),
                "server": 1,
                "created_at": int(time.time() * 1000),
                "members": {},
                "messages": [],
                "member_version": 1,
            }
    except Exception as e:
        print(f"[!] 初始化 ZeroTier Controller 提示: {e}")
    save_config()


def save_config():
    try:
        CONFIG_FILE.write_text(json.dumps(CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[-] 保存配置失败: {e}")


def cleanup_offline_players():
    while True:
        time.sleep(15)
        now = time.time()
        with LOCK:
            offline = [pid for pid, data in PLAYERS.items() if now - data.get("last_seen", 0) > 90]
            for pid in offline:
                del PLAYERS[pid]


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class RequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if any(
            self.path.startswith(p)
            for p in ("/api/heartbeat", "/api/status", "/api/admin/players", "/api/room/detail", "/api/room/list")
        ):
            return
        sys.stdout.write(f"[Server] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, code: int, data: dict | list):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-ZT1-Auth")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path, filename: str = ""):
        if not file_path.exists() or not file_path.is_file():
            self._send_json(404, {"error": "file not found"})
            return
        file_size = file_path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(file_size))
        self.send_header("Access-Control-Allow-Origin", "*")
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}")
        self.end_headers()
        with open(file_path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def do_OPTIONS(self):
        self._send_json(200, {"status": "ok"})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        qs = urllib.parse.parse_qs(parsed.query)

        # 1. 分发自建 ZeroTier Planet 与 Moon 节点文件
        if path == "/planet" or path.endswith("/planet"):
            p_file = PLANET_DIR / "planet"
            if not p_file.exists() and (ZT_HOME_DIR / "planet").exists():
                p_file = ZT_HOME_DIR / "planet"
            self._send_file(p_file, "planet")
            return

        if path == "/moons.json":
            moons = [f"moons/{p.name}" for p in PLANET_DIR.glob("*.moon")]
            self._send_json(200, moons)
            return

        if path.startswith("/moons/") and path.endswith(".moon"):
            self._send_file(PLANET_DIR / os.path.basename(path))
            return

        # 2. 服务器与 Planet/Controller 节点信息: /api/info & /api/health
        if path in ("/api/info", "/api/health"):
            ctrl_ok = False
            ctrl_addr = ""
            try:
                ctrl_addr = CONTROLLER.get_address()
                ctrl_ok = True
            except Exception as e:
                ctrl_addr = str(e)
            p_file = PLANET_DIR / "planet"
            p_md5 = hashlib.md5(p_file.read_bytes()).hexdigest() if p_file.exists() else ""
            with LOCK:
                self._send_json(
                    200,
                    {
                        "status": True,
                        "health": "running",
                        "serverName": "CK3-DirectLAN Self-Hosted Planet Node",
                        "publicIp": PUBLIC_IP,
                        "ztPort": ZT_PRIMARY_PORT,
                        "tcpRelayPort": ZT_PRIMARY_PORT,
                        "tcpFallbackRelay": f"{PUBLIC_IP}/{ZT_PRIMARY_PORT}",
                        "controllerOnline": ctrl_ok,
                        "controllerAddress": ctrl_addr,
                        "defaultNwid": CONFIG.get("default_nwid", ""),
                        "subnetPrefix": CONFIG.get("subnet_prefix", "10.155.155"),
                        "planetReady": p_file.exists(),
                        "planetMd5": p_md5,
                        "mode": CONFIG["mode"],
                        "online_players": len(PLAYERS),
                        "registered_names_count": len(CONFIG.get("registered_names", {})),
                    },
                )
            return

        # 3. 玩家查询状态: /api/status?player_id=xxx
        if path == "/api/status":
            pid = qs.get("player_id", [""])[0]
            with LOCK:
                if pid in PLAYERS:
                    p = PLAYERS[pid]
                    p["last_seen"] = time.time()
                    peer_ips = [item["ip"] for item in PLAYERS.values() if item.get("ip") and item.get("allowed", False)]
                    self._send_json(
                        200,
                        {
                            "allowed": p.get("allowed", False),
                            "name_conflict": p.get("name_conflict", False),
                            "conflict_msg": p.get("conflict_msg", ""),
                            "username": p.get("username", "Unknown"),
                            "virtual_ip": p.get("ip", ""),
                            "zt_address": p.get("zt_address", ""),
                            "nwid": p.get("nwid") or CONFIG.get("default_nwid", ""),
                            "host_ip": CONFIG["host_ip"],
                            "mode": CONFIG["mode"],
                            "peer_ips": peer_ips,
                            "server_time": time.time(),
                        },
                    )
                else:
                    self._send_json(
                        200,
                        {
                            "allowed": False,
                            "msg": "not_registered",
                            "nwid": CONFIG.get("default_nwid", ""),
                        },
                    )
            return

        # 4. 管理员获取在线玩家与已绑定昵称列表: /api/admin/players
        if path == "/api/admin/players":
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {ADMIN_TOKEN}":
                self._send_json(401, {"error": "unauthorized"})
                return

            with LOCK:
                player_list = []
                now = time.time()
                seen_pids = set()
                for pid, info in PLAYERS.items():
                    seen_pids.add(pid)
                    player_list.append(
                        {
                            "id": pid,
                            "username": info.get("username", ""),
                            "ip": info.get("ip", ""),
                            "zt_address": info.get("zt_address", ""),
                            "nwid": info.get("nwid") or CONFIG.get("default_nwid", ""),
                            "allowed": info.get("allowed", False),
                            "name_conflict": info.get("name_conflict", False),
                            "online": (now - info.get("last_seen", 0) < 35),
                            "last_seen_sec": int(now - info.get("last_seen", 0)),
                        }
                    )
                for nkey, reg in CONFIG.get("registered_names", {}).items():
                    r_pid = reg.get("player_id", "")
                    if r_pid and r_pid not in seen_pids:
                        is_wl = r_pid in CONFIG.get("whitelisted_players", []) or CONFIG.get("mode") == "auto"
                        player_list.append(
                            {
                                "id": r_pid,
                                "username": reg.get("username", nkey),
                                "ip": "离线 (已锁昵称)",
                                "zt_address": "-",
                                "nwid": CONFIG.get("default_nwid", ""),
                                "allowed": is_wl,
                                "name_conflict": False,
                                "online": False,
                                "last_seen_sec": 9999,
                            }
                        )

                self._send_json(
                    200,
                    {
                        "players": player_list,
                        "registered_names": CONFIG.get("registered_names", {}),
                        "mode": CONFIG["mode"],
                        "host_ip": CONFIG["host_ip"],
                        "default_nwid": CONFIG.get("default_nwid", ""),
                    },
                )
            return

        if path == "/api/room/detail":
            nwid = qs.get("nwid", [""])[0] or CONFIG.get("default_nwid", "")
            with LOCK:
                r = ROOMS.get(nwid)
                if not r:
                    self._send_json(404, {"status": False, "message": "房间不存在"})
                    return
                self._send_json(
                    200,
                    {
                        "status": True,
                        "data": {
                            **r,
                            "members": list(r["members"].values()),
                            "messages": r["messages"][-50:],
                        },
                    },
                )
            return

        self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len).decode("utf-8", errors="ignore") if content_len > 0 else "{}"
        try:
            req_data = json.loads(raw_body) if raw_body else {}
        except Exception:
            req_data = {}

        # 1. 唯一昵称校验与绑定锁定接口: /api/check_name
        if path == "/api/check_name":
            pid = str(req_data.get("player_id", "")).strip()
            username = str(req_data.get("username", "")).strip()
            if not pid:
                self._send_json(400, {"ok": False, "message": "缺少客户端 player_id"})
                return
            with LOCK:
                ok, msg = check_and_claim_nickname(pid, username)
            self._send_json(200, {"ok": ok, "username": username, "message": msg})
            return

        # 2. 管理员释放指定玩家的昵称绑定锁: /api/admin/release_name
        if path == "/api/admin/release_name":
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {ADMIN_TOKEN}":
                self._send_json(401, {"error": "unauthorized"})
                return
            target_pid = str(req_data.get("player_id", "")).strip()
            target_name = str(req_data.get("username", "")).strip()
            with LOCK:
                count = release_nickname_by_player_or_name(target_pid, target_name)
                if target_pid in PLAYERS:
                    PLAYERS.pop(target_pid, None)
                nwid = CONFIG.get("default_nwid", "")
                if nwid in ROOMS:
                    ROOMS[nwid]["members"].pop(target_pid, None)
            self._send_json(200, {"success": True, "released": count})
            return

        # 3. 玩家注册 / 心跳 + 唯一昵称核验 + ZeroTier Controller 动态准入授权: /api/heartbeat
        if path == "/api/heartbeat":
            pid = str(req_data.get("player_id", "")).strip()
            username = str(req_data.get("username", "")).strip() or f"Player_{pid[:4]}"
            vip = str(req_data.get("virtual_ip", "")).strip()
            zt_address = str(req_data.get("zt_address", "")).strip()
            nwid = str(req_data.get("nwid", "")).strip() or CONFIG.get("default_nwid", "")
            is_admin_flag = bool(req_data.get("is_admin", False))

            if not pid:
                self._send_json(400, {"error": "missing player_id"})
                return

            with LOCK:
                if not nwid:
                    try:
                        nwid = CONTROLLER.ensure_network(
                            name="CK3_DirectLAN",
                            subnet_prefix=CONFIG.get("subnet_prefix", "10.155.155"),
                        )
                        CONFIG["default_nwid"] = nwid
                        save_config()
                    except Exception:
                        pass

                name_ok, name_msg = check_and_claim_nickname(pid, username)
                is_whitelisted = pid in CONFIG.get("whitelisted_players", []) or is_admin_flag
                auto_mode = CONFIG.get("mode", "auto") == "auto"

                if pid not in PLAYERS:
                    init_allowed = (auto_mode or is_whitelisted) and name_ok
                    PLAYERS[pid] = {
                        "username": username,
                        "ip": vip,
                        "zt_address": zt_address,
                        "nwid": nwid,
                        "last_seen": time.time(),
                        "allowed": init_allowed,
                        "name_conflict": not name_ok,
                        "conflict_msg": "" if name_ok else name_msg,
                        "zt_synced_state": None,
                    }
                else:
                    PLAYERS[pid]["username"] = username
                    if vip:
                        PLAYERS[pid]["ip"] = vip
                    if zt_address:
                        PLAYERS[pid]["zt_address"] = zt_address
                    if nwid:
                        PLAYERS[pid]["nwid"] = nwid
                    PLAYERS[pid]["last_seen"] = time.time()
                    PLAYERS[pid]["name_conflict"] = not name_ok
                    PLAYERS[pid]["conflict_msg"] = "" if name_ok else name_msg
                    if not name_ok:
                        PLAYERS[pid]["allowed"] = False
                    elif auto_mode or is_whitelisted:
                        PLAYERS[pid]["allowed"] = True

                current_status = bool(PLAYERS[pid]["allowed"] and name_ok)

                sync_key = f"{nwid}:{zt_address}:{current_status}:{vip}"
                if zt_address and len(zt_address) == 10 and PLAYERS[pid].get("zt_synced_state") != sync_key:
                    CONTROLLER.set_member_auth(nwid, zt_address, current_status, assign_ip=vip)
                    PLAYERS[pid]["zt_synced_state"] = sync_key

                if nwid in ROOMS:
                    ROOMS[nwid]["members"][pid] = {
                        "uid": pid,
                        "social_uid": pid,
                        "nickname": username,
                        "address": zt_address,
                        "ip": vip,
                        "allowed": current_status,
                        "is_owner": is_admin_flag or (vip == CONFIG.get("host_ip")),
                        "last_seen": int(time.time() * 1000),
                    }

                peer_ips = [p["ip"] for p in PLAYERS.values() if p.get("ip") and p.get("allowed", False)]

            self._send_json(
                200,
                {
                    "allowed": current_status,
                    "name_conflict": not name_ok,
                    "conflict_msg": "" if name_ok else name_msg,
                    "nwid": nwid,
                    "virtual_ip": vip,
                    "host_ip": CONFIG["host_ip"],
                    "mode": CONFIG["mode"],
                    "peer_ips": peer_ips,
                },
            )
            return

        # 4. 管理员单人放行/阻断: /api/admin/toggle
        if path == "/api/admin/toggle":
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {ADMIN_TOKEN}":
                self._send_json(401, {"error": "unauthorized"})
                return

            pid = req_data.get("player_id", "")
            action = req_data.get("action", "")

            with LOCK:
                is_allow = action == "allow"
                wl = set(CONFIG.get("whitelisted_players", []))
                if is_allow:
                    wl.add(pid)
                else:
                    wl.discard(pid)
                CONFIG["whitelisted_players"] = list(wl)
                save_config()

                if pid in PLAYERS:
                    PLAYERS[pid]["allowed"] = is_allow and not PLAYERS[pid].get("name_conflict", False)
                    PLAYERS[pid]["zt_synced_state"] = None
                    zt_addr = PLAYERS[pid].get("zt_address", "")
                    nwid = PLAYERS[pid].get("nwid") or CONFIG.get("default_nwid", "")
                    vip = PLAYERS[pid].get("ip", "")
                    if zt_addr and nwid:
                        CONTROLLER.set_member_auth(nwid, zt_addr, PLAYERS[pid]["allowed"], assign_ip=vip)
                        PLAYERS[pid]["zt_synced_state"] = f"{nwid}:{zt_addr}:{PLAYERS[pid]['allowed']}:{vip}"

                self._send_json(200, {"success": True, "player_id": pid, "allowed": is_allow})
            return

        # 5. 管理员切换长效模式: /api/admin/set_mode
        if path == "/api/admin/set_mode":
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {ADMIN_TOKEN}":
                self._send_json(401, {"error": "unauthorized"})
                return

            mode = req_data.get("mode", "auto")
            with LOCK:
                CONFIG["mode"] = mode
                if mode == "auto":
                    for p in PLAYERS.values():
                        if not p.get("name_conflict", False):
                            p["allowed"] = True
                            p["zt_synced_state"] = None
                            if p.get("zt_address") and (p.get("nwid") or CONFIG.get("default_nwid")):
                                CONTROLLER.set_member_auth(
                                    p.get("nwid") or CONFIG["default_nwid"],
                                    p["zt_address"],
                                    True,
                                    assign_ip=p.get("ip", ""),
                                )
                save_config()

            self._send_json(200, {"success": True, "mode": CONFIG["mode"]})
            return

        if path == "/api/room/join":
            nwid = str(req_data.get("nwid", "")).strip() or CONFIG.get("default_nwid", "")
            uid = str(req_data.get("uid", "")).strip()
            nickname = str(req_data.get("nickname", "")).strip()
            zt_address = str(req_data.get("address", "")).strip()
            vip = str(req_data.get("virtual_ip", "")).strip()
            with LOCK:
                ok, msg = check_and_claim_nickname(uid, nickname)
                if not ok:
                    self._send_json(200, {"status": False, "message": msg})
                    return
                if nwid in ROOMS:
                    ROOMS[nwid]["members"][uid] = {
                        "uid": uid,
                        "social_uid": uid,
                        "nickname": nickname,
                        "address": zt_address,
                        "ip": vip,
                        "last_seen": int(time.time() * 1000),
                    }
            self._send_json(200, {"status": True, "nwid": nwid, "assigned_ip": vip})
            return

        if path == "/api/room/out":
            nwid = str(req_data.get("nwid", "")).strip() or CONFIG.get("default_nwid", "")
            uid = str(req_data.get("uid", "")).strip()
            with LOCK:
                release_nickname_by_player_or_name(player_id=uid)
                if nwid in ROOMS:
                    ROOMS[nwid]["members"].pop(uid, None)
            self._send_json(200, {"status": True})
            return

        self._send_json(404, {"error": "not_found"})


def main():
    global PUBLIC_IP, LISTEN_PORT, ZT_PRIMARY_PORT, ADMIN_TOKEN, ZT_HOME_DIR, CONTROLLER

    parser = argparse.ArgumentParser(description="CK3-DirectLAN 自建 Planet 根服务器与准入控制服务端")
    parser.add_argument("--public-ip", default="", help="服务器公网 IP 或房主电脑局域网/公网 IP")
    parser.add_argument("--auth-port", type=int, default=12030, help="准入控制与 Planet 分发 HTTP 端口 (默认 12030)")
    parser.add_argument("--zt-port", type=int, default=12020, help="ZeroTier Planet 监听端口 (默认 12020)")
    parser.add_argument("--admin-token", default="ck3_open_admin", help="房主管理端认证密码 (默认 ck3_open_admin)")
    parser.add_argument("--zt-home", default="", help="ZeroTier 数据目录")
    parser.add_argument("--init-planet", action="store_true", help="启动时重新生成 Planet 签名文件")
    parser.add_argument("--spawn-zt", action="store_true", help="自动拉起独立 ZeroTier Controller 进程 (适用于 Windows/房主电脑一键开服)")
    args = parser.parse_args()

    PUBLIC_IP = args.public_ip.strip() or PUBLIC_IP or detect_local_ip()
    LISTEN_PORT = args.auth_port
    ZT_PRIMARY_PORT = args.zt_port
    ADMIN_TOKEN = args.admin_token.strip() or "ck3_open_admin"
    ZT_HOME_DIR = Path(args.zt_home) if args.zt_home else get_default_zt_home(spawn_mode=args.spawn_zt)

    # 检查是否需要生成或更新 planet
    world_meta_file = PLANET_DIR / "world_config.json"
    need_gen = args.init_planet or not (PLANET_DIR / "planet").exists()
    if not need_gen and world_meta_file.exists():
        try:
            old_meta = json.loads(world_meta_file.read_text(encoding="utf-8"))
            if old_meta.get("publicIp") != PUBLIC_IP:
                need_gen = True
        except Exception:
            pass

    if need_gen:
        print(f"[*] 正在为节点 [{PUBLIC_IP}:{ZT_PRIMARY_PORT}] 生成加密签名 Planet 文件...")
        meta = generate_server_planet(PUBLIC_IP, ZT_PRIMARY_PORT, ZT_HOME_DIR, PLANET_DIR)
        print(f"[+] Planet 生成成功: {meta['planetPath']} (节点 ID: {meta['nodeId']})")
        try:
            shutil.copy2(PLANET_DIR / "planet", ZT_HOME_DIR / "planet")
        except Exception:
            pass

    zt_proc = None
    if args.spawn_zt:
        zt_bin = get_zt_binary()
        print(f"[*] 正在本机拉起独立 ZeroTier Planet/Controller 服务 ({zt_bin} -p{ZT_PRIMARY_PORT})...")
        cmd = [zt_bin, "-C", "-U", f"-p{ZT_PRIMARY_PORT}", str(ZT_HOME_DIR)] if os.name == "nt" else [zt_bin, "-U", f"-p{ZT_PRIMARY_PORT}", str(ZT_HOME_DIR)]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        zt_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        for _ in range(25):
            if (ZT_HOME_DIR / "authtoken.secret").exists():
                break
            time.sleep(0.3)
        time.sleep(1.0)

    CONTROLLER = ZeroTierController(zt_home=ZT_HOME_DIR, primary_port=ZT_PRIMARY_PORT)
    load_config()

    t = threading.Thread(target=cleanup_offline_players, daemon=True)
    t.start()

    print("=" * 68)
    print("🚀 CK3-DirectLAN 自建联机主节点已启动！")
    print(f"   • 节点连接地址 (填在客户端): {PUBLIC_IP}")
    print(f"   • 控制与 Planet 分发端口    : TCP {LISTEN_PORT} (http://{PUBLIC_IP}:{LISTEN_PORT}/planet)")
    print(f"   • ZeroTier 专网通信端口    : UDP/TCP {ZT_PRIMARY_PORT}")
    print(f"   • 房主管理密码 (Token)     : {ADMIN_TOKEN}")
    print("=" * 68)

    server = ThreadedHTTPServer(("0.0.0.0", LISTEN_PORT), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] 正在停止服务...")
    finally:
        server.server_close()
        if zt_proc:
            zt_proc.terminate()


if __name__ == "__main__":
    main()
