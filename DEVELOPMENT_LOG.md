# Development Log — VibeNet Control

## Project Overview

A macOS-based ARP spoofing tool for network interception and access control. Built with Python 3 + scapy, uses `sysctl` for kernel-level IP forwarding control. Features both a terminal CLI and a Streamlit Web UI.

**Development period**: 2026-05-06
**Status**: All 5 phases complete.

---

## Core Architecture

### Data Flow

```
gui.py (Web UI)  /  main.py (CLI)
  ├── core/scanner.py     →  ARP scan → device list + vendor resolution
  ├── core/spoofing.py    →  ARP spoof thread + restoration
  └── utils/sys_config.py →  sysctl IP forwarding toggle
```

### ARP Spoofing Mechanism

**Key insight**: ARP has no authentication. Any host on the local network can send an unsolicited "ARP Reply" (op=2) and most operating systems will accept and cache it immediately.

```
Normal flow:
  Target --[who has 192.168.1.1?]-->  Gateway
  Target <--[192.168.1.1 is at XX:XX]-- Gateway

Poisoned flow:
  Target <--[192.168.1.1 is at ATK_MAC]-- Attacker (spoofed)
  Gateway <--[192.168.1.5 is at ATK_MAC]-- Attacker (spoofed)
```

The spoofed packets are:

| Direction | psrc (claimed IP) | hwsrc (claimed MAC) | Effect |
|-----------|-------------------|---------------------|--------|
| → Target | gateway_ip | our MAC | Target sends traffic to us |
| → Gateway | target_ip | our MAC | Gateway sends replies to us |

### IP Forwarding as Kill Switch

macOS kernel parameter `net.inet.ip.forwarding`:

- `1`: Kernel routes packets between interfaces — transparent proxy
- `0`: Kernel **silently drops** non-local packets — the "kill" effect

Unlike iptables-based blocking, this requires no firewall rules and is instantly reversible.

### Restoration (Gratuitous ARP)

On exit, we send 3 rounds (with 0.3s intervals) of correct ARP replies:

```python
# Tell target: "gateway IP → gateway's real MAC"
ARP(op=2, psrc=gateway_ip, pdst=target_ip,
    hwsrc=real_gateway_mac, hwdst=target_mac)

# Tell gateway: "target IP → target's real MAC"
ARP(op=2, psrc=target_ip, pdst=gateway_ip,
    hwsrc=real_target_mac, hwdst=gateway_mac)
```

Multiple rounds guard against packet loss (ARP is best-effort).

### Threading Model

Spoofing runs in a **daemon thread** controlled by a `threading.Event`:

```python
while not self._stop_event.is_set():
    self._send_one_round()
    self._stop_event.wait(interval)  # interruptible sleep
```

- Daemon thread → won't block process exit
- Event-based stop → clean shutdown within one interval cycle
- `thread.join(timeout=5)` → safety timeout in case of hang

### Safe Exit Guarantee

`main.py` uses a three-layer defense:

```
Layer 1: signal.SIGINT handler  (registered, acts as safety net)
Layer 2: except KeyboardInterrupt  (catches Ctrl+C during I/O)
Layer 3: finally: spoofer.stop()   (ALWAYS runs, even on unexpected exit)
```

The `finally` block is the critical guarantee — even if an unhandled exception occurs, ARP restoration and IP forwarding disable are executed.

---

## Web UI Architecture (Phase 5)

### Session State Management

Streamlit re-executes the entire script on every widget interaction. To prevent background threads from being destroyed:

```
st.session_state
  ├── spoofers: Dict[str, ArpSpoofer]   # keyed by target IP
  ├── devices:  List[dict]              # scan results
  ├── oui_db:   Dict[str, str]          # parsed OUI database
  ├── gateway_ip: str                   # default gateway
  ├── network:  str                     # CIDR network string
  └── scanned:  bool                    # whether scan has been run
```

`_cleanup_dead_spoofers()` runs on every rerun to remove spoofers whose daemon threads have died (e.g., after Streamlit hot-reload).

### Multi-Target Design

Unlike the CLI which handles a single target, the GUI manages multiple `ArpSpoofer` instances simultaneously. Each spoofer is stored in `session_state.spoofers[target_ip]` and independently killable/restorable.

### Device Table — Real vs. Randomized

Modern OSes (iOS 14+, Android 10+, macOS) randomize MAC addresses during Wi-Fi scanning. The GUI splits devices into two tables:

| Table | MAC Type | Row Color | Text Color | Actionable |
|-------|----------|-----------|------------|------------|
| Connected Devices | Globally unique (bit 1 = 0) | Green alternating | Black | Yes |
| Nearby Scanning | Locally administered (bit 1 = 1) | Blue alternating | Gray | No |

Detection logic: second-least-significant bit of the first MAC byte = 1 → locally administered → randomized.

### HTML Table Rendering

Tables are rendered as raw HTML via `st.markdown(unsafe_allow_html=True)` to avoid pyarrow/numpy dependency conflicts in Streamlit's native `st.table`/`st.dataframe` components.

