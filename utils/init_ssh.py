#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 05 Utility
File     : modules/05_ipv6_eigrp_ospf_nornir/utils/init_ssh.py
Purpose  : Establish an SSH session to each lab router (R1–R9) in sequence,
           accepting the host key fingerprint, authenticating, confirming the
           router prompt is reachable, and exiting cleanly. Populates
           ~/.ssh/known_hosts with current host keys so that subsequent
           Nornir and Netmiko scripts can connect without interactive prompts.

           Run this after clear_known_hosts.sh following every EVE-NG lab
           reboot. IOL generates new RSA host keys on every Wipe+Start cycle,
           so known_hosts must be refreshed each time.

Usage:
    python init_ssh.py

    # Test a specific router only
    python init_ssh.py --router R1

    # Override credentials (default: netadmin / admin from YAML)
    python init_ssh.py --username netadmin --password admin

Pre-flight requirement:
    Run clear_known_hosts.sh first to remove stale host key entries.
    Running init_ssh.py without clearing first will fail if the stored
    key no longer matches (IOL generates new keys after every Wipe).

What this script does per router:
    1. Connects via paramiko with AutoAddPolicy (accepts any new host key)
    2. Persists the accepted key to ~/.ssh/known_hosts
    3. Reports PASS or FAIL per router
