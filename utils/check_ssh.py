#!/usr/bin/env python3
"""
File     : utils/check_ssh.py
Purpose  : Verify SSH connectivity to all lab devices via Netmiko.
           Use as a troubleshooting diagnostic — not part of the EVE-NG
           reset sequence (use init_ssh.py for that).

           Reads device list from utils/hosts.yaml — no module YAML
           dependency. Covers R1–R12, COSW-01, COSW-02, OOB-SW01.

Usage:
    python utils/check_ssh.py
    python utils/check_ssh.py --host R1
    python utils/check_ssh.py --host R1 R2 COSW-01
"""

import argparse
import os
import sys
import tempfile
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
YAML_FILE    = os.path.join(SCRIPT_DIR, "hosts.yaml")
KNOWN_HOSTS  = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# ANSI Colors
# =============================================================================
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def make_ssh_config() -> str:
    """Write a temp SSH config that accepts new host keys into known_hosts."""
    content = (
        "Host *\n"
        f"    StrictHostKeyChecking accept-new\n"
        f"    UserKnownHostsFile {KNOWN_HOSTS}\n"
    )
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ssh_config", delete=False, prefix="nams26_"
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


def check_ssh(host_name: str, dns_name: str,
              username: str, password: str, ssh_config: str) -> dict:
    """Attempt SSH connection to a single host, grab prompt, disconnect."""
    device = {
        "device_type":     "cisco_ios",
        "host":            dns_name,
        "username":        username,
        "password":        password,
        # TCP connection timeout in seconds.
        # Current: 10 s   Range: 5 – 30 s
        "conn_timeout":    10,
        "ssh_config_file": ssh_config,
    }
    try:
        with ConnectHandler(**device) as conn:
            hostname = conn.find_prompt().strip().rstrip("#>")
        return {
            "host":     host_name,
            "dns_name": dns_name,
            "status":   "PASS",
            "detail":   f"prompt: {hostname}",
        }
    except NetmikoAuthenticationException:
        return {
            "host":     host_name,
            "dns_name": dns_name,
            "status":   "AUTH FAIL",
            "detail":   "Bad username or password",
        }
    except NetmikoTimeoutException:
        return {
            "host":     host_name,
            "dns_name": dns_name,
            "status":   "TIMEOUT",
            "detail":   "Host unreachable or SSH not enabled",
        }
    except Exception as exc:
        return {
            "host":     host_name,
            "dns_name": dns_name,
            "status":   "ERROR",
            "detail":   str(exc),
        }


def print_result(r: dict) -> None:
    status = r["status"]
    color = GREEN if status == "PASS" else (YELLOW if status == "AUTH FAIL" else RED)
    print(f"  {BOLD}{r['host']:<12}{RESET}  {r['dns_name']:<18}  "
          f"{color}{BOLD}{status:<10}{RESET}  {r['detail']}")


def main():
    parser = argparse.ArgumentParser(
        description="NAMS26 Utility — SSH Connectivity Check (troubleshooting diagnostic)."
    )
    parser.add_argument(
        "--host",
        nargs="+",
        metavar="NAME",
        help="Check specific hosts only (e.g. --host R1 R2 COSW-01).",
    )
    args = parser.parse_args()

    # Load hosts.yaml
    if not os.path.isfile(YAML_FILE):
        print(f"[ERROR] hosts.yaml not found: {YAML_FILE}")
        sys.exit(1)

    with open(YAML_FILE, "r") as fh:
        data = yaml.safe_load(fh)

    hosts         = data.get("hosts", {})
    default_creds = data.get("default_credentials", {})

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
    print(f"\n{CYAN}{BOLD}{'─' * 65}{RESET}")
    print(f"{CYAN}{BOLD}  NAMS26 — SSH Connectivity Check{RESET}")
    print(f"{CYAN}{BOLD}  Hosts  : {', '.join(targets.keys())}{RESET}")
    print(f"{CYAN}{BOLD}{'─' * 65}{RESET}\n")
    print(f"  {'HOST':<12}  {'DNS NAME':<18}  {'STATUS':<10}  DETAIL")
    print(f"  {'─' * 60}")

    ssh_config = make_ssh_config()

    try:
        results = []
        # One thread per host — all checks run in parallel.
        # Wall-clock time = slowest single host, not the sum of all.
        with ThreadPoolExecutor(max_workers=len(targets)) as executor:
            futures = {
                executor.submit(
                    check_ssh,
                    host_name,
                    host_data.get("dns_name", ""),
                    host_data.get("credentials", default_creds).get("username", "netadmin"),
                    host_data.get("credentials", default_creds).get("password", "admin"),
                    ssh_config,
                ): host_name
                for host_name, host_data in targets.items()
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
            print(f"  {CYAN}All devices reachable. Lab is ready.{RESET}\n")
        else:
            print(f"  {YELLOW}[WARN]{RESET} {total - passed} device(s) unreachable. "
                  f"Check EVE-NG lab state and run init_ssh.py if needed.\n")

    finally:
        os.unlink(ssh_config)


if __name__ == "__main__":
    main()
