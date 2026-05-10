# 开发日志 — VibeNet Control（可控力场）

## 项目概述

一款基于 macOS 的 ARP 欺骗工具，用于网络拦截和访问控制。使用 Python 3 + scapy 构建，通过 `sysctl` 控制内核级 IP 转发。提供终端命令行界面（CLI）和 Streamlit Web 界面（GUI）。

**开发周期**：2026-05-06
**状态**：全部 8 个阶段已完成。

---

## 核心架构

### 数据流

```
gui.py (Web界面)  /  main.py (命令行)
  ├── core/scanner.py     →  ARP 扫描 → 设备列表 + 厂商识别
  ├── core/spoofing.py    →  ARP 欺骗线程 + kill/unkill + TrafficMonitor 集成
  ├── core/monitor.py     →  AsyncSniffer 流量捕获 + delta 速率计算
  └── utils/sys_config.py →  sysctl IP 转发开关
```

### .app 打包数据流 (Phase 8)

```
用户双击 .app
  → app_entry.py 启动（普通用户权限）
  → 弹出 AppleScript 密码对话框
  → 用户输入密码 → sudo -S -b 后台启动自身为 root
  → root 进程启动 Streamlit + 打开浏览器
  → 用户通过浏览器使用 GUI（普通用户权限）
  → 核心 ARP 操作以 root 运行
```

### ARP 欺骗机制

**核心原理**：ARP 协议没有认证机制。局域网内任何主机都可以发送未经请求的"ARP 应答"（op=2），大多数操作系统会立即接受并缓存。

```
正常流程：
  目标 --[who has 192.168.1.1?]-->  网关
  目标 <--[192.168.1.1 is at XX:XX]-- 网关

投毒流程：
  目标 <--[192.168.1.1 is at 攻击者MAC]-- 攻击者（伪造）
  网关 <--[192.168.1.5 is at 攻击者MAC]-- 攻击者（伪造）
```

欺骗数据包详情：

| 方向 | psrc（声称的 IP） | hwsrc（声称的 MAC） | 效果 |
|------|-------------------|---------------------|------|
| → 目标 | 网关 IP | 本机 MAC | 目标将流量发给本机 |
| → 网关 | 目标 IP | 本机 MAC | 网关将回复发给本机 |

### IP 转发作为断网开关

macOS 内核参数 `net.inet.ip.forwarding`：

- `1`：内核在网卡之间路由数据包——透明代理
- `0`：内核**静默丢弃**非本机数据包——"断网"效果

与基于 iptables 的阻断方式不同，这种方法不需要防火墙规则，且可立即恢复。

### 恢复机制（免费 ARP）

退出时发送 3 轮（间隔 0.3 秒）正确 ARP 应答：

```python
# 告知目标："网关 IP → 网关真实 MAC"
ARP(op=2, psrc=gateway_ip, pdst=target_ip,
    hwsrc=real_gateway_mac, hwdst=target_mac)

# 告知网关："目标 IP → 目标真实 MAC"
ARP(op=2, psrc=target_ip, pdst=gateway_ip,
    hwsrc=real_target_mac, hwdst=gateway_mac)
```

多轮发送是为了防范数据包丢失（ARP 是尽力而为协议）。

### 线程模型

欺骗在**守护线程**中运行，由 `threading.Event` 控制：

```python
while not self._stop_event.is_set():
    self._send_one_round()
    self._stop_event.wait(interval)  # 可中断的等待
```

- 守护线程 → 不会阻塞进程退出
- Event 停止机制 → 在一个间隔周期内干净关闭
- `thread.join(timeout=5)` → 安全超时防止卡死

### 安全退出保证

`main.py` 使用三层防护：

```
第一层：os.geteuid() 权限检查  （提前退出）
第二层：except KeyboardInterrupt  （捕获 Ctrl+C）
第三层：finally: spoofer.stop()   （始终运行，即使异常退出）
```

`finally` 代码块是关键保证——即使发生未处理的异常，ARP 恢复和 IP 转发关闭都会执行。

---

## Web UI 架构（Phase 5）

### Session State 管理

Streamlit 在每次控件交互时重新执行整个脚本。为防止后台线程被销毁：

