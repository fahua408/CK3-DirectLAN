#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CK3-DirectLAN · 免安装 Git 纯 Python 一键上传至 GitHub 仓库 & 自动发布 Release 工具
====================================================================================
由于本机未安装 git.exe，本脚本直接通过 GitHub 官方 REST API (https://api.github.com):
1. 自动在你的 GitHub 账号下创建或规范化开源仓库 (默认名称: CK3-DirectLAN)
2. 自动清理可能引发合规风险的冗余文件，并将源码、脚本、教程、脱敏实测截图推送至 main 分支
3. 自动设置 20 个高权重 SEO Topics 标签，最大化 GitHub 与搜索引擎曝光量
4. 自动创建/更新 v1.0.0 GitHub Release，并将编译好的 Windows 发行包上传为 Release 附件！
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

# 需要上传到 GitHub 源码仓库的合规文件列表
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
    "bin/zero/priority.bat",
]

# 需要在公开源码树中隐藏/移除的敏感或第三方原始文件
REMOVE_FROM_REPO_PATHS = [
    "bin/lan_patch/ColdClientLoader.ini",
    "bin/lan_patch/steam_settings/DLC.txt",
    "bin/lan_patch/steam_settings/disable_lan_only.txt",
    "assets/multiplayer_demo.mp4",
]

SEO_TOPICS = [
    "ck3",
    "crusader-kings-3",
    "crusader-kings-iii",
    "multiplayer",
    "zerotier",
    "zerotier-planet",
    "p2p",
    "virtual-lan",
    "lan-multiplayer",
    "paradox-interactive",
    "game-networking",
    "nat-traversal",
    "python",
    "windows",
    "direct-connect",
    "low-latency",
    "gaming-tool",
    "self-hosted",
    "vlan",
    "strategy-game",
]


def gh_request(url: str, token: str, method: str = "GET", body: dict | bytes | None = None, content_type: str = "application/json") -> dict | list:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CK3-DirectLAN-Uploader/1.1",
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
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw) if raw else {}


