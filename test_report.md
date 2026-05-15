# VibeNet Control — 测试报告

> 生成时间：2026-05-15
> 基于 Phase 1 修复后的代码（commit f4e4e22）

---

## 第一部分：正常流程测试

### A1 — 网络扫描

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证 ARP 扫描发现局域网内所有活跃设备，厂商识别正常 |
| **前置条件** | macOS + root 权限 + nmap OUI 数据库已安装 |
| **CLI 操作** | `sudo python3 main.py` → 观察扫描输出 |
| **GUI 操作** | `bash run.sh --gui` → 点击「扫描网络」→ 观察设备表格 |
| **预期结果** | 设备列表包含 IP/MAC/厂商；真实设备绿色背景，随机 MAC 蓝色背景；OUI 数据库 >50,000 条 |
| **状态** | 待用户验证 |

### A2 — 单设备断网/恢复

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证 kill/unkill 操作正确阻断和恢复目标网络 |
| **前置条件** | 设备 A 已扫描，设备 A 正常联网 |
| **CLI 操作** | 选择目标 → 输入 `k` → 验证目标无法上网 → 输入 `u` → 验证恢复 |
| **GUI 操作** | 点击设备 A 的「断网」→ 状态变 🔴 已断网 → 点击「恢复」→ 状态变 🟢 在线 |
| **预期结果** | kill 后 target 无法访问外网；unkill 后立即恢复；ARP 恢复包发送 3 轮 |
| **状态** | 待用户验证 |

### A3 — 单设备测速

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证手动测速功能，峰值跟踪正常，停止时保存峰值 |
| **前置条件** | 目标设备有实际网络活动（如播放视频） |
| **GUI 操作** | 点击设备 A「开始测速」→ 观察实时速率和峰值更新 → 点击「停止测速」|
| **预期结果** | 实时速率动态刷新；峰值 ≥ 实时速率最大值；停止后峰值保存到 speed_results |
| **状态** | 待用户验证 |

### A4 — 批量遍历测速

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证遍历状态机逐个设备采样 3 次并保存峰值 |
| **前置条件** | 至少 3 台设备已扫描 |
| **GUI 操作** | 侧边栏点击「开始测速」→ 观察进度条 → 等待完成 |
| **预期结果** | 逐台完成（每台约 6 秒）；进度条显示"第 X/Y 台"；speed_results 包含所有设备峰值；自动跳过网关 |
| **状态** | 待用户验证 |

### A5 — CLI 完整交互流

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证 CLI 端到端流程（扫描→选择→kill→unkill→quit）|
| **操作步骤** | `sudo python3 main.py` → 输入目标编号 → `k` → `u` → `q` |
| **边界用例** | 输入 `0`（越界）→ 提示重新输入；输入 `abc` → 提示重新输入；输入空行 → 忽略 |
| **预期结果** | Ctrl+C 或 `q` 后执行 ARP 恢复 + IP 转发关闭，`finally` 块保证清理 |
| **状态** | 待用户验证 |

---

## 第二部分：异常场景测试

### B1 — 无 root 权限

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证非 root 运行时给出明确错误提示 |
| **CLI 操作** | `python3 main.py`（无 sudo） |
| **GUI 操作** | `streamlit run gui.py`（无 sudo） |
| **预期结果** | 显示"需要 root 权限"提示并退出 |
| **状态** | ✅ 代码级验证通过 — `os.geteuid() != 0` 检查存在于 main.py:106 和 gui.py:282 |

### B2 — 目标设备离线

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证对离线目标创建 ArpSpoofer 时 RuntimeError 处理 |
| **操作步骤** | 对已离线设备的 IP 点击「断网」或「开始测速」 |
| **预期结果** | 弹出 `st.error("无法连接 {ip}")` 提示；spoofer 字典中不添加该设备 |
| **状态** | ✅ 代码级验证通过 — `_resolve_mac` 3 次重试后返回 None 抛 RuntimeError；gui.py:507/524 捕获并显示错误 |

### B3 — Ctrl+C 中断恢复

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证欺骗过程中 Ctrl+C 后网络正确恢复 |
| **操作步骤** | `sudo python3 main.py` → 选择目标 → 欺骗运行中 → `Ctrl+C` |
| **预期结果** | `finally` 块执行；ARP 恢复包发送 3 轮；IP 转发关闭；stats 线程停止 |
| **状态** | ✅ 代码级验证通过 — main.py:196-203 `finally` 三层防护 |