---

## OUI Vendor Database (Phase 5 Enhancement)

### Three-Layer Resolution

```python
def get_vendor(mac, oui_db, online=False):
    prefix = mac.replace(":", "")[:6].upper()
    # 1. Local primary DB (nmap, 52k entries) — instant
    # 2. Local supplement (oui_supplement.txt, ~2.9k entries) — instant
    # 3. Randomized MAC check — skip online for locally-administered
    # 4. Disk cache (oui_cache.json) — instant for previously looked-up
    # 5. Online API (maclookup.app) — ~1-3s, cached on success
```

### Supplement Database

`oui_supplement.txt` adds ~2,900 entries covering:
- Chinese phone brands: Xiaomi, Redmi, POCO, Huawei, Honor, OPPO, Realme, OnePlus, vivo, iQOO, Meizu, ZTE, Nubia, Lenovo, Motorola, TCL, Hisense, Coolpad, Smartisan, Black Shark, Gionee
- IoT / Smart Home: Xiaomi IoT, Mi Home
- Drones: DJI
- Networking: TP-Link, ASUS, Acer

Format matches nmap's `nmap-mac-prefixes`: `AABBCC VendorName`

### Online API Fallback

When a globally-unique MAC is not found locally, `get_vendor(mac, db, online=True)` queries `https://api.maclookup.app/v2/macs/{prefix}000000`. Successful results are cached to `oui_cache.json` for persistence across restarts.

---

## Key Design Decisions

### 1. Network detection: `route get default` + `ifconfig`

**Chosen over**: scapy's `conf.route` (returns integer-encoded routes, hard to parse correctly) and `netifaces` (extra dependency).

**Approach**: Use macOS-native `route -n get default` to find the default interface, then `ifconfig <iface>` to extract `inet` and `netmask` fields. Fall back to `/24` guess from socket-detected IP.

### 2. OUI database: nmap's `nmap-mac-prefixes` + supplement + online

**Chosen over**: Downloading IEEE's OUI CSV (timeout issues), or embedding a single database.

**Trade-off**: Adds nmap as a dependency, but the database is pre-installed and auto-updated by Homebrew. Supplement file fills gaps for Chinese brands. Online API provides a catch-all for genuinely unknown prefixes. The three-layer approach optimizes for speed (local) while maximizing coverage (online).

### 3. Continuous spoofing vs. one-shot

**Chosen**: Continuous background thread sending every 1 second.

**Reason**: ARP caches have TTLs (typically 30–300 seconds). If we send only once, the cache eventually expires and reverts. Continuous sending ensures the poisoning persists. 1 Hz is frequent enough to beat any cache timeout without causing noticeable network load.

### 4. Gateway detection: scapy routing table

**Chosen over**: Hardcoding `.1` or asking the user.

**Approach**: scapy's `conf.route.routes` contains the system routing table. The entry with `net=0, mask=0` is the default route — extract the gateway from `route[2]`. This is cross-platform (works on Linux too) and always correct.

### 5. Streamlit over other UI frameworks

**Chosen over**: Flask + custom frontend, Electron, or native macOS app.

**Reason**: Zero frontend code needed (pure Python), built-in session state management, automatic hot-reload during development, and one-line launch. Trade-off: requires `sudo streamlit run` (unusual but functional).

### 6. HTML table over st.table/st.dataframe

**Chosen over**: Streamlit's native table components.

**Reason**: `st.table` and `st.dataframe` internally depend on pyarrow → numpy, which had a version compatibility issue in this environment. Raw HTML via `st.markdown` avoids the entire dependency chain and provides full control over styling (alternating colors, per-section themes).

---

## Bugs Encountered & Solutions

### Bug 1: OUI format mismatch (2026-05-06)

**Symptom**: All vendor lookups returned "Unknown" despite 52,085 entries loaded.

**Root cause**: nmap's `nmap-mac-prefixes` uses delimiter-free hex (`AABBCC`), but scapy returns MACs with colons (`AA:BB:CC:DD:EE:FF`). The original code extracted the first 8 characters of the MAC string `"AA:BB:CC"` and tried to match against bare `"AABBCC"`.

**Fix**: Strip colons before extracting the prefix:
```python
prefix = mac.replace(":", "")[:6].upper()
```

### Bug 2: scapy route table — integer-encoded values (2026-05-06)

**Symptom**: `get_local_network()` initially tried to parse scapy's `conf.route` by iterating and matching string values, but the table contains integer-encoded network addresses (e.g., `3232238080` instead of `192.168.10.0`).

**Fix**: Abandoned scapy route parsing for network detection. Used macOS system commands (`route -n get default` + `ifconfig`) instead. Only kept scapy's route table for gateway detection, where the string-encoded gateway IP is directly accessible.

### Bug 3: sudo permission loop during testing (2026-05-06)

**Symptom**: Could not run scanner/spoofer tests from the sandbox because `sudo` requires a TTY for password input.

