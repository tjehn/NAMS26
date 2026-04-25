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
    1. Spawns: ssh -o StrictHostKeyChecking=accept-new <user>@<dns_name>
    2. Detects the "Are you sure you want to continue connecting" prompt
       and sends "yes" to accept and store the host key
    3. Detects the password prompt and sends the password
    4. Detects the IOS router prompt (e.g. R1> or R1#)
    5. Sends "exit" to close the session cleanly
    6. Reports PASS or FAIL per router
"""

import os
import sys
import yaml
import argparse
import pexpect

# =============================================================================
# PATH RESOLUTION
# utils/ sits one level below the module root:
#   modules/05_ipv6_eigrp_ospf_nornir/
#     data/ipv6_eigrp_ospf.yaml
#     utils/init_ssh.py   <-- here
# =============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(SCRIPT_DIR)
YAML_FILE  = os.path.join(MODULE_DIR, "data", "ipv6_eigrp_ospf.yaml")

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
def warned(msg): print(f"{YELLOW}  [WARN]{RESET} {msg}")
def info(msg):   print(f"{CYAN}  [INFO]{RESET} {msg}")


# =============================================================================
# SSH INIT
# =============================================================================

# Maximum seconds pexpect waits for any single pattern match during the SSH
# handshake (host key prompt → password prompt → router prompt → exit).
# IOL routers on EVE-NG can be slow to respond; 15 s gives enough headroom
# without letting a dead host stall the sequence for too long.
# Current: 15 s   Practical range: 10 – 30 s
SSH_TIMEOUT = 15

# Ordered list of string/regex patterns that pexpect watches for after each
# SSH interaction. pexpect.expect() returns the index of the first pattern
# that matches — the IDX_* constants below map those indices to human-readable
# names so the while-loop branches are self-documenting.
EXPECT_PATTERNS = [
    r"Are you sure you want to continue connecting",  # host key prompt (new/changed key)
    r"[Pp]assword:",                                  # password prompt
    r"[>#]",                                          # IOS exec or enable prompt
    pexpect.EOF,                                      # connection closed by remote
    pexpect.TIMEOUT,                                  # no pattern matched within SSH_TIMEOUT
]

IDX_HOSTKEY  = 0   # "Are you sure..." — send "yes" to accept and store the key
IDX_PASSWORD = 1   # Password: — send the credential password
IDX_PROMPT   = 2   # R1> or R1# — router is authenticated and at a prompt
IDX_EOF      = 3   # EOF — SSH process exited unexpectedly
IDX_TIMEOUT  = 4   # TIMEOUT — nothing matched within SSH_TIMEOUT seconds


def init_ssh_router(device_name: str, dns_name: str,
                    username: str, password: str) -> bool:
    """SSH to a single router, accept host key, authenticate, confirm prompt."""
    ssh_cmd = (
        f"ssh "
        # Accept new host keys automatically; reject keys that changed (protects
        # against accidental connection to the wrong host after a lab rebuild).
        f"-o StrictHostKeyChecking=accept-new "
        # Write accepted keys to the standard known_hosts file so Netmiko/Nornir
        # scripts can connect without host-key prompts after init_ssh runs.
        f"-o UserKnownHostsFile={os.path.expanduser('~/.ssh/known_hosts')} "
        # TCP-level connection timeout in seconds — distinct from SSH_TIMEOUT
        # (which governs pexpect pattern matching). A host that does not respond
        # to TCP SYN within this window is immediately reported FAIL.
        # Current: 10 s   Practical range: 5 – 20 s
        f"-o ConnectTimeout=10 "
        f"{username}@{dns_name}"
    )

    try:
        child = pexpect.spawn(ssh_cmd, timeout=SSH_TIMEOUT, encoding="utf-8")

        while True:
            idx = child.expect(EXPECT_PATTERNS)

            if idx == IDX_HOSTKEY:
                child.sendline("yes")
                info(f"{device_name} — host key accepted")
                continue

            elif idx == IDX_PASSWORD:
                child.sendline(password)
                break

            elif idx == IDX_PROMPT:
                info(f"{device_name} — already authenticated, prompt reached")
                child.sendline("exit")
                child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)
                return True

            elif idx == IDX_EOF:
                failed(f"{device_name} — connection closed unexpectedly before password prompt")
                return False

            elif idx == IDX_TIMEOUT:
                failed(f"{device_name} — timeout waiting for host key or password prompt")
                return False

        idx = child.expect(EXPECT_PATTERNS, timeout=SSH_TIMEOUT)

        if idx == IDX_PROMPT:
            child.sendline("exit")
            child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)
            return True

        elif idx == IDX_PASSWORD:
            failed(f"{device_name} — authentication failed (password re-prompt)")
            child.sendline("")
            child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)
            return False

        elif idx == IDX_EOF:
            failed(f"{device_name} — connection closed after password — check credentials")
            return False

        elif idx == IDX_TIMEOUT:
            failed(f"{device_name} — timeout waiting for router prompt after authentication")
            return False

        else:
            failed(f"{device_name} — unexpected state in SSH handshake")
            return False

    except pexpect.exceptions.TIMEOUT:
        failed(f"{device_name} — overall session timeout ({SSH_TIMEOUT}s)")
        return False
    except pexpect.exceptions.EOF:
        failed(f"{device_name} — unexpected EOF during SSH session")
        return False
    except FileNotFoundError:
        failed(f"{device_name} — 'ssh' binary not found — is OpenSSH installed?")
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
            "NAMS26 Module 05 Utility — SSH Initialization\n"
            "Connects to each lab router via SSH, accepts the host key,\n"
            "authenticates, confirms the router prompt, and exits cleanly.\n"
            "Populates ~/.ssh/known_hosts for use by Nornir and Netmiko scripts.\n"
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

    for device_data in devices.values():
        if not device_data.get("credentials"):
            device_data["credentials"] = default_creds

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

    print(f"\n{BOLD}NAMS26 — Module 05: SSH Initialization{RESET}")
    print(f"Targets : {', '.join(target_routers)}")
    print("=" * 60)

    results = {}

    for device_name in target_routers:
        device_data = devices[device_name]
        dns_name    = device_data.get("dns_name", "")
        creds       = device_data.get("credentials", default_creds)

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
        print(f"{YELLOW}  [WARN]{RESET} {fail_count} router(s) failed. "
              f"Resolve before running Nornir scripts.")
        sys.exit(1)
    else:
        passed("All routers reachable via SSH. known_hosts is current.")
        print(f"{CYAN}  Ready to run configure_ipv6_eigrp_ospf.py{RESET}\n")


if __name__ == "__main__":
    main()
