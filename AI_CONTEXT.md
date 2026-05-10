# AI_CONTEXT.md — VibeNet Control 项目全量上下文

> 生成时间：2026-05-06（更新：Phase 8 打包完成）
> 给下一个 AI 会话使用的结构化交接文档。

---

## 一、项目概述

**VibeNet Control（可控力场）** — 基于 macOS 的 ARP 欺骗工具，用于局域网设备发现、实时网速测量与访问控制。

- **语言**：Python 3.12+
- **核心库**：scapy 2.5+（ARP 数据包）、Streamlit 1.28+（Web 界面）
- **平台限制**：仅 macOS（依赖 `sysctl`、`route`、`ifconfig`、BPF）
- **权限要求**：`sudo`（原始套接字）
- **启动方式**：
  - CLI：`sudo python3 main.py`
  - GUI：`bash run.sh --gui`

---

## 二、项目结构

```
WIFIkiller/
├── main.py                 # CLI 入口（扫描→选择→欺骗→断网/恢复+实时速率）
├── gui.py                  # Streamlit Web 界面（扫描、批量测速、设备控制）
├── app_entry.py            # macOS .app 入口点（AppleScript 密码对话框 + sudo 提权）
├── run.sh                  # 一键启动脚本（依赖检查 + sudo -v + 启动）
├── build.sh                # .app 打包脚本（clean venv + PyInstaller）
├── generate_icon.py        # 应用图标生成器（PIL + iconutil）
├── icon.icns / icon.png    # 应用图标
├── requirements.txt        # scapy>=2.5.0, streamlit>=1.28.0
├── CLAUDE.md               # 原始项目指令
├── README.md / README-zh.md
├── DEVELOPMENT_LOG.md / DEVELOPMENT_LOG-zh.md
├── oui_supplement.txt      # 补充 OUI 数据库（~2,900 条中国品牌 + IoT）
├── oui_cache.json          # 在线 API 查询缓存（bundle 中存储在 ~/.vibenet/）
├── AI_CONTEXT.md           # 本文件
├── core/
│   ├── __init__.py
│   ├── scanner.py          # ARP 扫描 + 三层厂商识别 + 随机化 MAC 检测 + bundle 路径适配
│   ├── spoofing.py         # ArpSpoofer 类（线程 + ARP 恢复 + kill/unkill + 监控集成）
│   └── monitor.py          # TrafficMonitor 类（AsyncSniffer + delta 速率统计 + kill 感知）
└── utils/
    ├── __init__.py
    └── sys_config.py       # sysctl net.inet.ip.forwarding 读写封装
```

---

## 三、核心架构

### 3.1 整体数据流

```
app_entry.py (macOS .app 入口，Phase 8)
  → 非 root: AppleScript 密码对话框 → sudo -S -b 后台提权 → 打开浏览器
  → root: 启动 Streamlit + 打开浏览器

gui.py (Web UI)  /  main.py (CLI)
  ├── core/scanner.py    → ARP 扫描 → 设备列表 + 厂商识别
  ├── core/spoofing.py   → ARP 欺骗线程 + kill/unkill + TrafficMonitor 集成
  ├── core/monitor.py    → AsyncSniffer 流量捕获 + delta 速率计算
  └── utils/sys_config.py → sysctl IP 转发开关
```

### 3.2 ARP 欺骗机制

1. 发送伪造 ARP 应答：告诉目标「我是网关」、告诉网关「我是目标」
2. 双方流量经过本机
3. `net.inet.ip.forwarding=1`：内核转发数据包（透明代理，目标可上网）
4. `net.inet.ip.forwarding=0`：内核丢弃数据包（断网效果）
5. 退出时发送 3 轮正确 ARP 应答恢复（免费 ARP / gratuitous ARP）

### 3.3 线程模型

