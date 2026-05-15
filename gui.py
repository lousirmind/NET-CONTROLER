#!/usr/bin/env python3
"""
VibeNet Control — Streamlit Web 界面
=====================================
基于 ARP 欺骗的网络设备管理仪表盘。

需要 sudo 权限： sudo streamlit run gui.py
"""

import os
import sys
import time
from datetime import datetime

import streamlit as st
from scapy.all import conf

from core.scanner import get_local_network, load_oui_db, get_vendor, scan_network
from core.spoofing import ArpSpoofer

# ---------------------------------------------------------------------------
# 页面配置
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="VibeNet Control",
    page_icon="📡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# 全局 CSS 主题 — "Cyber-Network Terminal"
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ===== CSS 自定义属性 ===== */
:root {
    --bg-primary: #0B1120;
    --bg-secondary: #111827;
    --bg-surface: #1A2332;
    --bg-surface-alt: #1F2A3A;
    --border: #2D3A4A;
    --text-primary: #E2E8F0;
    --text-secondary: #94A3B8;
    --text-muted: #64748B;
    --accent: #00D4AA;
    --accent-glow: rgba(0,212,170,0.25);
    --warning: #F59E0B;
    --warning-glow: rgba(245,158,11,0.25);
    --danger: #EF4444;
    --danger-glow: rgba(239,68,68,0.3);
    --info: #3B82F6;
    --random-tag: #8B5CF6;
}