```
st.session_state
  ├── spoofers: Dict[str, ArpSpoofer]   # 按目标 IP 索引
  ├── devices:  List[dict]              # 扫描结果
  ├── oui_db:   Dict[str, str]          # 解析后的 OUI 数据库
  ├── gateway_ip: str                   # 默认网关
  ├── network:  str                     # CIDR 网络地址
  └── scanned:  bool                    # 是否已扫描
```

`_cleanup_dead_spoofers()` 在每次重渲染时运行，清除守护线程已死亡（如 Streamlit 热重载后）的 spoofer。

### 多目标设计

CLI 版本一次只能处理一个目标，GUI 则管理多个 `ArpSpoofer` 实例。每个 spoofer 存储在 `session_state.spoofers[target_ip]` 中，可独立断网/恢复。

### 设备表格 — 真实 vs. 随机化

现代操作系统（iOS 14+、Android 10+、macOS）在 Wi-Fi 扫描时使用随机 MAC 地址。GUI 将设备分为两个表格：

| 表格 | MAC 类型 | 行颜色 | 字体颜色 | 可操作 |
|------|----------|--------|----------|--------|
| 真实设备 | 全球唯一（bit 1 = 0） | 绿色交替 | 黑色 | 是 |
| 路过扫描 | 本地管理（bit 1 = 1） | 蓝色交替 | 灰色 | 否 |

检测逻辑：MAC 地址第一个字节的第二位 = 1 → 本地管理 → 随机化。

### HTML 表格渲染

表格通过 `st.markdown(unsafe_allow_html=True)` 以原始 HTML 形式渲染，避免 Streamlit 原生 `st.table`/`st.dataframe` 组件中 pyarrow/numpy 的依赖冲突问题。

---

## Phase 6：实时网速监控（2026-05-06）

### 目标
为被拦截的目标设备提供实时上传/下载速率显示，CLI 和 GUI 均可使用。

### 新增文件：`core/monitor.py`

`TrafficMonitor` 类封装 scapy AsyncSniffer，对单个目标设备进行流量捕获和速率统计：

```python
class TrafficMonitor:
    def __init__(self, target_ip):   # 初始化，不启动
    def start(self):                  # 创建 AsyncSniffer 并启动
    def stop(self):                   # 停止 sniffer
    def set_active(enabled):          # kill 开关感知（disabled 时不计包、返回 0）
    def get_stats(self):              # delta 式：返回 (up_kbps, down_kbps)，消费后归零
```

**关键设计决策：**

### BPF 过滤器
使用 `f"host {target_ip} and not arp"` 仅捕获目标设备的非 ARP 流量，避免虚假的 ARP 包计入速率。

### AsyncSniffer 替代 sniff()
macOS 上 scapy 的 `sniff()` 创建的 `L2bpfListenSocket` 在 `__del__` 中访问未初始化的 `bpf_fd` 属性，导致 `AttributeError`。`AsyncSniffer` 通过显式的 `start()`/`stop()` 管理 BPF socket 生命周期，避免了此问题。

### kill 感知
`threading.Event _active` 控制流量计数：kill 时 `set_active(False)` → `_process_packet()` 直接返回 → `get_stats()` 返回 `(0.0, 0.0)` 并重置快照，防止恢复后出现虚假的速率尖峰。

### delta 速率计算
`get_stats()` 每次调用计算自上次调用以来的速率并重置内部计数器。**绝对不能多次调用**——第二次调用必然返回 `(0.0, 0.0)`。

### ArpSpoofer 集成
- `__init__(enable_monitor=True)`：控制是否创建 TrafficMonitor
- `start()`：同时启动欺骗线程和 monitor
- `stop()`：同时停止 monitor 和欺骗线程
- `kill()`/`unkill()`：透传调用 `monitor.set_active(False/True)`
- `get_traffic_stats()`：委托给 monitor

### CLI 实时显示（main.py）
Daemon 线程每秒调用 `get_traffic_stats()`，用 `\r` 覆盖同一行显示实时速率：
```
[↓ 1.2 MB/s  ↑ 0.3 KB/s]
```

---

## Phase 7：多设备速测与 Kill/Test 解耦（2026-05-06）