**Fix**: Established a workflow where:
1. Code is written and syntax-checked in the sandbox
2. Actual `sudo python3` execution is done by the user in their terminal
3. Debugging data (OUI verification, network detection, route inspection) is tested non-interactively

### Bug 4: pyarrow/numpy compatibility (2026-05-06)

**Symptom**: `ImportError: numpy.core.multiarray failed to import` when Streamlit tried to render `st.table` or `st.dataframe`.

**Root cause**: Installed numpy version was incompatible with pyarrow (Streamlit's internal data rendering dependency).

**Fix**: Replaced `st.table`/`st.dataframe` with raw HTML table rendering via `st.markdown(unsafe_allow_html=True)`. This completely bypasses the pyarrow/numpy dependency chain and provides full control over table styling.

### Bug 5: Streamlit session state — thread loss on rerun (2026-05-06)

**Symptom**: Background ARP spoofing threads would die after page refresh or widget interaction.

**Root cause**: Streamlit re-executes the entire script on every interaction. Local variables are recreated; threads created in previous runs are orphaned.

**Fix**: Store `ArpSpoofer` instances in `st.session_state` (which survives reruns). Add `_cleanup_dead_spoofers()` to detect and remove dead threads on each rerun.

---

## Project Structure

```
WIFIkiller/
├── main.py                 # CLI: scan → select → spoof → control
├── gui.py                  # Streamlit Web UI (Phase 5)
├── run.sh                  # One-click dependency check & launch (--gui flag)
├── requirements.txt        # scapy>=2.5.0, streamlit>=1.28.0
├── README.md               # User-facing guide (English)
├── README-zh.md            # User-facing guide (Chinese)
├── DEVELOPMENT_LOG.md      # This file (English)
├── DEVELOPMENT_LOG-zh.md   # Developer handover (Chinese)
├── CLAUDE.md               # Claude Code project instructions
├── oui_supplement.txt      # Supplementary OUI database (~2,900 entries)
├── oui_cache.json          # Online API lookup cache (auto-generated)
├── core/
│   ├── __init__.py
│   ├── scanner.py           # ARP scan + 3-layer vendor resolution + randomized MAC detection
│   └── spoofing.py          # ArpSpoofer class (thread + restore + context manager)
└── utils/
    ├── __init__.py
    └── sys_config.py        # sysctl net.inet.ip.forwarding wrapper
```

---

## Testing

| Test | Method | Status |
|------|--------|--------|
| Permission gate (no sudo) | `python3 main.py` → shows help | ✅ |
| Network detection | `get_local_network()` → CIDR | ✅ |
| OUI loading (nmap) | `load_oui_db()` → 52,091 entries | ✅ |
| OUI loading (merged) | `load_oui_db()` → 54,067 entries | ✅ |
| Vendor lookup (local) | `get_vendor("F4:0F:24:...", db)` → vendor | ✅ |
| Vendor lookup (online) | `get_vendor("00:11:22:...", db, online=True)` → API result | ✅ |
| Randomized MAC detection | `52:F9:2C:...` → "Randomized" | ✅ |
| Online API cache | `oui_cache.json` persisted across calls | ✅ |
| sysctl read | `is_forwarding_enabled()` → False (safe default) | ✅ |
| ARP scan | `sudo python3 core/scanner.py` → device table | User-tested |
| ARP spoof (CLI) | `sudo python3 main.py` → kill/unkill loop | User-tested |
| Ctrl+C restore (CLI) | Press Ctrl+C during spoofing → ARP restored | User-tested |
| Web UI scan | `bash run.sh --gui` → device table rendered | ✅ |
| Web UI kill/restore | Button click → spoofer start/stop | User-tested |
| Web UI Emergency Stop | Button click → all spoofers restored | User-tested |
| Real/randomized split | Two tables with distinct styling | ✅ |
| Browser auto-open | `bash run.sh --gui` → opens localhost:8501 | ✅ |

---

## Future Improvements

1. **Target bandwidth throttling**: Instead of binary kill/unkill, add rate limiting using macOS's `pf` (packet filter) or `dnctl` for graduated control.

2. **Packet capture & inspection**: Add a mode that logs intercepted traffic (HTTP hosts, DNS queries) for analysis — useful for IoT device profiling.

3. **Cross-platform support**: Replace macOS-specific `sysctl` and `route` calls with abstractions for Linux (`/proc/sys/net/ipv4/ip_forward`, `ip route`).

4. **ARP watch mode**: Passive monitoring mode that detects ARP spoofing attacks from other devices on the network.

5. **systemd/launchd daemon**: Run as a background service with a REST API for remote control.

6. **Graceful degradation without nmap**: Fall back to an embedded minimal OUI database (top 100 vendors) when nmap is not installed, so the scanner still shows useful vendor info.

7. **Local OUI DB auto-update**: Periodically fetch and merge the latest IEEE OUI registrations to keep the local database current.

8. **Traffic graph in Web UI**: Real-time bandwidth visualization per intercepted target using Streamlit charts.
