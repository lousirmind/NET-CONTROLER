# VibeNet Control

A macOS network management tool that uses ARP Spoofing to intercept and control local network devices. Features both a terminal CLI and a browser-based Web UI. Intended for **educational and network testing purposes only**.

## Features

- **Network Scanner** — Discover all active devices on the local network with IP, MAC address, and vendor name (uses nmap OUI database + supplementary Chinese brand database + online API fallback).
- **Real vs. Randomized Detection** — Automatically distinguishes real connected devices from nearby devices using randomized MAC addresses (iOS/Android privacy feature).
- **ARP Spoofing** — Intercept traffic between a target device and the gateway (Man-in-the-Middle).
- **Kill Switch** — Drop the target's internet access with a single keystroke or button click.
- **Multi-Target Control (GUI)** — Manage multiple targets simultaneously from the Web UI.
- **Emergency Stop** — One-click restoration of all active spoofing sessions and system forwarding settings.
- **Safe Recovery** — Ctrl+C (CLI) or Emergency Stop button (GUI) always triggers clean ARP restoration.

## Requirements

| Component | Version | Purpose |
|-----------|---------|---------|
| macOS | Monterey+ | Host platform |
| Python | 3.9+ | Runtime |
| scapy | 2.5+ | ARP packet crafting & sending |
| streamlit | 1.28+ | Web UI framework (GUI mode only) |
| nmap | 7+ | MAC vendor database (OUI) |
| sudo | — | Root privileges for raw socket access |

## Installation

### 1. Clone or download the project

```bash
cd WIFIkiller
```

### 2. Install dependencies

**Option A — one-click script (CLI mode):**
```bash
bash run.sh
```

**Option B — one-click script (GUI mode):**
```bash
bash run.sh --gui
```

**Option C — manual install:**
```bash
pip3 install scapy streamlit
brew install nmap
```

## Usage

### Web UI (Recommended)

```bash
bash run.sh --gui
```

Your browser opens automatically at `http://localhost:8501`.

1. Click **Scan Network** in the left sidebar.
2. View devices split into two tables:
   - **Connected Devices** (real MAC) — green rows, full vendor info, actionable.
   - **Nearby Scanning** (randomized MAC) — blue rows, gray text, read-only.
3. Each real device has a **Kill** button in the Device Control section below.
4. Killed devices show a **Restore** button to bring them back online.
5. Use **Emergency Stop** at the bottom to restore everything at once.

### CLI (Terminal)

```bash
sudo python3 main.py
```

| Command | Action |
|---------|--------|
| `k` | **Kill** — Cut the target's internet (IP forwarding off) |
| `u` | **Unkill** — Restore the target's internet (IP forwarding on) |
| `q` | **Quit** — Stop spoofing, restore ARP, and exit |
| `Ctrl+C` | **Emergency stop** — Immediately restore everything and exit |

### Standalone Scanner

```bash
sudo python3 core/scanner.py
```

## How It Works

```
                    ┌──────────────┐
    target ──ARP──> │  This Mac    │ ──ARP──>  gateway
                    │  (forwarder) │
                    └──────────────┘
```

1. **ARP Poisoning**: The tool continuously sends fake ARP replies telling the target "I am the gateway" and telling the gateway "I am the target". Both devices update their ARP caches and send traffic to the wrong MAC address — ours.

2. **IP Forwarding**: With `net.inet.ip.forwarding=1`, the Mac routes intercepted packets between its interfaces, so the target experiences normal internet access (but all traffic passes through us).

3. **Kill Switch**: Setting `net.inet.ip.forwarding=0` causes the Mac to **silently drop** all forwarded packets. The target's traffic arrives at our machine but goes nowhere.

4. **Recovery**: On exit, genuine ARP replies (with correct MAC mappings) are sent 3 times to both the target and gateway, ensuring their ARP caches return to normal immediately.

## Vendor Database

The tool uses three layers for MAC vendor identification:

| Layer | Source | Entries | Speed |
|-------|--------|---------|-------|
| 1. Local primary | nmap `nmap-mac-prefixes` | 52,091 | Instant |
| 2. Local supplement | `oui_supplement.txt` | ~2,900 | Instant |
| 3. Online fallback | maclookup.app API | — | ~1-3s (cached) |

The supplement database adds extensive coverage for Chinese phone brands (Xiaomi, Huawei, OPPO, vivo, OnePlus, Realme, Meizu, ZTE, Nubia, Lenovo, TCL, Hisense, etc.) as well as IoT devices, drones (DJI), and networking equipment.

Randomized MAC addresses (used by iOS/Android for Wi-Fi privacy scanning) are automatically detected and labeled — these cannot be resolved to a vendor by design.

## Safety Notes

- This tool sends raw ARP packets that modify the ARP caches of other devices on your network. **Only use it on networks you own or have explicit permission to test.**
- The `finally` block in `main.py` and the Emergency Stop button in the GUI guarantee that restoration packets are sent on any exit path.
- IP forwarding is **always disabled on exit**, restoring normal system behavior.
- Randomized MAC devices cannot be targeted — their addresses are ephemeral and change frequently.

## License

Educational and testing use only. Not for malicious purposes.