### 目标
- 多设备流量监控和批量操作
- 测速与断网解耦（独立按钮）
- 逐个轮询自动测速（遍历式）
- 固定状态区防止 UI 跳动
- 随机 MAC 设备加入控制区

### 核心架构变更

| 之前 | 之后 |
|------|------|
| spoofer = Kill 时创建，Restore 时销毁 | spoofer = 测速时创建/停止时销毁 |
| Kill = `disable_ip_forwarding()` | Kill = 仅关闭转发（spoofer 继续跑，monitor 显示 0） |

### 完整 Session State

```python
st.session_state = {
    "spoofers":         {ip: ArpSpoofer},     # 所有活动的 spoofer
    "_testing":         {ip: bool},           # 测速是否激活
    "devices":          [...],                # 扫描结果
    "oui_db":           {"AABBCC": "Vendor"},
    "gateway_ip":       str,
    "network":          str,
    "scanned":          bool,
    "speed_results":    {ip: {"up": kbps, "down": kbps, "time": "HH:MM:SS"}},
    "_peak_speeds":     {ip: {"up": kbps, "down": kbps}},  # 手动测速峰值
    "_speed_snap":      {ip: (up, down)},     # 每 rerun 缓存一次（防 delta 重复消费）
    # 遍历测速状态机
    "_trav_queue":      [ip, ...],
    "_trav_current_ip": str | None,
    "_trav_samples":    int,
    "_trav_peak_up":    float,
    "_trav_peak_down":  float,
    "_trav_running":    bool,
    "_trav_current":    int,
    "_trav_total":      int,
    "auto_refresh":     bool,
}
```

### 关键技术模式

#### 1. `_speed_snap` 快照缓存
`get_traffic_stats()` 是 delta 式的（消费后归零）。每个 rerun 周期必须只调用一次。
**解决方案**：在主循环开头采集所有 spoofer 的快照存入 `_speed_snap`，后续所有渲染（表格、控制卡片、遍历状态机）只从快照读取。

#### 2. Rerun 驱动的遍历状态机
`st.session_state` 不能在后台线程访问。遍历改由 Streamlit auto-refresh（每 2 秒）驱动：
```
IDLE → 取队列下一 IP → 创建 ArpSpoofer.start()
  → 采样（从 _speed_snap 读取）→ 更新峰值
  → 采样 → 更新峰值
  → 采样 → 更新峰值（共 3 次/~6 秒）
  → sp.stop() → 保存峰值到 speed_results → 取下一个...
```

#### 3. 峰值跟踪
手动测速使用 `_peak_speeds` 跟踪最大值（每 rerun 更新 `max()`），停止时保存峰值而非最后采样。

#### 4. 统一侧边栏状态区
三种状态始终占用同一位置，防止按钮上下跳动：
```
遍历中：🔍 批量测速中：第 3/22 台设备  [进度条]
手动中：📡 手动测速中：2 台设备
空闲：  💤 待命中 — 点击下方按钮开始
```

### 设备控制卡片按钮逻辑

每设备两个按钮并排（测速 + 断网/恢复）：

| 状态 | 左按钮 | 右按钮 |
|------|--------|--------|
| 空闲、无 spoofer | 🔍 开始测速 | 🔴 断网 |
| 测速中、未断网 | ⏹ 停止测速 | 🔴 断网 |
| 测速中、已断网 | ⏹ 停止测速 | 🟢 恢复 |

### IP 转发全局性处理
`net.inet.ip.forwarding` 是系统级设置。多设备 kill 状态协调：
- 任意一台 unkill → 全局打开转发
- 所有设备 kill → 全局关闭转发
- killed 设备的 monitor 设为 `inactive` → 显示 0 但不影响全局

---

## Phase 8：macOS .app 打包（2026-05-06）

### 目标
将整个项目打包为 macOS 原生 .app，双击即可启动 Streamlit Web GUI，无需手动安装依赖。

### 打包方案：PyInstaller + AppleScript 提权

**选型依据**：
- SMJobBless + XPC Helper 方案需要 Apple Developer 证书和代码签名，不适合快速分发
- 选择更实用的 **osascript 密码对话框 + sudo** 方案
- 创建干净 virtualenv 进行 PyInstaller 构建，避免 conda 环境的依赖冲突