def main():
    parser = argparse.ArgumentParser(description="一键将 CK3-DirectLAN 上传至 GitHub 并发布 Release")
    parser.add_argument("--token", default="", help="GitHub Personal Access Token (需勾选 repo 权限)")
    parser.add_argument("--repo", default="CK3-DirectLAN", help="目标仓库名 (默认 CK3-DirectLAN)")
    parser.add_argument("--private", action="store_true", help="是否设为私有仓库 (默认公开开源仓库)")
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

    target_slug = "CK3-DirectLAN"
    desc = (
        "👑 CK3-更好的私人联机助手-DirectLAN | 《十字军之王3 / 王国风云3 (Crusader Kings III)》"
        "自建虚拟局域网 P2P 高速直连联机工具 | 支持玩家电脑对电脑直连 & 自建云服务器 Planet 根节点 | "
        "唯一联机昵称锁 + 兼容 1.18+《白银与丝绸》| 实测 4~5 速稳定同步 (CK3 LAN Multiplayer & Desync/Lag Optimization)"
    )

    # 2. 检查现有仓库 (如果之前创建为 CK3---DirectLAN 则自动规范重命名为 CK3-DirectLAN)
    print(f"[2/5] 正在检查/规范化仓库 {owner}/{target_slug} ...")
    repo_name = target_slug
    found_existing = False
    for check_slug in (target_slug, "CK3---DirectLAN", args.repo.strip()):
        if not check_slug:
            continue
        try:
            repo_obj = gh_request(f"https://api.github.com/repos/{owner}/{urllib.parse.quote(check_slug)}", token)
            actual_name = repo_obj["name"]
            found_existing = True
            if actual_name != target_slug:
                print(f"[*] 正在将旧仓库 URL ({actual_name}) 规范化重命名为高 SEO 名称 ({target_slug})...")
                updated = gh_request(
                    f"https://api.github.com/repos/{owner}/{urllib.parse.quote(actual_name)}",
                    token,
                    method="PATCH",
                    body={"name": target_slug, "description": desc, "private": bool(args.private)},
                )
                repo_name = updated["name"]
            else:
                gh_request(
                    f"https://api.github.com/repos/{owner}/{urllib.parse.quote(actual_name)}",
                    token,
                    method="PATCH",
                    body={"description": desc, "private": bool(args.private)},
                )
                repo_name = actual_name
            print(f"[+] 仓库已就绪: https://github.com/{owner}/{repo_name}")
            break
        except urllib.error.HTTPError as he:
            if he.code == 404:
                continue
            raise

    if not found_existing:
        created_repo = gh_request(
            "https://api.github.com/user/repos",
            token,
            method="POST",
            body={
                "name": target_slug,
                "description": desc,
                "private": bool(args.private),
                "auto_init": True,
            },
        )
        repo_name = created_repo["name"]
        print(f"[+] 成功创建 GitHub 开源仓库: https://github.com/{owner}/{repo_name}")

    q_repo = urllib.parse.quote(repo_name)

    # 设置 20 个满额 SEO Topics 标签
    try:
        gh_request(
            f"https://api.github.com/repos/{owner}/{q_repo}/topics",
            token,
            method="PUT",
            body={"names": SEO_TOPICS},
        )
        print(f"[+] 已配置 {len(SEO_TOPICS)} 个 GitHub 高权重搜索标签 (Topics)")
    except Exception as e:
        print(f"[!] Topics 设置提示: {e}")

    # 清理/隐藏公开源码树中不合规或不需要展示的文件
    for rm_path in REMOVE_FROM_REPO_PATHS:
        api_rm = f"https://api.github.com/repos/{owner}/{q_repo}/contents/{urllib.parse.quote(rm_path)}"
        try:
            existing_rm = gh_request(api_rm, token)
            if isinstance(existing_rm, dict) and existing_rm.get("sha"):
                gh_request(
                    api_rm,
                    token,
                    method="DELETE",
                    body={"message": f"Remove {rm_path} for compliance", "sha": existing_rm["sha"]},
                )
                print(f"   🛡️ 已从公开源码树隐藏/移除: {rm_path}")
        except urllib.error.HTTPError as he:
            if he.code != 404:
                print(f"   [!] 清理 {rm_path} 提示: {he}")
        except Exception:
            pass

    # 3. 逐个上传仓库文件 (Contents API 自动处理创建与更新)
    print("[3/5] 正在上传合规化源码、脚本、教程与隐私脱敏截图至 GitHub ...")
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

    # 4. 创建或更新 v1.0.0 Release 并上传 Windows 可执行程序压缩包
    print("[4/5] 正在创建/更新 v1.0.0 GitHub Release...")
    release_title = "👑 CK3-更好的私人联机助手-DirectLAN v1.0.0 — 开源独立版 (支持自建服 & 玩家电脑P2P直连)"
    release_notes = """## 🎉 CK3-更好的私人联机助手-DirectLAN v1.0.0 正式开源发布！

- **双模式自主联机（零商业后台依赖）**：支持【🖥️ 玩家电脑对电脑直连（免云服务器）】与【☁️ 玩家自建云服务器（附 Linux/Windows 一键脚本）】。
- **局域网大厅直连 + 全服唯一联机昵称锁**：自动绑定唯一 64 位会话标识 (`SteamID64`) 与唯一联机昵称，当前玩家占用的昵称他人无法重名，改名自动释放。
- **兼容最新 1.18+《普天之下 / 白银与丝绸》大型剧本联机协议**：实测 4~5 速双方玩家日期完全同步。
- **一键无损还原官方默认模式**。
"""
    release_obj = None
    try:
        release_obj = gh_request(f"https://api.github.com/repos/{owner}/{q_repo}/releases/tags/v1.0.0", token)
        if isinstance(release_obj, dict) and release_obj.get("id"):
            release_obj = gh_request(
                f"https://api.github.com/repos/{owner}/{q_repo}/releases/{release_obj['id']}",
                token,
                method="PATCH",
                body={
                    "name": release_title,
                    "body": release_notes,
                },
            )
    except urllib.error.HTTPError as he:
        if he.code == 404:
            release_obj = gh_request(
                f"https://api.github.com/repos/{owner}/{q_repo}/releases",
                token,
                method="POST",
                body={
                    "tag_name": "v1.0.0",
                    "name": release_title,
                    "body": release_notes,
                    "draft": False,
                    "prerelease": False,
                },
            )

    zip_file = ROOT_DIR / "CK3-DirectLAN-v1.0.0-Windows-x64.zip"
    if release_obj and zip_file.is_file():
        print(f"[5/5] 正在上传最新合规版 Release 发行包附件: {zip_file.name} ({round(zip_file.stat().st_size / 1024 / 1024, 2)} MB)...")
        upload_url_tmpl = release_obj.get("upload_url", "").split("{")[0]
        if upload_url_tmpl:
            for asset in release_obj.get("assets", []):
                if asset.get("name") == zip_file.name:
                    try:
                        gh_request(f"https://api.github.com/repos/{owner}/{q_repo}/releases/assets/{asset['id']}", token, method="DELETE")
                    except Exception:
                        pass
            up_url = f"{upload_url_tmpl}?name={urllib.parse.quote(zip_file.name)}"
            gh_request(up_url, token, method="POST", body=zip_file.read_bytes(), content_type="application/zip")
            print("[+] Release 发行包上传成功！")

    print("=" * 68)
    print("🎉 GitHub 开源仓库合规化升级、SEO 优化与 v1.0.0 Release 全部发布成功！")
    print(f"👉 规范化仓库主页 : https://github.com/{owner}/{repo_name}")
    print(f"👉 Release 下载页 : https://github.com/{owner}/{repo_name}/releases/tag/v1.0.0")
    print("=" * 68)


if __name__ == "__main__":
    main()