/* ===== Streamlit 全局覆盖 ===== */
.stApp {
    background: var(--bg-primary);
}
[data-testid="stSidebar"] {
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] .stMetric label,
[data-testid="stSidebar"] label {
    color: var(--text-secondary) !important;
}
[data-testid="stSidebar"] .stMetric [data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-family: monospace;
}
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s !important;
    font-size: 13px !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.stButton > button[kind="primary"] {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    color: #0B1120 !important;
}
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
}
hr, .stDivider {
    border-color: var(--border) !important;
}
.stAlert {
    border-radius: 8px !important;
}
[data-testid="stInfo"] {
    background: rgba(59,130,246,0.08) !important;
}
[data-testid="stSidebar"] .stProgress > div > div {
    background: linear-gradient(90deg, var(--accent), #00b894) !important;
}

/* ===== 主标题 ===== */
.vibenet-title {
    font-size: 32px;
    font-weight: 800;
    color: var(--text-primary);
    margin-bottom: 0;
    letter-spacing: -0.5px;
}
.vibenet-title .accent { color: var(--accent); }
.vibenet-subtitle {
    font-size: 14px;
    color: var(--text-muted);
    margin-top: 4px;
    margin-bottom: 28px;
}

/* ===== 设备表格 ===== */
.vibenet-table-wrapper {
    overflow-x: auto;
    border-radius: 8px;
    border: 1px solid var(--border);
    margin: 16px 0 24px 0;
    background: var(--bg-primary);
}
.vibenet-table-wrapper h4 {
    margin: 0;
    padding: 14px 16px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    font-size: 14px;
    color: var(--text-primary);
    font-weight: 600;
}
.vibenet-table-wrapper h4 .count {
    color: var(--accent);
    font-family: monospace;
}
.vibenet-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    color: var(--text-primary);
}
.vibenet-table thead th {
    background: linear-gradient(180deg, #1A2332 0%, #111827 100%);
    padding: 11px 14px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    text-align: left;
    border-bottom: 2px solid var(--accent);
    white-space: nowrap;
    color: var(--text-secondary);
}
.vibenet-table tbody td {
    padding: 9px 14px;
    border-bottom: 1px solid rgba(45,58,74,0.5);
    white-space: nowrap;
}
.vibenet-table tbody tr { transition: background 0.15s; }
.vibenet-table tbody tr:hover { background: rgba(0,212,170,0.06) !important; }
.vibenet-table .row-real-even { background: var(--bg-surface); }
.vibenet-table .row-real-odd  { background: var(--bg-surface-alt); }
.vibenet-table .row-random { opacity: 0.7; }
.vibenet-table .row-random:nth-child(even) { background: rgba(26,35,50,0.6); }
.vibenet-table .row-random:nth-child(odd)  { background: rgba(31,42,58,0.5); }
.vibenet-table .row-killed {
    background: rgba(239,68,68,0.12) !important;
}
.vibenet-table .row-killed td { color: var(--danger); }
.vibenet-table .row-killed:hover { background: rgba(239,68,68,0.18) !important; }
.vibenet-table .col-ip { font-weight: 600; font-family: "SF Mono", "Fira Code", monospace; }
.vibenet-table .col-mac { font-family: "SF Mono", "Fira Code", monospace; color: var(--text-secondary); font-size: 12px; }
.vibenet-table .col-status { font-weight: 600; }
.vibenet-table .speed-down { color: var(--accent); font-weight: 600; }
.vibenet-table .speed-up   { color: var(--info); font-weight: 600; }
.vibenet-table .speed-unit { color: var(--text-muted); font-size: 11px; }

/* ===== 设备控制卡片 ===== */
.vibenet-card {
    background: var(--bg-surface);
    border-radius: 12px;
    border: 1px solid var(--border);
    padding: 14px 16px;
    margin-bottom: 8px;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.vibenet-card:hover {
    border-color: var(--accent);
    box-shadow: 0 0 16px var(--accent-glow);
}
.vibenet-card.randomized {
    opacity: 0.82;
    border-color: rgba(139,92,246,0.25);
}
.vibenet-card .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
    flex-wrap: wrap;
    gap: 4px;
}
.vibenet-card .card-ip {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
    font-family: "SF Mono", "Fira Code", monospace;
}
.vibenet-card .card-tag {
    font-size: 10px;
    background: var(--random-tag);
    color: #fff;
    padding: 2px 7px;
    border-radius: 4px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.vibenet-card .card-mac {
    font-size: 11px;
    color: var(--text-muted);
    font-family: "SF Mono", "Fira Code", monospace;
    margin-bottom: 2px;
}
.vibenet-card .card-vendor {
    font-size: 11px;
    color: var(--text-secondary);
    margin-bottom: 8px;
}
.vibenet-card .card-speed-box {
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 12px;
    margin: 8px 0;
    padding: 8px 10px;
    background: rgba(0,0,0,0.25);
    border-radius: 6px;
    border-left: 3px solid var(--accent);
    line-height: 1.6;
}
.vibenet-card .card-speed-box .dl { color: var(--accent); font-weight: 600; }
.vibenet-card .card-speed-box .ul { color: var(--info); font-weight: 600; }
.vibenet-card .card-speed-box .pk { color: var(--text-muted); }
.vibenet-card .card-speed-box .sp { color: var(--text-secondary); }

/* 状态指示器 */
.status-indicator {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
    font-size: 13px;
    margin: 4px 0 6px 0;
}
.status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
}
.status-dot.online  { background: var(--accent); }
.status-dot.testing {
    background: var(--warning);
    animation: vibenet-pulse 1.5s ease-in-out infinite;
}
.status-dot.killed  { background: var(--danger); }
.status-text.online  { color: var(--accent); }
.status-text.testing { color: var(--warning); }
.status-text.killed  { color: var(--danger); }

@keyframes vibenet-pulse {
    0%, 100% { box-shadow: 0 0 0 0 var(--warning); opacity: 1; }
    50%      { box-shadow: 0 0 8px 2px var(--warning); opacity: 0.6; }
}

/* ===== 紧急停止 ===== */
.emergency-container {
    border: 2px solid var(--danger);
    border-radius: 12px;
    padding: 20px 24px;
    background: rgba(239,68,68,0.06);
    margin: 24px 0;
}

/* ===== 侧边栏状态卡 ===== */
.sidebar-status-card {
    background: var(--bg-surface);
    border-radius: 8px;
    padding: 10px 12px;
    text-align: center;
    border: 1px solid var(--border);
    font-size: 13px;
}
.sidebar-status-card .state-active {
    color: var(--warning);
    font-weight: 600;
}
.sidebar-status-card .state-idle {
    color: var(--text-muted);
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state — 跨 Streamlit 重渲染保持状态
# ---------------------------------------------------------------------------

DEFAULTS = {
    "spoofers": {},           # {target_ip: ArpSpoofer}
    "_testing": {},           # {target_ip: bool} — 测速是否激活
    "devices": [],
    "oui_db": {},
    "gateway_ip": None,
    "network": None,
    "scanned": False,
    "speed_results": {},      # {ip: {"up": kbps, "down": kbps, "time": "HH:MM:SS"}}
    "_peak_speeds": {},       # {ip: {"up": kbps, "down": kbps}} — 手动测速峰值

    # 遍历测速状态机（rerun 驱动，不用后台线程）
    "_trav_queue": [],        # 待测设备 IP 列表
    "_trav_current_ip": None, # 当前正在测的设备
    "_trav_samples": 0,       # 当前设备已采样次数
    "_trav_peak_up": 0.0,     # 当前设备上行峰值
    "_trav_peak_down": 0.0,   # 当前设备下行峰值
    "_trav_running": False,   # 遍历是否进行中
    "_trav_current": 0,       # 当前第几个
    "_trav_total": 0,         # 总共几个
}
for key, default in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _format_speed(kbps):
    """人类可读的速率格式。"""
    if kbps < 1:
        return "0.0 KB/s"
    elif kbps < 1024:
        return f"{kbps:.1f} KB/s"
    else:
        return f"{kbps / 1024:.1f} MB/s"


def _get_gateway():
    """从系统路由表获取默认网关 IP。"""
    for route in conf.route.routes:
        net, mask, gw, iface = route[:4]
        if net == 0 and mask == 0 and iface != "lo0":
            return gw
    return None


def _cleanup_dead_spoofers():
    """清理线程已死的 spoofer（如 Streamlit 热重载后）。"""
    dead = [
        ip for ip, s in st.session_state.spoofers.items()
        if not s.is_running
    ]
    for ip in dead:
        try:
            st.session_state.spoofers[ip].stop(restore=True)
        except Exception:
            pass
        del st.session_state.spoofers[ip]
        st.session_state._testing.pop(ip, None)


def _is_randomized(mac):
    """检查 MAC 地址是否为本地管理（随机化）。"""
    try:
        return (int(mac.replace(":", "")[:2], 16) & 0x02) != 0
    except ValueError:
        return False


def _ip_int(ip):
    return tuple(int(x) for x in ip.split("."))


# ---------------------------------------------------------------------------
# 遍历测速状态机（每次 rerun 处理一步）
# ---------------------------------------------------------------------------

def _process_traversal_step():
    """在每次 rerun 时推进遍历测速一步。由 auto-refresh 驱动。"""
    ts = st.session_state
    if not ts._trav_running:
        return

    queue = ts._trav_queue
    current_ip = ts._trav_current_ip

    # —— 没有正在测的设备：从队列取下一个 ——
    if current_ip is None:
        if not queue:
            # 遍历完成
            ts._trav_running = False
            ts._trav_current = 0
            return

        ip = queue.pop(0)
        ts._trav_queue = queue
        ts._trav_current = len(ts.devices) - len(queue)
        ts._trav_total = ts._trav_current + len(queue)

        if ip == ts.gateway_ip:
            # 跳过网关
            ts._trav_current_ip = None
            return

        try:
            sp = ArpSpoofer(ip, ts.gateway_ip)
            sp.start()  # 透明代理模式
            ts.spoofers[ip] = sp
            ts._testing[ip] = True
            ts._trav_current_ip = ip
            ts._trav_samples = 0
            ts._trav_peak_up = 0.0
            ts._trav_peak_down = 0.0
        except RuntimeError:
            ts._trav_current_ip = None
        return

    # —— 正在测当前设备：采样（从快照读取，避免重复消耗 delta） ——
    sp = ts.spoofers.get(current_ip)
    if sp is None or not sp.is_running:
        ts._trav_current_ip = None
        return

    up, down = ts.get("_speed_snap", {}).get(current_ip, (0.0, 0.0))
    ts._trav_peak_up = max(ts._trav_peak_up, up)
    ts._trav_peak_down = max(ts._trav_peak_down, down)
    ts._trav_samples += 1

    # 采集 3 个样本（~6 秒）后完成该设备
    if ts._trav_samples >= 3:
        ts.speed_results[current_ip] = {
            "up": round(ts._trav_peak_up, 1),
            "down": round(ts._trav_peak_down, 1),
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        sp.stop(restore=True)
        del ts.spoofers[current_ip]
        ts._testing.pop(current_ip, None)
        ts._trav_current_ip = None


def _start_traversal():
    """初始化遍历队列并标记开始。"""
    ts = st.session_state
    if not ts.devices:
        return

    # 停止已有的手动测速
    for ip, sp in list(ts.spoofers.items()):
        try:
            sp.stop(restore=True)
        except Exception:
            pass
    ts.spoofers = {}
    ts._testing = {}
    ts._peak_speeds = {}

    ts._trav_queue = [d["ip"] for d in ts.devices]
    ts._trav_current_ip = None
    ts._trav_samples = 0
    ts._trav_running = True
    ts._trav_current = 0
    ts._trav_total = len(ts.devices)


# ---------------------------------------------------------------------------
# 侧边栏
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("🌐 网络扫描")

    if st.button("🔍 扫描网络", type="primary", use_container_width=True):
        with st.spinner("正在扫描局域网..."):
            st.session_state.network = get_local_network()
            st.session_state.oui_db = load_oui_db()
            st.session_state.gateway_ip = _get_gateway()
            devices = scan_network(st.session_state.network)
            devices.sort(key=lambda d: tuple(int(x) for x in d["ip"].split(".")))
            st.session_state.devices = devices
            st.session_state.scanned = True
            st.session_state.spoofers = {}
            st.session_state._testing = {}
            st.session_state._peak_speeds = {}
            st.session_state.speed_results = {}
        st.rerun()

    if st.session_state.scanned:
        st.divider()
        st.metric("发现设备数", len(st.session_state.devices))
        st.metric("网关", st.session_state.gateway_ip or "未知")
        st.metric("网络", st.session_state.network or "未知")

        oui_count = len(st.session_state.oui_db)
        if oui_count:
            st.caption(f"OUI 数据库：{oui_count:,} 条")

        # —— 统一状态区 ——
        st.divider()
        trav = st.session_state._trav_running
        active = len(st.session_state.spoofers)

        if trav:
            cur = st.session_state._trav_current
            tot = st.session_state._trav_total
            st.markdown(
                f'<div class="sidebar-status-card">'
                f'🔍 <span class="state-active">批量测速中：第 {cur}/{tot} 台设备</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if tot:
                st.progress(cur / tot if tot else 0)
        elif active:
            st.markdown(
                f'<div class="sidebar-status-card">'
                f'📡 <span class="state-active">手动测速中：{active} 台设备</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="sidebar-status-card">'
                '<span class="state-idle">💤 待命中 — 点击下方按钮开始</span>'
                '</div>',
                unsafe_allow_html=True,
            )

        st.divider()
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button("🔍 开始测速", use_container_width=True,
                         help="对所有设备逐个测速"):
                _start_traversal()
                st.rerun()
        with c_btn2:
            if st.button("⏹ 停止测速", use_container_width=True,
                         help="停止所有批量测速和手动测速"):
                st.session_state._trav_running = False
                st.session_state._trav_queue = []
                st.session_state._trav_current_ip = None
                for ip, sp in list(st.session_state.spoofers.items()):
                    try:
                        sp.stop(restore=True)
                    except Exception:
                        pass
                st.session_state.spoofers = {}
                st.session_state._testing = {}
                st.session_state._peak_speeds = {}
                st.rerun()

        st.session_state.auto_refresh = st.checkbox(
            "自动刷新（每 2 秒）", value=st.session_state.get("auto_refresh", True)
        )

# ---------------------------------------------------------------------------
# 权限检查
# ---------------------------------------------------------------------------

if os.geteuid() != 0:
    st.error("此工具需要 root 权限。请使用：`sudo streamlit run gui.py`")
    st.stop()

# ---------------------------------------------------------------------------
# 主界面
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="vibenet-title">📡 <span class="accent">VibeNet</span> Control</div>'
    '<div class="vibenet-subtitle">基于 ARP 欺骗的局域网设备管理与测速</div>',
    unsafe_allow_html=True,
)

if not st.session_state.scanned:
    st.info("👈 点击左侧边栏的 **扫描网络** 发现局域网内的设备。")
    st.stop()

devices = st.session_state.devices
oui_db = st.session_state.oui_db
gateway_ip = st.session_state.gateway_ip

if not devices:
    st.warning("网络中没有设备响应。")
    st.stop()

# 清理死线程
_cleanup_dead_spoofers()

# 采集一次速率快照（每个 spoofer 只调用一次 get_traffic_stats，避免 delta 被多次消耗）
st.session_state._speed_snap = {}
for ip, sp in st.session_state.spoofers.items():
    if sp.is_running:
        up, down = sp.get_traffic_stats()
        st.session_state._speed_snap[ip] = (up, down)

        # 更新手动测速峰值（遍历测速有自己的峰值跟踪）
        if st.session_state._testing.get(ip) and not st.session_state._trav_running:
            pk = st.session_state._peak_speeds.setdefault(ip, {"up": 0.0, "down": 0.0})
            pk["up"] = max(pk["up"], up)
            pk["down"] = max(pk["down"], down)

# 推进遍历测速状态机（从快照读取速率，不再调用 get_traffic_stats）
_process_traversal_step()

# ---------------------------------------------------------------------------
# 设备表格
# ---------------------------------------------------------------------------

def _row_class(idx, is_killed, is_random):
    if is_killed:
        return "row-killed"
    if is_random:
        return f"row-random"
    return f"row-real-{'even' if idx % 2 == 0 else 'odd'}"


def _build_table(devices, start_num, title, count_suffix, is_random):
    spoofers = st.session_state.spoofers
    speed_results = st.session_state.speed_results

    killed_count = 0
    testing_count = 0
    online_count = len(devices)

    rows_html = []
    for i, d in enumerate(devices):
        vendor = get_vendor(d["mac"], oui_db, online=True)
        ip = d["ip"]
        in_test = ip in spoofers and spoofers[ip].is_running
        is_killed = in_test and spoofers[ip].is_killed

        if is_killed:
            status_cls = "killed"
            status_text = "已断网"
            killed_count += 1
            online_count -= 1
        elif in_test:
            status_cls = "testing"
            status_text = "测速中"
            testing_count += 1
            online_count -= 1
        else:
            status_cls = "online"
            status_text = "在线"

        # 速率列
        snap = st.session_state.get("_speed_snap", {})
        if in_test and ip in snap:
            up, down = snap[ip]
            speed = (
                f'<span class="speed-down">↓ {_format_speed(down)}</span>'
                f'  <span class="speed-up">↑ {_format_speed(up)}</span>'
            )
        elif ip in speed_results:
            sr = speed_results[ip]
            speed = (
                f'<span class="pk">↓ {_format_speed(sr["down"])}</span>'
                f'  <span class="sp">↑ {_format_speed(sr["up"])}</span>'
            )
        else:
            speed = '<span class="pk">-</span>'

        row_cls = _row_class(i, is_killed, is_random)
        rows_html.append(
            f'<tr class="{row_cls}">'
            f'<td>{start_num + i}</td>'
            f'<td class="col-ip">{ip}</td>'
            f'<td class="col-mac">{d["mac"]}</td>'
            f'<td>{vendor}</td>'
            f'<td class="col-status"><span class="status-dot {status_cls}"></span> {status_text}</td>'
            f'<td>{speed}</td>'
            f'</tr>'
        )

    summary = f'{online_count} 在线'
    if testing_count:
        summary += f' · {testing_count} 测速中'
    if killed_count:
        summary += f' · {killed_count} 断网'

    return (
        f'<div class="vibenet-table-wrapper">'
        f'<h4>{title} <span class="count">{count_suffix}</span>'
        f'<span style="font-weight:400;font-size:11px;color:var(--text-muted);float:right;margin-top:2px;">{summary}</span></h4>'
        f'<table class="vibenet-table">'
        f'<thead><tr>'
        f'<th>#</th><th>IP 地址</th><th>MAC 地址</th><th>厂商</th><th>状态</th><th>速率</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table></div>'
    )


# 拆分设备
real_devices = [d for d in devices if not _is_randomized(d["mac"])]
random_devices = [d for d in devices if _is_randomized(d["mac"])]

real_devices.sort(key=lambda d: _ip_int(d["ip"]))
random_devices.sort(key=lambda d: _ip_int(d["ip"]))

st.subheader(f"网络 {st.session_state.network} 中的设备")

html_all = []
html_all.append(_build_table(real_devices, 1,
    "📡 真实设备（全球唯一 MAC）", f"({len(real_devices)})", is_random=False))

if random_devices:
    start = len(real_devices) + 1
    html_all.append(_build_table(random_devices, start,
        "🔒 路过扫描设备（随机化 MAC）", f"({len(random_devices)})", is_random=True))

st.markdown("".join(html_all), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 设备控制卡片
# ---------------------------------------------------------------------------

def _render_device_cards(device_list, is_randomized_section=False):
    COLS_PER_ROW = 3
    for i in range(0, len(device_list), COLS_PER_ROW):
        batch = device_list[i : i + COLS_PER_ROW]
        cols = st.columns(COLS_PER_ROW)
        for j, d in enumerate(batch):
            ip = d["ip"]
            mac = d["mac"]
            vendor = get_vendor(mac, oui_db, online=True)
            is_gateway = ip == gateway_ip

            has_spoofer = ip in st.session_state.spoofers
            sp = st.session_state.spoofers.get(ip)
            in_test = has_spoofer and sp.is_running and st.session_state._testing.get(ip, False)
            is_killed = has_spoofer and sp.is_running and sp.is_killed

            # 状态信息
            if is_killed:
                status_cls = "killed"
                status_text = "已断网"
            elif in_test:
                status_cls = "testing"
                status_text = "测速中"
            else:
                status_cls = "online"
                status_text = "在线"

            # 速率区域 HTML
            speed_html = ""
            if in_test:
                up, down = st.session_state.get("_speed_snap", {}).get(ip, (0.0, 0.0))
                speed_html = (
                    f'<div class="card-speed-box">'
                    f'实时 <span class="dl">↓ {_format_speed(down)}</span>'
                    f'  <span class="ul">↑ {_format_speed(up)}</span>'
                )
                pk = st.session_state._peak_speeds.get(ip)
                if pk and (pk["up"] > 0 or pk["down"] > 0):
                    speed_html += (
                        f'<br>峰值 <span class="dl">↓ {_format_speed(pk["down"])}</span>'
                        f'  <span class="ul">↑ {_format_speed(pk["up"])}</span>'
                    )
                speed_html += "</div>"
            elif ip in st.session_state.speed_results:
                sr = st.session_state.speed_results[ip]
                speed_html = (
                    f'<div class="card-speed-box">'
                    f'<span class="pk">上次测速 ({sr["time"]})</span><br>'
                    f'<span class="dl">↓ {_format_speed(sr["down"])}</span>'
                    f'  <span class="ul">↑ {_format_speed(sr["up"])}</span>'
                    f'</div>'
                )
            else:
                speed_html = '<div class="card-speed-box" style="border-left-color:var(--border);"><span class="pk">暂无测速数据</span></div>'

            with cols[j]:
                card_cls = "vibenet-card randomized" if is_randomized_section else "vibenet-card"
                tag_html = '<span class="card-tag">随机MAC</span>' if is_randomized_section else ""

                card_html = (
                    f'<div class="{card_cls}">'
                    f'<div class="card-header">'
                    f'<span class="card-ip">{ip}</span>{tag_html}'
                    f'</div>'
                    f'<div class="status-indicator">'
                    f'<span class="status-dot {status_cls}"></span>'
                    f'<span class="status-text {status_cls}">{status_text}</span>'
                    f'</div>'
                    f'<div class="card-mac">{mac}</div>'
                    f'<div class="card-vendor">{vendor}</div>'
                    f'{speed_html}'
                    f'</div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)

                if is_gateway:
                    st.warning("⚠️ 网关 — 不可操作")
                    continue

                c1, c2 = st.columns(2)

                with c1:
                    if in_test:
                        if st.button("⏹ 停止测速", key=f"stop_{ip}", use_container_width=True):
                            pk = st.session_state._peak_speeds.get(ip, {})
                            st.session_state.speed_results[ip] = {
                                "up": round(pk.get("up", 0), 1),
                                "down": round(pk.get("down", 0), 1),
                                "time": datetime.now().strftime("%H:%M:%S"),
                            }
                            st.session_state._peak_speeds.pop(ip, None)
                            if is_killed:
                                st.session_state._testing[ip] = False
                            else:
                                sp.stop(restore=True)
                                del st.session_state.spoofers[ip]
                                st.session_state._testing.pop(ip, None)
                            st.rerun()
                    else:
                        if st.button("🔍 开始测速", key=f"start_{ip}", use_container_width=True):
                            if has_spoofer and sp.is_running:
                                st.session_state._testing[ip] = True
                            else:
                                try:
                                    new_sp = ArpSpoofer(ip, gateway_ip)
                                    new_sp.start()
                                    st.session_state.spoofers[ip] = new_sp
                                    st.session_state._testing[ip] = True
                                except RuntimeError as e:
                                    st.error(f"无法连接 {ip}：{e}")
                            st.rerun()

                with c2:
                    if is_killed:
                        if st.button("🟢 恢复", key=f"restore_{ip}", use_container_width=True):
                            sp.unkill()
                            for s in st.session_state.spoofers.values():
                                if s.is_running:
                                    s._killed = False
                            st.rerun()
                    else:
                        if st.button("🔴 断网", key=f"kill_{ip}", use_container_width=True):
                            if not has_spoofer or not sp.is_running:
                                try:
                                    new_sp = ArpSpoofer(ip, gateway_ip)
                                    new_sp.start()
                                    st.session_state.spoofers[ip] = new_sp
                                    new_sp.kill()
                                except RuntimeError as e:
                                    st.error(f"无法连接 {ip}：{e}")
                            else:
                                sp.kill()
                            for s in st.session_state.spoofers.values():
                                if s.is_running:
                                    s._killed = True
                            st.rerun()


st.divider()
st.subheader("🎛 设备控制")
st.info("注意：断网/恢复基于系统级 IP 转发，同时影响所有被拦截的设备。")

_render_device_cards(real_devices)

if random_devices:
    st.divider()
    st.subheader("🔒 路过扫描设备控制（随机化 MAC）")
    st.caption("这些设备的 MAC 地址会随机变化，测速和断网操作仍然有效，但设备可能随时更换 MAC。")
    _render_device_cards(random_devices, is_randomized_section=True)

# ---------------------------------------------------------------------------
# 紧急停止
# ---------------------------------------------------------------------------

st.divider()

st.markdown(
    '<div class="emergency-container">',
    unsafe_allow_html=True,
)

st.subheader("🚨 紧急停止")
st.caption("立即停止所有活动的欺骗 / 测速并恢复网络。")

spoofer_count = len(st.session_state.spoofers)
trav_running = st.session_state._trav_running

if spoofer_count > 0 or trav_running:
    if spoofer_count > 0:
        st.markdown(f"**{spoofer_count} 台设备活动中：**")
        for target_ip in st.session_state.spoofers:
            st.markdown(f"- 🟡 {target_ip}")
    if trav_running:
        cur = st.session_state._trav_current
        tot = st.session_state._trav_total
        st.markdown(f"**自动批量测速进行中**（第 {cur}/{tot} 台）")

col1, col2, col3 = st.columns([1, 1, 3])
with col1:
    if st.button("🚨 紧急停止 — 全部恢复", type="secondary", use_container_width=True):
        if spoofer_count == 0 and not trav_running:
            st.info("没有活动中的会话。")
        else:
            # 停止遍历
            st.session_state._trav_running = False
            st.session_state._trav_queue = []
            st.session_state._trav_current_ip = None

            # 停止所有 spoofer
            restored = 0
            errors = []
            for target_ip, sp in list(st.session_state.spoofers.items()):
                try:
                    sp.stop(restore=True)
                    restored += 1
                except Exception as e:
                    errors.append(f"{target_ip}: {e}")
            st.session_state.spoofers.clear()
            st.session_state._testing.clear()
            st.session_state._peak_speeds = {}

            if errors:
                for err in errors:
                    st.error(f"恢复失败 — {err}")
            st.success(f"已恢复 {restored} 台设备。网络已清理。")
            st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 自动刷新
# ---------------------------------------------------------------------------

should_refresh = (
    st.session_state.get("auto_refresh", True)
    and (st.session_state.spoofers or st.session_state._trav_running)
)
if should_refresh:
    time.sleep(2)
    st.rerun()
