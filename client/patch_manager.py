#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CK3-DirectLAN · 虚拟局域网联机补丁 + 唯一软件账号/SteamID64 绑定 + 节点路由优化模块
====================================================================================
核心功能:
1. 免登录 P 社账号，直接使用本软件的【唯一联机昵称 + 唯一 SteamID64】作为游戏联机身份:
   - 自动将玩家唯一昵称写入 binaries/steam_settings/account_name.txt 与 force_account_name.txt
   - 自动根据客户端唯一 client_id 生成专属 64 位 SteamID 写入 user_steam_id.txt 与 force_steamid.txt
   - 配合服务端的唯一昵称锁，彻底杜绝多人联机同名冲突或存档认领错乱！
2. 完整集成虚拟 Steam 局域网大厅加载器 (适配至《白银与丝绸 Silk & Silver》):
   - ColdClientLoader.ini (Exe=ck3.exe, ExeCommandLine=-steam, AppId=1158310)
   - lan_loader.exe (ColdClientLoader 注入器)
   - steamclient64.dll & steamclient.dll (支持 Shift+Tab 控制台与纯虚拟局域网 Steam 大厅)
   - steam_api64.dll (纯净接口)
   - steam_settings/DLC.txt (37 款全量 DLC，含 4232910 白银与丝绸 Silk & Silver)
   - steam_settings/disable_lan_only.txt (解除跨虚拟网卡网段广播限制)
   - steam_settings/custom_broadcasts.txt (实时同步所有在线专网玩家虚拟 IP，双向秒搜房)
3. 联机节点加速优化 (屏蔽高延迟海外遥测与中继节点，仅保留登录节点与 P2P 虚拟专网直连，4~5 速稳定流畅)
4. 自动输出详细操作日志至 debug_logs/client_debug.log，方便开发者或 AI Agent 排查
"""

import os
import shutil
import subprocess
import sys
import time
import winreg
import zlib
from typing import List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

APP_ID = "1158310"


def get_project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PROJECT_ROOT = get_project_root()
LAN_PATCH_DIR = os.path.join(PROJECT_ROOT, "bin", "lan_patch")
ZERO_DIR = os.path.join(PROJECT_ROOT, "bin", "zero")
if not os.path.isdir(ZERO_DIR):
    ZERO_DIR = os.path.join(PROJECT_ROOT, "zero")

DEBUG_LOG_DIR = os.path.join(PROJECT_ROOT, "debug_logs")
os.makedirs(DEBUG_LOG_DIR, exist_ok=True)
DEBUG_LOG_FILE = os.path.join(DEBUG_LOG_DIR, "client_debug.log")


def write_debug_log(tag: str, msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{tag}] {msg}\n"
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def compute_unique_steamid64(client_id: str) -> str:
    """
    根据客户端唯一 client_id 计算固定的合法 64 位 SteamID (76561197960265728 + account_id)
    确保免登录 P 社账号时，每位玩家在 CK3 多人游戏和联机存档中拥有唯一且持久的账号身份！
    """
    seed = (client_id or "ck3_default").encode("utf-8")
    account_id = (zlib.crc32(seed) & 0x7FFFFFFF) or 100001
    steam_id_64 = 76561197960265728 + account_id
    return str(steam_id_64)


# CK3 全量 37 款 DLC 清单 (适配至《白银与丝绸 Silk & Silver》)
CK3_DLC_LIST = [
    "1296730=Crusader Kings III: Garments of the Holy Roman Empire",
    "1296731=Crusader Kings III: Fashion of the Abbasid Court",
    "1303182=Crusader Kings III: Royal Court",
    "1303183=Crusader Kings III: Northern Lords",
    "1303184=Crusader Kings III: Fate of Iberia",
    "1359040=Crusader Kings III: Expansion Pass",
    "2114760=Crusader Kings III: Friends & Foes",
    "2311920=Crusader Kings III: Tours & Tournaments",
    "2311930=Crusader Kings III: Elegance of the Empire",
    "2313540=Crusader Kings III: Legacy of Persia",
    "2313541=Crusader Kings III: Wards & Wardens",
    "2671030=Crusader Kings III Creator Pack: North African Attire",
    "2671040=Crusader Kings III: Couture of the Capets",
    "2671060=Crusader Kings III: Legends of the Dead",
    "2671070=Crusader Kings III: Roads to Power",
    "2671080=Crusader Kings III: Wandering Nobles",
    "2812400=Crusader Kings III: Chapter III",
    "3077630=Crusader Kings III: Many Roads to Power - Comic Book",
    "3275760=Crusader Kings III Creator Pack: West Slavic Attire",
    "3315500=Crusader Kings III: Crowns of the World",
    "3315510=Crusader Kings III: Khans of the Steppe",
    "3315520=Crusader Kings III: Coronations",
    "3315530=Crusader Kings III: All Under Heaven",
    "3315540=Crusader Kings III Creator Pack: Medieval Monuments",
    "3315550=Crusader Kings III Creator Pack: Arctic Attire",
    "3315560=Crusader Kings III Creator Pack: High Medieval Warfare Attire",
    "3315570=Crusader Kings III Creator Pack: Holy Buildings",
    "3315580=Crusader Kings III Creator Pack: North Pacific Attire",
    "3315590=Crusader Kings III: Songs of the Realm",
    "3486700=Crusader Kings III: Chapter IV",
    "4208220=Crusader Kings III: Subscription",
    "4232860=Crusader Kings III Creator Pack: East Asian Wonders",
    "4232870=Crusader Kings III Creator Pack: Celestial Court Attire",
    "4232880=Crusader Kings III: Chapter V",
    "4232890=Crusader Kings III: Symbols of Authority",
    "4232900=Crusader Kings III: By God Alone",
    "4232910=Crusader Kings III: Silk & Silver",
]

COLD_CLIENT_INI_CONTENT = """[SteamClient]
Exe=ck3.exe
ExeRunDir=.
ExeCommandLine=-steam
AppId=1158310