### 新增文件

| 文件 | 用途 |
|------|------|
| `app_entry.py` | PyInstaller 入口点：非 root 时弹出 AppleScript 密码对话框 → sudo -S -b 后台重启自身为 root；root 时启动 Streamlit + 打开浏览器 |
| `build.sh` | 一键构建脚本：创建 venv → 安装 scapy+streamlit → PyInstaller onedir → 输出 .app |
| `generate_icon.py` | 通过 PIL 生成 1024x1024 PNG，调用 iconutil 转为 .icns |
| `icon.icns` | 应用图标 |

### PyInstaller 构建关键点

```bash
pyinstaller \
    --onedir --windowed \                    # macOS .app 包
    --name "VibeNet Control" \
    --icon icon.icns \
    --add-data "gui.py:." \                  # 主脚本作为数据文件
    --add-data "core/__init__.py:core" \     # core 包（每文件单独添加）
    --add-data "core/scanner.py:core" \
    --add-data "core/spoofing.py:core" \
    --add-data "core/monitor.py:core" \
    --add-data "utils/__init__.py:utils" \
    --add-data "utils/sys_config.py:utils" \
    --add-data "oui_supplement.txt:." \      # OUI 数据库
    --add-data "nmap-mac-prefixes:." \       # nmap OUI（如存在）
    --collect-all streamlit \                # 确保前端 static 文件打包
    --collect-all scapy \                    # 确保 scapy layers
    --hidden-import ... \                    # 处理遗漏导入
    app_entry.py
```

### core/scanner.py 路径适配

为兼容 PyInstaller bundle 内的文件布局：

```python
def _get_data_dir():
    """PyInstaller bundle 内用 sys._MEIPASS，否则用项目根"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(__file__))

def _get_user_data_dir():
    """用户可写目录 ~/.vibenet/（bundle 内不可写）"""
    path = os.path.expanduser("~/.vibenet")
    os.makedirs(path, exist_ok=True)
    return path

def _resolve_oui_db_path():
    """OUI 数据库优先 bundle 内，其次 /opt/homebrew，最后 /usr/local"""
    candidates = [
        os.path.join(_get_data_dir(), "nmap-mac-prefixes"),
        "/opt/homebrew/share/nmap/nmap-mac-prefixes",
        "/usr/local/share/nmap/nmap-mac-prefixes",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]
```

### .app 包结构

```
VibeNet Control.app/                    (~239 MB)
├── Contents/
│   ├── Info.plist
│   ├── MacOS/VibeNet Control           # PyInstaller bootloader (arm64)
│   ├── Resources/                       # sys._MEIPASS 指向此处
│   │   ├── gui.py, core/, utils/       # 项目代码（--add-data）
│   │   ├── oui_supplement.txt          # 补充 OUI
│   │   ├── nmap-mac-prefixes           # nmap OUI (52,091 条)
│   │   ├── streamlit/, scapy/, ...     # Python 依赖
│   │   └── libpython3.12.dylib         # Python 运行时
│   └── Frameworks/                     # 原生动态库 + 各包符号链接
```

### 已知问题

1. **sudo -S -b 启动可靠性**：`app_entry.py` 使用 `sudo -S -b` 后台启动 root 进程。在某些 macOS 配置下 `-b` 标志可能不被支持（较老版本 sudo），需回退到 `nohup ... &` 方式。当前版本的密码验证 + 后台启动逻辑可能需要根据实际环境微调。

2. **Ad-hoc 签名**：应用使用 ad-hoc 签名（非 Apple Developer），首次启动需右键→打开或 `xattr -dr com.apple.quarantine` 移除隔离标记。

3. **Streamlit 静态文件**：`--collect-all streamlit` 确保前端 static 文件被打包，约增加 ~50MB 体积。如 Streamlit 版本升级，需重新构建。

4. **跨机器分发**：.app 为 arm64 架构（Apple Silicon），Intel Mac 需额外构建。分发时需要对方在「安全性」设置中允许运行。

