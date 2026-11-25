# 👑 CK3-更好的私人联机助手-DirectLAN — 《十字军之王3》自建虚拟局域网 P2P 高速直连联机方案

<p align="center">
  <img src="https://img.shields.io/badge/Game-Crusader%20Kings%20III-gold?style=for-the-badge" alt="CK3">
  <img src="https://img.shields.io/badge/DLC-Silk%20%26%20Silver%20(37%20DLCs)-emerald?style=for-the-badge" alt="DLC">
  <img src="https://img.shields.io/badge/Network-Self--Hosted%20ZeroTier%20Planet%20%2B%20P2P-blue?style=for-the-badge" alt="Network">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

**CK3-DirectLAN** 是一套完全开源、零商业后台依赖的《十字军之王3 (Crusader Kings III)》高帧率多人联机直连工具。

针对原版 CK3 多人联机长期存在的 **海外 Nakama 服务器高延迟、2 速掉帧、玩家日期长期落后、未登录 P 社账号多人按钮灰化、频繁不同步 (OOS)** 等痛点，本项目通过 **自建 ZeroTier Planet 私有根服务器 + 自动化 Controller 节点准入 + 虚拟 Steam 局域网大厅 (`-steam`) + 最高路由跃点数 (`Metric=1`) + 全局广播转发 (`WinIPBroadcast`)**，将所有联机同步流量 100% 切换至玩家之间的 **P2P 虚拟局域网直连**，实测全 37 款 DLC（含最新《普天之下》《白银与丝绸》大地图）下 **4~5 速稳定流畅同步**！

---

## 📸 实测联机效果展示

> **实测双人联机（开启《普天之下 / 白银与丝绸》全 DLC 东亚大地图）：4~5 速下双方玩家日期完全同步（`867年9月21日`），无落后、无卡顿：**

<p align="center">
  <img src="assets/multiplayer_ingame.png" width="88%" alt="CK3 联机实测截图">
</p>

<p align="center">
  <img src="assets/multiplayer_5speed_sync.jpg" width="48%" alt="5速日期同步实测">
</p>

---

## ✨ 核心特性

- 🔓 **免登录 P 社 (Paradox) 账号**：
  - 自动配置 `ColdClientLoader (-steam)` 虚拟局域网大厅，彻底绕过 P 社海外 Nakama 登录校验，游戏主菜单【多人游戏】直接亮起可用。
  - 根据每台电脑自动生成**专属唯一 64 位 SteamID (`SteamID64`)**，多人存档读档时自动认领各自上次游玩的领主角色。
- 🔒 **全服唯一联机昵称锁（防撞名冲突）**：
  - 玩家在客户端顶部输入的**联机昵称**即为游戏内的联机账号。
  - 服务端实时锁定昵称唯一性（一人绑定，其他人无法使用同名昵称；当本人修改昵称时，旧昵称自动释放）。
- 🌐 **支持两种完全自主的联机拓扑（零第三方服务器依赖）**：
  1. **🖥️ 玩家电脑对电脑直连模式 (Host-to-Peer，免买云服务器)**：房主直接在软件右上角点击 **【🖥️ 本机一键做主机】**，软件自动在房主电脑拉起内置的 Planet 根节点与 Controller 服务，朋友输入房主电脑 IP 即可直连。
  2. **☁️ 玩家自建云服务器模式 (Self-Hosted VPS)**：提供 Linux (`deploy_linux_server.sh`) 与 Windows (`start_windows_server.bat`) 一键开服脚本，1 分钟即可在自己的服务器上搭好 24 小时运行的专属 Planet 联机中心。
- ⚡ **6 步底层虚拟局域网全自动调优**：
  - `[1/6]` 自动从主节点同步加密签名的私有 `planet` 文件并配置 `local.conf`（支持 TCP 中继回退）
  - `[2/6]` 自动部署 `zttap300` 虚拟网卡驱动与目录权限
  - `[3/6]` 启动独立端口 (`56814`) 的 ZeroTier 核心守护进程
  - `[4/6]` 自动加入虚拟局域网 (`10.155.155.0/24`)
  - `[5/6]` 主节点 Controller 秒级自动授权节点并绑定固定虚拟 IP（无需去网页后台手动打勾！）
  - `[6/6]` 自动启动 `WinIPBroadcast` 局域网广播转发、将虚拟网卡路由跃点数设为 `Metric=1`（最高优先级）、屏蔽高延迟海外遥测/中继节点，并将全员虚拟 IP 实时写入 `custom_broadcasts.txt`。
- 🔄 **一键无损还原官方原版**：
  - 随时点击 **【🔄 还原官方原版】** 即可 100% 恢复 Steam 原版文件、云存档与成就系统。

