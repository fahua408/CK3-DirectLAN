#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CK3-DirectLAN · 免安装 Git 纯 Python 一键上传至 GitHub 仓库 & 自动发布 Release 工具
====================================================================================
由于本机未安装 git.exe，本脚本直接通过 GitHub 官方 REST API (https://api.github.com):
1. 自动在你的 GitHub 账号下创建开源仓库 (默认名称: CK3-DirectLAN，若已存在则直接复用)
2. 自动将本开源目录下的所有源码、脚本、教程、实测截图 (assets/*) 批量打包为 Git Tree 并推送至 main 分支
3. 自动创建 v1.0.0 GitHub Release，并将编译好的 Windows 发行包 (CK3-DirectLAN-v1.0.0-Windows-x64.zip) 上传为 Release 附件！

用法:
  python upload_to_github.py --token <你的GitHub_Personal_Access_Token> [--repo CK3-DirectLAN]
  或直接双击运行【一键上传到GitHub.bat】按提示粘贴 Token 即可！
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent

# 需要上传到 GitHub 源码仓库的文件列表 (排除大体积构建缓存与原始未裁剪素材)
UPLOAD_PATHS = [
    "README.md",
    "LICENSE",
    ".gitignore",
    "GITHUB_RELEASE_COPY.md",
    "package_dist.py",
    "upload_to_github.py",
    "一键上传到GitHub.bat",
    "client/version.py",
    "client/patch_manager.py",
    "client/network_service.py",
    "client/ui_user.py",
    "client/ui_admin.py",
    "server/lan_server.py",
    "server/deploy_linux_server.sh",
    "server/start_windows_server.bat",
    "assets/multiplayer_ingame.png",
    "assets/multiplayer_5speed_sync.jpg",
    "assets/multiplayer_demo.mp4",
    "bin/zero/priority.bat",
    "bin/lan_patch/ColdClientLoader.ini",
    "bin/lan_patch/steam_settings/DLC.txt",
    "bin/lan_patch/steam_settings/disable_lan_only.txt",
]


def gh_request(url: str, token: str, method: str = "GET", body: dict | bytes | None = None, content_type: str = "application/json") -> dict | list:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CK3-DirectLAN-Uploader/1.0",
    }
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        elif isinstance(body, bytes):
            data = body
            headers["Content-Type"] = content_type
            headers["Content-Length"] = str(len(data))
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw) if raw else {}


def main():
    parser = argparse.ArgumentParser(description="一键将 CK3-DirectLAN 上传至 GitHub 并发布 Release")
    parser.add_argument("--token", default="", help="GitHub Personal Access Token (需勾选 repo 权限)")
    parser.add_argument("--repo", default="CK3-DirectLAN", help="目标仓库名 (默认 CK3-DirectLAN)")
    parser.add_argument("--private", action="store_true", help="是否创建为私有仓库 (默认公开开源仓库)")
    args = parser.parse_args()

    token = args.token.strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("=" * 68)
        print("🔑 请输入你的 GitHub Personal Access Token (PAT)")
        print("   获取地址: https://github.com/settings/tokens/new (勾选 'repo' 权限即可)")
        print("=" * 68)
        token = input("请粘贴 GitHub Token 并回车: ").strip()
        if not token:
            print("[-] 未提供 Token，已退出。")
            sys.exit(1)

    # 1. 获取当前登录的 GitHub 用户名
    print("[1/5] 正在验证 GitHub 账号身份...")
    try:
        user_info = gh_request("https://api.github.com/user", token)
        owner = user_info["login"]
        print(f"[+] 验证成功！GitHub 账号: {owner}")
    except Exception as e:
        print(f"[-] GitHub Token 验证失败: {e}")
        sys.exit(1)

    repo_name = args.repo.strip() or "CK3-DirectLAN"
    desc = "👑 《十字军之王3 (Crusader Kings III)》自建虚拟局域网 P2P 高速直连联机工具 | 支持玩家电脑对电脑直连 & 自建云服务器 Planet 根节点 | 免登录P社账号 + 全服唯一昵称锁 + 适配《白银与丝绸》全37款DLC | 实测 4~5 速稳定流畅"

    # 2. 检查或创建仓库
    print(f"[2/5] 正在检查/创建仓库 {owner}/{repo_name} ...")
    repo_exists = False
    try:
        repo_obj = gh_request(f"https://api.github.com/repos/{owner}/{urllib.parse.quote(repo_name)}", token)
        repo_name = repo_obj["name"]
        repo_exists = True
        print(f"[+] 仓库 {owner}/{repo_name} 已存在，将直接更新文件。")
    except urllib.error.HTTPError as he:
        if he.code == 404:
            created_repo = gh_request(
                "https://api.github.com/user/repos",
                token,
                method="POST",
                body={
                    "name": repo_name,
                    "description": desc,
                    "private": bool(args.private),
                    "auto_init": True,
                },
            )
            repo_name = created_repo["name"]
            print(f"[+] 成功创建 GitHub 开源仓库: https://github.com/{owner}/{repo_name}")
        else:
            raise

    q_repo = urllib.parse.quote(repo_name)

    # 设置仓库 Topics 标签
    try:
        gh_request(
            f"https://api.github.com/repos/{owner}/{q_repo}/topics",
            token,
            method="PUT",
            body={
                "names": [
                    "crusader-kings-3",
                    "ck3",
                    "multiplayer",
                    "zerotier",
                    "p2p",
                    "virtual-lan",
                    "paradox-interactive",
                    "python",
                ]
            },
        )
    except Exception:
        pass

    # 3. 逐个上传仓库文件 (Contents API 自动处理创建与更新)
    print("[3/5] 正在上传源码、脚本、教程与实测截图至 GitHub ...")
    for rel_path in UPLOAD_PATHS:
        local_f = ROOT_DIR / rel_path
        if not local_f.is_file():
            continue
        encoded_content = base64.b64encode(local_f.read_bytes()).decode("ascii")
        api_path = f"https://api.github.com/repos/{owner}/{q_repo}/contents/{urllib.parse.quote(rel_path)}"
        old_sha = None
        try:
            existing_f = gh_request(api_path, token)
            if isinstance(existing_f, dict):
                old_sha = existing_f.get("sha")
        except Exception:
            pass

        payload = {
            "message": f"Update {rel_path}",
            "content": encoded_content,
        }
        if old_sha:
            payload["sha"] = old_sha
        gh_request(api_path, token, method="PUT", body=payload)
        print(f"   ✓ 已上传: {rel_path} ({local_f.stat().st_size} bytes)")

    # 4. 创建 v1.0.0 Release 并上传 Windows 可执行程序压缩包
    print("[4/5] 正在创建 v1.0.0 GitHub Release...")
    release_notes = """## 🎉 CK3-更好的私人联机助手-DirectLAN v1.0.0 正式开源发布！

- **双模式自主联机（零商业后台依赖）**：支持【🖥️ 玩家电脑对电脑直连（免云服务器）】与【☁️ 玩家自建云服务器】。
- **免登录 P 社账号 + 全服唯一联机昵称锁**：自动绑定唯一 64 位 SteamID 与唯一联机昵称，当前人占用的昵称他人无法重名，改名自动释放。
- **适配最新《白银与丝绸 (Silk & Silver)》全 37 款 DLC**：实测 4~5 速日期完全同步。
- **一键无损还原官方原版**。
"""
    release_obj = None
    try:
        release_obj = gh_request(f"https://api.github.com/repos/{owner}/{q_repo}/releases/tags/v1.0.0", token)
    except urllib.error.HTTPError as he:
        if he.code == 404:
            release_obj = gh_request(
                f"https://api.github.com/repos/{owner}/{q_repo}/releases",
                token,
                method="POST",
                body={
                    "tag_name": "v1.0.0",
                    "name": "👑 CK3-更好的私人联机助手-DirectLAN v1.0.0 — 开源独立版 (支持自建服 & 玩家电脑直连)",
                    "body": release_notes,
                    "draft": False,
                    "prerelease": False,
                },
            )

    zip_file = ROOT_DIR / "CK3-DirectLAN-v1.0.0-Windows-x64.zip"
    if release_obj and zip_file.is_file():
        print(f"[5/5] 正在上传 Release 发行包附件: {zip_file.name} ({round(zip_file.stat().st_size / 1024 / 1024, 2)} MB)...")
        upload_url_tmpl = release_obj.get("upload_url", "").split("{")[0]
        if upload_url_tmpl:
            # 若已有同名 asset 先删除
            for asset in release_obj.get("assets", []):
                if asset.get("name") == zip_file.name:
                    try:
                        gh_request(f"https://api.github.com/repos/{owner}/{q_repo}/releases/assets/{asset['id']}", token, method="DELETE")
                    except Exception:
                        pass
            up_url = f"{upload_url_tmpl}?name={urllib.parse.quote(zip_file.name)}"
            gh_request(up_url, token, method="POST", body=zip_file.read_bytes(), content_type="application/zip")
            print(f"[+] Release 发行包上传成功！")

    print("=" * 68)
    print(f"🎉 GitHub 开源仓库与 v1.0.0 Release 全部发布成功！")
    print(f"👉 仓库主页  : https://github.com/{owner}/{repo_name}")
    print(f"👉 Release页 : https://github.com/{owner}/{repo_name}/releases/tag/v1.0.0")
    print("=" * 68)


if __name__ == "__main__":
    main()
