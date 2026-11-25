#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CK3-DirectLAN · 玩家端 GUI (开源独立版)
====================================================================
核心特性：
1. 支持【连接自建云服务器】与【玩家电脑对电脑直连 (填房主电脑 IP)】两种拓扑，无任何第三方后台或在线更新；
2. 免登录 P 社账号：直接使用本软件的【唯一联机昵称 + 唯一 SteamID64】作为游戏联机账号；
3. 联机昵称唯一锁定：服务端实时校验并锁定，当前玩家绑定后其他人不可同名，改名时自动释放旧名；
4. 6 步自建 ZeroTier Planet 虚拟局域网引擎 + DirectLAN 虚拟大厅联机补丁（适配《白银与丝绸》）+ P2P 路由加速。
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import patch_manager
from network_service import NetworkService, detect_local_ip
from version import APP_VERSION


class NicAndNatDialog(tk.Toplevel):
    """网卡优先级管理与 NAT 类型诊断弹窗"""

    def __init__(self, parent: tk.Misc, net_service: NetworkService):
        super().__init__(parent)
        self.net_service = net_service
        self.title("📡 网卡路由优先级管理 & NAT 联机诊断")
        self.geometry("760x460")
        self.configure(bg="#12161E")
        self.transient(parent)

        top_bar = tk.Frame(self, bg="#1A212E", padx=12, pady=10)
        top_bar.pack(fill="x", padx=12, pady=(12, 6))

        self.lbl_nat = tk.Label(
            top_bar,
            text=f"🛡️ 本机 NAT 类型: {self.net_service.nat_type} {('(' + self.net_service.nat_text + ')') if self.net_service.nat_text else '(点击右侧按钮检测)'}",
            font=("Microsoft YaHei", 9, "bold"),
            fg="#38BDF8",
            bg="#1A212E",
            anchor="w",
        )
        self.lbl_nat.pack(side="left", fill="x", expand=True)

        ttk.Button(top_bar, text="🛡️ 检测 NAT 类型", style="Secondary.TButton", command=self._run_nat).pack(side="right", padx=(6, 0))
        ttk.Button(top_bar, text="⚡ 一键设 ZeroTier 跃点数为 1", style="Primary.TButton", command=self._opt_metric).pack(side="right")

        tip = tk.Label(
            self,
            text="💡 提示：若游戏内搜不到房间，可点击【一键设 ZeroTier 跃点数为 1】，或选中多余虚拟网卡（如 VMware/VirtualBox）点击【禁用选中网卡】。切勿禁用正在上网的物理网卡！",
            font=("Microsoft YaHei", 9),
            fg="#F59E0B",
            bg="#12161E",
            justify="left",
            wraplength=730,
        )
        tip.pack(fill="x", padx=14, pady=(2, 6))

        cols = ("name", "description", "metric", "mtu", "status", "admin_state")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=11)
        self.tree.heading("name", text="网卡名称")
        self.tree.heading("description", text="硬件/虚拟网卡描述")
        self.tree.heading("metric", text="跃点数(Metric)")
        self.tree.heading("mtu", text="MTU")
        self.tree.heading("status", text="连接状态")
        self.tree.heading("admin_state", text="启用状态")

        self.tree.column("name", width=165)
        self.tree.column("description", width=230)
        self.tree.column("metric", width=95, anchor="center")
        self.tree.column("mtu", width=65, anchor="center")
        self.tree.column("status", width=85, anchor="center")
        self.tree.column("admin_state", width=80, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=12, pady=4)

        btn_row = tk.Frame(self, bg="#12161E")
        btn_row.pack(fill="x", padx=12, pady=8)
        ttk.Button(btn_row, text="🔄 刷新网卡列表", style="Secondary.TButton", command=self._refresh).pack(side="left")
        ttk.Button(btn_row, text="🟢 启用选中网卡", style="Success.TButton", command=lambda: self._toggle(True)).pack(side="right", padx=(6, 0))
        ttk.Button(btn_row, text="🔴 禁用选中网卡", style="Danger.TButton", command=lambda: self._toggle(False)).pack(side="right")

        self._refresh()

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for iface in self.net_service.get_network_interfaces():
            self.tree.insert(
                "",
                "end",
                values=(
                    iface.get("name", ""),
                    iface.get("description", ""),
                    iface.get("metric", ""),
                    iface.get("mtu", ""),
                    iface.get("status", ""),
                    iface.get("admin_state", ""),
                ),
            )

    def _opt_metric(self):
        names = self.net_service.optimize_zerotier_adapter_metric()
        self._refresh()
        if names:
            messagebox.showinfo("优化成功", f"已将以下 ZeroTier 虚拟网卡跃点数设为 1 (最高优先级) 并开启转发:\n{', '.join(names)}", parent=self)
        else:
            messagebox.showwarning("提示", "暂未检测到活动的 ZeroTier 虚拟网卡，请先点击主界面【🚀 一键连入专网】！", parent=self)

    def _run_nat(self):
        self.lbl_nat.configure(text="🛡️ 正在调用 NATTest.exe 检测本机 NAT 类型，请稍候...")

        def worker():
            ntype, ntext = self.net_service.detect_nat_type()
            self.after(0, lambda: self.lbl_nat.configure(text=f"🛡️ 本机 NAT 类型: {ntype} ({ntext})"))

        threading.Thread(target=worker, daemon=True).start()

    def _toggle(self, enable: bool):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选中一张网卡", parent=self)
            return
        iface_name = self.tree.item(sel[0], "values")[0]
        if not enable and not messagebox.askyesno("确认禁用", f"确定要禁用网卡【{iface_name}】吗？\n(切勿禁用你的物理上网网卡)", parent=self):
            return

        def worker():
            self.net_service.set_interface_enabled(iface_name, enable)
            self.after(400, self._refresh)

        threading.Thread(target=worker, daemon=True).start()


class UserApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"CK3-DirectLAN 自建虚拟局域网联机工具 · 玩家端 v{APP_VERSION} (开源独立版)")
        self.geometry("820x930")
        self.minsize(760, 860)
        self.configure(bg="#12161E")

        self.net_service = NetworkService(is_admin=False)
        self.game_path = patch_manager.find_steam_ck3_path() or ""

        self._init_styles()
        self._build_ui()
        self._refresh_game_status()
        self._schedule_poll()

    def _init_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.style.configure(".", background="#12161E", foreground="#E2E8F0", font=("Microsoft YaHei", 10))
        self.style.configure("Card.TFrame", background="#1A212E", relief="flat")

        self.style.configure("Primary.TButton", background="#2563EB", foreground="#FFFFFF", font=("Microsoft YaHei", 10, "bold"), borderwidth=0, padding=6)
        self.style.map("Primary.TButton", background=[("active", "#1D4ED8"), ("disabled", "#334155")])

        self.style.configure("Secondary.TButton", background="#334155", foreground="#E2E8F0", font=("Microsoft YaHei", 9), borderwidth=0, padding=5)
        self.style.map("Secondary.TButton", background=[("active", "#475569")])

        self.style.configure("Success.TButton", background="#10B981", foreground="#FFFFFF", font=("Microsoft YaHei", 10, "bold"), borderwidth=0, padding=6)
        self.style.map("Success.TButton", background=[("active", "#059669"), ("disabled", "#334155")])

        self.style.configure("Danger.TButton", background="#EF4444", foreground="#FFFFFF", font=("Microsoft YaHei", 10, "bold"), borderwidth=0, padding=6)
        self.style.map("Danger.TButton", background=[("active", "#DC2626")])

        self.style.configure("Host.TButton", background="#8B5CF6", foreground="#FFFFFF", font=("Microsoft YaHei", 9, "bold"), borderwidth=0, padding=5)
        self.style.map("Host.TButton", background=[("active", "#7C3AED")])

        self.style.configure("BigLaunch.TButton", background="#059669", foreground="#FFFFFF", font=("Microsoft YaHei", 13, "bold"), padding=10)
        self.style.map("BigLaunch.TButton", background=[("active", "#047857"), ("disabled", "#334155")])

    def _build_ui(self):
        self.main_frame = tk.Frame(self, bg="#12161E", padx=16, pady=12)
        self.main_frame.pack(fill="both", expand=True)

        # 1. 顶部：连接服务器 / 玩家电脑对电脑直连配置卡片
        srv_card = tk.Frame(self.main_frame, bg="#1A212E", highlightbackground="#2B3548", highlightthickness=1, padx=12, pady=10)
        srv_card.pack(fill="x", pady=(0, 10))

        tk.Label(srv_card, text="🌐 自建服 / 房主电脑 IP:", font=("Microsoft YaHei", 10, "bold"), fg="#38BDF8", bg="#1A212E").pack(side="left", padx=(0, 6))
        self.entry_host = tk.Entry(
            srv_card, width=18, font=("Consolas", 11), bg="#10141C", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", highlightbackground="#334155", highlightthickness=1
        )
        self.entry_host.insert(0, self.net_service.server_host)
        self.entry_host.pack(side="left", padx=(0, 8), ipady=3)

        tk.Label(srv_card, text="控制端口:", font=("Microsoft YaHei", 9), fg="#94A3B8", bg="#1A212E").pack(side="left")
        self.entry_port = tk.Entry(
            srv_card, width=7, font=("Consolas", 10), bg="#10141C", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", highlightbackground="#334155", highlightthickness=1
        )
        self.entry_port.insert(0, str(self.net_service.auth_port))
        self.entry_port.pack(side="left", padx=(4, 8), ipady=3)

        ttk.Button(srv_card, text="🔍 测试并保存节点", style="Primary.TButton", command=self._test_and_save_server).pack(side="left", padx=(0, 8))

        self.btn_self_host = ttk.Button(srv_card, text="🖥️ 本机一键做主机 (电脑直连)", style="Host.TButton", command=self._toggle_self_host)
        self.btn_self_host.pack(side="right")

        # 2. 专属联机账号昵称卡片 (免登录P社账号 + 全服唯一昵称锁)
        name_card = tk.Frame(self.main_frame, bg="#1A212E", highlightbackground="#2B3548", highlightthickness=1, padx=12, pady=10)
        name_card.pack(fill="x", pady=(0, 10))

        tk.Label(name_card, text="👤 专属联机昵称 (免P社账号·唯一锁定):", font=("Microsoft YaHei", 10, "bold"), fg="#93C5FD", bg="#1A212E").pack(side="left", padx=(0, 8))
        self.entry_name = tk.Entry(
            name_card, font=("Microsoft YaHei", 11), bg="#10141C", fg="#FFFFFF", insertbackground="#FFFFFF", relief="flat", highlightbackground="#334155", highlightthickness=1
        )
        self.entry_name.insert(0, self.net_service.username)
        self.entry_name.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=3)

        ttk.Button(name_card, text="📡 网卡与NAT诊断", style="Secondary.TButton", command=self._open_nic_dialog).pack(side="right", padx=(6, 0))
        ttk.Button(name_card, text="🔒 保存并锁定昵称", style="Secondary.TButton", command=self._save_nickname).pack(side="right")

        # 3. 游戏路径与虚拟局域网联机补丁卡片
        patch_card = tk.Frame(self.main_frame, bg="#1A212E", highlightbackground="#2B3548", highlightthickness=1, padx=12, pady=10)
        patch_card.pack(fill="x", pady=(0, 10))

        path_row = tk.Frame(patch_card, bg="#1A212E")
        path_row.pack(fill="x", pady=(0, 6))
        tk.Label(path_row, text="🎮 游戏目录:", font=("Microsoft YaHei", 10, "bold"), fg="#F8FAFC", bg="#1A212E").pack(side="left", padx=(0, 8))
        self.lbl_path = tk.Label(path_row, text=self.game_path or "未检测到，请点击右侧浏览选择", font=("Microsoft YaHei", 9), fg="#94A3B8", bg="#1A212E", anchor="w")
        self.lbl_path.pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="📁 浏览...", style="Secondary.TButton", command=self._browse_path).pack(side="right")

        btn_row = tk.Frame(patch_card, bg="#1A212E")
        btn_row.pack(fill="x", pady=(4, 6))
        self.lbl_patch_status = tk.Label(btn_row, text="补丁状态: 检测中...", font=("Microsoft YaHei", 10, "bold"), fg="#F59E0B", bg="#1A212E")
        self.lbl_patch_status.pack(side="left", fill="x", expand=True)

        self.btn_install_patch = ttk.Button(btn_row, text="⚡ 安装虚拟局域网联机补丁", style="Success.TButton", command=self._install_patch)
        self.btn_install_patch.pack(side="right", padx=(6, 0))

        self.btn_restore_patch = ttk.Button(btn_row, text="🔄 还原官方原版", style="Secondary.TButton", command=self._restore_patch)
        self.btn_restore_patch.pack(side="right")

        lbl_desc = tk.Label(
            patch_card,
            text="💡 说明：安装补丁后无需登录 P 社账号！系统自动将上方的【专属联机昵称 + 唯一 SteamID64】绑定为你的游戏联机账号（适配至《白银与丝绸》全 37 款 DLC），并可随时无损还原原版。",
            font=("Microsoft YaHei", 9),
            fg="#64748B",
            bg="#1A212E",
            justify="left",
            wraplength=750,
        )
        lbl_desc.pack(fill="x", pady=(4, 0))

        # 4. 核心红绿灯通行指示与 Planet 虚拟专网面板
        tunnel_card = tk.Frame(self.main_frame, bg="#1A212E", highlightbackground="#2B3548", highlightthickness=1, padx=14, pady=12)
        tunnel_card.pack(fill="x", pady=(0, 10))

        light_box = tk.Frame(tunnel_card, bg="#1A212E")
        light_box.pack(fill="x", pady=(0, 8))

        self.lbl_light = tk.Label(light_box, text="⚪", font=("Segoe UI Emoji", 28), bg="#1A212E")
        self.lbl_light.pack(side="left", padx=(0, 12))

        txt_box = tk.Frame(light_box, bg="#1A212E")
        txt_box.pack(side="left", fill="x", expand=True)
        self.lbl_tunnel_title = tk.Label(txt_box, text="当前自建 Planet 虚拟专网未连接", font=("Microsoft YaHei", 12, "bold"), fg="#FFFFFF", bg="#1A212E")
        self.lbl_tunnel_title.pack(anchor="w")
        self.lbl_tunnel_detail = tk.Label(txt_box, text="在顶部填好自建服或房主电脑 IP 后，点击右侧【🚀 一键连入专网】", font=("Microsoft YaHei", 10), fg="#94A3B8", bg="#1A212E")
        self.lbl_tunnel_detail.pack(anchor="w")

        self.btn_toggle_net = ttk.Button(light_box, text="🚀 一键连入专网", style="Primary.TButton", command=self._toggle_tunnel)
        self.btn_toggle_net.pack(side="right", ipady=4)

        opt_row = tk.Frame(tunnel_card, bg="#1A212E")
        opt_row.pack(fill="x", pady=(2, 8))

        self.var_relay_shield = tk.BooleanVar(value=self.net_service.use_relay_shield)
        chk_shield = tk.Checkbutton(
            opt_row,
            text="🛡️ P2P 高速直连优化 (屏蔽海外中继仅保留登录节点，4~5速稳定)",
            variable=self.var_relay_shield,
            bg="#1A212E",
            fg="#34D399",
            selectcolor="#10141C",
            activebackground="#1A212E",
            activeforeground="#34D399",
            font=("Microsoft YaHei", 9),
            command=self._on_opt_changed,
        )
        chk_shield.pack(side="left", padx=(0, 12))

        self.var_force_bind = tk.BooleanVar(value=self.net_service.use_force_bind)
        chk_bind = tk.Checkbutton(
            opt_row,
            text="📌 ForceBindIP64 绑定虚拟网卡",
            variable=self.var_force_bind,
            bg="#1A212E",
            fg="#93C5FD",
            selectcolor="#10141C",
            activebackground="#1A212E",
            activeforeground="#93C5FD",
            font=("Microsoft YaHei", 9),
            command=self._on_opt_changed,
        )
        chk_bind.pack(side="left", padx=(0, 12))

        self.var_force_tcp = tk.BooleanVar(value=self.net_service.force_tcp)
        chk_tcp = tk.Checkbutton(
            opt_row,
            text="⚡ 增强连接 (强制走主节点TCP中继)",
            variable=self.var_force_tcp,
            bg="#1A212E",
            fg="#FBBF24",
            selectcolor="#10141C",
            activebackground="#1A212E",
            activeforeground="#FBBF24",
            font=("Microsoft YaHei", 9),
            command=self._on_opt_changed,
        )
        chk_tcp.pack(side="left")

        self.btn_launch = ttk.Button(tunnel_card, text="⚔️ 启动 CK3 开始联机", style="BigLaunch.TButton", command=self._launch_game, state="disabled")
        self.btn_launch.pack(fill="x", pady=(4, 0))

        # 5. 底部联机与自建节点教程
        tut_card = tk.Frame(self.main_frame, bg="#161D29", highlightbackground="#2B3548", highlightthickness=1, padx=12, pady=10)
        tut_card.pack(fill="both", expand=True)

        tut_header = tk.Frame(tut_card, bg="#161D29")
        tut_header.pack(fill="x", pady=(0, 6))
        tk.Label(tut_header, text="📖 开源版双模式联机教程 (自建云服务器 / 玩家电脑直连)", font=("Microsoft YaHei", 11, "bold"), fg="#60A5FA", bg="#161D29").pack(side="left")
        tk.Label(tut_header, text=f"开源版本: v{APP_VERSION}", font=("Microsoft YaHei", 9), fg="#94A3B8", bg="#161D29").pack(side="right")

        tut_text = tk.Text(tut_card, bg="#10141C", fg="#CBD5E1", font=("Microsoft YaHei", 9), relief="flat", highlightthickness=0, wrap="word", padx=10, pady=8)
        tut_text.pack(fill="both", expand=True)

        tut_content = f"""【方式一：玩家电脑对电脑直连 (无需购买云服务器)】：
1. 房主点击右上角【🖥️ 本机一键做主机 (电脑直连)】，输入房主电脑的公网 IP / 校园网局域网 IP / 端口映射 IP；
2. 房主和朋友在顶部【🌐 自建服 / 房主电脑 IP】填入房主的 IP；
3. 输入各自唯一的英文/数字昵称，点击【⚡ 安装虚拟局域网联机补丁】 -> 点击【🚀 一键连入专网】变绿灯后启动游戏即可直连！

【方式二：玩家自行搭建云服务器 (推荐长期联机)】：
1. 在任意 Linux 云服务器上运行本项目提供的 `sudo ./server/deploy_linux_server.sh <你的服务器公网IP>`（放行 TCP 12030 与 UDP/TCP 12020）；
2. 所有玩家在顶部填入你的云服务器 IP，点击【🚀 一键连入专网】即可 24 小时自助绿灯联机！

【免登录 P 社账号 & 唯一联机昵称锁】：
- 本机专属 ID ({self.net_service.client_id}) 已为你自动绑定唯一 64 位 SteamID ({patch_manager.compute_unique_steamid64(self.net_service.client_id)})，无需登录 P 社账号；
- 你的联机昵称在当前连接的主节点上唯一锁定，其他人不可重名，改名时旧名自动释放。
"""
        tut_text.insert("1.0", tut_content)
        tut_text.configure(state="disabled")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _sync_endpoint_from_ui(self):
        host = self.entry_host.get().strip() or "127.0.0.1"
        try:
            port = int(self.entry_port.get().strip() or "12030")
        except Exception:
            port = 12030
        self.net_service.set_server_endpoint(host, auth_port=port)

    def _test_and_save_server(self):
        self._sync_endpoint_from_ui()

        def worker():
            ok, info, err = self.net_service.test_server_reachability()
            if ok:
                msg = (
                    f"✅ 成功连接到自建联机主节点！\n\n"
                    f"• 节点地址: {self.net_service.base_http_url}\n"
                    f"• ZeroTier Planet 端口: {info.get('ztPort', 12020)}\n"
                    f"• 虚拟局域网 ID (NWID): {info.get('defaultNwid', '-')}\n"
                    f"• 准入模式: {'自由加入模式' if info.get('mode') == 'auto' else '房主白名单审核模式'}\n"
                    f"• 当前在线人数: {info.get('online_players', 0)} 人"
                )
                self.after(0, lambda: messagebox.showinfo("节点连接成功", msg))
            else:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "节点连接失败",
                        f"无法连接到 {self.net_service.base_http_url}\n错误原因: {err}\n\n"
                        f"请检查 IP 和端口是否正确，或点击右侧【🖥️ 本机一键做主机】。",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_self_host(self):
        if self.net_service.is_self_hosted_running():
            self.net_service.stop_self_hosted_node()
            self.btn_self_host.configure(text="🖥️ 本机一键做主机 (电脑直连)")
            messagebox.showinfo("已停止", "本机直连主节点已关闭。")
            return

        default_ip = detect_local_ip()
        host_ip = simpledialog.askstring(
            "🖥️ 开启本机直连主节点 (电脑对电脑直连)",
            "请输入本机用于供朋友连接的 IP 地址：\n"
            "• 局域网/校园网/异地组网直连：填本机内网 IP\n"
            "• 路由器端口映射/公网直连：填你的公网 IP (需映射 TCP 12030 与 UDP/TCP 12020)",
            initialvalue=default_ip,
            parent=self,
        )
        if not host_ip:
            return

        ok, msg = self.net_service.start_self_hosted_node(public_ip=host_ip.strip(), auth_port=12030, zt_port=12020)
        if ok:
            self.entry_host.delete(0, tk.END)
            self.entry_host.insert(0, host_ip.strip())
            self.entry_port.delete(0, tk.END)
            self.entry_port.insert(0, "12030")
            self.btn_self_host.configure(text="🛑 停止本机主机 (运行中)")
            messagebox.showinfo("本机主节点已启动", msg)
        else:
            messagebox.showerror("启动失败", msg)

    def _on_opt_changed(self):
        self.net_service.use_relay_shield = bool(self.var_relay_shield.get())
        self.net_service.use_force_bind = bool(self.var_force_bind.get())
        self.net_service.force_tcp = bool(self.var_force_tcp.get())
        self.net_service.save_preferences()
        patch_manager.set_paradox_relay_shield(self.net_service.use_relay_shield)

    def _open_nic_dialog(self):
        NicAndNatDialog(self, self.net_service)

    def _save_nickname(self):
        self._sync_endpoint_from_ui()
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("提示", "联机昵称不能为空！")
            return
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
        messagebox.showinfo("🔒 唯一昵称锁定成功", f"{msg}\n游戏内已自动同步该专属昵称！")

    def _browse_path(self):
        path = filedialog.askdirectory(title="请选择 Crusader Kings III 游戏根目录")
        if path:
            if patch_manager.verify_ck3_path(path):
                self.game_path = path
                self.lbl_path.configure(text=path)
                self._refresh_game_status()
            else:
                messagebox.showerror("错误", "所选目录下未找到 ck3.exe！")

    def _refresh_game_status(self):
        if not self.game_path or not patch_manager.verify_ck3_path(self.game_path):
            self.lbl_patch_status.configure(text="补丁状态: 未找到游戏目录", fg="#EF4444")
            self.btn_install_patch.configure(state="disabled")
            self.btn_restore_patch.configure(state="disabled")
            return

        status, desc = patch_manager.get_patch_status(self.game_path)
        if status == "PATCHED":
            self.lbl_patch_status.configure(text=f"补丁状态: {desc}", fg="#10B981")
            self.btn_install_patch.configure(text="⚡ 重新覆盖联机补丁", state="normal")
            self.btn_restore_patch.configure(state="normal")
        else:
            self.lbl_patch_status.configure(text=f"补丁状态: {desc}", fg="#94A3B8")
            self.btn_install_patch.configure(text="⚡ 安装虚拟局域网联机补丁", state="normal")
            self.btn_restore_patch.configure(state="disabled")

    def _install_patch(self):
        self._sync_endpoint_from_ui()
        name = self.entry_name.get().strip()
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
        if messagebox.askyesno("确认还原", "确定要还原为官方原版吗？还原后将恢复 Steam 官方原版文件与成就。"):
            ok, msg = patch_manager.restore_original(self.game_path)
            if ok:
                messagebox.showinfo("成功", msg)
            else:
                messagebox.showerror("失败", msg)
            self._refresh_game_status()

    def _toggle_tunnel(self):
        if not self.net_service.is_running:
            self._sync_endpoint_from_ui()
            name = self.entry_name.get().strip()
            self.net_service.username = name
            self._on_opt_changed()
            ok, msg = self.net_service.start_tunnel()
            if not ok:
                messagebox.showerror("无法启动专网", msg)
            else:
                self.btn_toggle_net.configure(text="⏹️ 断开专网", style="Danger.TButton")
        else:
            self.net_service.stop_tunnel()
            self.btn_toggle_net.configure(text="🚀 一键连入专网", style="Primary.TButton")

    def _launch_game(self):
        self._sync_endpoint_from_ui()
        name = self.entry_name.get().strip()
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

    def _schedule_poll(self):
        color = self.net_service.light_color
        detail = self.net_service.status_text

        if color == "green":
            self.lbl_light.configure(text="🟢")
            self.lbl_tunnel_title.configure(text=f"通行状态：正常准入 (专属账号【{self.net_service.username}】已锁定放行)", fg="#34D399")
            self.lbl_tunnel_detail.configure(text=detail, fg="#94A3B8")
            self.btn_launch.configure(state="normal")
        elif color == "red":
            self.lbl_light.configure(text="🔴")
            title_txt = "通行状态：昵称已被他人占用 (请修改上方昵称)" if self.net_service.name_conflict else "通行状态：受阻 / 等待房主放行"
            self.lbl_tunnel_title.configure(text=title_txt, fg="#F87171")
            self.lbl_tunnel_detail.configure(text=detail, fg="#F87171")
            self.btn_launch.configure(state="disabled")
            if not self.net_service.is_running:
                self.btn_toggle_net.configure(text="🚀 一键连入专网", style="Primary.TButton")
        elif color == "yellow":
            self.lbl_light.configure(text="🟡")
            self.lbl_tunnel_title.configure(text="通行状态：正在执行 6 步自建 Planet 专网握手...", fg="#FBBF24")
            self.lbl_tunnel_detail.configure(text=detail, fg="#FBBF24")
            self.btn_launch.configure(state="disabled")
        else:
            self.lbl_light.configure(text="⚪")
            self.lbl_tunnel_title.configure(text="当前自建 Planet 虚拟专网未连接", fg="#94A3B8")
            self.lbl_tunnel_detail.configure(text=detail, fg="#64748B")
            self.btn_launch.configure(state="disabled")

        self.after(1000, self._schedule_poll)

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
    app = UserApp()
    app.mainloop()


if __name__ == "__main__":
    main()