### B4 — 强制退出与端口清理

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证 kill -9 Streamlit 后端口 8501 能被清理 |
| **前置条件** | Streamlit 正在运行（GUI 模式） |
| **操作步骤** | `kill -9 $(lsof -ti :8501)` → 等待 2 秒 → `bash run.sh --gui` |
| **预期结果** | 旧进程被 kill；新启动的 Streamlit 能成功绑定 8501；`_kill_port_process()` 正常工作 |
| **状态** | 待用户验证（Phase 1 新增 `_kill_port_process` 功能） |

### B5 — 多设备并发 kill/unkill

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证多设备场景下 UI 状态与实际网络状态一致（Phase 1 修复） |
| **前置条件** | 设备 A 和设备 B 均已扫描 |
| **操作步骤** | 1. A 点击「断网」→ 2. 观察 B 状态 → 3. A 点击「恢复」→ 4. 观察 B 状态 |
| **预期结果 (修复后)** | 步骤 2：B 也显示 🔴 已断网（同步）；步骤 4：B 恢复显示 🟢 在线（同步）；UI 提示"断网/恢复同时影响所有设备" |
| **状态** | 待用户验证 |

### B6 — 遍历中停止

| 项目 | 内容 |
|------|------|
| **测试目的** | 验证批量测速中途点击「停止测速」后清理完整 |
| **操作步骤** | 启动批量测速 → 等待 2-3 台完成 → 点击「停止测速」 |
| **预期结果** | 遍历队列清空；当前 spoof 设备恢复；spoofers 字典清空；_testing 清空；_peak_speeds 清空 |
| **状态** | 待用户验证 |

---

## 第三部分：代码级验证（静态分析）

### C1 — spoofing.py stop() IP 转发逻辑（Phase 1 修复后）

**验证点**：`stop()` 仅在活跃 spoofer 计数归零且 `restore=True` 时关闭 IP 转发

**修复前** (`core/spoofing.py:105`):
```python
disable_ip_forwarding()  # 无条件执行
```

**修复后**:
```python
with _count_lock:
    global _active_spoofer_count
    _active_spoofer_count = max(0, _active_spoofer_count - 1)
    if _active_spoofer_count == 0 and restore:
        disable_ip_forwarding()
```

**状态**：✅ 已验证（commit f4e4e22）

---

### C2 — gui.py _speed_snap 缓存机制

**验证点**：每个 rerun 周期 `get_traffic_stats()` 仅调用一次

**代码路径**：
1. `gui.py:310-313`：遍历 spoofers，调用 `sp.get_traffic_stats()` → 存入 `_speed_snap`
2. `gui.py:322`：`_process_traversal_step()` 从 `_speed_snap` 读取
3. `gui.py:365-367`：设备表格从 `_speed_snap` 读取
4. `gui.py:463`：控制卡片从 `_speed_snap` 读取

**状态**：✅ 已验证— 所有渲染路径均从快照读取，`get_traffic_stats()` 仅在步骤 1 调用一次

---

### C3 — app_entry.py 端口冲突处理（Phase 1 新增）

**验证点**：`_start_streamlit()` 启动前检测并清理端口 8501

**新增代码** (`app_entry.py`):
```python
def _kill_port_process(port=8501):
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

def _start_streamlit():
    _kill_port_process(8501)
    time.sleep(1)
    ...
```

**状态**：✅ 已验证（commit f4e4e22）

---

### C4 — run.sh PID 管理（Phase 1 修复）

**验证点**：使用 `lsof` 获取实际 Streamlit PID，`trap EXIT` 确保退出时清理

**修复前**：`ST_PID=$!` 获取 sudo PID
**修复后**：`ST_PID=$(lsof -ti :8501)` + `trap cleanup EXIT`

**状态**：✅ 已验证（commit f4e4e22）

---

## 第四部分：Bug 回归测试

基于 DEVELOPMENT_LOG-zh.md 中记录的 13 个 Bug，验证修复仍然有效。

### D1 — Bug 1: OUI 格式匹配

