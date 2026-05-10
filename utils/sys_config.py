#!/usr/bin/env python3
"""
Manage macOS network sysctl knobs needed for ARP spoofing.

net.inet.ip.forwarding = 1   ->  the Mac routes packets between interfaces
net.inet.ip.forwarding = 0   ->  the Mac drops forwarded packets (kill-switch)
"""

import subprocess

SYSCTL_KEY = "net.inet.ip.forwarding"


def enable_ip_forwarding():
    """Turn on IP forwarding so intercepted packets are routed onward."""
    subprocess.run(
        ["sysctl", "-w", f"{SYSCTL_KEY}=1"],
        check=True, capture_output=True, text=True,
    )


def disable_ip_forwarding():
    """
    Turn off IP forwarding.
    When forwarding is disabled, packets from the poisoned target are
    silently dropped by this machine — the "kill switch" effect.
    """
    subprocess.run(
        ["sysctl", "-w", f"{SYSCTL_KEY}=0"],
        check=True, capture_output=True, text=True,
    )


def is_forwarding_enabled():
    """Return True if IP forwarding is currently active."""
    result = subprocess.run(
        ["sysctl", "-n", SYSCTL_KEY],
        capture_output=True, text=True,
    )
    return result.stdout.strip() == "1"