---

## 🚀 快速使用指南

### 模式 A：玩家电脑对电脑直连（无需购买云服务器）

1. **房主开启本机主节点**：
   - 房主运行 `CK3联机助手-房主端.exe`（或玩家端），点击右上角 **【🖥️ 本机一键开启主节点 (电脑直连开服)】**。
   - 输入房主电脑可供朋友访问的 IP（若在同一局域网/校园网/异地组网内，填本机内网 IP；若通过路由器端口映射/公网 IP 直连，填公网 IP 并映射 `TCP 12030` 与 `UDP/TCP 12020`）。
2. **所有玩家连入专网**：
   - 房主与朋友在顶部 **【🌐 自建服 / 房主电脑 IP】** 填入房主 IP，端口填 `12030`。
   - 在 **【👤 专属联机昵称】** 输入各自唯一的英文或数字昵称，点击 **【⚡ 安装虚拟局域网联机补丁】**。
   - 点击 **【🚀 一键连入专网】**，等待指示灯变为 **🟢 绿灯**。
3. **启动游戏畅玩**：
   - 点击 **【⚔️ 启动 CK3 开始联机】** 进入游戏主菜单 -> 直接点击 **【多人游戏】** 即可秒搜到房主房间！

---

### 模式 B：玩家自行搭建云服务器（推荐长期多好友联机）

如果你有一台轻量应用服务器或 VPS（Ubuntu / Debian / CentOS 均可，1核1G 即可流畅带动）：

1. 将本仓库 `server/` 目录下的 `lan_server.py` 和 `deploy_linux_server.sh` 上传至你的云服务器同一目录。
2. 执行一键部署命令：
   ```bash
   chmod +x deploy_linux_server.sh
   sudo ./deploy_linux_server.sh <你的服务器公网IP> <自定义房主管理密码> 12030 12020
   ```
3. 在云服务器防火墙/安全组放行以下端口：
   - **`TCP 12030`**（准入控制、唯一昵称锁与 `/planet` 自动分发）
   - **`UDP 12020`** 与 **`TCP 12020`**（ZeroTier Planet 核心 P2P 握手与中转端口）
4. 所有玩家打开客户端，在顶部填入你的 **`服务器公网IP`** 与端口 **`12030`**，点击 **【🚀 一键连入专网】** 即可 24 小时随时绿灯联机！

---

## 🛠️ 从源码运行与打包

### 1. 环境要求
- Windows 10 / 11 (x64)
- Python 3.10+

### 2. 直接运行源码
```powershell
# 启动玩家端 (需管理员权限以配置虚拟网卡跃点数)
python client/ui_user.py

# 启动房主控制台
python client/ui_admin.py
```

### 3. 使用 PyInstaller 打包独立 `.exe`
```powershell
pip install pyinstaller
python package_dist.py 1.0.0
```
打包完成后，独立可执行程序将生成在 `dist/CK3联机助手-玩家端/` 与 `dist/CK3联机助手-房主端/` 目录下。

---

## ❓ 常见问题与联机防掉速/防不同步 (OOS) 指南

### Q1：网上说打 UMMS 等联机优化模组可以降低延迟，是真的吗？
- **物理网络延迟 (Ping)**：MOD 只能修改游戏脚本，不能改变物理网络延迟（物理网络延迟已由本工具的 **自建 Planet + 虚拟 Steam 大厅 P2P 直连** 压到最低）。
- **逻辑运算卡顿 / 中后期掉速 (Tick Lag)**：**是真的有效**。CK3 多人联机采用严格的“按日同步（Daily Lockstep）”机制，每天所有玩家的电脑必须算完地图上数万名 AI 角色的事件与寻路并比对校验和后，日期才会推进。中后期无领地路人 AI 角色成倍膨胀时，搭配 **UMMS (Unofficial Multiplayer Mod)** 或 **Population Control（人口控制）** 模组，能大幅减少无意义的 AI 轮询与每天跨网同步的数据量，配合本工具的 P2P 专网直连，中后期依然能稳定维持 4~5 速且极少发生不同步 (OOS)。

### Q2：游戏内如何修改显示语言或联机名字？
- 本工具在安装补丁时已默认将游戏语言设为 **简体中文 (`schinese`)**，并将你在软件顶部锁定的唯一昵称写入配置。
- 进入游戏后，你也可以随时按键盘 **`Shift + Tab`** 呼出内置联机设置面板进行查看。

---

## 📜 开源协议与免责声明

本项目遵循 [MIT License](LICENSE) 开源协议，仅供《十字军之王3》正版玩家与技术爱好者学习研究虚拟局域网 P2P 组网与多人联机网络优化使用，严禁用于任何商业售卖或牟利行为。