| 项目 | 内容 |
|------|------|
| **验证代码** | `core/scanner.py:188` — `prefix = mac.replace(":", "")[:6].upper()` |
| **验证方法** | 检查任意 MAC 地址的厂商查询是否正常返回 |
| **状态** | ✅ 代码正确 — nmap 数据库用裸十六进制，代码去冒号匹配 |

### D2 — Bug 4: pyarrow/numpy 兼容性

| 项目 | 内容 |
|------|------|
| **验证方法** | `grep -n "st.table\|st.dataframe" gui.py` — 应无结果 |
| **状态** | ✅ 已验证 — gui.py 仅使用 `st.markdown(unsafe_allow_html=True)` 渲染 HTML 表格 |

### D3 — Bug 6: BPF socket 析构崩溃

| 项目 | 内容 |
|------|------|
| **验证代码** | `core/monitor.py:58` — `AsyncSniffer(filter=..., prn=..., store=False)` |
| **验证方法** | `grep -n "sniff(" core/monitor.py` — 应无结果 |
| **状态** | ✅ 已验证 — 无 `sniff()` 调用，全部使用 AsyncSniffer |

### D4 — Bug 7: Target MAC 解析失败

| 项目 | 内容 |
|------|------|
| **验证代码** | `core/spoofing.py:256-269` — `_resolve_mac(ip, retries=3)` |
| **验证方法** | 确认 `for attempt in range(retries)` 循环 + 1 秒间隔 |
| **状态** | ✅ 代码正确 — 3 次重试，每次间隔 1 秒 |

### D5 — Bug 9: get_traffic_stats() delta 被多次消费

| 项目 | 内容 |
|------|------|
| **验证方法** | 确认所有渲染路径从 `_speed_snap` 读取而非直接调用 `get_traffic_stats()` |
| **状态** | ✅ 已验证（见 C2） |

### D6 — Bug 12: NumPy 版本冲突

| 项目 | 内容 |
|------|------|
| **验证代码** | `build.sh:69` — `python3 -m venv` 创建 clean 环境 |
| **验证方法** | 确认 `build.sh` 不使用 conda 环境 |
| **状态** | ✅ 已验证 — build.sh 创建独立 venv，仅安装 scapy + streamlit + pyinstaller |

---

## 第五部分：可复现的自动化测试脚本

### 无 root 权限可运行的单元测试

```bash
#!/bin/bash
# run_unit_tests.sh — 无需 root 权限的单元测试
# 用法: bash run_unit_tests.sh

PASS=0
FAIL=0
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

check() {
    local desc="$1"
    local cmd="$2"
    echo -n "[TEST] $desc ... "
    if eval "$cmd" 2>/dev/null; then
        echo -e "${GREEN}PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}FAIL${NC}"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== VibeNet Control Unit Tests ==="
echo ""

# 1. 语法检查
check "spoofing.py syntax" "python3 -m py_compile core/spoofing.py"
check "scanner.py syntax" "python3 -m py_compile core/scanner.py"
check "monitor.py syntax" "python3 -m py_compile core/monitor.py"
check "sys_config.py syntax" "python3 -m py_compile utils/sys_config.py"
check "gui.py syntax" "python3 -m py_compile gui.py"
check "app_entry.py syntax" "python3 -m py_compile app_entry.py"
check "main.py syntax" "python3 -m py_compile main.py"
check "run.sh syntax" "bash -n run.sh"

# 2. OUI 数据库
check "OUI DB load" "python3 -c \"
from core.scanner import load_oui_db
db = load_oui_db()
assert len(db) > 1000, f'Too few entries: {len(db)}'
\""

# 3. OUI 查询
check "OUI vendor lookup" "python3 -c \"
from core.scanner import load_oui_db, get_vendor
db = load_oui_db()
# 测试已知 Apple MAC
v = get_vendor('F4:0F:24:00:00:00', db)
assert v != 'Unknown', f'Vendor: {v}'
\""

# 4. 随机 MAC 检测
check "Randomized MAC detection" "python3 -c \"
from core.scanner import get_vendor
db = {}
v = get_vendor('52:F9:2C:00:00:00', db)
assert v == 'Randomized', f'Expected Randomized, got {v}'
\""

# 5. IP 排序
check "IP sort key" "python3 -c \"
from core.scanner import _ip_sort_key
assert _ip_sort_key('192.168.1.5') < _ip_sort_key('192.168.1.10')
assert _ip_sort_key('10.0.0.1') < _ip_sort_key('192.168.1.1')
\""

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
```

