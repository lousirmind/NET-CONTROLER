#!/usr/bin/env bash
#
# run.sh — One-click launcher for VibeNet Control
# ================================================
# 1. Checks Python 3, scapy, and nmap.
# 2. Auto-installs missing dependencies when possible.
# 3. Launches main.py with sudo.
#
# Usage:  bash run.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ---- Parse arguments ----
GUI_MODE=0
for arg in "$@"; do
    case "$arg" in
        --gui) GUI_MODE=1 ;;
    esac
done

echo ""
echo "=============================================="
echo "  VibeNet Control — Environment Setup"
echo "=============================================="
echo ""

MISSING=0

# ---- Python 3 ----
echo -n "[*] Python 3 .............. "
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo -e "${GREEN}OK${NC}  (${PY_VER})"
else
    echo -e "${RED}MISSING${NC}"
    echo "    Install: https://www.python.org/downloads/"
    MISSING=1
fi

# ---- scapy ----
echo -n "[*] scapy ................. "
if python3 -c "import scapy" 2>/dev/null; then
    SCAPY_VER=$(python3 -c "import scapy; print(scapy.__version__)" 2>/dev/null)
    echo -e "${GREEN}OK${NC}  (${SCAPY_VER})"
else
    echo -e "${YELLOW}INSTALLING...${NC}"
    pip3 install scapy
    if python3 -c "import scapy" 2>/dev/null; then
        echo -e "    ${GREEN}Done${NC}"
    else
        echo -e "    ${RED}Failed — try: pip3 install scapy${NC}"
        MISSING=1
    fi
fi

# ---- nmap (for OUI database) ----
echo -n "[*] nmap .................. "
if command -v nmap &>/dev/null; then
    NMAP_VER=$(nmap --version 2>&1 | head -1 | awk '{print $3}')
    echo -e "${GREEN}OK${NC}  (${NMAP_VER})"
elif [ -f /opt/homebrew/share/nmap/nmap-mac-prefixes ]; then
    echo -e "${GREEN}OK${NC}  (OUI DB found, binary missing — non-critical)"
else
    echo -e "${YELLOW}MISSING${NC}"
    if command -v brew &>/dev/null; then
        echo "    Installing with Homebrew..."
        brew install nmap
    else
        echo "    Install: brew install nmap"
        echo "    (Vendor lookup will show 'Unknown' without it.)"
        MISSING=1
    fi
fi

# ---- streamlit (GUI mode only) ----
if [ "$GUI_MODE" -eq 1 ]; then
    echo -n "[*] streamlit ............. "
    if python3 -c "import streamlit" 2>/dev/null; then
        ST_VER=$(python3 -c "import streamlit; print(streamlit.__version__)" 2>/dev/null)
        echo -e "${GREEN}OK${NC}  (${ST_VER})"
    else
        echo -e "${YELLOW}INSTALLING...${NC}"
        pip3 install streamlit
        if python3 -c "import streamlit" 2>/dev/null; then
            echo -e "    ${GREEN}Done${NC}"
        else
            echo -e "    ${RED}Failed — try: pip3 install streamlit${NC}"
            MISSING=1
        fi
    fi
fi

# ---- Summary ----
echo ""
if [ "$MISSING" -eq 1 ]; then
    echo -e "${RED}[!] Some dependencies could not be installed.${NC}"
    echo "    Please fix the issues above and re-run."
    exit 1
fi

echo -e "${GREEN}[*] All dependencies ready.${NC}"
echo ""

# ---- Launch ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$GUI_MODE" -eq 1 ]; then
    echo "=============================================="
    echo "  Launching VibeNet Control — Web UI"
    echo "  (sudo is required for raw ARP packets)"
    echo "=============================================="
    echo ""

    # 先验证 sudo 密码（前台，确保用户输入完成）
    sudo -v
    if [ $? -ne 0 ]; then
        echo "sudo 认证失败，退出。"
        exit 1
    fi

    # 后台启动 Streamlit
    ST_PID=""
    cleanup() {
        if [ -n "$ST_PID" ] && kill -0 "$ST_PID" 2>/dev/null; then
            kill "$ST_PID" 2>/dev/null
        fi
    }
    trap cleanup EXIT

    sudo streamlit run "$SCRIPT_DIR/gui.py" --server.headless true &
    sleep 2
    ST_PID=$(lsof -ti :8501 2>/dev/null | head -1)

    if [ -z "$ST_PID" ]; then
        echo "错误：无法获取 Streamlit 进程 PID，端口 8501 可能未成功启动。"
        exit 1
    fi

    # 等待服务就绪后再打开浏览器
    echo "等待 Streamlit 启动..."
    for i in $(seq 1 15); do
        if curl -s http://localhost:8501 > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    echo "打开浏览器 http://localhost:8501"
    open http://localhost:8501
    wait "$ST_PID"
else
    echo "=============================================="
    echo "  Launching VibeNet Control..."
    echo "  (sudo is required for raw ARP packets)"
    echo "=============================================="
    echo ""
    exec sudo python3 "$SCRIPT_DIR/main.py"
fi
