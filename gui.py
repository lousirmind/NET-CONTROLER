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

        # —— 统一状态区（始终存在，避免显隐导致排版跳动） ——
        st.divider()
        trav = st.session_state._trav_running
        active = len(st.session_state.spoofers)

        if trav:
            cur = st.session_state._trav_current
            tot = st.session_state._trav_total
            st.caption(f"🔍 批量测速中：第 {cur}/{tot} 台设备")
            if tot:
                st.progress(cur / tot if tot else 0)
        elif active:
            st.caption(f"📡 手动测速中：{active} 台设备")
        else:
            st.caption("💤 待命中 — 点击下方按钮开始")

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

st.title("📡 VibeNet Control")
st.caption("基于 ARP 欺骗的局域网设备管理与测速")

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

CELL_STYLE = "padding:8px 12px; border:1px solid #ccc;"


def _build_table(devices, start_num, title, row_style, font_color):
    """渲染 HTML 设备表格。"""
    spoofers = st.session_state.spoofers
    speed_results = st.session_state.speed_results

    html = [
        f"<h4 style='margin-top:16px; margin-bottom:8px;'>{title} ({len(devices)})</h4>",
        "<table style='width:100%; border-collapse:collapse; font-size:14px; border:1px solid #ccc;'>",
        "<tr style='text-align:left; background:#333;'>",
        f"<th style='{CELL_STYLE} color:#fff;'>#</th>",
        f"<th style='{CELL_STYLE} color:#fff;'>IP 地址</th>",
        f"<th style='{CELL_STYLE} color:#fff;'>MAC 地址</th>",
        f"<th style='{CELL_STYLE} color:#fff;'>厂商</th>",
        f"<th style='{CELL_STYLE} color:#fff;'>状态</th>",
        f"<th style='{CELL_STYLE} color:#fff;'>速率</th>",
        "</tr>",
    ]

    for i, d in enumerate(devices):
        vendor = get_vendor(d["mac"], oui_db, online=True)
        ip = d["ip"]
        in_test = ip in spoofers and spoofers[ip].is_running
        is_killed = in_test and spoofers[ip].is_killed

        # 状态
        if is_killed:
            status = "🔴 已断网"
        elif in_test:
            status = "🟡 测速中"
        else:
            status = "🟢 在线"

        # 速率列（从快照读取，避免重复调用 get_traffic_stats）
        snap = st.session_state.get("_speed_snap", {})
        if in_test and ip in snap:
            up, down = snap[ip]
            speed = f"<b>↓ {_format_speed(down)}  ↑ {_format_speed(up)}</b>"
        elif ip in speed_results:
            sr = speed_results[ip]
            speed = f"↓ {_format_speed(sr['down'])}  ↑ {_format_speed(sr['up'])}"
        else:
            speed = "-"

        bg, color = row_style(i, is_killed)
        html.append(
            f"<tr style='background:{bg}; color:{color};'>"
            f"<td style='{CELL_STYLE}'>{start_num + i}</td>"
            f"<td style='{CELL_STYLE}'><b>{ip}</b></td>"
            f"<td style='{CELL_STYLE} font-family:monospace;'>{d['mac']}</td>"
            f"<td style='{CELL_STYLE}'>{vendor}</td>"
            f"<td style='{CELL_STYLE}'>{status}</td>"
            f"<td style='{CELL_STYLE} font-family:monospace;'>{speed}</td>"
            f"</tr>"
        )
    html.append("</table>")
    return "".join(html)


# 拆分设备
real_devices = [d for d in devices if not _is_randomized(d["mac"])]
random_devices = [d for d in devices if _is_randomized(d["mac"])]

real_devices.sort(key=lambda d: _ip_int(d["ip"]))
random_devices.sort(key=lambda d: _ip_int(d["ip"]))

st.subheader(f"网络 {st.session_state.network} 中的设备")

# --- 真实设备表格 ---
def _real_row_style(idx, is_killed):
    if is_killed:
        return "#ffcdd2", "#000"
    bg = "#e8f5e9" if idx % 2 == 0 else "#c8e6c9"
    return bg, "#000"

html_all = []
html_all.append(_build_table(real_devices, 1,
    "📡 真实设备（全球唯一 MAC）", _real_row_style, "#000"))

# --- 随机化设备表格 ---
def _random_row_style(idx, is_killed):
    bg = "#e3f2fd" if idx % 2 == 0 else "#bbdefb"
    return bg, "#777"

if random_devices:
    start = len(real_devices) + 1
    html_all.append(_build_table(random_devices, start,
        "🔒 路过扫描设备（随机化 MAC）", _random_row_style, "#777"))

st.markdown("".join(html_all), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 设备控制卡片
# ---------------------------------------------------------------------------

def _render_device_cards(device_list, is_randomized_section=False):
    """渲染一组设备的控制卡片。"""
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

            with cols[j]:
                with st.container(border=True):
                    tag = " 🔒随机" if is_randomized_section else ""
                    st.markdown(f"**{ip}**{tag}")
                    st.caption(f"{mac}")
                    st.caption(f"{vendor}")

                    if is_gateway:
                        st.warning("⚠️ 网关 — 不可操作")
                        continue

                    # --- 状态 + 速率 ---
                    if is_killed:
                        st.markdown("🔴 **已断网**")
                    elif in_test:
                        st.markdown("🟡 **测速中**")
                    else:
                        st.markdown("🟢 **在线**")

                    # 速率显示（从快照读取，避免重复调用 get_traffic_stats）
                    if in_test:
                        up, down = st.session_state.get("_speed_snap", {}).get(ip, (0.0, 0.0))
                        st.caption(f"实时 ↓ {_format_speed(down)}  ↑ {_format_speed(up)}")

                        # 峰值
                        pk = st.session_state._peak_speeds.get(ip)
                        if pk and (pk["up"] > 0 or pk["down"] > 0):
                            st.caption(f"峰值 ↓ {_format_speed(pk['down'])}  ↑ {_format_speed(pk['up'])}")
                    elif ip in st.session_state.speed_results:
                        sr = st.session_state.speed_results[ip]
                        st.caption(f"上次测速 ({sr['time']})：↓ {_format_speed(sr['down'])}  ↑ {_format_speed(sr['up'])}")
                    else:
                        st.caption("暂无测速数据")

                    # --- 两个按钮：测速 + 断网/恢复 ---
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
                                st.rerun()


st.divider()
st.subheader("🎛 设备控制")

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
    """
    <style>
    .emergency-container {
        border: 3px solid #ff4b4b;
        border-radius: 12px;
        padding: 20px;
        background-color: #fff0f0;
        margin-bottom: 20px;
    }
    </style>
    """,
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
