#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CK3-DirectLAN 开源独立版自动化打包脚本:
1. 使用 PyInstaller 编译【CK3联机助手-玩家端.exe】与【CK3联机助手-房主端.exe】
2. 同步核心依赖:
   - bin/zero/ (ZeroTier 虚拟网卡、WinIPBroadcast 广播转发、ForceBindIP64、NATTest、iperf3)
   - bin/lan_patch/ (ColdClientLoader.ini、lan_loader.exe、steamclient64.dll、DLC.txt、disable_lan_only.txt)
   - server/ (lan_server.py、deploy_linux_server.sh、start_windows_server.bat，支持本机一键做主机开服)
3. 生成开源发布压缩包 CK3-DirectLAN-v1.0.0-Windows-x64.zip
"""

import os
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CLIENT_DIR = os.path.join(PROJECT_ROOT, "client")
SERVER_DIR = os.path.join(PROJECT_ROOT, "server")
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_TMP = os.path.join(PROJECT_ROOT, "build_tmp")

USER_SRC = os.path.join(CLIENT_DIR, "ui_user.py")
ADMIN_SRC = os.path.join(CLIENT_DIR, "ui_admin.py")


def sync_version_file(version: str):
    version_py_path = os.path.join(CLIENT_DIR, "version.py")
    content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CK3-DirectLAN 开源版版本号定义"""

import os
import sys

DEFAULT_VERSION = "{version}"


def get_app_version() -> str:
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        v_file = os.path.join(base_dir, "version.txt")
        if os.path.isfile(v_file):
            with open(v_file, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
    except Exception:
        pass
    return DEFAULT_VERSION


APP_VERSION = get_app_version()
'''
    with open(version_py_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] client/version.py 版本号已同步为: {version}")


def write_version_txt(target_folder: str, version: str):
    v_path = os.path.join(target_folder, "version.txt")
    with open(v_path, "w", encoding="utf-8") as f:
        f.write(version.strip() + "\n")


def build_one(src_file, name):
    print(f"[*] 正在通过 PyInstaller 打包: {name}.exe ...")
    ico_file = os.path.join(PROJECT_ROOT, "assets", "directlan.ico")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--uac-admin",
        "--name",
        name,
        "--distpath",
        DIST_DIR,
        "--workpath",
        BUILD_TMP,
        "--specpath",
        BUILD_TMP,
        "--paths",
        CLIENT_DIR,
    ]
    if os.path.isfile(ico_file):
        cmd.extend(["--icon", ico_file])
    cmd.append(src_file)
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        print(f"[-] 打包 {name} 失败！")
        return False
    print(f"[+] {name}.exe 打包完成！")
    return True


def copy_dependencies(target_folder):
    target_bin = os.path.join(target_folder, "bin")
    if os.path.exists(target_bin):
        shutil.rmtree(target_bin)

    # 1. 复制 bin/zero
    zero_src = os.path.join(BIN_DIR, "zero")
    zero_dst = os.path.join(target_bin, "zero")
    if os.path.isdir(zero_src):
        shutil.copytree(zero_src, zero_dst, dirs_exist_ok=True)

    # 2. 复制 bin/lan_patch
    patch_src = os.path.join(BIN_DIR, "lan_patch")
    patch_dst = os.path.join(target_bin, "lan_patch")
    if os.path.isdir(patch_src):
        shutil.copytree(patch_src, patch_dst, dirs_exist_ok=True)

    # 3. 复制 server/ (供房主本机一键开服及自建云服务器使用)
    srv_dst = os.path.join(target_folder, "server")
    os.makedirs(srv_dst, exist_ok=True)
    for fn in ["lan_server.py", "deploy_linux_server.sh", "start_windows_server.bat"]:
        sf = os.path.join(SERVER_DIR, fn)
        if os.path.isfile(sf):
            shutil.copy2(sf, os.path.join(srv_dst, fn))

    os.makedirs(os.path.join(target_folder, "debug_logs"), exist_ok=True)
    print(f"[+] 开源版依赖同步完成: {target_folder}")


def build_distribution(version: str = "1.0.0") -> bool:
    os.makedirs(DIST_DIR, exist_ok=True)
    os.makedirs(BUILD_TMP, exist_ok=True)

    sync_version_file(version)

    if not build_one(USER_SRC, "CK3联机助手-玩家端"):
        return False
    player_folder = os.path.join(DIST_DIR, "CK3联机助手-玩家端")
    copy_dependencies(player_folder)
    write_version_txt(player_folder, version)

    if not build_one(ADMIN_SRC, "CK3联机助手-房主端"):
        return False
    admin_folder = os.path.join(DIST_DIR, "CK3联机助手-房主端")
    copy_dependencies(admin_folder)
    write_version_txt(admin_folder, version)

    zip_output = os.path.join(PROJECT_ROOT, f"CK3-DirectLAN-v{version}-Windows-x64")
    print(f"[*] 正在压缩生成开源发行包: {zip_output}.zip ...")
    shutil.make_archive(zip_output, "zip", DIST_DIR, "CK3联机助手-玩家端")

    shutil.rmtree(BUILD_TMP, ignore_errors=True)
    print("=" * 64)
    print(f"✅ CK3-DirectLAN 开源独立版打包完成！(v{version})")
    print(f"1. 玩家端 EXE : {os.path.join(player_folder, 'CK3联机助手-玩家端.exe')}")
    print(f"2. 房主端 EXE : {os.path.join(admin_folder, 'CK3联机助手-房主端.exe')}")
    print(f"3. Release ZIP: {zip_output}.zip")
    print("=" * 64)
    return True


if __name__ == "__main__":
    ver = sys.argv[1].strip() if len(sys.argv) > 1 else "1.0.0"
    build_distribution(ver)