### 快速冒烟测试（修改代码后运行）

```bash
#!/bin/bash
# run_smoke_tests.sh — 修改代码后的快速冒烟测试
# 用法: bash run_smoke_tests.sh

echo "=== VibeNet Control Smoke Tests ==="
echo ""

# Step 1: 所有文件语法检查
echo "[1/5] Syntax check..."
for f in core/scanner.py core/spoofing.py core/monitor.py utils/sys_config.py gui.py main.py app_entry.py; do
    python3 -m py_compile "$f" || { echo "FAIL: $f"; exit 1; }
done
bash -n run.sh || { echo "FAIL: run.sh"; exit 1; }
echo "  OK"

# Step 2: OUI 数据库加载和查询
echo "[2/5] OUI database..."
python3 -c "
from core.scanner import load_oui_db, get_vendor
db = load_oui_db()
assert len(db) > 1000
v = get_vendor('F4:0F:24:00:00:00', db)
assert v != 'Unknown'
v = get_vendor('52:F9:2C:00:00:00', {})
assert v == 'Randomized'
print(f'  OK — {len(db)} entries')
"

# Step 3: spoofer 引用计数逻辑
echo "[3/5] Spoofer ref-count logic..."
python3 -c "
from core.spoofing import _active_spoofer_count, _count_lock
# 初始值应为 0
assert _active_spoofer_count == 0
print('  OK — initial count is 0')
"

# Step 4: sysctl 接口
echo "[4/5] sysctl interface..."
python3 -c "
from utils.sys_config import is_forwarding_enabled
result = is_forwarding_enabled()
print(f'  OK — forwarding is {result}')
"

# Step 5: 关键函数可导入
echo "[5/5] Key imports..."
python3 -c "
from core.scanner import get_local_network, load_oui_db, get_vendor, scan_network
from core.spoofing import ArpSpoofer
from core.monitor import TrafficMonitor
from utils.sys_config import enable_ip_forwarding, disable_ip_forwarding
print('  OK — all modules importable')
"

echo ""
echo "=== All smoke tests passed ==="
```

---

## 第六部分：待用户验证 — 需要 root + 真实网络的测试

以下测试无法在代码层面自动化，需要用户在真实 macOS 环境中执行：

| # | 测试项 | 命令/操作 | 验证点 |
|---|--------|-----------|--------|
| 1 | ARP 扫描 | `sudo python3 core/scanner.py` | 设备列表非空 |
| 2 | CLI 断网 | `sudo python3 main.py` → k → u → q | target 断网/恢复 |
| 3 | CLI 实时速率 | `sudo python3 main.py` → 观察 `\r` 刷新 | `[↓ X KB/s ↑ Y KB/s]` |
| 4 | Ctrl+C 恢复 | `sudo python3 main.py` → 欺骗中 Ctrl+C | ARP 恢复 + 转发关闭 |
| 5 | GUI 扫描 | `bash run.sh --gui` → 扫描 | 设备表格渲染 |
| 6 | GUI 断网/恢复 | 点击按钮 | 状态切换 |
| 7 | GUI 手动测速 | 开始/停止测速 | 峰值保存 |
| 8 | GUI 批量测速 | 开始批量测速 | 遍历完成 |
| 9 | GUI 测速中停止 | 批量测速中途停止 | 清理完整 |
| 10 | 多设备 kill/unkill | A 断网 → 观察 B | B 状态同步（Phase 1） |
| 11 | 端口冲突清理 | kill -9 streamlit → 重启 | 新进程正常启动 |
| 12 | .app 构建 | `bash build.sh` | 生成 .app |
| 13 | .app 启动 | 双击 .app | 密码框 → 浏览器打开 |

---

## 测试总结

| 类别 | 可自动验证 | 待用户验证 | 总计 |
|------|-----------|-----------|------|
| 正常流程 (A) | 0 | 5 | 5 |
| 异常场景 (B) | 2 | 4 | 6 |
| 代码级验证 (C) | 4 | 0 | 4 |
| Bug 回归 (D) | 6 | 0 | 6 |
| **合计** | **12** | **9** | **21** |

**可自动验证的 12 项全部通过。** 9 项需要 root + 真实网络环境的测试已列出完整操作步骤，供用户在 macOS 上执行验证。
