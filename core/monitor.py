#!/usr/bin/env python3
"""
Traffic Monitor (core/monitor.py)

Captures and measures network traffic for a specific target device
while ARP spoofing is active. Uses scapy's AsyncSniffer (store=False)
to avoid memory accumulation and for clean BPF socket lifecycle on macOS.

Usage::

    monitor = TrafficMonitor("192.168.1.10")
    monitor.start()
    # ... spoofing active ...
    up_kbps, down_kbps = monitor.get_stats()
    monitor.stop()
"""

import threading
import time

from scapy.all import AsyncSniffer, IP


class TrafficMonitor:
    """Sniff traffic for a single target IP using a background AsyncSniffer.

    Accumulates byte counts per direction (upload / download) and
    provides per-second rate calculation via ``get_stats()``.
    """

    def __init__(self, target_ip):
        self.target_ip = target_ip

        self._sniffer = None
        self._lock = threading.Lock()
        self._active = threading.Event()
        self._active.set()  # counting is on by default

        # Cumulative byte counters
        self._upload_bytes = 0
        self._download_bytes = 0

        # Snapshot for delta calculation
        self._last_upload = 0
        self._last_download = 0
        self._last_time = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Begin capturing traffic in a background thread."""
        if self._sniffer and self._sniffer.running:
            return

        filt = f"host {self.target_ip} and not arp"
        self._sniffer = AsyncSniffer(
            filter=filt,
            prn=self._process_packet,
            store=False,
        )
        self._sniffer.start()

    def stop(self):
        """Stop the underlying AsyncSniffer."""
        if self._sniffer:
            self._sniffer.stop()
            self._sniffer = None

    def set_active(self, enabled):
        """Enable or disable byte counting. When disabled, no packets are
        accumulated and get_stats() returns (0.0, 0.0). Use this to
        reflect kill-switch state."""
        if enabled:
            self._active.set()
        else:
            self._active.clear()

    def get_stats(self):
        """Return (upload_kbps, download_kbps) — rate since last call.

        Each call computes the delta from the previous call, so the
        returned value reflects the average rate over the interval.
        When the monitor is inactive (kill-switch), returns (0.0, 0.0)
        and resets the snapshot to avoid stale bursts on restore.
        """
        if not self._active.is_set():
            # Reset snapshot so restore doesn't show a stale spike
            with self._lock:
                self._last_upload = self._upload_bytes
                self._last_download = self._download_bytes
                self._last_time = time.time()
            return 0.0, 0.0

        with self._lock:
            now = time.time()
            elapsed = now - self._last_time
            up_delta = self._upload_bytes - self._last_upload
            down_delta = self._download_bytes - self._last_download

            self._last_upload = self._upload_bytes
            self._last_download = self._download_bytes
            self._last_time = now

        if elapsed <= 0:
            return 0.0, 0.0

        up_kbps = (up_delta / elapsed) / 1024.0
        down_kbps = (down_delta / elapsed) / 1024.0
        return up_kbps, down_kbps

    @property
    def is_running(self):
        return self._sniffer is not None and self._sniffer.running

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_packet(self, pkt):
        """Classify a single packet and add its length to the right counter."""
        if not self._active.is_set():
            return
        if not IP in pkt:
            return

        length = len(pkt)
        with self._lock:
            if pkt[IP].src == self.target_ip:
                self._upload_bytes += length
            elif pkt[IP].dst == self.target_ip:
                self._download_bytes += length