5. **端口占用**：如 8501 端口已被占用（如上次未正常退出），Streamlit 启动会失败。`app_entry.py` 未处理端口冲突，需手动 `kill` 残留进程。

### 构建与测试

```bash
# 构建
bash build.sh

# 测试（首次可能需要右键→打开）
open dist/VibeNet\ Control.app

# 移除隔离标记（如需要）
xattr -dr com.apple.quarantine "dist/VibeNet Control.app"
```

---

### 三层解析机制

```python
def get_vendor(mac, oui_db, online=False):
    prefix = mac.replace(":", "")[:6].upper()
    # 1. 本地主库（nmap，52k 条）—— 即时
    # 2. 本地补充库（oui_supplement.txt，~2.9k 条）—— 即时
    # 3. 随机化 MAC 检测 —— 跳过在线查询
    # 4. 磁盘缓存（oui_cache.json）—— 即时（之前查过的）
    # 5. 在线 API（maclookup.app）—— ~1-3秒，成功则缓存
```

### 补充数据库

`oui_supplement.txt` 新增约 2,900 条记录，覆盖：
- 中国手机品牌：小米、Redmi、POCO、华为、荣耀、OPPO、Realme、OnePlus、vivo、iQOO、魅族、中兴、努比亚、联想、摩托罗拉、TCL、海信、酷派、锤子、黑鲨、金立
- 智能家居/IoT：小米 IoT、米家
- 无人机：大疆（DJI）
- 网络设备：普联（TP-Link）、华硕（ASUS）、宏碁（Acer）

格式与 nmap 的 `nmap-mac-prefixes` 一致：`AABBCC VendorName`

### 在线 API 回退

当本地数据库未找到全球唯一 MAC 时，`get_vendor(mac, db, online=True)` 会查询 `https://api.maclookup.app/v2/macs/{prefix}000000`。成功结果缓存到 `oui_cache.json`，重启后仍可用。

---

## 关键设计决策

### 1. 网络检测：`route get default` + `ifconfig`

**替代方案**：scapy 的 `conf.route`（返回整数编码的路由，难以正确解析）和 `netifaces`（额外依赖）。

**做法**：使用 macOS 原生命令 `route -n get default` 查找默认网卡，再用 `ifconfig <网卡名>` 提取 `inet` 和 `netmask` 字段。失败时回退到 socket 检测 IP 猜测 `/24` 子网。

### 2. OUI 数据库：nmap + 补充库 + 在线 API

**替代方案**：下载 IEEE OUI CSV（连接超时）、嵌入单个数据库。

**权衡**：以 nmap 为必需依赖，但数据库由 Homebrew 预装并自动更新。补充文件填补中国品牌空白。在线 API 作为兜底方案。三层设计在速度（本地）和覆盖度（在线）之间取得平衡。

### 3. 持续欺骗 vs. 单次欺骗

**选择**：持续后台线程，每秒发送一次。

**原因**：ARP 缓存有 TTL（通常 30-300 秒）。只发送一次，缓存过期后会恢复。持续发送确保投毒状态保持。1Hz 足够击败任何缓存超时，同时不产生可察觉的网络负载。

### 4. 网关检测：scapy 路由表

**替代方案**：硬编码 `.1` 或询问用户。

**做法**：scapy 的 `conf.route.routes` 包含系统路由表。`net=0, mask=0` 的条目是默认路由——从中提取 `route[2]` 即为网关 IP。此方法跨平台（在 Linux 上同样有效）且始终准确。

### 5. 选择 Streamlit 而非其他 UI 框架

**替代方案**：Flask + 前端、Electron、原生 macOS 应用。

**原因**：零前端代码（纯 Python），内置 session state 管理，开发时自动热重载，一行命令启动。代价：需要 `sudo streamlit run`（不常规但可用）。

### 6. HTML 表格替代 st.table/st.dataframe

**替代方案**：Streamlit 原生表格组件。

**原因**：`st.table` 和 `st.dataframe` 内部依赖 pyarrow → numpy，当前环境中存在版本兼容性问题。原始 HTML 通过 `st.markdown` 渲染完全避开该依赖链，并提供完整的样式控制（交替颜色、分区主题）。

---

## 遇到的 Bug 及解决方案

