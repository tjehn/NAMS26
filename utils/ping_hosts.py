#!/usr/bin/env python3
"""
File     : utils/ping_hosts.py
Purpose  : Ping all lab devices and report ICMP reachability.
           Hosts are resolved via the lab DNS server (192.168.1.12, domain: .lab).
           No hardcoded IPs — all resolution is handled by the OS resolver.

           Reads device list from utils/hosts.yaml — no module dependency.
           Covers R1–R12, COSW-01, COSW-02, OOB-SW01.

Usage:
    python utils/ping_hosts.py
    python utils/ping_hosts.py --host R1
    python utils/ping_hosts.py --host R1 R2 COSW-01
    python utils/ping_hosts.py --count 5
"""

import argparse
import os
import platform
import re
import subprocess
import sys
import time
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
YAML_FILE    = os.path.join(SCRIPT_DIR, "hosts.yaml")

# =============================================================================
# ANSI Colors
# =============================================================================
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# Limit concurrent pings to avoid saturating the lab DNS server with
# simultaneous resolution requests.
# Current: 5   Range: 1 (fully sequential) – 15 (fully parallel)
MAX_WORKERS = 5

# Stagger between thread submissions in seconds — gives the DNS resolver
# a brief gap between bursts of lookups.
# Current: 0.3 s   Range: 0.1 – 1.0 s
LAUNCH_STAGGER = 0.3


# =============================================================================
# PING
# =============================================================================

def ping(host_name: str, dns_name: str, count: int = 3) -> dict:
    """
    Ping a single host by DNS name and return a result dict.

    Args:
        host_name : Display label (e.g. 'R1').
        dns_name  : Hostname to resolve and ping (e.g. 'r1.lab').
        count     : Number of ICMP echo-request packets to send.
                    Default: 3   Min: 1   Practical max: 10
    """
    try:
        if platform.system() == "Windows":
            # Windows ping: -n count, -w timeout_ms (no -c/-W flags)
            cmd = ["ping", "-n", str(count), "-w", "2000", dns_name]
        else:
            # -c count : number of echo requests to send
            # -W 2     : wait up to 2 seconds per reply before giving up.
            #            Current: 2 s   Range: 1 – 5 s
            cmd = ["ping", "-c", str(count), "-W", "2", dns_name]

        result    = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        reachable = result.returncode == 0
        output    = result.stdout.decode(errors="replace")

        if platform.system() == "Windows":
            # Windows loss line example:
            #   "    Packets: Sent = 3, Received = 3, Lost = 0 (0% loss),"
            loss = "unknown"
            for line in output.splitlines():
                if "Lost" in line:
                    m = re.search(r'Lost\s*=\s*\d+\s*\((\d+%\s*loss)\)', line, re.IGNORECASE)
                    if m:
                        loss = m.group(1)
                        break
        else:
            loss_line = [l for l in output.splitlines() if "packet loss" in l]
            loss      = loss_line[0].split(",")[2].strip() if loss_line else "unknown"

        return {
            "host":      host_name,
            "dns_name":  dns_name,
            "reachable": reachable,
            "loss":      loss,
        }

    except Exception as exc:
        return {
            "host":      host_name,
            "dns_name":  dns_name,
            "reachable": False,
            "loss":      f"error: {exc}",
        }


def print_result(r: dict) -> None:
    status = f"{GREEN}PASS{RESET}" if r["reachable"] else f"{RED}FAIL{RESET}"
    print(f"  {BOLD}{r['host']:<12}{RESET}  {r['dns_name']:<18}  {status}   {r['loss']}")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="NAMS26 Utility — Ping all lab devices."
    )
    parser.add_argument(
        "--host",
        nargs="+",
        metavar="NAME",
        help="Ping specific hosts only (e.g. --host R1 R2 COSW-01).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Ping count per host (default: 3).",
    )
    args = parser.parse_args()

    # Load hosts.yaml
    if not os.path.isfile(YAML_FILE):
        print(f"[ERROR] hosts.yaml not found: {YAML_FILE}")
        sys.exit(1)

    with open(YAML_FILE, "r") as fh:
        data = yaml.safe_load(fh)

    hosts = data.get("hosts", {})

    if not hosts:
        print("[ERROR] No hosts found in hosts.yaml.")
        sys.exit(1)

    # Resolve target list
    if args.host:
        targets = {}
        for name in args.host:
            if name in hosts:
                targets[name] = hosts[name]
            else:
                print(f"  {YELLOW}[WARN]{RESET} '{name}' not found in hosts.yaml — skipped.")
        if not targets:
            print("[ERROR] No valid targets.")
            sys.exit(1)
    else:
        targets = hosts

    # Header
    print(f"\n{CYAN}{BOLD}{'─' * 60}{RESET}")
    print(f"{CYAN}{BOLD}  NAMS26 — Ping Hosts Utility{RESET}")
    print(f"{CYAN}{BOLD}  Hosts  : {', '.join(targets.keys())}{RESET}")
    print(f"{CYAN}{BOLD}{'─' * 60}{RESET}\n")
    print(f"  {'HOST':<12}  {'DNS NAME':<18}  {'STATUS':<6}   PACKET LOSS")
    print(f"  {'─' * 55}")

    # Throttled parallel pings — MAX_WORKERS concurrent at a time with a
    # short stagger between submissions to avoid saturating the lab DNS server.
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for host_name, host_data in targets.items():
            future = executor.submit(
                ping,
                host_name,
                host_data.get("dns_name", host_name),
                args.count,
            )
            futures[future] = host_name
            time.sleep(LAUNCH_STAGGER)

        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda r: r["host"])
    for r in results:
        print_result(r)

    passed = sum(1 for r in results if r["reachable"])
    total  = len(results)
    color  = GREEN if passed == total else (YELLOW if passed > 0 else RED)
    print(f"\n  {color}{BOLD}Result: {passed}/{total} hosts reachable{RESET}\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
