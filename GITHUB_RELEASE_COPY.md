# 📋 GitHub 仓库与社区分享合规文案 (`GITHUB_RELEASE_COPY.md`)

以下文案已进行**全面合规化脱敏与搜索引擎 SEO 关键词优化**，在 GitHub 发布或去贴吧 / B站 / NGA / 论坛分享时可直接复制使用：

---

## 1. GitHub 仓库基本信息 (Repository Info & SEO)

- **规范化仓库 URL 名称 (Repository Slug)**：
  `CK3-DirectLAN`
- **一句话简介 (Description - 含中英文高频检索词)**：
  `👑 CK3-更好的私人联机助手-DirectLAN | 《十字军之王3 / 王国风云3 (Crusader Kings III)》自建虚拟局域网 P2P 高速直连联机工具 | 支持玩家电脑对电脑直连 & 自建云服务器 Planet 根节点 | 唯一联机昵称锁 + 兼容 1.18+《白银与丝绸》| 实测 4~5 速稳定同步 (CK3 LAN Multiplayer & Desync/Lag Optimization)`
- **20 个满额推荐标签 (Topics - 提升 GitHub 搜索与推荐权重)**：
  `ck3` `crusader-kings-3` `crusader-kings-iii` `multiplayer` `zerotier` `zerotier-planet` `p2p` `virtual-lan` `lan-multiplayer` `paradox-interactive` `game-networking` `nat-traversal` `python` `windows` `direct-connect` `low-latency` `gaming-tool` `self-hosted` `vlan` `strategy-game`

---

## 2. GitHub Release (v1.0.0) 发布文案

### 标题 (Release Title)
`👑 CK3-更好的私人联机助手-DirectLAN v1.0.0 — 开源独立版（支持自建云服务器 & 玩家电脑对电脑 P2P 直连，实测 4~5 速稳定）`

### 正文内容 (Release Notes)
```markdown
## 🎉 CK3-更好的私人联机助手-DirectLAN v1.0.0 正式开源发布！

针对《十字军之王3 / 王国风云3 (Crusader Kings III)》多人联机常见的跨国中继高延迟、开局 2 速卡顿、玩家日期落后以及频繁不同步 (OOS) 问题，我们将这套经过实测的 **自建 ZeroTier Planet 私有根节点 + DirectLAN 虚拟局域网大厅桥接 (`-steam`) + 路由跃点优先级 (`Metric=1`) 与全局定向广播转发** 联机方案整理为完全独立的开源版本！

### 🌟 核心亮点
1. **双模式自主联机（零商业后台依赖）**：
   - **🖥️ 玩家电脑对电脑直连**：房主无需购买云服务器，直接在客户端点击【🖥️ 本机一键做主机】，朋友输入房主电脑 IP 即可建立专网直连。
   - **☁️ 玩家自建云服务器**：提供 `server/deploy_linux_server.sh` 与 `server/start_windows_server.bat` 一键部署脚本，1 分钟即可搭建属于自己的 24 小时联机中心。
2. **局域网大厅直连 + 全服唯一联机昵称锁**：
   - 自动绑定每台设备专属的 64 位会话标识 (`SteamID64`) 与唯一联机昵称，无需等待外部中继账号登录即可进入多人游戏大厅。
   - 服务端实时锁定昵称唯一性（当前玩家绑定某昵称后其他人不可同名，改名时自动释放旧名），彻底解决联机撞号与读档角色错乱。
3. **兼容最新 1.18+《普天之下 / 白银与丝绸》大型剧本联机协议**：
   - 自动配置跨网段发现与专网全员定向广播 (`custom_broadcasts.txt`)，大型剧本下依然实测 4~5 速稳定同步。
4. **一键无损还原官方默认模式**：
   - 随时点击【🔄 还原官方默认模式】，瞬间恢复 Steam 官方原版设置、云存档与成就。

### 📦 下载与使用说明
- 下载下方附件中的 **`CK3-DirectLAN-v1.0.0-Windows-x64.zip`** 解压即可使用：
  - 普通玩家运行：**`CK3联机助手-玩家端.exe`**
  - 房主/自建服管理员运行：**`CK3联机助手-房主端.exe`**
```

---

## 3. 贴吧 / B站 / 社区开源分享帖文案（合规无敏感词版）

> **【开源分享】做了一个 CK3 虚拟局域网 P2P 直连联机助手（CK3-DirectLAN），支持玩家电脑直连或自建服务器，实测 1.18 白银与丝绸 4~5 速稳定同步！**
>
> 平时和朋友联机《十字军之王3》（王国风云3）跑《普天之下 / 白银与丝绸》大地图，走默认的跨国中继节点经常卡在 2 速、副机日期疯狂落后甚至频繁不同步 (OOS)。
> 后来研究了一套纯虚拟局域网 P2P 直连架构：**自建 ZeroTier Planet 私有根节点 + Controller 自动准入分配固定虚拟 IP + 虚拟局域网大厅桥接 (`-steam`) + `WinIPBroadcast` 全局广播增强 + `Metric=1` 最高网卡跃点数**，让所有联机同步流量 100% 走玩家之间的 P2P 专网直连，实测 4~5 速双方日期完全同步、丝滑流畅！
>
> 现在把这个工具整理成了完全纯净的**开源独立版 (`CK3-DirectLAN`)** 发在 GitHub 上：
> - **支持玩家电脑对电脑直连**：不用买云服务器，房主在软件右上角点一下【本机一键做主机】，朋友填房主 IP 就能直连；
> - **也支持自己用云服务器一键搭建**：附带了 Linux / Windows 一键开服脚本，1 分钟搭好自己的 24 小时私人联机服；
> - **唯一联机昵称锁 + 读档角色自动认领**：直接用软件里的昵称当联机身份（自动绑定唯一 64 位会话 ID），当前人用了某昵称别人就不能重名，改名自动释放；
> - **支持一键无损还原 Steam 官方默认模式**。
>
> 完整 Python 源码、一键开服脚本和打包好的 Windows 图形界面 `.exe` 都已经上传 GitHub Releases，纯公益开源（MIT 协议），欢迎大家自取体验或 Star 支持！
> 🔗 GitHub 地址：`https://github.com/fahua408/CK3-DirectLAN`
