#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CK3-DirectLAN · 👑 房主/服务端控制台 GUI (开源独立版)
====================================================================
核心特性：
1. 支持【本机一键开启联机主节点 (电脑对电脑直连)】与【远程管理自建云服务器】两种模式，无任何私有后台或在线更新；
2. 免登录 P 社账号：直接使用本软件的【唯一联机昵称 + 唯一 SteamID64】作为游戏联机账号；
3. 唯一昵称锁与节点准入管理：房主可查看全服在线玩家及已绑定昵称列表，支持一键【放行 / 阻断】以及【🔓 释放昵称锁】。
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import patch_manager
from network_service import NetworkService, detect_local_ip
from ui_user import NicAndNatDialog
from version import APP_VERSION


class AdminApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"CK3-DirectLAN 自建虚拟局域网联机工具 · 👑 房主控制台 v{APP_VERSION} (开源独立版)")
        self.geometry("960x900")
        self.minsize(860, 820)
        self.configure(bg="#0F172A")

        self.net_service = NetworkService(is_admin=True)
        self.game_path = patch_manager.find_steam_ck3_path() or ""
        self.room_mode = "auto"

        self._init_styles()
        self._build_ui()
        self._refresh_game_status()
        self._schedule_poll()

    def _init_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.style.configure(".", background="#0F172A", foreground="#E2E8F0", font=("Microsoft YaHei", 10))
        self.style.configure("Card.TFrame", background="#1E293B", relief="flat")

        self.style.configure("Primary.TButton", background="#3B82F6", foreground="#FFFFFF", font=("Microsoft YaHei", 10, "bold"), borderwidth=0, padding=6)
        self.style.map("Primary.TButton", background=[("active", "#2563EB")])

        self.style.configure("Secondary.TButton", background="#475569", foreground="#E2E8F0", font=("Microsoft YaHei", 9), borderwidth=0, padding=5)
        self.style.map("Secondary.TButton", background=[("active", "#64748B")])

        self.style.configure("Success.TButton", background="#10B981", foreground="#FFFFFF", font=("Microsoft YaHei", 10, "bold"), borderwidth=0, padding=6)
        self.style.map("Success.TButton", background=[("active", "#059669")])

        self.style.configure("Danger.TButton", background="#EF4444", foreground="#FFFFFF", font=("Microsoft YaHei", 10, "bold"), borderwidth=0, padding=6)
        self.style.map("Danger.TButton", background=[("active", "#DC2626")])

        self.style.configure("Host.TButton", background="#8B5CF6", foreground="#FFFFFF", font=("Microsoft YaHei", 10, "bold"), borderwidth=0, padding=6)
        self.style.map("Host.TButton", background=[("active", "#7C3AED")])

        self.style.configure("Treeview", background="#0F172A", foreground="#F8FAFC", fieldbackground="#0F172A", font=("Microsoft YaHei", 9), rowheight=28)
        self.style.configure("Treeview.Heading", background="#1E293B", foreground="#94A3B8", font=("Microsoft YaHei", 10, "bold"))
        self.style.map("Treeview", background=[("selected", "#2563EB")])

    def _build_ui(self):
        main_frame = tk.Frame(self, bg="#0F172A", padx=16, pady=12)
        main_frame.pack(fill="both", expand=True)

        # 0. 顶部：自建云服务器 / 本机电脑直连开服配置栏
        srv_card = tk.Frame(main_frame, bg="#1E293B", highlightbackground="#334155", highlightthickness=1, padx=12, pady=10)
        srv_card.pack(fill="x", pady=(0, 10))

        tk.Label(srv_card, text="🌐 自建服 / 本机 IP:", font=("Microsoft YaHei", 10, "bold"), fg="#38BDF8", bg="#1E293B").pack(side="left", padx=(0, 6))
        self.entry_host = tk.Entry(
            srv_card, width=16, font=("Consolas", 10), bg="#0F172A", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", highlightbackground="#475569", highlightthickness=1
        )
        self.entry_host.insert(0, self.net_service.server_host)
        self.entry_host.pack(side="left", padx=(0, 8), ipady=3)

        tk.Label(srv_card, text="控制端口:", font=("Microsoft YaHei", 9), fg="#94A3B8", bg="#1E293B").pack(side="left")
        self.entry_port = tk.Entry(
            srv_card, width=6, font=("Consolas", 10), bg="#0F172A", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", highlightbackground="#475569", highlightthickness=1
        )
        self.entry_port.insert(0, str(self.net_service.auth_port))
        self.entry_port.pack(side="left", padx=(4, 8), ipady=3)

        tk.Label(srv_card, text="管理密码:", font=("Microsoft YaHei", 9), fg="#94A3B8", bg="#1E293B").pack(side="left")
        self.entry_token = tk.Entry(
            srv_card, width=14, font=("Consolas", 10), bg="#0F172A", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", highlightbackground="#475569", highlightthickness=1
        )
        self.entry_token.insert(0, self.net_service.admin_token)
        self.entry_token.pack(side="left", padx=(4, 8), ipady=3)

        ttk.Button(srv_card, text="🔍 连接并保存", style="Primary.TButton", command=self._test_and_save_server).pack(side="left", padx=(0, 8))

        self.btn_self_host = ttk.Button(srv_card, text="🖥️ 本机一键开启主节点 (电脑直连开服)", style="Host.TButton", command=self._toggle_self_host)
        self.btn_self_host.pack(side="right")

        # 1. 房主昵称与专网节点开关
        top_card = tk.Frame(main_frame, bg="#1E293B", highlightbackground="#334155", highlightthickness=1, padx=12, pady=10)
        top_card.pack(fill="x", pady=(0, 10))

        tk.Label(top_card, text="👑 房主专属昵称 (唯一锁定):", font=("Microsoft YaHei", 10, "bold"), fg="#FBBF24", bg="#1E293B").pack(side="left", padx=(0, 8))
        self.entry_name = tk.Entry(
            top_card, font=("Microsoft YaHei", 11), bg="#0F172A", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", highlightbackground="#475569", highlightthickness=1
        )
        self.entry_name.insert(0, self.net_service.username)
        self.entry_name.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=3)

        ttk.Button(top_card, text="🔒 保存锁定", style="Secondary.TButton", command=self._save_nickname).pack(side="left", padx=(0, 6))
        ttk.Button(top_card, text="📡 网卡与NAT", style="Secondary.TButton", command=self._open_nic_dialog).pack(side="left", padx=(0, 10))

        self.btn_toggle_tunnel = ttk.Button(top_card, text="🚀 启动房主节点 (10.155.155.2)", style="Success.TButton", command=self._toggle_tunnel)
        self.btn_toggle_tunnel.pack(side="right", ipady=4)

        # 2. 补丁与游戏操作卡片
        patch_card = tk.Frame(main_frame, bg="#1E293B", highlightbackground="#334155", highlightthickness=1, padx=12, pady=10)
        patch_card.pack(fill="x", pady=(0, 10))

        path_row = tk.Frame(patch_card, bg="#1E293B")
        path_row.pack(fill="x", pady=(0, 6))
        tk.Label(path_row, text="🎮 游戏目录:", font=("Microsoft YaHei", 10, "bold"), fg="#F8FAFC", bg="#1E293B").pack(side="left", padx=(0, 8))
        self.lbl_path = tk.Label(path_row, text=self.game_path or "未检测到，请点击右侧选择", font=("Microsoft YaHei", 9), fg="#94A3B8", bg="#1E293B", anchor="w")
        self.lbl_path.pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="📁 浏览...", style="Secondary.TButton", command=self._browse_path).pack(side="right")

        act_row = tk.Frame(patch_card, bg="#1E293B")
        act_row.pack(fill="x", pady=(4, 0))
        self.lbl_patch_status = tk.Label(act_row, text="补丁状态: 检测中...", font=("Microsoft YaHei", 10, "bold"), fg="#F59E0B", bg="#1E293B")
        self.lbl_patch_status.pack(side="left", fill="x", expand=True)

        ttk.Button(act_row, text="⚡ 安装虚拟局域网联机补丁", style="Success.TButton", command=self._install_patch).pack(side="right", padx=(6, 0))
        ttk.Button(act_row, text="🔄 还原官方原版", style="Secondary.TButton", command=self._restore_patch).pack(side="right", padx=(6, 0))
        ttk.Button(act_row, text="⚔️ 启动 CK3 建房", style="Primary.TButton", command=self._launch_game).pack(side="right")

        self.lbl_host_tunnel = tk.Label(
            patch_card,
            text="⚪ 房主本机 Planet 专网状态：未启动 (可连接自建云服务器，或点击右上角【🖥️ 本机一键开启主节点】直接用本机电脑做主机)",
            font=("Microsoft YaHei", 9),
            fg="#38BDF8",
            bg="#1E293B",
            anchor="w",
        )
        self.lbl_host_tunnel.pack(fill="x", pady=(6, 0))

        # 3. 👑 房主准入权限与唯一昵称锁控制卡片
        ctrl_card = tk.Frame(main_frame, bg="#1E293B", highlightbackground="#334155", highlightthickness=1, padx=14, pady=12)
        ctrl_card.pack(fill="both", expand=True)

        mode_row = tk.Frame(ctrl_card, bg="#1E293B")
        mode_row.pack(fill="x", pady=(0, 8))
        tk.Label(mode_row, text="🔒 专网准入策略:", font=("Microsoft YaHei", 11, "bold"), fg="#38BDF8", bg="#1E293B").pack(side="left", padx=(0, 10))

        self.mode_var = tk.StringVar(value="auto")
        rb_auto = tk.Radiobutton(
            mode_row,
            text="🟢 自由加入模式 (Controller 自动授权，无需手动审核)",
            variable=self.mode_var,
            value="auto",
            command=self._on_mode_change,
            bg="#1E293B",
            fg="#E2E8F0",
            selectcolor="#0F172A",
            activebackground="#1E293B",
            activeforeground="#FFFFFF",
        )
        rb_auto.pack(side="left", padx=(0, 10))

        rb_whitelist = tk.Radiobutton(
            mode_row,
            text="🛡️ 白名单审核模式 (需房主放行才在 Controller 授权虚拟网卡)",
            variable=self.mode_var,
            value="whitelist",
            command=self._on_mode_change,
            bg="#1E293B",
            fg="#E2E8F0",
            selectcolor="#0F172A",
            activebackground="#1E293B",
            activeforeground="#FFFFFF",
        )
        rb_whitelist.pack(side="left", padx=(0, 10))

        ttk.Button(mode_row, text="全部放行 🟢", style="Success.TButton", command=self._allow_all).pack(side="right", padx=(6, 0))
        ttk.Button(mode_row, text="全部阻断 🔴", style="Danger.TButton", command=self._block_all).pack(side="right")

        tree_frame = tk.Frame(ctrl_card, bg="#0F172A")
        tree_frame.pack(fill="both", expand=True, pady=(6, 8))

        columns = ("name", "id", "zt_addr", "ip", "status", "action")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="唯一绑定昵称 (软件账号)")
        self.tree.heading("id", text="客户端 ID")
        self.tree.heading("zt_addr", text="ZeroTier 节点 ID")
        self.tree.heading("ip", text="虚拟局域网 IP")
        self.tree.heading("status", text="通行状态 (红绿灯)")
        self.tree.heading("action", text="Controller 授权状态")

        self.tree.column("name", width=170, anchor="w")
        self.tree.column("id", width=95, anchor="center")
        self.tree.column("zt_addr", width=115, anchor="center")
        self.tree.column("ip", width=135, anchor="center")
        self.tree.column("status", width=165, anchor="center")
        self.tree.column("action", width=135, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        op_row = tk.Frame(ctrl_card, bg="#1E293B")
        op_row.pack(fill="x", pady=(4, 0))
        self.lbl_selected = tk.Label(
            op_row, text="💡 提示：双击玩家切换【放行/阻断】；选中玩家点击【🔓 释放昵称锁】可解除该昵称占用", font=("Microsoft YaHei", 9), fg="#94A3B8", bg="#1E293B"
        )
        self.lbl_selected.pack(side="left")

        ttk.Button(op_row, text="🟢 放行选定玩家", style="Success.TButton", command=self._allow_selected).pack(side="right", padx=(6, 0))
        ttk.Button(op_row, text="🔴 阻断选定玩家", style="Danger.TButton", command=self._block_selected).pack(side="right", padx=(6, 0))
        ttk.Button(op_row, text="🔓 释放选中玩家昵称锁", style="Secondary.TButton", command=self._release_selected_name).pack(side="right")

        self.lbl_cloud_status = tk.Label(
            main_frame,
            text=f"🌐 CK3-DirectLAN 开源独立版 v{APP_VERSION} | 支持自建云服务器 & 玩家电脑对电脑直连",
            font=("Microsoft YaHei", 9),
            fg="#64748B",
            bg="#0F172A",
        )
        self.lbl_cloud_status.pack(side="left", pady=(4, 0))

        self.tree.bind("<Double-1>", lambda e: self._toggle_selected())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _sync_endpoint_from_ui(self):
        host = self.entry_host.get().strip() or "127.0.0.1"
        try:
            port = int(self.entry_port.get().strip() or "12030")
        except Exception:
            port = 12030
        token = self.entry_token.get().strip() or "ck3_open_admin"
        self.net_service.set_server_endpoint(host, auth_port=port, admin_token=token)

    def _test_and_save_server(self):
        self._sync_endpoint_from_ui()

        def worker():
            ok, info, err = self.net_service.test_server_reachability()
            if ok:
                msg = (
                    f"✅ 成功连接到联机主节点！\n\n"
                    f"• 节点地址: {self.net_service.base_http_url}\n"
                    f"• ZeroTier Planet 端口: {info.get('ztPort', 12020)}\n"
                    f"• 虚拟局域网 ID (NWID): {info.get('defaultNwid', '-')}\n"
                    f"• Controller 状态: {'在线 (' + str(info.get('controllerAddress')) + ')' if info.get('controllerOnline') else '未就绪'}"
                )
                self.after(0, lambda: messagebox.showinfo("节点连接成功", msg))
                self._poll_players()
            else:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "节点连接失败",
                        f"无法连接到 {self.net_service.base_http_url}\n错误原因: {err}\n\n"
                        f"若你尚未启动云服务器，可直接点击右上角【🖥️ 本机一键开启主节点】在本机开服！",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_self_host(self):
        if self.net_service.is_self_hosted_running():
            self.net_service.stop_self_hosted_node()
            self.btn_self_host.configure(text="🖥️ 本机一键开启主节点 (电脑直连开服)")
            messagebox.showinfo("已停止", "本机直连主节点已关闭。")
            return

        default_ip = detect_local_ip()
        host_ip = simpledialog.askstring(
            "🖥️ 在本机启动联机主节点 (玩家电脑直连开服)",
            "请输入本机用于供朋友连接的 IP 地址：\n"
            "• 局域网/校园网/异地组网直连：填本机局域网 IP\n"
            "• 路由器端口映射/公网直连：填本机公网 IP (需映射 TCP 12030 与 UDP/TCP 12020)",
            initialvalue=default_ip,
            parent=self,
        )
        if not host_ip:
            return

        self._sync_endpoint_from_ui()
        ok, msg = self.net_service.start_self_hosted_node(
            public_ip=host_ip.strip(),
            auth_port=self.net_service.auth_port,
            zt_port=self.net_service.zt_server_port,
            admin_token=self.net_service.admin_token,
        )
        if ok:
            self.entry_host.delete(0, tk.END)
            self.entry_host.insert(0, host_ip.strip())
            self.btn_self_host.configure(text="🛑 停止本机主节点 (运行中)")
            messagebox.showinfo("本机主节点已启动", msg)
        else:
            messagebox.showerror("启动失败", msg)

    def _open_nic_dialog(self):
        NicAndNatDialog(self, self.net_service)

    def _save_nickname(self):
        self._sync_endpoint_from_ui()
        name = self.entry_name.get().strip() or "Host"
        ok, msg = self.net_service.check_and_reserve_username(name)
        if not ok:
            messagebox.showerror("❌ 昵称已被占用", msg)
            return
        if patch_manager.verify_ck3_path(self.game_path):
            status, _ = patch_manager.get_patch_status(self.game_path)
            if status == "PATCHED":
                patch_manager.install_patch(
                    self.game_path,
                    name,
                    host_ip=self.net_service.host_ip,
                    peer_ips=self.net_service.peer_ips,
                    enable_relay_shield=self.net_service.use_relay_shield,
                    client_id=self.net_service.client_id,
                )
        messagebox.showinfo("🔒 房主昵称锁定成功", msg)

    def _browse_path(self):
        path = filedialog.askdirectory(title="请选择 Crusader Kings III 游戏根目录")
        if path and patch_manager.verify_ck3_path(path):
            self.game_path = path
            self.lbl_path.configure(text=path)
            self._refresh_game_status()
        elif path:
            messagebox.showerror("错误", "所选目录下未找到 ck3.exe！")

    def _refresh_game_status(self):
        if not self.game_path or not patch_manager.verify_ck3_path(self.game_path):
            self.lbl_patch_status.configure(text="补丁状态: 未找到游戏目录", fg="#EF4444")
            return
        status, desc = patch_manager.get_patch_status(self.game_path)
        self.lbl_patch_status.configure(text=f"补丁状态: {desc}", fg="#10B981" if status == "PATCHED" else "#94A3B8")

    def _install_patch(self):
        self._sync_endpoint_from_ui()
        name = self.entry_name.get().strip() or "Host"
        ok_name, msg_name = self.net_service.check_and_reserve_username(name)
        if not ok_name:
            messagebox.showerror("❌ 昵称已被占用", msg_name)
            return
        ok, msg = patch_manager.install_patch(
            self.game_path,
            self.net_service.username,
            host_ip=self.net_service.host_ip,
            peer_ips=self.net_service.peer_ips,
            enable_relay_shield=self.net_service.use_relay_shield,
            client_id=self.net_service.client_id,
        )
        if ok:
            messagebox.showinfo("成功", msg)
        else:
            messagebox.showerror("失败", msg)
        self._refresh_game_status()

    def _restore_patch(self):
        if messagebox.askyesno("确认", "确定还原为官方原版？"):
            ok, msg = patch_manager.restore_original(self.game_path)
            if ok:
                messagebox.showinfo("成功", msg)
            else:
                messagebox.showerror("失败", msg)
            self._refresh_game_status()

    def _launch_game(self):
        self._sync_endpoint_from_ui()
        name = self.entry_name.get().strip() or "Host"
        ok_name, msg_name = self.net_service.check_and_reserve_username(name)
        if not ok_name:
            messagebox.showerror("❌ 昵称冲突", msg_name)
            return
        status, _ = patch_manager.get_patch_status(self.game_path)
        if status != "PATCHED":
            if messagebox.askyesno("提示", "当前尚未安装虚拟局域网联机补丁，是否现在立即自动安装并启动游戏？"):
                self._install_patch()
        else:
            patch_manager.install_patch(
                self.game_path,
                self.net_service.username,
                host_ip=self.net_service.host_ip,
                peer_ips=self.net_service.peer_ips,
                enable_relay_shield=self.net_service.use_relay_shield,
                client_id=self.net_service.client_id,
            )
        ok, msg = patch_manager.launch_game(
            self.game_path,
            virtual_ip=self.net_service.virtual_ip,
            use_force_bind=self.net_service.use_force_bind,
        )
        if not ok:
            messagebox.showerror("启动失败", msg)

    def _toggle_tunnel(self):
        if not self.net_service.is_running:
            self._sync_endpoint_from_ui()
            self.net_service.username = self.entry_name.get().strip() or "Host"
            ok, msg = self.net_service.start_tunnel()
            if ok:
                self.btn_toggle_tunnel.configure(text="⏹️ 关闭房主节点", style="Danger.TButton")
            else:
                messagebox.showerror("启动失败", msg)
        else:
            self.net_service.stop_tunnel()
            self.btn_toggle_tunnel.configure(text="🚀 启动房主节点 (10.155.155.2)", style="Success.TButton")

    def _on_mode_change(self):
        self._sync_endpoint_from_ui()
        m = self.mode_var.get()
        self.net_service.admin_set_mode(m)

    def _allow_all(self):
        self._sync_endpoint_from_ui()
        ok, players, _ = self.net_service.admin_get_players()
        if ok:
            for p in players:
                self.net_service.admin_toggle_player(p["id"], True)
            self._poll_players()

    def _block_all(self):
        self._sync_endpoint_from_ui()
        ok, players, _ = self.net_service.admin_get_players()
        if ok:
            for p in players:
                self.net_service.admin_toggle_player(p["id"], False)
            self._poll_players()

    def _get_selected_pid(self):
        sel = self.tree.selection()
        if sel:
            item = self.tree.item(sel[0])
            return str(item["values"][1])
        return None

    def _allow_selected(self):
        pid = self._get_selected_pid()
        if pid:
            self.net_service.admin_toggle_player(pid, True)
            self._poll_players()

    def _block_selected(self):
        pid = self._get_selected_pid()
        if pid:
            self.net_service.admin_toggle_player(pid, False)
            self._poll_players()

    def _release_selected_name(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选中要释放昵称锁的玩家！")
            return
        vals = self.tree.item(sel[0])["values"]
        uname, pid = str(vals[0]), str(vals[1])
        if messagebox.askyesno("确认释放昵称锁", f"确定要释放玩家【{uname}】(ID: {pid}) 的唯一昵称绑定锁吗？\n释放后任何玩家均可重新绑定该昵称。"):
            if self.net_service.admin_release_player_name(player_id=pid, username=uname):
                messagebox.showinfo("已释放", f"昵称【{uname}】的唯一绑定锁已成功释放！")
                self._poll_players()
            else:
                messagebox.showerror("失败", "请求服务端释放昵称锁失败。")

    def _toggle_selected(self):
        pid = self._get_selected_pid()
        if pid:
            sel = self.tree.selection()
            status_str = self.tree.item(sel[0])["values"][4]
            currently_allowed = "🟢" in status_str
            self.net_service.admin_toggle_player(pid, not currently_allowed)
            self._poll_players()

    def _schedule_poll(self):
        self.lbl_host_tunnel.configure(text=f"📡 房主本机专网状态：{self.net_service.status_text}")
        threading.Thread(target=self._poll_players, daemon=True).start()
        self.after(2500, self._schedule_poll)

    def _poll_players(self):
        ok, players, mode = self.net_service.admin_get_players()
        if not ok:
            return
        self.after(0, self._render_players, players, mode)

    def _render_players(self, players, mode):
        if mode != self.room_mode:
            self.room_mode = mode
            self.mode_var.set(mode)

        sel_pid = self._get_selected_pid()

        for item in self.tree.get_children():
            self.tree.delete(item)

        for p in players:
            pid = p.get("id", "")
            uname = p.get("username", "")
            zt_addr = p.get("zt_address") or "-"
            ip = p.get("ip") or "已连入"
            allowed = p.get("allowed", False)
            conflict = p.get("name_conflict", False)
            if conflict:
                status_text = "🔴 昵称冲突拦截"
                act_text = "昵称重复未授权"
            else:
                status_text = "🟢 正常放行 (绿灯)" if allowed else "🔴 已阻断 (红灯)"
                act_text = "Controller 已授权" if allowed else "Controller 已撤销"

            item_id = self.tree.insert("", "end", values=(uname, pid, zt_addr, ip, status_text, act_text))
            if str(pid) == str(sel_pid):
                self.tree.selection_set(item_id)

    def _on_close(self):
        if self.net_service.is_running:
            self.net_service.stop_tunnel()
        if self.net_service.is_self_hosted_running():
            self.net_service.stop_self_hosted_node()
        self.destroy()


def ensure_admin():
    try:
        import ctypes

        if not ctypes.windll.shell32.IsUserAnAdmin():
            params = " ".join([f'"{arg}"' for arg in sys.argv])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
            sys.exit(0)
    except Exception:
        pass


def main():
    ensure_admin()
    app = AdminApp()
    app.mainloop()


if __name__ == "__main__":
    main()
