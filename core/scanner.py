#!/usr/bin/env python3
"""
ARP-based LAN scanner. Discovers all active devices on the local network
and resolves MAC addresses to vendor names using the nmap OUI database.
"""

import json
import os
import re
import socket
import struct
import subprocess
import sys
import urllib.request

from scapy.all import ARP, Ether, srp


def _get_data_dir():
    """返回数据文件根目录：PyInstaller bundle 内为 sys._MEIPASS，否则为项目根。"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(__file__))


def _get_user_data_dir():
    """返回用户可写数据目录（~/.vibenet/），自动创建。"""
    path = os.path.expanduser("~/.vibenet")
    os.makedirs(path, exist_ok=True)
    return path


def _resolve_oui_db_path():
    """解析 OUI 数据库路径：优先 bundle 内，其次 /opt/homebrew，最后 /usr/local。"""
    candidates = [
        os.path.join(_get_data_dir(), "nmap-mac-prefixes"),
        "/opt/homebrew/share/nmap/nmap-mac-prefixes",
        "/usr/local/share/nmap/nmap-mac-prefixes",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]  # 返回第一个作为默认值（即使不存在）


OUI_DB_PATH = None  # 延迟解析，在 load_oui_db() 中调用 _resolve_oui_db_path()
_SUPPLEMENT_PATH = os.path.join(_get_data_dir(), "oui_supplement.txt")
_CACHE_PATH = os.path.join(_get_user_data_dir(), "oui_cache.json")


def _get_iface():
    """Find the default network interface via `route get default`."""
    try:
        out = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, text=True,
        ).stdout
        m = re.search(r"interface:\s+(\S+)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def get_local_network():
    """
    Return the local network in CIDR notation (e.g. '192.168.1.0/24').
    Uses the default interface's IP and netmask.
    """
    iface = _get_iface()
    if iface:
        try:
            out = subprocess.run(
                ["ifconfig", iface], capture_output=True, text=True
            ).stdout
            ip_m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
            mask_m = re.search(r"netmask\s+(0x[0-9a-f]+)", out)
            if ip_m and mask_m:
                ip = ip_m.group(1)
                mask_int = int(mask_m.group(1), 16)
                cidr = bin(mask_int).count("1")
                ip_int = struct.unpack("!I", socket.inet_aton(ip))[0]
                net_int = ip_int & mask_int
                net = socket.inet_ntoa(struct.pack("!I", net_int))
                return f"{net}/{cidr}"
        except Exception:
            pass

    # Fallback: guess a /24 from whichever local IP we can reach out with
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        parts = local_ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        return None


def load_oui_db(path=None):
    """
    Parse OUI databases into a dict.
    Loads the primary nmap database first, then overlays the supplementary
    database (supplement entries take precedence for newer/corrected data).

    Key:  bare hex prefix (e.g. 'AABBCC')
    Value: vendor name string
    """
    if path is None:
        path = _resolve_oui_db_path()

    def _parse_file(filepath, target):
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    target[parts[0].upper()] = parts[1]

    oui = {}
    _parse_file(path, oui)
    _parse_file(_SUPPLEMENT_PATH, oui)  # supplement overwrites primary
    return oui


def _load_cache():
    """Load the offline vendor cache (MAC prefix -> vendor)."""
    if os.path.exists(_CACHE_PATH):
        try:
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache):
    """Persist the vendor cache to disk."""
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _lookup_online(prefix):
    """Query maclookup.app API for a single MAC prefix. Returns vendor name or None."""
    url = f"https://api.maclookup.app/v2/macs/{prefix}000000"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VibeNetControl/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            if data.get("success") and data.get("found"):
                company = data.get("company", "").strip()
                if company:
                    return company
    except Exception:
        pass
    return None


def get_vendor(mac, oui_db, online=False):
    """
    Look up the vendor name for a MAC address.

    1. Check local OUI database (fast)
    2. Check disk cache (previous online lookups)
    3. If *online* is True, query maclookup.app API (slow, ~1-3s)
    4. Fall back to "Randomized" for locally-administered MACs
    """
    if not mac or mac == "UNKNOWN":
        return "Unknown"

    # Detect MAC randomization: second bit of first byte = 1 means
    # locally administered (randomized, will never appear in any OUI DB)
    try:
        first_byte = int(mac.replace(":", "")[:2], 16)
        is_local = (first_byte & 0x02) != 0
    except ValueError:
        return "Unknown"

    prefix = mac.replace(":", "")[:6].upper()

    # 1. Local database
    vendor = oui_db.get(prefix)
    if vendor:
        return vendor

    # 2. Randomized MAC — don't waste time with online lookup
    if is_local:
        return "Randomized"

    # 3. Disk cache
    cache = _load_cache()
    vendor = cache.get(prefix)
    if vendor:
        return vendor

    # 4. Online lookup (only when requested)
    if online:
        vendor = _lookup_online(prefix)
        if vendor:
            cache[prefix] = vendor
            _save_cache(cache)
            return vendor

    return "Unknown"


def scan_network(network, timeout=3):
    """
    Send ARP requests to every IP in *network* and collect responses.

    Returns a list of dicts: [{"ip": ..., "mac": ...}, ...]
    """
    arp_req = ARP(pdst=network)
    eth_broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = eth_broadcast / arp_req

    answered, _ = srp(packet, timeout=timeout, verbose=0)

    devices = []
    for _, recv in answered:
        devices.append({"ip": recv.psrc, "mac": recv.hwsrc.upper()})
    return devices


def _ip_sort_key(ip):
    """Convert '192.168.1.5' to a tuple of ints for natural sorting."""
    return tuple(int(octet) for octet in ip.split("."))


def print_table(devices, oui_db):
    """Pretty-print scan results as an aligned table."""
    if not devices:
        print("\n[!] No devices responded on this network.\n")
        return

    ip_w = max(max(len(d["ip"]) for d in devices), 11)
    mac_w = max(max(len(d["mac"]) for d in devices), 17)
    vendor_w = 28

    sep = f"+{'=' * (ip_w + 2)}+{'=' * (mac_w + 2)}+{'=' * (vendor_w + 2)}+"
    row_fmt = f"| {{:<{ip_w}}} | {{:<{mac_w}}} | {{:<{vendor_w}}} |"

    print(f"\n{sep}")
    print(row_fmt.format("IP", "MAC", "Vendor"))
    print(sep)

    for d in sorted(devices, key=lambda x: _ip_sort_key(x["ip"])):
        vendor = get_vendor(d["mac"], oui_db)
        print(row_fmt.format(d["ip"], d["mac"], vendor[:vendor_w]))

    print(sep)
    print(f"  {len(devices)} device(s) found\n")


def main():
    if os.geteuid() != 0:
        print("=" * 56)
        print("  This tool needs root privileges to send raw ARP packets.")
        print("  Please re-run with:  sudo python3 core/scanner.py")
        print("=" * 56)
        sys.exit(1)

    print()
    print("=" * 56)
    print("  VibeNet Scanner  -  Local Network Discovery")
    print("=" * 56)

    network = get_local_network()
    if not network:
        print("[!] Could not detect local network. Exiting.")
        sys.exit(1)
    print(f"[*] Detected network:  {network}")

    oui_db = load_oui_db()
    if oui_db:
        print(f"[*] OUI database:      {len(oui_db):,} vendor entries loaded")
    else:
        print("[!] OUI database missing — vendor column will show 'Unknown'")

    devices = scan_network(network)
    print_table(devices, oui_db)


if __name__ == "__main__":
    main()