```
ArpSpoofer
  ├── _thread (daemon)              → _spoof_loop() 每 1 秒发送 ARP 欺骗包
  │   由 threading.Event 控制停止
  ├── monitor (TrafficMonitor)       → AsyncSniffer 后台捕获目标流量
  │   独立于欺骗线程，可单独启停
  ├── _killed (bool)                 → 标记当前断网状态
  └── _testing (session_state 中的标记)  → GUI 测速是否激活
```

### 3.4 ArpSpoofer 关键 API

| 方法 | 说明 |
|------|------|
| `__init__(target_ip, gateway_ip, interval=1.0, enable_monitor=True)` | MAC 解析（3 次重试），失败抛 RuntimeError |
| `start()` | 开启转发 → 启动欺骗线程 → 启动 TrafficMonitor |
| `stop(restore=True)` | 停止欺骗线程 → 停止 monitor → 恢复 ARP → 关闭转发 |
| `kill()` | `_killed=True` → 关闭转发 → `monitor.set_active(False)` → 速率归零 |
| `unkill()` | `_killed=False` → 开启转发 → `monitor.set_active(True)` → 速率恢复 |
| `is_running` | 欺骗线程是否存活 |
| `is_killed` | 是否处于断网状态 |
| `get_traffic_stats()` | 返回 `(upload_kbps, download_kbps)`，**delta 式**：每次调用消耗内部计数器 |
| `enable_monitoring()` | 运行时启动/恢复流量监控 |
| `disable_monitoring()` | 运行时暂停流量监控（`set_active(False)`） |

### 3.5 TrafficMonitor 关键 API（core/monitor.py）

| 方法 | 说明 |
|------|------|
| `__init__(target_ip)` | 初始化，不启动 |
| `start()` | 创建 `AsyncSniffer(filter="host {ip} and not arp", store=False)` 并启动 |
| `stop()` | 停止 AsyncSniffer |
| `set_active(enabled)` | 控制 `threading.Event`，disabled 时不计包、`get_stats()` 返回 `(0,0)` |
| `get_stats()` | **delta 式**，返回自上次调用以来的 `(up_kbps, down_kbps)`，调用后重置内部计数器 |
| `is_running` | sniffer 是否运行中 |

**重要：`get_stats()` 是消费式（delta）的。** 每个 spoofer 在每个 rerun 周期内必须只调用一次，否则后续调用拿到 `(0.0, 0.0)`。当前 gui.py 使用 `_speed_snap` 缓存解决。

---

## 四、GUI 架构（gui.py）

### 4.1 Session State 完整字典

```python
st.session_state = {
    # === 核心数据 ===
    "spoofers":         {ip: ArpSpoofer},        # 所有活动的 spoofer
    "_testing":         {ip: bool},              # 手动测速是否激活（区别于遍历）
    "devices":          [{"ip": ..., "mac": ...}], # 扫描结果
    "oui_db":           {"AABBCC": "VendorName"},  # 厂商数据库
    "gateway_ip":       str,
    "network":          str,                     # CIDR 格式
    "scanned":          bool,

    # === 测速结果 ===
    "speed_results":    {ip: {"up": kbps, "down": kbps, "time": "HH:MM:SS"}},
    "_peak_speeds":     {ip: {"up": kbps, "down": kbps}},  # 手动测速峰值（不断更新取最大）

    # === 遍历测速状态机（rerun 驱动，不用后台线程） ===
    "_trav_queue":      [ip, ...],               # 待测设备 IP 队列
    "_trav_current_ip": str | None,              # 当前正在测的 IP
    "_trav_samples":    int,                     # 当前设备已采样次数（0/1/2）
    "_trav_peak_up":    float,                   # 当前设备上行峰值
    "_trav_peak_down":  float,                   # 当前设备下行峰值
    "_trav_running":    bool,                    # 遍历状态机是否激活
    "_trav_current":    int,                     # 当前第几台
    "_trav_total":      int,                     # 总共几台

    # === 速率快照缓存 ===
    "_speed_snap":      {ip: (up_kbps, down_kbps)},  # 每个 rerun 周期计算一次

    # === UI 状态 ===
    "auto_refresh":     bool,                    # 自动刷新复选框
}
```