### Bug 1: OUI 格式不匹配（2026-05-06）

**现象**：所有厂商查询返回 "Unknown"，尽管已加载 52,085 条记录。

**根因**：nmap 的 `nmap-mac-prefixes` 使用无分隔符十六进制（`AABBCC`），但 scapy 返回带冒号的 MAC（`AA:BB:CC:DD:EE:FF`）。原始代码截取 MAC 字符串的前 8 个字符得到 `"AA:BB:CC"`（含冒号），无法匹配裸十六进制 `"AABBCC"`。

**修复**：提取前缀前先去掉冒号：
```python
prefix = mac.replace(":", "")[:6].upper()
```

### Bug 2: scapy 路由表整数编码（2026-05-06）

**现象**：`get_local_network()` 尝试通过迭代匹配字符串值来解析 scapy 的 `conf.route`，但表中包含整数编码的网络地址（如 `3232238080` 代表 `192.168.10.0`）。

**修复**：放弃 scapy 路由表解析网络检测。改用 macOS 系统命令（`route -n get default` + `ifconfig`）。仅保留 scapy 路由表用于网关检测（网关 IP 直接以字符串形式提供）。

### Bug 3: sudo 权限测试死锁（2026-05-06）

**现象**：无法在沙箱中运行扫描器/欺骗器测试，因为 `sudo` 需要 TTY 输入密码。

**修复**：建立分离测试工作流：
1. 沙箱中编写代码并检查语法
2. `sudo python3` 实机执行由用户在终端完成
3. 调试数据（OUI 验证、网络检测、路由检查）以非交互方式测试

### Bug 4: pyarrow/numpy 兼容性（2026-05-06）

**现象**：Streamlit 渲染 `st.table` 或 `st.dataframe` 时报 `ImportError: numpy.core.multiarray failed to import`。

**根因**：安装的 numpy 版本与 pyarrow（Streamlit 内部数据渲染依赖）不兼容。

**修复**：用 `st.markdown(unsafe_allow_html=True)` 渲染原始 HTML 表格，彻底绕过 pyarrow/numpy 依赖链，同时获得完整的样式控制能力。

### Bug 6: macOS BPF socket 析构崩溃（2026-05-06 — Phase 6）

**现象**：使用 `scapy.sniff()` 循环捕获时抛出 `AttributeError: 'L2bpfListenSocket' object has no attribute 'bpf_fd'`。

**根因**：scapy 的 `L2bpfListenSocket.__del__` 在 socket 未正确初始化时访问 `bpf_fd` 属性。macOS BPF 套接字在异常退出路径上可能处于未初始化状态。

**修复**：改用 `scapy.all.AsyncSniffer(store=False)`，通过显式的 `start()`/`stop()` 管理 BPF socket 生命周期。`AsyncSniffer` 正确初始化和清理 socket，避免析构时的未初始化访问。

### Bug 7: Target MAC 解析失败（2026-05-06 — Phase 6）

**现象**：`RuntimeError: Could not resolve MAC for target 192.168.11.137`。目标设备在扫描和欺骗之间可能离线或切换网络。

**修复**：在 `ArpSpoofer._resolve_mac()` 中添加 3 次重试逻辑，每次间隔 1 秒。

### Bug 8: 后台线程访问 session_state 崩溃（2026-05-06 — Phase 7）

**现象**：后台线程访问 `st.session_state` 时报 `Missing ScriptRunContext`，Streamlit session_state 只能在主线程中访问。

**修复**：完全移除后台测速线程。改为 **rerun 驱动的状态机**——`_process_traversal_step()` 在每次 Streamlit rerun 时推进一步，由 auto-refresh（2 秒）驱动。

### Bug 9: get_traffic_stats() delta 被多次消费（2026-05-06 — Phase 7）

**现象**：测速过程中明明有流量但显示 0 KB/s，断断续续。

**根因**：`get_traffic_stats()` 是 delta 式的——每次调用计算自上次调用以来的速率并重置内部计数器。设备表格和控制卡片的渲染逻辑各自调用了一次，第二次调用必然返回 `(0.0, 0.0)`。