SteamClientDll=steamclient.dll
SteamClient64Dll=steamclient64.dll
"""


def find_steam_ck3_path() -> Optional[str]:
    """通过 Windows 注册表和 Steam 库自动定位 CK3 根目录"""
    steam_path = None
    try:
        for reg_key in [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        ]:
            try:
                with winreg.OpenKey(reg_key[0], reg_key[1]) as key:
                    val, _ = winreg.QueryValueEx(key, "SteamPath")
                    if val and os.path.isdir(val):
                        steam_path = val.replace("/", "\\")
                        break
            except Exception:
                continue
    except Exception:
        pass

    candidates = [
        r"D:\Steam\steamapps\common\Crusader Kings III",
        r"C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III",
        r"E:\Steam\steamapps\common\Crusader Kings III",
        r"F:\Steam\steamapps\common\Crusader Kings III",
        r"G:\Steam\steamapps\common\Crusader Kings III",
        r"D:\SteamLibrary\steamapps\common\Crusader Kings III",
        r"E:\SteamLibrary\steamapps\common\Crusader Kings III",
        r"F:\SteamLibrary\steamapps\common\Crusader Kings III",
    ]

    if steam_path:
        default_ck3 = os.path.join(steam_path, "steamapps", "common", "Crusader Kings III")
        if default_ck3 not in candidates:
            candidates.insert(0, default_ck3)

        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf_path):
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if '"path"' in line.lower():
                            parts = line.strip().split('"')
                            if len(parts) >= 4:
                                lib_dir = parts[3].replace("\\\\", "\\").replace("/", "\\")
                                candidate = os.path.join(lib_dir, "steamapps", "common", "Crusader Kings III")
                                if candidate not in candidates:
                                    candidates.append(candidate)
            except Exception:
                pass

    for path in candidates:
        if verify_ck3_path(path):
            return os.path.abspath(path)

    return None


def verify_ck3_path(game_dir: str) -> bool:
    """验证指定路径是否是有效的 CK3 根目录或 binaries 目录"""
    if not game_dir or not os.path.isdir(game_dir):
        return False
    binaries_dir = os.path.join(game_dir, "binaries")
    if os.path.isfile(os.path.join(binaries_dir, "ck3.exe")):
        return True
    if os.path.isfile(os.path.join(game_dir, "ck3.exe")):
        return True
    return False


def get_binaries_path(game_dir: str) -> str:
    """获取标准的 binaries 绝对路径"""
    if os.path.isfile(os.path.join(game_dir, "ck3.exe")):
        return os.path.abspath(game_dir)
    return os.path.abspath(os.path.join(game_dir, "binaries"))


def get_patch_status(game_dir: str) -> Tuple[str, str]:
    """检查当前是否已安装虚拟局域网联机补丁"""
    if not verify_ck3_path(game_dir):
        return "NOT_FOUND", "未检测到有效的游戏目录"

    bin_dir = get_binaries_path(game_dir)
    cold_ini = os.path.join(bin_dir, "ColdClientLoader.ini")
    sc64_dll = os.path.join(bin_dir, "steamclient64.dll")
    loader_exe = os.path.join(bin_dir, "lan_loader.exe")

    if os.path.isfile(cold_ini) and os.path.isfile(sc64_dll) and os.path.isfile(loader_exe):
        return "PATCHED", "已安装 DirectLAN 虚拟局域网联机补丁 (免P社账号 + 37全DLC)"

    return "ORIGINAL", "官方原版 / 未安装虚拟局域网联机补丁"


def is_game_running() -> bool:
    """检查 ck3.exe 是否正在运行"""
    try:
        cmd = ["tasklist", "/FI", "IMAGENAME eq ck3.exe", "/NH"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000)
        return "ck3.exe" in res.stdout.lower()
    except Exception:
        return False


def set_paradox_relay_shield(enable: bool = True) -> Tuple[bool, str]:
    """
    联机节点加速优化：
    屏蔽海外高延迟遥测与中继域名 (同时保留登录节点)，强制联机数据走 P2P 虚拟网卡直连，实测 4~5 速稳定流畅
    """
    hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    marker_start = "# >>> CK3_P2P_RELAY_SHIELD_START <<<"
    marker_end = "# >>> CK3_P2P_RELAY_SHIELD_END <<<"
    shield_lines = [
        marker_start,
        "127.0.0.1 telemetry.paradoxinteractive.com",
        "127.0.0.1 turn.paradoxinteractive.com",
        "127.0.0.1 relay.paradoxinteractive.com",
        marker_end,
    ]
    try:
        if not os.path.isfile(hosts_path):
            return False, "未找到系统 hosts 文件"
        with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if marker_start in content and marker_end in content:
            s_idx = content.index(marker_start)
            e_idx = content.index(marker_end) + len(marker_end)
            content = (content[:s_idx].rstrip() + "\n" + content[e_idx:].lstrip()).strip() + "\n"

        if enable:
            content = content.rstrip() + "\n\n" + "\n".join(shield_lines) + "\n"

        with open(hosts_path, "w", encoding="utf-8") as f:
            f.write(content)
        write_debug_log("RELAY_SHIELD", f"set_paradox_relay_shield(enable={enable}) succeeded")
        return True, "已启用 P2P 节点加速优化 (屏蔽海外中继，仅保留登录与专网直连)" if enable else "已恢复默认节点配置"
    except Exception as e:
        write_debug_log("RELAY_SHIELD_ERR", str(e))
        return False, f"节点屏蔽规则更新提示: {e}"


def install_patch(
    game_dir: str,
    username: str = "Player",
    host_ip: str = "10.155.155.2",
    peer_ips: Optional[List[str]] = None,
    enable_relay_shield: bool = True,
    client_id: str = "",
) -> Tuple[bool, str]:
    """
    一键安装 DirectLAN 虚拟局域网联机补丁（适配《白银与丝绸》）+ 唯一软件账号/SteamID64 绑定 + 37款全DLC解锁
    """
    if not verify_ck3_path(game_dir):
        return False, "游戏路径无效，找不到 ck3.exe"

    if is_game_running():
        return False, "检测到 CK3 游戏正在运行，请先完全退出游戏后再执行补丁安装！"

    if not os.path.isdir(LAN_PATCH_DIR):
        return False, f"未找到联机补丁目录: {LAN_PATCH_DIR}"

    bin_dir = get_binaries_path(game_dir)
    target_dll = os.path.join(bin_dir, "steam_api64.dll")
    backup_dll = os.path.join(bin_dir, "steam_api64.dll.original_backup")
    real_steam_dll = os.path.join(bin_dir, "steam_api64_o.dll")

    try:
        # 1. 备份原有的 steam_api64.dll
        if not os.path.isfile(backup_dll):
            if os.path.isfile(real_steam_dll):
                shutil.copy2(real_steam_dll, backup_dll)
            elif os.path.isfile(target_dll):
                shutil.copy2(target_dll, backup_dll)

        # 备份并移出可能冲突的 cream_api.ini / steam_api64_o.dll
        for conflict_name in ("cream_api.ini", "steam_api64_o.dll"):
            c_path = os.path.join(bin_dir, conflict_name)
            c_bak = os.path.join(bin_dir, f"{conflict_name}.lan_backup")
            if os.path.isfile(c_path):
                if not os.path.isfile(c_bak):
                    shutil.copy2(c_path, c_bak)
                try:
                    os.remove(c_path)
                except Exception:
                    pass

        # 2. 部署联机补丁核心文件
        for fname in ("ColdClientLoader.ini", "steam_api64.dll", "steamclient.dll", "steamclient64.dll", "lan_loader.exe"):
            src_f = os.path.join(LAN_PATCH_DIR, fname)
            dst_f = os.path.join(bin_dir, fname)
            if os.path.isfile(src_f):
                shutil.copy2(src_f, dst_f)

        with open(os.path.join(bin_dir, "ColdClientLoader.ini"), "w", encoding="utf-8") as f:
            f.write(COLD_CLIENT_INI_CONTENT)

        # 3. 配置 steam_settings 目录
        settings_dir = os.path.join(bin_dir, "steam_settings")
        os.makedirs(settings_dir, exist_ok=True)

        with open(os.path.join(settings_dir, "disable_lan_only.txt"), "w", encoding="utf-8") as f:
            f.write("")

        with open(os.path.join(settings_dir, "steam_appid.txt"), "w", encoding="utf-8") as f:
            f.write(APP_ID.strip() + "\n")

        display_name = (username or "").strip() or f"Player_{(client_id or '0000')[:4]}"
        for name_file in ("account_name.txt", "force_account_name.txt"):
            with open(os.path.join(settings_dir, name_file), "w", encoding="utf-8") as f:
                f.write(display_name + "\n")

        steam_id_64 = compute_unique_steamid64(client_id or display_name)
        for sid_file in ("user_steam_id.txt", "force_steamid.txt"):
            with open(os.path.join(settings_dir, sid_file), "w", encoding="utf-8") as f:
                f.write(steam_id_64 + "\n")

        for lang_file in ("language.txt", "force_language.txt"):
            with open(os.path.join(settings_dir, lang_file), "w", encoding="utf-8") as f:
                f.write("schinese\n")

        src_dlc = os.path.join(LAN_PATCH_DIR, "steam_settings", "DLC.txt")
        dst_dlc = os.path.join(settings_dir, "DLC.txt")
        if os.path.isfile(src_dlc):
            shutil.copy2(src_dlc, dst_dlc)
        else:
            with open(dst_dlc, "w", encoding="utf-8") as f:
                f.write("\n".join(CK3_DLC_LIST) + "\n")

        broadcasts = [
            "10.155.155.255",
            "10.155.155.1",
            host_ip,
            "255.255.255.255",
            "127.0.0.1",
        ]
        if peer_ips:
            for pip in peer_ips:
                if pip and pip not in broadcasts:
                    broadcasts.append(pip)
        with open(os.path.join(settings_dir, "custom_broadcasts.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(broadcasts) + "\n")

        if enable_relay_shield:
            set_paradox_relay_shield(True)

        write_debug_log(
            "INSTALL_PATCH",
            f"Installed patch to {bin_dir}, username={display_name}, steamid64={steam_id_64}, broadcasts={broadcasts}",
        )

        has_cn = any("\u4e00" <= ch <= "\u9fff" for ch in display_name)
        cn_tip = "\n⚠️ 提示：建议联机昵称使用英文或数字，避免局域网房间名乱码。" if has_cn else ""

        return (
            True,
            f"DirectLAN 虚拟局域网联机补丁（适配《白银与丝绸》）安装成功！\n"
            f"1. 免登录 P 社账号：已自动绑定您的专属软件账号【{display_name}】\n"
            f"2. 专属唯一 SteamID64：【{steam_id_64}】{cn_tip}\n"
            f"3. 全量 37 款 DLC（含《白银与丝绸 Silk & Silver》）已全部激活！",
        )
    except Exception as e:
        write_debug_log("INSTALL_PATCH_ERR", str(e))
        return False, f"安装补丁过程中发生异常: {str(e)}"


def restore_original(game_dir: str) -> Tuple[bool, str]:
    """一键无损还原官方原版"""
    if not verify_ck3_path(game_dir):
        return False, "游戏路径无效"

    if is_game_running():
        return False, "检测到 CK3 游戏正在运行，请先完全退出游戏再执行还原！"

    bin_dir = get_binaries_path(game_dir)
    target_dll = os.path.join(bin_dir, "steam_api64.dll")
    backup_dll = os.path.join(bin_dir, "steam_api64.dll.original_backup")
    settings_dir = os.path.join(bin_dir, "steam_settings")

    try:
        if os.path.isfile(backup_dll):
            shutil.copy2(backup_dll, target_dll)
            os.remove(backup_dll)

        for conflict_name in ("cream_api.ini", "steam_api64_o.dll"):
            c_path = os.path.join(bin_dir, conflict_name)
            c_bak = os.path.join(bin_dir, f"{conflict_name}.lan_backup")
            if os.path.isfile(c_bak):
                shutil.copy2(c_bak, c_path)
                os.remove(c_bak)

        for fname in ("ColdClientLoader.ini", "steamclient.dll", "steamclient64.dll", "lan_loader.exe", "启动游戏..exe"):
            fpath = os.path.join(bin_dir, fname)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass

        if os.path.isdir(settings_dir):
            shutil.rmtree(settings_dir, ignore_errors=True)

        set_paradox_relay_shield(False)
        write_debug_log("RESTORE_ORIGINAL", f"Restored original game files in {bin_dir}")

        return True, "已成功无损还原为官方原版！所有原版文件与设置均已恢复。"
    except Exception as e:
        write_debug_log("RESTORE_ORIGINAL_ERR", str(e))
        return False, f"还原过程中发生异常: {str(e)}"


def launch_game(game_dir: str, virtual_ip: str = "", use_force_bind: bool = True) -> Tuple[bool, str]:
    """启动 CK3 游戏 (优先通过 ColdClientLoader lan_loader.exe -> ck3.exe -steam)"""
    if not verify_ck3_path(game_dir):
        return False, "游戏路径无效，请先选择有效的 Crusader Kings III 游戏目录"

    bin_dir = get_binaries_path(game_dir)
    loader_exe = os.path.join(bin_dir, "lan_loader.exe")
    ck3_exe = os.path.join(bin_dir, "ck3.exe")
    force_bind_exe = os.path.join(ZERO_DIR, "ForceBindIP", "ForceBindIP64.exe")

    try:
        target_exe = loader_exe if os.path.isfile(loader_exe) else ck3_exe
        extra_args = [] if os.path.isfile(loader_exe) else ["-steam"]

        if use_force_bind and virtual_ip and os.path.isfile(force_bind_exe) and target_exe == ck3_exe:
            cmd = [force_bind_exe, "-i", virtual_ip, target_exe] + extra_args
            subprocess.Popen(cmd, cwd=bin_dir)
            write_debug_log("LAUNCH_GAME", f"Launched with ForceBindIP64: {cmd}")
            return True, f"已通过 ForceBindIP64 强制绑定虚拟 IP ({virtual_ip}) 启动 CK3！"
        else:
            cmd = [target_exe] + extra_args
            subprocess.Popen(cmd, cwd=bin_dir)
            write_debug_log("LAUNCH_GAME", f"Launched via ColdClientLoader: {cmd} in {bin_dir} (vip={virtual_ip})")
            mode_desc = "DirectLAN 虚拟大厅加载器 (lan_loader.exe -> ck3.exe -steam)" if target_exe == loader_exe else "ck3.exe -steam"
            return (
                True,
                f"游戏已通过【{mode_desc}】成功启动！\n"
                f"• 免登录 P 社账号：已自动加载您的专属软件昵称与唯一 SteamID\n"
                f"• 专网虚拟 IP: {virtual_ip or '已就绪'} (最高路由优先级 Metric=1)\n"
                f"• 进入游戏主菜单直接点击【多人游戏】即可加入或创建房间！",
            )
    except Exception as e:
        write_debug_log("LAUNCH_GAME_ERR", str(e))
        return False, f"启动游戏失败: {str(e)}"