### 4.2 每个 Rerun 的执行顺序

```
1. 侧边栏渲染（扫描按钮、指标、状态区、测速按钮、auto-refresh）
2. 权限检查（非 root → 报错退出）
3. 设备数据检查（未扫描/无设备 → 提示退出）
4. _cleanup_dead_spoofers()              ← 清理死线程
5. 速率快照采集                          ← 遍历所有 spoofer，各调用一次 get_traffic_stats()
                                         ← 同时更新 _peak_speeds（手动测速）
6. _process_traversal_step()             ← 从 _speed_snap 读取速率，推进遍历状态机
7. 设备表格渲染（HTML table，从 _speed_snap / speed_results 读取）
8. 设备控制卡片渲染（实时速率 + 峰值 + 开始/停止测速 + 断网/恢复）
9. 紧急停止区
10. auto-refresh → sleep(2) → st.rerun()
```

**关键设计点**：步骤 5 确保 `get_traffic_stats()` 每 spoofer 每 rerun 只调用一次，速率存入 `_speed_snap`，步骤 6/7/8 只从 `_speed_snap` 读取，不再调用 `get_traffic_stats()`。

### 4.3 遍历测速状态机

不依赖后台线程（`st.session_state` 只能从主线程访问），改为 **rerun 驱动**：

```
IDLE → 取队列下一个 IP → 创建 ArpSpoofer.start()
  → 等待 2s（auto-refresh）
  → 采样（从 _speed_snap 读取）→ 更新峰值
  → 等待 2s → 采样 → 更新峰值
  → 等待 2s → 采样 → 更新峰值 → 采集 3 次完成
  → sp.stop() → 保存峰值到 speed_results
  → 取下一个 IP...
  → 队列空 → _trav_running = False
```

- 每设备采样 3 次（2s × 3 = 6 秒）
- 自动跳过网关
- 遍历范围：所有设备（真实 + 随机 MAC）

### 4.4 设备控制卡片按钮逻辑

每个设备**两个按钮并排**：测速按钮（左）+ 断网/恢复按钮（右）

| 状态 | 左按钮 | 右按钮 |
|------|--------|--------|
| 空闲、无 spoofer | `🔍 开始测速` | `🔴 断网` |
| 空闲、有 spoofer（仅断网中） | `🔍 开始测速` | `🟢 恢复` |
| 测速中、未断网 | `⏹ 停止测速` | `🔴 断网` |
| 测速中、已断网 | `⏹ 停止测速` | `🟢 恢复` |

- **开始测速**：创建 ArpSpoofer + start()（透明代理，forwarding=ON）
- **停止测速**：保存峰值到 speed_results；如果已断网则只去激活测速标记（spoofer 保留），否则完全停止 spoofer
- **断网**：如果无 spoofer 则创建 + kill()，否则直接 kill()
- **恢复**：unkill()

### 4.5 侧边栏统一状态区（避免排版跳动）

```python
if trav:
    → "🔍 批量测速中：第 {cur}/{tot} 台设备" + 进度条
elif active:
    → "📡 手动测速中：{active} 台设备"
else:
    → "💤 待命中 — 点击下方按钮开始"
```

始终占位，不随状态显隐。

### 4.6 控制区包含随机 MAC 设备

两个 section：
1. **🎛 设备控制** — 真实设备（全球唯一 MAC）
2. **🔒 路过扫描设备控制（随机化 MAC）** — IP 后标注 `🔒随机` 标签，附说明提示

---

## 五、Phase 演进历史

### Phases 1-4（已完成）
环境检查、设备扫描、ARP 欺骗核心、CLI 交互。详见 `DEVELOPMENT_LOG-zh.md`。

