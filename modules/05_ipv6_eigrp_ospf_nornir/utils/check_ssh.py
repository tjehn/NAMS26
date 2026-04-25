#!/usr/bin/env python3
"""
Module   : NAMS26 Project Utility
File     : modules/05_ipv6_eigrp_ospf_nornir/utils/check_ssh.py
Purpose  : Verify SSH connectivity to all lab hosts via Netmiko.
           Hosts are resolved via the lab DNS server (192.168.1.12, domain: .lab).
           No hardcoded IPs — all resolution is handled by the OS resolver.

           On a successful connection, each router's host key is written to
           ~/.ssh/known_hosts so that subsequent manual SSH sessions from the
           terminal work without host key mismatch errors.

           Use this as a troubleshooting diagnostic — not part of the EVE-NG
           reset sequence (use init_ssh.py for that).

Usage:
    python check_ssh.py
    python check_ssh.py --host R1
    python check_ssh.py --host r1.lab
"""

import argparse
import tempfile
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

# ─── Lab Host Inventory (DNS names — resolved via 192.168.1.12) ───────────────
HOSTS = {
    "R1": "r1.lab",
    "R2": "r2.lab",
    "R3": "r3.lab",
    "R4": "r4.lab",
    "R5": "r5.lab",
    "R6": "r6.lab",
    "R7": "r7.lab",
    "R8": "r8.lab",
    "R9": "r9.lab",
}

# ─── Credentials ──────────────────────────────────────────────────────────────
USERNAME = "netadmin"
PASSWORD = "admin"

# ─── ANSI Colors ───────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def make_ssh_config() -> str:
    """Write a temp SSH config that accepts new host keys into ~/.ssh/known_hosts."""
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    content = (
        "Host *\n"
        f"    StrictHostKeyChecking accept-new\n"
        f"    UserKnownHostsFile {known_hosts}\n"
    )
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".ssh_config",
                                     delete=False, prefix="nams26_")
    tmp.write(content)
    tmp.close()
    return tmp.name


def check_ssh(host: str, dns_name: str, ssh_config: str) -> dict:
    """Attempt SSH connection to a single host, grab prompt, disconnect."""
    device = {
        "device_type":     "cisco_ios",
        "host":            dns_name,
        "username":        USERNAME,
        "password":        PASSWORD,
        # TCP connection timeout in seconds. If the host does not respond to the
        # SSH TCP handshake within this window, Netmiko raises NetmikoTimeoutException.
        # Current: 10 s   Practical range: 5 – 30 s (increase for slow/remote hosts)
        "conn_timeout":    10,
        "ssh_config_file": ssh_config,
    }
    try:
        with ConnectHandler(**device) as conn:
            hostname = conn.find_prompt().strip().rstrip("#>")
        return {
            "host":     host,
            "dns_name": dns_name,
            "status":   "PASS",
            "detail":   f"prompt: {hostname}",
        }

    except NetmikoAuthenticationException:
        return {
            "host":     host,
            "dns_name": dns_name,
            "status":   "AUTH FAIL",
            "detail":   "Bad username or password",
        }
    except NetmikoTimeoutException:
        return {
            "host":     host,
            "dns_name": dns_name,
            "status":   "TIMEOUT",
            "detail":   "Host unreachable or SSH not enabled",
        }
    except Exception as e:
        return {
            "host":     host,
            "dns_name": dns_name,
            "status":   "ERROR",
            "detail":   str(e),
        }


def print_result(r: dict) -> None:
    status = r["status"]
    if status == "PASS":
        color = GREEN
    elif status == "AUTH FAIL":
        color = YELLOW
    else:
        color = RED

    print(f"  {BOLD}{r['host']:6}{RESET}  {r['dns_name']:16}  "
          f"{color}{BOLD}{status:<10}{RESET}  {r['detail']}")


def main():
    parser = argparse.ArgumentParser(description="Check SSH connectivity to NAMS26 Module 05 lab hosts.")
    parser.add_argument("--host", help="Check a single host by name (R1) or DNS name (r1.lab).")
    args = parser.parse_args()

    print(f"\n{CYAN}{BOLD}{'─' * 65}")
    print("  NAMS26 — Module 05: SSH Connectivity Check")
    print(f"  Credentials: {USERNAME} / {'*' * len(PASSWORD)}")
    print(f"{'─' * 65}{RESET}\n")
    print(f"  {'HOST':<8}{'DNS NAME':<18}{'STATUS':<12}DETAIL")
    print(f"  {'─' * 60}")

    if args.host:
        target = {k: v for k, v in HOSTS.items()
                  if v.lower() == args.host.lower() or k == args.host.upper()}
        if not target:
            target = {"CUSTOM": args.host}
        hosts_to_check = target
    else:
        hosts_to_check = HOSTS

    ssh_config = make_ssh_config()

    try:
        results = []
        # max_workers = number of hosts — launches one thread per host so all
        # SSH checks run in parallel. Total wall-clock time equals the slowest
        # single host rather than the sum of all host connection times.
        # as_completed() yields futures as they finish (arrival order, not
        # submission order) — results are sorted by hostname before display.
        with ThreadPoolExecutor(max_workers=len(hosts_to_check)) as executor:
            futures = {
                executor.submit(check_ssh, host, dns_name, ssh_config): host
                for host, dns_name in hosts_to_check.items()
            }
            for future in as_completed(futures):
                results.append(future.result())

        results.sort(key=lambda r: r["host"])
        for r in results:
            print_result(r)

        passed = sum(1 for r in results if r["status"] == "PASS")
        total  = len(results)
        color  = GREEN if passed == total else (YELLOW if passed > 0 else RED)
        print(f"\n  {color}{BOLD}Result: {passed}/{total} hosts SSH reachable{RESET}\n")

        if passed == total:
            print(f"  {CYAN}Host keys written to ~/.ssh/known_hosts — manual SSH sessions ready.{RESET}\n")

    finally:
        os.unlink(ssh_config)


if __name__ == "__main__":
    main()
