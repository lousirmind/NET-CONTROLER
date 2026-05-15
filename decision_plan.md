# VibeNet Control — 问题优先级与执行计划

> 生成时间：2026-05-15
> 基于 DEVELOPMENT_LOG-zh.md 和全部源码审查

---

## 一、现有代码缺陷清单（按优先级排列）

### C1 [严重] spoofing.py:106 — 单个 spoofer.stop() 全局关闭 IP 转发

**位置**：`core/spoofing.py` 第 106 行

**现状**：
```python
def stop(self, restore=True):
    ...
    if restore:
        self._restore_arp()
    disable_ip_forwarding()  # 无条件执行！
```

**问题**：
1. `disable_ip_forwarding()` 在 `if restore:` 块外部，即使 `restore=False` 也会执行
2. 当 GUI 中有多个设备同时被 spoof 时，停止其中一台会关闭全局 IP 转发，导致其他正常 spoof 的设备也被意外断网

**影响**：GUI 多设备并发场景下核心功能异常

**修复思路**：在模块级维护活跃 spoofer 引用计数，仅在计数归零时关闭转发；或将 `disable_ip_forwarding()` 移入条件判断

---

### C2 [严重] app_entry.py — 端口 8501 冲突无处理

**位置**：`app_entry.py` `_start_streamlit()` 函数及 `main()` 函数

**问题**：
1. 上次 Streamlit 未正常退出时，端口 8501 仍被占用
2. 新启动的 Streamlit 会静默失败
3. 用户看到的现象是：输入密码 → 浏览器打开 → "无法连接" / "无服务"

**影响**：.app 打包版本的核心启动流程失败，用户无任何错误提示

**修复思路**：
1. 在 `_start_streamlit()` 开头检测 8501 端口占用
2. 如被占用，`kill` 旧进程后重试
3. 添加明确的错误提示（AppleScript dialog）

---

### C3 [中等] app_entry.py:127 — `sudo -S -b` 兼容性

**位置**：`app_entry.py` 第 127 行

**问题**：
- `sudo -S -b` 的 `-b`（background）标志在 macOS 较老版本（Monterey 及更早）的 sudo 中可能不被支持
- `proc.wait(timeout=5)` 在 `-b` 模式下的行为不一致：`-b` 会使 sudo fork 后立即退出，但进程的实际启动状态未知

**影响**：老版本 macOS 上 .app 可能无法启动

**修复思路**：
1. 用 Python 原生的 `subprocess.Popen` + `start_new_session=True` 替代 `sudo -S -b`
2. 或检测 `-b` 支持性，不支持时回退到 `nohup ... &` 方案

---

### C4 [中等] gui.py — 多设备 kill/unkill 状态与全局 IP 转发的语义不一致

**位置**：`gui.py` 设备控制卡片 unkill 按钮（第 512-514 行）

**问题**：
- 用户 kill 设备 A → 全局 IP 转发关闭 → 设备 B 也被断网（但 UI 显示 B 仍"在线"）
- 用户 unkill 设备 A → 全局 IP 转发打开 → 设备 B 实际恢复（但 UI 显示 B 仍"已断网"）
- UI 状态与实际网络状态不一致

**影响**：用户困惑，kill/unkill 语义在多设备场景下不准确

**说明**：这是 `sysctl net.inet.ip.forwarding` 全局性的固有限制。彻底解决需要 `pf`/`dnctl` 逐设备限速（Phase 3 未来改进）。当前 Phase 1 可做 UI 层面的提示优化。

**修复思路**：
1. 在 kill/unkill 操作后刷新所有 spoofer 的状态显示
2. 添加 UI 提示："注意：断网/恢复作用于整个网络，可能影响其他设备"
3. 在 unkill 某设备时，同时更新其他被杀设备的状态标记

---

### C5 [轻微] run.sh:127 — `$!` 捕获的是 sudo 的 PID 而非 streamlit

**位置**：`run.sh` 第 127-128 行

**问题**：
```bash
sudo streamlit run "$SCRIPT_DIR/gui.py" --server.headless true &
ST_PID=$!
```
`$!` 获取的是 `sudo` 进程的 PID，不是 `streamlit` 的 PID。`wait $ST_PID` 等待的是 sudo 进程退出（通常很快），而不是 streamlit 的完整生命周期。

**影响**：Ctrl+C 后 `wait` 可能立即返回，streamlit 进程变为孤儿继续占用端口

**修复思路**：使用 `sudo ... &` 后通过 `pgrep` 或 `lsof` 找到实际 streamlit PID 进行管理

---

### C6 [轻微] app_entry.py — 浏览器打开竞态条件

**位置**：`app_entry.py` 第 43-51 行 `_open_browser()` 和第 141-149 行 `main()`

**问题**：
- 轮询最多 20 秒（`range(20)` × 1 秒）
- 首次启动时 Streamlit 可能需要更长时间（JIT 编译、大量静态文件加载）
- 超过 20 秒后浏览器仍会打开，显示"无服务"

**影响**：首次冷启动时可能看到连接失败页面

**修复思路**：增加轮询次数到 60 次（60 秒），超时后弹出错误提示而非静默打开浏览器

---

## 二、Phase 8 遗留问题

以下问题来自 DEVELOPMENT_LOG-zh.md Phase 8 已知问题部分：