### Phase 5（已完成）
Streamlit Web UI、OUI 数据库增强、真实/随机设备分表、auto-refresh。详见 `DEVELOPMENT_LOG-zh.md`。

### Phase 6（已完成）
实时网速监控功能：
- 新增 `core/monitor.py`（TrafficMonitor，使用 AsyncSniffer 避免 BPF socket 析构 bug）
- `ArpSpoofer` 集成 monitor（`start()` 创建、`stop()` 销毁）
- CLI 实时速率显示（daemon 线程 + `\r` 刷新）
- GUI 表格和控制卡片显示实时速率

### Phase 7（已完成，经历多次调整）

**初始需求**：多设备网速监控 + 批量操作

**第一次调整**：改为独立测速按钮，测速与 Kill 解耦
- spoofer 生命周期由测速按钮控制（不再是 Kill 时创建）
- 新增自动遍历测速（逐个设备 ARP 欺骗 → 采样 → 保存峰值）

**第二次调整**：
- 取消自动测速，改为手动「开始测速」/「停止测速」按钮
- 遍历范围扩展到所有设备（含随机 MAC）
- 随机 MAC 设备加入控制区

**第三次调整**：
- 修复 `get_traffic_stats()` delta 被多次消费导致速率显示 0 的问题
- 新增 `_speed_snap` 每 rerun 只调用一次
- 新增 `_peak_speeds` 跟踪手动测速最大值
- 控制区显示「实时速率」+「峰值」两行
- 停止测速时保存峰值而非最后采样
- 修复侧边栏排版跳动（统一状态区）

**第四次调整**：
- `run.sh` 改为 `sudo -v` 前台等密码，Streamlit 就绪后再打开浏览器

---

### Phase 8（已完成 — 2026-05-06）
macOS .app 打包：
- **打包方案**：PyInstaller `--onedir --windowed` + clean venv（避免 conda NumPy 冲突）
- **提权方案**：`app_entry.py` 使用 AppleScript 密码对话框 + `sudo -S -b` 后台启动 root 进程
- **路径适配**：`core/scanner.py` 新增 `_get_data_dir()` / `_get_user_data_dir()` / `_resolve_oui_db_path()`，bundle 内用 `sys._MEIPASS`
- **新增文件**：`app_entry.py`（入口）、`build.sh`（构建）、`generate_icon.py`（图标）、`icon.icns`
- **产物**：`dist/VibeNet Control.app`（~239 MB，arm64）

**关键经验教训**：
1. **永远用 clean venv 构建 PyInstaller**：conda 环境的 NumPy 版本冲突（pyarrow 编译于 NumPy 1.x，conda 有 2.4.4）导致 `ImportError`。创建独立 venv 仅安装目标包可完全避免。
2. **避免 `do shell script with administrator privileges`**：AppleScript → shell 三层引号嵌套导致路径空格和特殊字符转义极其复杂且易出错。更好的方案是独立密码对话框 + `sudo -S`。
3. **`--windowed` 二进制无终端输出**：调试时 stdout/stderr 不显示。需写入日志文件或使用 `--console` 模式构建调试版本。

**已知未解决问题**：
1. `sudo -S -b` 后台启动可靠性：在某些 macOS 配置下可能失败，导致浏览器打开时 Streamlit 未就绪（"无服务"）。需进一步测试和可能的回退方案（如 `Popen` + 轮询）。
2. 端口 8501 冲突未处理：上次未正常退出时端口仍被占用，需手动 `kill` 旧进程。

---

## 六、已知问题与注意事项

### 6.1 架构级注意事项

1. **IP 转发是全局的**：`net.inet.ip.forwarding` 是系统级设置。如果多台设备同时处于不同 kill 状态：
   - 任意一台 unkill → forwarding 全局打开 → 其他 killed 设备的 monitor 设为 `inactive`（`set_active(False)`），显示 0 但不影响全局
   - 所有设备都 kill → forwarding 全局关闭

