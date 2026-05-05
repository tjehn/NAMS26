#!/usr/bin/env python3
"""
File     : utils/init_ssh.py
Purpose  : Establish an SSH session to each lab device in sequence,
           accepting the host key fingerprint, authenticating, and
           persisting the key to ~/.ssh/known_hosts.

           Run this after clear_known_hosts.sh following every EVE-NG
           lab reboot. IOL generates new RSA host keys on every
           Wipe+Start cycle — known_hosts must be refreshed each time.

           Reads device list from utils/hosts.yaml — no module YAML
           dependency. Covers R1–R12, COSW-01, COSW-02, OOB-SW01.

           IOL 15.7 compatibility: paramiko is configured to offer legacy
           key exchange, MAC, and host key algorithms that IOL 1.99
           requires. Modern OpenSSH clients must pass these explicitly:
             -o KexAlgorithms=diffie-hellman-group14-sha1
             -o MACs=hmac-sha1
             -o HostKeyAlgorithms=ssh-rsa
           This script does the equivalent in paramiko automatically.

Usage:
    python utils/init_ssh.py
    python utils/init_ssh.py --host R1
    python utils/init_ssh.py --host R1 R2 COSW-01
    python utils/init_ssh.py --username netadmin --password admin

Pre-flight requirement:
    Run clear_known_hosts.sh first to remove stale host key entries.
"""

import os
import sys
import yaml
import argparse
import paramiko

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

def passed(msg): print(f"  {GREEN}[PASS]{RESET} {msg}")
def failed(msg): print(f"  {RED}[FAIL]{RESET} {msg}")
def info(msg):   print(f"  {CYAN}[INFO]{RESET} {msg}")


# =============================================================================
# IOL SSH COMPATIBILITY
# =============================================================================

# IOL 15.7 runs SSH version 1.99 and only supports legacy algorithms.
# These are set directly on the paramiko Transport after connect() so
# that the negotiation succeeds. Equivalent to passing:
#   -o KexAlgorithms=diffie-hellman-group14-sha1
#   -o MACs=hmac-sha1
#   -o HostKeyAlgorithms=ssh-rsa
# on the OpenSSH command line.

# TCP connection timeout in seconds.
# Current: 15 s   Range: 5 – 30 s
SSH_TIMEOUT = 15


def _apply_iol_transport_options(transport: paramiko.Transport) -> None:
    """
    Force legacy algorithm negotiation on an active paramiko Transport.
    Must be called after the TCP connection is established but before
    the SSH handshake completes — i.e. via the sock= approach below.
    """
    transport.get_security_options().kex       = [
        "diffie-hellman-group14-sha1",
        "diffie-hellman-group-exchange-sha1",
        "diffie-hellman-group1-sha1",
    ]
    transport.get_security_options().ciphers   = [
        "aes128-ctr",
        "aes192-ctr",
        "aes256-ctr",
        "aes128-cbc",
        "3des-cbc",
    ]
    transport.get_security_options().digests   = [
        "hmac-sha1",
        "hmac-sha1-96",
    ]
    transport.get_security_options().key_types = [
        "ssh-rsa",
    ]


