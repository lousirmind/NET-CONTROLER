#!/usr/bin/env bash
#
# build.sh — Build VibeNet Control.app from source
# ==================================================
# Creates a clean venv, installs only needed dependencies,
# then uses PyInstaller to produce a standalone .app bundle.
#
# Prerequisites: Python 3.12+
# Output: dist/VibeNet Control.app  (~240 MB)
#
# Usage:
#   bash build.sh            # Full build
#   open dist/VibeNet\ Control.app   # Test launch
#
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
APP_NAME="VibeNet Control"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
VENV_DIR="$SCRIPT_DIR/.build_venv"

echo ""
echo "=============================================="
echo "  Building $APP_NAME.app"
echo "=============================================="
echo ""

# ---- 1. Check Python ----
echo -n "[*] Python 3 ............... "
python3 -c "import sys; v=f'{sys.version_info.major}.{sys.version_info.minor}'; print(v)"
echo ""

# ---- 2. Prepare OUI Database ----
echo -n "[*] OUI database ........... "
if [ -f /opt/homebrew/share/nmap/nmap-mac-prefixes ]; then
    cp /opt/homebrew/share/nmap/nmap-mac-prefixes "$SCRIPT_DIR/nmap-mac-prefixes"
    COUNT=$(wc -l < "$SCRIPT_DIR/nmap-mac-prefixes" | tr -d ' ')
    echo -e "${GREEN}OK${NC}  ($COUNT entries)"
elif [ -f /usr/local/share/nmap/nmap-mac-prefixes ]; then
    cp /usr/local/share/nmap/nmap-mac-prefixes "$SCRIPT_DIR/nmap-mac-prefixes"
    COUNT=$(wc -l < "$SCRIPT_DIR/nmap-mac-prefixes" | tr -d ' ')
    echo -e "${GREEN}OK${NC}  ($COUNT entries)"
else
    echo -e "${YELLOW}NOT FOUND${NC} (vendor lookup will use supplement only)"
fi

# ---- 3. Generate Icon ----
echo -n "[*] App icon ............... "
if [ ! -f "$SCRIPT_DIR/icon.icns" ]; then
    python3 "$SCRIPT_DIR/generate_icon.py" "$SCRIPT_DIR"
fi
echo -e "${GREEN}OK${NC}"

# ---- 4. Clean Previous Build ----
rm -rf "$DIST_DIR" "$SCRIPT_DIR/build" "$VENV_DIR"

# ---- 5. Create Clean Virtual Environment ----
echo ""
echo "=============================================="
echo "  Setting up build venv"
echo "=============================================="

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip pyinstaller 2>&1 | tail -1
pip install scapy streamlit 2>&1 | tail -1

echo "[*] Build environment ready:"
python3 -c "import scapy, streamlit, PyInstaller; print(f'  scapy={scapy.__version__}  streamlit={streamlit.__version__}')"

# ---- 6. PyInstaller Build ----
echo ""
echo "=============================================="
echo "  Running PyInstaller"
echo "=============================================="

cd "$SCRIPT_DIR"

ADD_DATA=(
    --add-data "gui.py:."
    --add-data "core/__init__.py:core"
    --add-data "core/scanner.py:core"
    --add-data "core/spoofing.py:core"
    --add-data "core/monitor.py:core"
    --add-data "utils/__init__.py:utils"
    --add-data "utils/sys_config.py:utils"
    --add-data "oui_supplement.txt:."
)
if [ -f "$SCRIPT_DIR/nmap-mac-prefixes" ]; then
    ADD_DATA+=(--add-data "nmap-mac-prefixes:.")
fi

python3 -m PyInstaller \
    --onedir \
    --windowed \
    --name "$APP_NAME" \
    --icon "$SCRIPT_DIR/icon.icns" \
    --osx-bundle-identifier "com.vibenet.control" \
    "${ADD_DATA[@]}" \
    --collect-all streamlit \
    --collect-all scapy \
    --hidden-import streamlit.web.cli \
    --hidden-import streamlit.web.server \
    --hidden-import streamlit.runtime \
    --hidden-import streamlit.runtime.scriptrunner \
    --hidden-import scapy.all \
    --hidden-import scapy.layers \
    --hidden-import scapy.layers.inet \
    --hidden-import scapy.layers.l2 \
    --hidden-import scapy.contrib \
    --hidden-import tornado.web \
    --hidden-import tornado.ioloop \
    --hidden-import tornado.httpserver \
    --hidden-import watchdog.observers \
    --hidden-import watchdog.events \
    --hidden-import jinja2 \
    app_entry.py

echo ""

# ---- 7. Verify Output ----
if [ ! -d "$APP_BUNDLE" ]; then
    echo -e "${RED}[!] Build failed: .app bundle not found.${NC}"
    exit 1
fi

# ---- 8. Customize Info.plist ----
PLIST="$APP_BUNDLE/Contents/Info.plist"
if [ -f "$PLIST" ]; then
    /usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 12.0" "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 12.0" "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 1.0.0" "$PLIST" 2>/dev/null || true
fi

# ---- 9. Cleanup ----
deactivate
rm -rf "$VENV_DIR" "$SCRIPT_DIR/build"
if [ -f "$SCRIPT_DIR/nmap-mac-prefixes" ] && [ -f "$APP_BUNDLE/Contents/Resources/nmap-mac-prefixes" ]; then
    rm -f "$SCRIPT_DIR/nmap-mac-prefixes"
fi

# ---- 10. Summary ----
echo "=============================================="
echo -e "  ${GREEN}Build Complete${NC}"
echo "=============================================="
echo ""
echo "  App:  $APP_BUNDLE"
echo "  Size: $(du -sh "$APP_BUNDLE" 2>/dev/null | cut -f1)"
echo ""
echo "  To launch:  open \"$APP_BUNDLE\""
echo ""
echo "  On first launch, right-click → Open to bypass Gatekeeper."
echo "  Or de-quarantine:  xattr -dr com.apple.quarantine \"$APP_BUNDLE\""
echo ""
