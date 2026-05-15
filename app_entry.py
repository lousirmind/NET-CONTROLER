#!/usr/bin/env python3
"""
VibeNet Control macOS .app 入口点
==================================
- 非 root：弹出密码对话框 → sudo 提权重启自身为 root → 打开浏览器 → 退出
- root：设置路径 → 启动 Streamlit → 打开浏览器
"""

import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser


def _is_root():
    return os.geteuid() == 0


def _bundle_dir():
    """PyInstaller bundle 资源目录。"""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


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


def _start_streamlit():
    """以 root 启动 Streamlit 服务器。"""
    _kill_port_process(8501)
    time.sleep(1)

    bundle = _bundle_dir()
    gui_path = os.path.join(bundle, "gui.py")

    if not os.path.exists(gui_path):
        subprocess.run([
            "osascript", "-e",
            'display dialog "应用文件损坏，找不到 gui.py。" '
            'with title "VibeNet Control" buttons {"确定"} default button 1 with icon stop',
        ])
        sys.exit(1)

    if bundle not in sys.path:
        sys.path.insert(0, bundle)

    def _open_browser():
        for _ in range(20):
            time.sleep(1)
            try:
                import urllib.request
                urllib.request.urlopen("http://localhost:8501", timeout=1)
                break
            except Exception:
                pass
        webbrowser.open("http://localhost:8501")

    threading.Thread(target=_open_browser, daemon=True).start()

    import streamlit.web.cli as stcli
    sys.argv = [
        "streamlit", "run", gui_path,
        "--server.headless", "true",
        "--server.port", "8501",
        "--browser.serverAddress", "localhost",
    ]
    stcli.main()


def _get_password_via_dialog():
    """弹出标准 macOS 密码对话框，返回用户输入的密码。"""
    script = '''
    tell application "System Events"
        display dialog "VibeNet Control 需要管理员权限才能发送原始 ARP 数据包。" & return & return & "请输入管理员密码：" ¬
            with title "VibeNet Control" ¬
            default answer "" ¬
            with hidden answer ¬
            with icon caution
        return text returned of result
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except subprocess.TimeoutExpired:
        pass
    return ""


def _show_alert(message):
    """弹出 macOS 提示对话框。"""
    msg = message.replace('\\', '\\\\').replace('"', '\\"')
    subprocess.run([
        "osascript", "-e",
        f'display dialog "{msg}" with title "VibeNet Control" '
        f'buttons {{"确定"}} default button 1 with icon stop',
    ])


def main():
    if _is_root():
        _start_streamlit()
        return

    # ---- 非 root：弹出密码对话框 → sudo 提权 ----
    password = _get_password_via_dialog()
    if not password:
        sys.exit(0)  # 用户取消，静默退出

    logdir = os.path.expanduser("~/.vibenet")
    os.makedirs(logdir, exist_ok=True)
    logfile = os.path.join(logdir, "app.log")
    binary = sys.executable

    # 用 subprocess.Popen + sudo -S 后台启动 root 进程
    # 先验证密码
    valid = subprocess.run(
        ["sudo", "-S", "-k", "true"],
        input=password + "\n",
        capture_output=True, text=True, timeout=10,
    )
    if valid.returncode != 0:
        _show_alert("密码不正确，请重新打开应用并输入正确的管理员密码。")
        sys.exit(1)

    # 密码正确 — 后台启动自身为 root
    proc = subprocess.Popen(
        ["sudo", "-S", binary],
        stdin=subprocess.PIPE,
        stdout=open(logfile, "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    proc.stdin.write((password + "\n").encode())
    proc.stdin.close()

    for _ in range(20):
        time.sleep(1)
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8501", timeout=1)
            break
        except Exception:
            pass
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    main()