def init_ssh_host(host_name: str, dns_name: str,
                  username: str, password: str) -> bool:
    """
    Connect via paramiko with IOL-compatible legacy SSH algorithms,
    auto-accept the host key, and persist it to known_hosts.

    Uses a low-level Transport connection so that algorithm preferences
    can be set before the SSH handshake — the standard SSHClient.connect()
    path does not allow this.

    Returns True on success, False on any failure.
    """
    import socket

    try:
        # Open a raw TCP socket first so we can configure the Transport
        # before the SSH handshake begins.
        sock = socket.create_connection((dns_name, 22), timeout=SSH_TIMEOUT)
        transport = paramiko.Transport(sock)

        # Apply IOL-compatible algorithms before the handshake.
        _apply_iol_transport_options(transport)

        # Run the SSH handshake.
        transport.start_client(timeout=SSH_TIMEOUT)

        # Retrieve and store the host key.
        host_key = transport.get_remote_server_key()

        # Load existing known_hosts and add the new key.
        host_keys = paramiko.HostKeys()
        if os.path.isfile(KNOWN_HOSTS):
            host_keys.load(KNOWN_HOSTS)
        host_keys.add(dns_name, host_key.get_name(), host_key)
        host_keys.save(KNOWN_HOSTS)

        # Authenticate.
        transport.auth_password(username, password)

        transport.close()
        sock.close()
        return True

    except paramiko.AuthenticationException:
        failed(f"{host_name} — authentication failed (check credentials)")
        return False
    except paramiko.SSHException as exc:
        failed(f"{host_name} — SSH error: {exc}")
        return False
    except OSError as exc:
        failed(f"{host_name} — connection failed: {exc}")
        return False
    except Exception as exc:
        failed(f"{host_name} — unexpected error: {exc}")
        return False


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "NAMS26 Utility — SSH Lab Initialization\n"
            "Connects to each lab device, accepts the host key,\n"
            "and persists it to ~/.ssh/known_hosts.\n\n"
            "Run after clear_known_hosts.sh following every EVE-NG lab reboot."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python utils/init_ssh.py\n"
            "  python utils/init_ssh.py --host R1\n"
            "  python utils/init_ssh.py --host R1 R2 COSW-01\n"
        ),
    )
    parser.add_argument(
        "--host",
        nargs="+",
        metavar="NAME",
        help="Initialize specific hosts only (e.g. --host R1 R2 COSW-01).",
    )
    parser.add_argument(
        "--username",
        metavar="USER",
        default=None,
        help="SSH username (overrides hosts.yaml credentials).",
    )
    parser.add_argument(
        "--password",
        metavar="PASS",
        default=None,
        help="SSH password (overrides hosts.yaml credentials).",
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
    print(f"\n{CYAN}{BOLD}{'─' * 60}{RESET}")
    print(f"{CYAN}{BOLD}  NAMS26 — SSH Lab Initialization{RESET}")
    print(f"{CYAN}{BOLD}  Hosts  : {', '.join(targets.keys())}{RESET}")
    print(f"{CYAN}{BOLD}{'─' * 60}{RESET}\n")

    results = {}

    for host_name, host_data in targets.items():
        dns_name = host_data.get("dns_name", "")
        creds    = host_data.get("credentials", default_creds)

        username = args.username or creds.get("username", "netadmin")
        password = args.password or creds.get("password", "admin")

        if not dns_name:
            failed(f"{host_name} — no dns_name in hosts.yaml, skipping")
            results[host_name] = False
            continue

        info(f"{host_name} ({dns_name}) — connecting...")
        ok = init_ssh_host(host_name, dns_name, username, password)
        results[host_name] = ok

        if ok:
            passed(f"{host_name} ({dns_name}) — host key accepted, known_hosts updated")

    # Summary
    print(f"\n{CYAN}{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}  SSH Initialization Summary{RESET}")
    print(f"{CYAN}{BOLD}{'─' * 60}{RESET}")

    pass_count = sum(1 for v in results.values() if v)
    fail_count = sum(1 for v in results.values() if not v)

    for host_name, ok in results.items():
        dns = targets[host_name].get("dns_name", "")
        status = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {status}  {host_name:<12}  {dns}")

    print(f"{CYAN}{'─' * 60}{RESET}")
    print(f"  {GREEN}{pass_count} passed{RESET}  "
          f"{(RED + str(fail_count) + ' failed' + RESET) if fail_count else (GREEN + '0 failed' + RESET)}")
    print()

    if fail_count:
        print(f"  {YELLOW}[WARN]{RESET} {fail_count} device(s) failed. Resolve before running lab scripts.")
        sys.exit(1)
    else:
        passed("All devices reachable via SSH. known_hosts is current.")
        print(f"  {CYAN}Ready to run lab scripts.{RESET}\n")


if __name__ == "__main__":
    main()