"""

import os
import sys
import yaml
import argparse
import paramiko

# =============================================================================
# PATH RESOLUTION
# utils/ sits one level below the module root:
#   modules/05_ipv6_eigrp_ospf_nornir/
#     data/ipv6_eigrp_ospf.yaml
#     utils/init_ssh.py   <-- here
# =============================================================================
SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR       = os.path.dirname(SCRIPT_DIR)
MODULES_DIR      = os.path.dirname(MODULE_DIR)
PROJECT_ROOT     = os.path.dirname(MODULES_DIR)
YAML_FILE        = os.path.join(MODULE_DIR, "data", "ipv6_eigrp_ospf.yaml")
KNOWN_HOSTS_PATH = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# TERMINAL OUTPUT HELPERS
# =============================================================================
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def passed(msg): print(f"{GREEN}  [PASS]{RESET} {msg}")
def failed(msg): print(f"{RED}  [FAIL]{RESET} {msg}")
def info(msg):   print(f"{CYAN}  [INFO]{RESET} {msg}")


# =============================================================================
# SSH INIT
# =============================================================================

# TCP connection timeout passed to paramiko.SSHClient.connect().
# Raises socket.timeout if the TCP handshake does not complete within this window.
# Current: 10 s   Practical range: 5 – 20 s
SSH_TIMEOUT = 10


def init_ssh_router(device_name: str, dns_name: str,
                    username: str, password: str) -> bool:
    """Connect via paramiko, auto-accept host key, update known_hosts.

    Args:
        device_name : Display name (e.g. 'R1') — used for output only.
        dns_name    : SSH target hostname (e.g. 'r1.lab').
        username    : SSH username.
        password    : SSH password.

    Returns:
        True if the connection succeeded and known_hosts was updated.
        False on any failure (timeout, auth error, connection refused).
    """
    client = paramiko.SSHClient()
    if os.path.isfile(KNOWN_HOSTS_PATH):
        client.load_host_keys(KNOWN_HOSTS_PATH)
    # AutoAddPolicy accepts new host keys and adds them to the in-memory store.
    # save_host_keys() below persists them to known_hosts after a successful connect.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=dns_name,
            username=username,
            password=password,
            timeout=SSH_TIMEOUT,
        )
        client.save_host_keys(KNOWN_HOSTS_PATH)
        info(f"{device_name} — host key accepted and stored")
        client.close()
        return True

    except paramiko.AuthenticationException:
        failed(f"{device_name} — authentication failed (check credentials)")
        return False
    except paramiko.SSHException as exc:
        failed(f"{device_name} — SSH error: {exc}")
        return False
    except OSError as exc:
        failed(f"{device_name} — connection failed: {exc}")
        return False
    except Exception as exc:
        failed(f"{device_name} — unexpected error: {exc}")
        return False


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "NAMS26 Module 05 Utility — SSH Lab Initialization\n"
            "Connects to each lab router via SSH, accepts the host key,\n"
            "authenticates, and persists the key to ~/.ssh/known_hosts.\n"
            "\n"
            "Run after clear_known_hosts.sh following every EVE-NG lab reboot."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python init_ssh.py\n"
            "  python init_ssh.py --router R1\n"
            "  python init_ssh.py --router R3 R5 R6\n"
        ),
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help=(
            "Test specific routers only. Accepts R1, r1, or r1.lab. "
            "Defaults to all routers in YAML."
        ),
    )
    parser.add_argument(
        "--username",
        metavar="USER",
        default=None,
        help="SSH username (overrides YAML credentials).",
    )
    parser.add_argument(
        "--password",
        metavar="PASS",
        default=None,
        help="SSH password (overrides YAML credentials).",
    )
    args = parser.parse_args()

    # Load YAML
    if not os.path.isfile(YAML_FILE):
        print(f"[ERROR] YAML file not found: {YAML_FILE}")
        sys.exit(1)

    try:
        with open(YAML_FILE, "r") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        print(f"[ERROR] Failed to parse YAML: {exc}")
        sys.exit(1)

    devices       = data.get("devices", {})
    default_creds = data.get("default_credentials", {})

    if not devices:
        print("[ERROR] No devices found in YAML.")
        sys.exit(1)

    # Inject default credentials
    for device_data in devices.values():
        if not device_data.get("credentials"):
            device_data["credentials"] = default_creds

    # Resolve target routers
    def resolve_router(token: str) -> str | None:
        if token in devices:
            return token
        upper = token.upper()
        if upper in devices:
            return upper
        for key, dev in devices.items():
            if dev.get("dns_name", "").lower() == token.lower():
                return key
        return None

    if args.router:
        target_routers = []
        for token in args.router:
            resolved = resolve_router(token)
            if resolved:
                target_routers.append(resolved)
            else:
                print(f"[WARNING] Router not found in YAML (skipped): '{token}'")
    else:
        target_routers = list(devices.keys())

    if not target_routers:
        print("[ERROR] No valid target routers.")
        sys.exit(1)

    # Run header
    print(f"\n{BOLD}NAMS26 — Module 05: SSH Lab Initialization{RESET}")
    print(f"Targets : {', '.join(target_routers)}")
    print("=" * 60)

    results = {}

    for device_name in target_routers:
        device_data = devices[device_name]
        dns_name    = device_data.get("dns_name", "")
        creds       = device_data.get("credentials", default_creds)

        # CLI args override YAML credentials
        username = args.username or creds.get("username", "netadmin")
        password = args.password or creds.get("password", "admin")

        if not dns_name:
            failed(f"{device_name} — no dns_name in YAML, skipping")
            results[device_name] = False
            continue

        info(f"{device_name} ({dns_name}) — connecting...")
        ok = init_ssh_router(device_name, dns_name, username, password)
        results[device_name] = ok

        if ok:
            passed(f"{device_name} ({dns_name}) — SSH OK, known_hosts updated")

    # Summary
    print("\n" + "=" * 60)
    print(f"{BOLD}  SSH Initialization Summary{RESET}")
    print("=" * 60)

    pass_count = sum(1 for v in results.values() if v)
    fail_count = sum(1 for v in results.values() if not v)

    for device_name, ok in results.items():
        dns_name = devices[device_name].get("dns_name", "")
        if ok:
            print(f"  {GREEN}PASS{RESET}  {device_name:<6}  {dns_name}")
        else:
            print(f"  {RED}FAIL{RESET}  {device_name:<6}  {dns_name}")

    print("=" * 60)
    print(f"  {GREEN}{pass_count} passed{RESET}  "
          f"{(RED + str(fail_count) + ' failed' + RESET) if fail_count else (GREEN + '0 failed' + RESET)}")
    print()

    if fail_count:
        print(f"{YELLOW}  [WARN]{RESET} {fail_count} router(s) failed SSH initialization. "
              f"Resolve before running Nornir scripts.")
        sys.exit(1)
    else:
        passed("All routers reachable via SSH. known_hosts is current.")
        print(f"{CYAN}  Ready to run configure_ipv6_eigrp_ospf.py{RESET}\n")


if __name__ == "__main__":
    main()
