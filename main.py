#!/usr/bin/env python3
"""
VibeNet Control  -  CLI Entry Point
====================================
1. Scan the local network for all active devices.
2. Pick a target by number.
3. Intercept its traffic via ARP spoofing.
4. Kill / unkill its internet access on demand.
5. Ctrl+C always triggers a clean network restore.
"""

import os
import socket
import struct
import sys
import threading

from scapy.all import conf

from core.scanner import get_local_network, load_oui_db, get_vendor, scan_network
from core.spoofing import ArpSpoofer


def _pick_target(devices, oui_db):
    """Print a numbered device list and let the user choose one."""
    print(f"\n{'#':<4} {'IP':<16} {'MAC':<18} Vendor")
    print("-" * 66)
    for i, d in enumerate(devices, 1):
        vendor = get_vendor(d["mac"], oui_db)
        print(f"{i:<4} {d['ip']:<16} {d['mac']:<18} {vendor[:32]}")
    print("-" * 66)

    while True:
        try:
            choice = input(f"\nChoose target [1-{len(devices)} / q=quit]: ").strip()
            if choice.lower() == "q":
                sys.exit(0)
            idx = int(choice) - 1
            if 0 <= idx < len(devices):
                return devices[idx]
            print(f"  => Enter a number between 1 and {len(devices)}")
        except ValueError:
            print(f"  => Enter a number between 1 and {len(devices)}")
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)


def _get_gateway():
    """Return the default gateway IP from the system routing table."""
    for route in conf.route.routes:
        net, mask, gw, iface = route[:4]
        # Default route: network == 0, mask == 0, not loopback
        if net == 0 and mask == 0 and iface != "lo0":
            return gw
    return None


def _format_speed(kbps):
    """Format a speed value in human-readable form."""
    if kbps < 1:
        return "0.0 KB/s"
    elif kbps < 1024:
        return f"{kbps:.1f} KB/s"
    else:
        return f"{kbps / 1024:.1f} MB/s"


def _ip_in_subnet(ip, cidr):
    """Check if *ip* falls within the given *cidr* network."""
    net_str, bits_str = cidr.split("/")
    bits = int(bits_str)
    ip_int = struct.unpack("!I", socket.inet_aton(ip))[0]
    net_int = struct.unpack("!I", socket.inet_aton(net_str))[0]
    mask = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF
    return (ip_int & mask) == (net_int & mask)


def _cidr_range_str(cidr):
    """Return a human-readable IP range string for a CIDR, e.g. '192.168.10.0 - 192.168.11.255'."""
    net_str, bits_str = cidr.split("/")
    bits = int(bits_str)
    net_int = struct.unpack("!I", socket.inet_aton(net_str))[0]
    mask = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF
    broadcast = net_int | (~mask & 0xFFFFFFFF)
    first = socket.inet_ntoa(struct.pack("!I", net_int))
    last = socket.inet_ntoa(struct.pack("!I", broadcast))
    return f"{first} - {last}"


def _display_stats_loop(spoofer, stop_event):
    """Daemon thread target: prints traffic stats every second."""
    first = True
    while not stop_event.is_set():
        if not first:
            up_kbps, down_kbps = spoofer.get_traffic_stats()
            up_str = _format_speed(up_kbps)
            down_str = _format_speed(down_kbps)
            print(f"\r  [↓ {down_str}  ↑ {up_str}]", end="", flush=True)
        first = False
        stop_event.wait(1.0)
    print("\r" + " " * 50 + "\r", end="", flush=True)


def main():
    if os.geteuid() != 0:
        print("=" * 56)
        print("  This tool needs root privileges (raw ARP packets).")
        print("  Please re-run with:  sudo python3 main.py")
        print("=" * 56)
        sys.exit(1)

    spoofer = None
    stats_stop = threading.Event()
    stats_thread = None

    try:
        # ---- header ----
        print()
        print("=" * 56)
        print("  VibeNet Control")
        print("=" * 56)

        # ---- scan ----
        network = get_local_network()
        print(f"\n[*] Network: {network}  ({_cidr_range_str(network)})")

        oui_db = load_oui_db()
        print(f"[*] OUI DB:   {len(oui_db):,} vendors")

        devices = scan_network(network)
        if not devices:
            print("[!] No devices responded.")
            sys.exit(1)
        devices.sort(key=lambda d: tuple(int(x) for x in d["ip"].split(".")))

        gateway_ip = _get_gateway()
        print(f"[*] Gateway:  {gateway_ip}")

        # ---- pick target ----
        target = _pick_target(devices, oui_db)
        print(f"\n[*] Target:  {target['ip']}  ({target['mac']})")
        print(f"[*] Gateway: {gateway_ip}")

        # Validate target is in the local subnet (should always be true since
        # the ARP scan found it, but warn if something looks off)
        if not _ip_in_subnet(target["ip"], network):
            print(f"[!] WARNING: {target['ip']} is outside your subnet ({network}).")
            print(f"    ARP spoofing may fail if the target uses a different gateway.")
            answer = input("    Continue anyway? [y/N]: ").strip().lower()
            if answer != "y":
                print("[*] Aborted.")
                sys.exit(0)

        # ---- start spoofing ----
        print()
        spoofer = ArpSpoofer(target["ip"], gateway_ip)
        spoofer.start()

        # Start the real-time speed display
        stats_thread = threading.Thread(
            target=_display_stats_loop,
            args=(spoofer, stats_stop),
            daemon=True,
        )
        stats_thread.start()

        print()
        print("=" * 56)
        print(f"  {target['ip']} is now intercepted.")
        print(f"  [k] kill  |  [u] unkill  |  [q] quit")
        print(f"  Ctrl+C to immediately restore and exit.")
        print("=" * 56)

        # ---- interactive loop ----
        while True:
            try:
                cmd = input("\n> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break

            if cmd == "k":
                spoofer.kill()
            elif cmd == "u":
                spoofer.unkill()
            elif cmd == "q":
                break
            elif cmd == "":
                continue
            else:
                print("  [k] kill  [u] unkill  [q] quit")

    except KeyboardInterrupt:
        print("\n\n[!] Ctrl+C — restoring network...")

    finally:
        stats_stop.set()
        if stats_thread:
            stats_thread.join(timeout=2)

        if spoofer is not None:
            spoofer.stop(restore=True)

    print("[*] Goodbye.\n")


if __name__ == "__main__":
    main()
