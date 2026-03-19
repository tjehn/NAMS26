#!/usr/bin/env python3
"""
Module   : NAMS26 Project Utility
File     : modules/02_eigrp_netmiko/utils/ping_hosts.py
Purpose  : Ping all lab hosts and report reachability.
           Hosts are resolved via the lab DNS server (192.168.1.12, domain: .lab).
           No hardcoded IPs — all resolution is handled by the OS resolver.

Usage:
    python ping_hosts.py
    python ping_hosts.py --host R1
    python ping_hosts.py --host r1.lab
"""

import subprocess
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Lab Host Inventory (DNS names — resolved via 192.168.1.12) ───────────────
HOSTS = {
    "R1": "r1.lab",
    "R2": "r2.lab",
    "R3": "r3.lab",
    "R4": "r4.lab",
    "R5": "r5.lab",
    "R6": "r6.lab",
}

# ─── ANSI Colors ───────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def ping(host: str, dns_name: str, count: int = 3) -> dict:
    """Ping a single host by DNS name and return result dict."""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", dns_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        reachable = result.returncode == 0

        # Parse packet loss from output
        output = result.stdout.decode()
        loss_line = [l for l in output.splitlines() if "packet loss" in l]
        loss = loss_line[0].split(",")[2].strip() if loss_line else "unknown"

        return {"host": host, "dns_name": dns_name, "reachable": reachable, "loss": loss}

    except Exception as e:
        return {"host": host, "dns_name": dns_name, "reachable": False, "loss": f"error: {e}"}


def print_result(r: dict) -> None:
    status  = f"{GREEN}PASS{RESET}" if r["reachable"] else f"{RED}FAIL{RESET}"
    loss    = r["loss"]
    print(f"  {BOLD}{r['host']:6}{RESET}  {r['dns_name']:16}  {status}   {loss}")


def main():
    parser = argparse.ArgumentParser(description="Ping NAMS26 lab hosts.")
    parser.add_argument("--host", help="Ping a single host by name (R1) or DNS name (r1.lab).")
    parser.add_argument("--count", type=int, default=3, help="Ping count (default: 3).")
    args = parser.parse_args()

    print(f"\n{CYAN}{BOLD}{'─'*55}")
    print("  NAMS26 — Ping Hosts Utility")
    print(f"{'─'*55}{RESET}\n")
    print(f"  {'HOST':<8}{'DNS NAME':<18}{'STATUS':<10}PACKET LOSS")
    print(f"  {'─'*50}")

    if args.host:
        # Single host mode — find by DNS name or hostname key
        target = {k: v for k, v in HOSTS.items()
                  if v == args.host or k == args.host.upper()}
        if not target:
            target = {"CUSTOM": args.host}
        hosts_to_ping = target
    else:
        hosts_to_ping = HOSTS

    results = []
    with ThreadPoolExecutor(max_workers=len(hosts_to_ping)) as executor:
        futures = {
            executor.submit(ping, host, dns_name, args.count): host
            for host, dns_name in hosts_to_ping.items()
        }
        for future in as_completed(futures):
            results.append(future.result())

    # Sort by hostname for consistent output
    results.sort(key=lambda r: r["host"])
    for r in results:
        print_result(r)

    passed = sum(1 for r in results if r["reachable"])
    total  = len(results)
    color  = GREEN if passed == total else (YELLOW if passed > 0 else RED)
    print(f"\n  {color}{BOLD}Result: {passed}/{total} hosts reachable{RESET}\n")


if __name__ == "__main__":
    main()