| # | 问题 | 优先级 | 说明 |
|---|------|--------|------|
| P8-1 | .app 启动后浏览器显示"无服务" | 严重 | 与 C2 和 C3 关联 |
| P8-2 | Ad-hoc 签名分发限制 | 轻微 | 需要开发者文档说明，非代码问题 |
| P8-3 | 仅 arm64 架构 | 轻微 | Intel Mac 需单独构建 |

---

## 三、分阶段执行计划

### Phase 1（本次必须修复）— 核心稳定性

| 序号 | 问题 | 文件 | 改动量 | 预计时间 |
|------|------|------|--------|----------|
| P1-1 | C1: spoofing.stop() 全局转发 | `core/spoofing.py` | ~15 行 | 30 min |
| P1-2 | C2: 端口 8501 冲突处理 | `app_entry.py` | ~25 行 | 20 min |
| P1-3 | C3: sudo -b 兼容性 | `app_entry.py` | ~10 行 | 15 min |
| P1-4 | C4: 多设备 kill/unkill UI 提示 | `gui.py` | ~8 行 | 10 min |
| P1-5 | C5: run.sh PID 管理 | `run.sh` | ~8 行 | 15 min |

**Phase 1 总改动量**：~66 行，预计 1.5 小时

### Phase 2（建议修复）— 用户体验

| 序号 | 问题 | 说明 |
|------|------|------|
| P2-1 | C6: 浏览器打开超时延长 | 60 秒 + 超时错误提示 |
| P2-2 | 遍历测速性能优化 | 减少采样数或缩短间隔（当前 6s/台） |

### Phase 3（未来迭代）— 功能增强

| 序号 | 改进方向 | 说明 |
|------|----------|------|
| P3-1 | 带宽限速 | 使用 macOS `pf`/`dnctl` 替代二进制的 kill/unkill |
| P3-2 | 数据包捕获与检查 | HTTP 域名、DNS 查询拦截记录 |
| P3-3 | 跨平台支持 | Linux `/proc/sys/net/ipv4/ip_forward` + `ip route` |
| P3-4 | ARP 监控模式 | 被动检测网络中其他设备的 ARP 欺骗 |
| P3-5 | 系统守护进程 | launchd/systemd + REST API |
| P3-6 | 无 nmap 优雅降级 | 内置最小 OUI 数据库（前 100 厂商） |
| P3-7 | Web UI 流量图表 | Streamlit 图表实时展示带宽 |

---

## 四、各问题具体修复方案

### P1-1: spoofing.stop() IP 转发修复

**文件**：`core/spoofing.py`

**方案**：在模块级维护活跃 spoofer 计数

```python
# 模块级计数器
_active_spoofer_count = 0
_lock = threading.Lock()

class ArpSpoofer:
    def start(self):
        ...
        with _lock:
            global _active_spoofer_count
            _active_spoofer_count += 1
        ...

    def stop(self, restore=True):
        ...
        with _lock:
            global _active_spoofer_count
            _active_spoofer_count = max(0, _active_spoofer_count - 1)
            if _active_spoofer_count == 0:
                disable_ip_forwarding()
```

**注意**：`enable_ip_forwarding()` 在 `start()` 中调用，如果已经有其他 spoofer 在运行，转发已经开启，重复调用是幂等的。

---

### P1-2: 端口 8501 冲突处理

**文件**：`app_entry.py`

**方案**：在 `_start_streamlit()` 开头添加端口检测

```python
def _kill_port_process(port=8501):
    """Kill any process occupying the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        for pid in result.stdout.strip().split("\n"):
            if pid:
                os.kill(int(pid), signal.SIGTERM)
                time.sleep(0.5)
    except Exception:
        pass
```

---

### P1-3: sudo -b 兼容性

**文件**：`app_entry.py`

**方案**：用 `start_new_session=True` 替代 `-b` 标志

```python
# 旧：["sudo", "-S", "-b", binary]
# 新：
proc = subprocess.Popen(
    ["sudo", "-S", binary],
    stdin=subprocess.PIPE,
    stdout=open(logfile, "w"),
    stderr=subprocess.STDOUT,
    start_new_session=True,  # 替代 sudo -b，Python 3.2+ 原生支持
)
```

---

### P1-4: 多设备 kill/unkill UI 提示

**文件**：`gui.py`

**方案**：
1. 在设备控制区顶部添加全局提示
2. kill/unkill 操作后刷新所有 spoofer 的 `_killed` 状态以与实际网络状态一致

---

### P1-5: run.sh PID 管理

**文件**：`run.sh`

**方案**：使用 `lsof` 追踪实际 streamlit PID

```bash
sudo streamlit run "$SCRIPT_DIR/gui.py" --server.headless true &
SUDO_PID=$!
sleep 2
ST_PID=$(lsof -ti :8501 2>/dev/null | head -1)
# ... wait and cleanup using ST_PID
```

---

## 五、风险矩阵

| 修改 | 风险等级 | 回退方案 |
|------|----------|----------|
| spoofing.py 引用计数 | 低 | 逻辑简单，可独立测试 |
| app_entry.py 端口检测 | 低 | 仅新增，不影响现有路径 |
| app_entry.py sudo 改造 | 中 | 保留旧代码路径作为 fallback |
| gui.py UI 提示 | 极低 | 纯展示层改动 |
| run.sh PID 修复 | 低 | shell 层面，可独立验证 |