2. **`get_traffic_stats()` 是 delta 式的**：每次调用重置内部计数器。**绝对不能**多次调用。gui.py 通过 `_speed_snap` 缓存保证每 rerun 一次。

3. **`st.session_state` 不能从后台线程访问**：只能在主脚本线程中访问。遍历测速因此设计为 rerun 驱动的状态机，不用后台线程。

4. **macOS BPF 套接字 bug**：`scapy.sniff()` 创建的 `L2bpfListenSocket` 在 `__del__` 中访问未初始化的 `bpf_fd`。已通过使用 `AsyncSniffer` 解决。

5. **GUI 测速只在设备有实际流量时才准**：ARP 欺骗（透明代理模式）将流量引到本机后，`sniff` 才能捕获。如果目标空闲无网络活动，速率为 0。

### 6.2 .app 打包注意事项（Phase 8）

1. **`sys._MEIPASS` 指向 Resources**：PyInstaller onedir macOS app 中，所有 `--add-data` 文件在 `Contents/Resources/`，`sys._MEIPASS` 指向此处。`core/scanner.py` 已通过 `_get_data_dir()` 适配。

2. **bundle 内不可写**：`oui_cache.json` 必须存储在 `~/.vibenet/`（`_get_user_data_dir()`），不可尝试写入 bundle。

3. **sudo 后台启动**：`app_entry.py` 使用 `sudo -S -b` 后台启动 root 进程。如遇 `-b` 标志不可用（老版本 sudo），需改用 `sudo -S` + `nohup` + `&` via shell。

4. **Ad-hoc 签名限制**：当前使用 ad-hoc 签名（无 Developer ID），分发到其他 Mac 需要对方在「隐私与安全性」中允许运行，或运行 `xattr -dr com.apple.quarantine`。

5. **仅 arm64**：当前构建为 Apple Silicon 架构。Intel Mac 需在 Intel 机器上构建或使用 `--target-arch universal2`。

### 6.3 潜在的待优化点

1. **遍历测速慢**：每设备 6 秒（3 样本 × 2s），22 台设备需 ~2 分钟。可减少样本数或缩短 auto-refresh 间隔来加速。

2. **无带宽限速功能**：目前只有二进制的断网/恢复，无分级限速。DEVELOPMENT_LOG 提到可用 macOS `pf`/`dnctl` 实现。

3. **跨平台**：`sysctl`、`route`、`ifconfig` 均为 macOS 专用，Linux 需替换为 `/proc/sys/net/ipv4/ip_forward`、`ip route`。

4. **厂商数据库**：依赖 nmap 的 OUI 数据库，无 nmap 时无优雅降级。

5. **遍历时停止问题**：遍历中使用 spoofers dict 存储临时 spoofer，和手动测速共享同一字典。点击「停止测速」会清空所有 spoofer（包括正在遍历的），但遍历状态机的 `_trav_running=False`+清空队列已处理。

6. **app 启动失败排查困难**：`--windowed` 二进制无终端输出，错误信息隐藏在 `~/.vibenet/app.log`。未来可添加 GUI 错误提示。

---

## 七、开发约定

- 用户偏好中文界面（GUI 全部中文化）
- 不要修改 `core/` 模块的核心逻辑，除非必要
- `finally` 块的安全退出保证不可破坏
- 不使用 pyarrow/numpy（Streamlit 版本兼容性问题），HTML 表格通过 `st.markdown(unsafe_allow_html=True)` 渲染
- 不使用后台线程访问 `st.session_state`
- PyInstaller 构建必须在 clean venv 中进行，不可使用 conda 环境
- `core/scanner.py` 的 `_get_data_dir()` 用于所有数据文件路径，保证开发/bundle 双环境兼容
- 用户可写数据（缓存）存储在 `~/.vibenet/`，不可写入 bundle 内
