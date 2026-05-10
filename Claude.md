# Project: VibeNet Control (macOS)

## 0. Project Overview
A macOS-based network management tool inspired by "WiFi Killer". It uses ARP Spoofing to manage local network devices and can programmatically restrict internet access for specific targets for educational and network testing purposes.

## 1. Technical Context
- **Environment**: macOS (Current)
- **Primary Language**: Python 3.x
- **Core Library**: `scapy` (for packet manipulation)
- **Dependency Tools**: `nmap` or `arp-scan` (for device discovery), `streamlit` (for Web UI)
- **Permissions**: Requires `sudo` for raw socket access.

## 2. Core Logic (ARP Spoofing)
The application achieves network control through the following logic:
1. **Discovery**: Scan the subnet to map IP to MAC addresses.
2. **Impersonation**:
   - Send fake ARP replies to the **Target**: "I am the Gateway".
   - Send fake ARP replies to the **Gateway**: "I am the Target".
3. **Interception**: All traffic from the Target flows through this Mac.
4. **Kill Switch**: 
   - Set `sysctl -w net.inet.ip.forwarding=0` to drop all intercepted packets.
5. **Recovery**: Send "Gratuitous ARP" packets to restore correct ARP tables on exit.

## 3. Project Structure (Target)
- `main.py`: CLI entry point and interactive control loop.
- `gui.py`: Streamlit Web UI entry point (Phase 5).
- `app_entry.py`: macOS .app entry point with privilege escalation (Phase 8).
- `core/scanner.py`: Network scanning, OUI vendor resolution, online API fallback.
- `core/spoofing.py`: ARP poisoning engine with background daemon thread + integrated traffic monitor.
- `core/monitor.py`: Per-target traffic capture via AsyncSniffer with delta rate calculation (Phase 6).
- `utils/sys_config.py`: macOS `sysctl net.inet.ip.forwarding` wrapper.
- `oui_supplement.txt`: Supplementary OUI database (Chinese brands + more, ~2,900 entries).
- `oui_cache.json`: Local cache for online MAC vendor lookups (auto-generated, stored in `~/.vibenet/` when bundled).
- `requirements.txt`: Project dependencies.
- `run.sh`: One-click dependency check & launch (supports `--gui` flag).
- `build.sh`: macOS .app packaging script — creates standalone `VibeNet Control.app` via PyInstaller (Phase 8).
- `generate_icon.py`: App icon generator (Phase 8).

## 4. Development Principles (Vibe Coding Mode)
- **Simplicity First**: Use Python standard libraries or Scapy. Avoid complex GUI until core logic is stable.
- **Safety First**: Always implement a "Emergency Restore" function to stop spoofing and re-enable IP forwarding.
- **Explanations**: Since the user is a non-coder, explain what each major file/function does in simple terms.
- **Atomic Commits**: Suggest a git commit after each successful feature implementation.

## 5. Progress Tracking
- [x] Phase 1: Environment Check & Tooling (Scapy, nmap) — 2026-05-06
- [x] Phase 2: Device Scanner (IP/MAC/Manufacturer) — 2026-05-06
- [x] Phase 3: Core ARP Poisoning Logic — 2026-05-06
- [x] Phase 4: Integrated CLI & Emergency Stop — 2026-05-06
- [x] Phase 5: Streamlit-based Web UI — 2026-05-06
- [x] Phase 6: Real-time Traffic Monitor (core/monitor.py) — 2026-05-06
- [x] Phase 7: Multi-device Speed Test & Decoupled Kill/Test — 2026-05-06
- [x] Phase 8: macOS .app Packaging (PyInstaller + osascript) — 2026-05-06

## 6. Project Deliverables (2026-05-06)
All 8 phases complete. The tool is fully functional with CLI, Web UI, real-time speed monitoring, multi-device traversal testing, and standalone .app packaging:

### Core
- `main.py` — interactive CLI with scan / select / spoof / kill / unkill + real-time speed display
- `gui.py` — Streamlit Web UI with real/randomized device tables, per-device control cards (speed test + kill/restore), traversal batch testing, and Emergency Stop
- `core/scanner.py` — ARP-based network scanner with bundle-aware OUI paths, dual OUI DB + online API fallback + randomized MAC detection
- `core/spoofing.py` — `ArpSpoofer` class with background spoof thread, kill-switch (IP forwarding toggle), integrated TrafficMonitor, and safe ARP restoration
- `core/monitor.py` — `TrafficMonitor` class using AsyncSniffer (store=False) to avoid macOS BPF socket bug, with kill-aware byte counting and delta rate calculation
- `utils/sys_config.py` — macOS `sysctl net.inet.ip.forwarding` wrapper

### Packaging
- `app_entry.py` — macOS .app entry point: non-root → password dialog (AppleScript) → sudo -S re-launch; root → start Streamlit + open browser
- `build.sh` — one-click build script: creates clean venv, installs scapy+streamlit, runs PyInstaller with all hidden imports, outputs `dist/VibeNet Control.app` (~240 MB)
- `generate_icon.py` — generates app icon (PNG → ICNS via iconutil)
- `icon.icns` — app icon

### Data & Docs
- `oui_supplement.txt` — Supplementary OUI database (~2,900 entries: Chinese phone brands, IoT, drones)
- `oui_cache.json` — Local cache for online MAC vendor lookups (stored in `~/.vibenet/` when bundled)
- `run.sh` — one-click dependency check & launch script (supports `--gui` flag)
- `README.md` / `README-zh.md`
- `DEVELOPMENT_LOG.md` / `DEVELOPMENT_LOG-zh.md`
- `AI_CONTEXT.md` — structured handover document for AI sessions

### Key Technical Details
- **Safe exit**: `finally` block guarantees ARP restoration + IP forwarding disable on any exit path
- **Web UI state**: `st.session_state` persists `ArpSpoofer` instances across Streamlit reruns; `_cleanup_dead_spoofers()` removes threads that died between reruns
- **Multi-target**: GUI manages multiple `ArpSpoofer` instances in a dict keyed by target IP
- **OUI database**: 54,067 local entries (nmap 52k + supplement 2.9k) + online API fallback via maclookup.app + disk cache
- **Randomized MAC detection**: Locally-administered bit check distinguishes real devices from nearby Wi-Fi scanners
- **OUI format**: nmap uses delimiter-free hex (`AABBCC`), scapy returns colon-separated — converter required
- **Network detection**: macOS-native `route get default` + `ifconfig` (more reliable than scapy's integer-encoded route table)
- **Threading**: daemon thread + `threading.Event` for interruptible sleep between spoof rounds
- **Traffic monitoring**: AsyncSniffer with BPF filter `host {ip} and not arp`, kill-aware via `threading.Event` toggling byte counting, delta-based `get_stats()` consumed once per rerun
- **Delta consumption pattern**: `get_traffic_stats()` resets internal counters on each call → `_speed_snap` cache guarantees one call per spoofer per rerun, all rendering reads from cache
- **Rerun-driven state machine**: Traversal progress driven by Streamlit auto-refresh (every 2s), no background threads — `_process_traversal_step()` advances one step per rerun
- **Kill/Test decoupling**: Spoofer lifecycle controlled by speed test button; kill button independently toggles `net.inet.ip.forwarding` (system-global) + `monitor.set_active(False)`
- **App packaging**: PyInstaller `--onedir --windowed` → 239 MB .app; app_entry.py uses AppleScript password dialog + `sudo -S -b` for privilege escalation; clean venv build avoids dependency conflicts