**修复**：引入 `_speed_snap` 缓存模式——每个 rerun 周期开始前采集一次所有 spoofer 的快照存入 `session_state._speed_snap`，后续所有渲染和遍历状态机只从快照读取。

### Bug 10: 侧边栏 UI 跳动（2026-05-06 — Phase 7）

**现象**：遍历进度信息和状态文本根据条件显隐，导致下方按钮上下跳动。

**修复**：将三种状态（遍历中/手动测速中/空闲）合并为统一的固定高度状态区，始终占据相同空间。

### Bug 11: run.sh 浏览器提前打开（2026-05-06 — Phase 7）

**现象**：`bash run.sh --gui` 在用户输入 sudo 密码之前就打开浏览器，导致密码输入被干扰。

**修复**：`sudo -v` 前台执行等待密码验证完成后，再后台启动 streamlit 并轮询 8501 端口就绪后打开浏览器。

### Bug 12: PyInstaller NumPy 版本冲突（2026-05-06 — Phase 8）

**现象**：在 conda 环境中构建时，pyarrow/scipy 等包编译于 NumPy 1.x，与 conda 的 NumPy 2.4.4 不兼容，导致 `ImportError: numpy.core.multiarray_umath`。

**修复**：创建干净的 `python3 -m venv` 环境，仅安装 scapy 和 streamlit，避免 conda 的科学计算包污染。这是 PyInstaller 构建的最佳实践。

### Bug 13: osascript do shell script 提权失败（2026-05-06 — Phase 8）

**现象**：用户反复看到"授权被取消"提示，即使输入正确密码。

**根因**：`osascript -e 'do shell script "...nohup...&..." with administrator privileges'` 的 AppleScript 字符串转义极其复杂——Python f-string → AppleScript → shell 三层引号嵌套，`sys.executable` 路径含空格导致 shell 命令解析失败。

**修复**：放弃 `do shell script with administrator privileges` 方案。改用：
1. `osascript` 显示独立密码对话框（`display dialog ... with hidden answer`）
2. `sudo -S -k true` 验证密码
3. `subprocess.Popen` + `sudo -S -b` 后台启动 root 进程

### Bug 5: Streamlit Session State 线程丢失（2026-05-06）

**现象**：页面刷新或控件交互后，后台 ARP 欺骗线程丢失。

**根因**：Streamlit 在每次交互时重新执行整个脚本。本地变量被重建，之前运行中创建的线程被孤立。

**修复**：将 `ArpSpoofer` 实例存储在 `st.session_state`（跨重渲染存活）中。添加 `_cleanup_dead_spoofers()` 在每次重渲染时检测并移除死线程。

---

## 项目结构

```
WIFIkiller/
├── main.py                 # CLI：扫描 → 选择 → 欺骗 → 控制 + 实时速率
├── gui.py                  # Streamlit Web 界面（Phase 5-7）
├── app_entry.py            # .app 入口点（Phase 8）
├── run.sh                  # 一键依赖检查与启动（支持 --gui）
├── build.sh                # .app 打包脚本（Phase 8）
├── generate_icon.py        # 图标生成器（Phase 8）
├── icon.icns / icon.png    # 应用图标（Phase 8）
├── requirements.txt        # scapy>=2.5.0, streamlit>=1.28.0
├── README.md / README-zh.md
├── DEVELOPMENT_LOG.md / DEVELOPMENT_LOG-zh.md
├── AI_CONTEXT.md           # AI 会话交接文档
├── CLAUDE.md               # Claude Code 项目指令
├── oui_supplement.txt      # 补充 OUI 数据库（~2,900 条）
├── oui_cache.json          # 在线 API 查询缓存（自动生成，bundle 中存储在 ~/.vibenet/）
├── core/
│   ├── __init__.py
│   ├── scanner.py           # ARP 扫描 + 三层厂商识别 + 随机化 MAC 检测 + bundle 路径适配
│   ├── spoofing.py          # ArpSpoofer 类（线程 + kill/unkill + TrafficMonitor 集成）
│   └── monitor.py           # TrafficMonitor（AsyncSniffer + delta 速率 + kill 感知）
└── utils/
    ├── __init__.py
    └── sys_config.py        # sysctl net.inet.ip.forwarding 封装
```

---

## 测试矩阵

| 测试项 | 方法 | 状态 |
|--------|------|------|
| 权限检查（无 sudo） | `python3 main.py` → 显示帮助 | ✅ |
| 网络检测 | `get_local_network()` → CIDR 地址 | ✅ |
| OUI 加载（nmap） | `load_oui_db()` → 52,091 条 | ✅ |
| OUI 加载（合并后） | `load_oui_db()` → 54,067 条 | ✅ |
| 厂商查询（本地） | `get_vendor("F4:0F:24:...", db)` → 厂商名 | ✅ |
| 厂商查询（在线） | `get_vendor("00:11:22:...", db, online=True)` → API 结果 | ✅ |
| 随机化 MAC 检测 | `52:F9:2C:...` → "Randomized" | ✅ |
| 在线 API 缓存 | `oui_cache.json` 跨调用持久化 | ✅ |
| sysctl 读取 | `is_forwarding_enabled()` → False（安全默认值） | ✅ |
| ARP 扫描 | `sudo python3 core/scanner.py` → 设备表格 | 用户测试通过 |
| ARP 欺骗（CLI） | `sudo python3 main.py` → 断网/恢复循环 | 用户测试通过 |
| Ctrl+C 恢复（CLI） | 欺骗中按 Ctrl+C → ARP 恢复 | 用户测试通过 |
| Web UI 扫描 | `bash run.sh --gui` → 设备表格渲染 | ✅ |
| Web UI 断网/恢复 | 按钮点击 → spoofer 启动/停止 | 用户测试通过 |
| Web UI 紧急停止 | 按钮点击 → 所有 spoofer 恢复 | 用户测试通过 |
| 真实/随机设备分离 | 两个表格，样式区分 | ✅ |
| 浏览器自动打开 | `bash run.sh --gui` → 打开 localhost:8501 | ✅ |
| 实时速率显示 (CLI) | `sudo python3 main.py` → `\r` 覆盖行 | ✅ |
| 实时速率显示 (GUI) | 控制卡片 + 表格显示速率 | ✅ |
| 遍历批量测速 | 逐个设备 ARP 欺骗 → 采样 3 次 → 保存峰值 | 用户测试通过 |
| 测速/断网解耦 | 测速中可独立断网/恢复 | ✅ |
| 峰值记录 | 停止测速时保存最大速率而非最后采样 | ✅ |
| 随机 MAC 设备控制 | 随机设备也可测速和断网 | ✅ |
| .app 构建 | `bash build.sh` → 输出 239MB .app | ✅ |
| .app 启动 | 双击 → 密码对话框 → 输入密码 | ⚠️ 需进一步测试 |

**⚠️ Phase 8 已知问题**：
- `sudo -S -b` 后台启动的可靠性需在不同 macOS 版本上验证
- 密码验证成功后，root 进程启动 Streamlit 的衔接逻辑可能需要调试
- 用户报告输入密码后浏览器显示"无服务"——root 进程可能未成功启动 Streamlit

---

## 未来改进方向

1. **目标带宽限速**：使用 macOS 的 `pf`（包过滤器）或 `dnctl` 实现分级控制，替代二进制的断网/恢复。

2. **数据包捕获与检查**：添加记录拦截流量（HTTP 域名、DNS 查询）的模式，用于 IoT 设备行为分析。

3. **跨平台支持**：替换 macOS 专用的 `sysctl` 和 `route` 调用，抽象出 Linux 对应的接口（`/proc/sys/net/ipv4/ip_forward`、`ip route`）。

4. **ARP 监控模式**：被动监控模式，检测网络中其他设备的 ARP 欺骗攻击。

5. **系统守护进程**：作为后台服务运行，提供 REST API 供远程控制（systemd/launchd）。

6. **无 nmap 时的优雅降级**：当 nmap 未安装时，回退到内置的最小 OUI 数据库（前 100 个常见厂商）。

7. **本地 OUI 数据库自动更新**：定期获取并合并最新的 IEEE OUI 注册数据。

8. **Web UI 流量图表**：使用 Streamlit 图表实时展示每台被拦截目标的带宽使用情况。
