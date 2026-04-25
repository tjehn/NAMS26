#!/usr/bin/env python3
"""
Module   : NAMS26 Project Utility
File     : modules/03_ospf1_napalm/utils/push_config.py
Purpose  : Send one or more ad-hoc configuration lines to one or more lab
           routers via Netmiko. Designed as a demonstration companion to
           troubleshoot_ospf_classic.py — use it to inject a fault, run the
           troubleshooter to show the symptom, then restore with a second
           push_config.py call.

           Routers are resolved from ospf_classic.yaml using the same
           --router alias logic as the other module scripts (R1, r1, r1.lab
           are all accepted). SSH host key verification relies on
           ~/.ssh/known_hosts populated by check_ssh.py.

Input modes (combinable):
    --cmd   One or more config lines passed directly on the command line.
    prompt  If no --cmd lines are supplied, an interactive prompt collects
            lines one at a time. Enter a blank line to finish.

Usage:
    # Single command — one router
    python push_config.py --router R1 --cmd "no router ospf 1"

    # Multiple commands — one router
    python push_config.py --router R2 --cmd "router ospf 1" "no network 192.1.100.0 0.0.0.255 area 0"

    # Multiple routers — same commands pushed to each
    python push_config.py --router R1 R2 --cmd "no ip domain-lookup"

    # Interactive prompt — enter lines one at a time, blank line to finish
    python push_config.py --router R1

    # Dry-run — show commands that would be sent, no SSH connection
    python push_config.py --router R1 --cmd "no router ospf 1" --dry-run

    # List available routers from YAML
    python push_config.py --list-routers

Pre-flight requirement:
    Run utils/clear_known_hosts.sh and utils/check_ssh.py after every
    EVE-NG lab reboot before using this script.
"""

import os
import sys
import yaml
import argparse
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# =============================================================================
# PATH RESOLUTION
# utils/ sits one level below the module root:
#   modules/03_ospf1_napalm/
#     data/ospf_classic.yaml
#     utils/push_config.py   <-- here
# =============================================================================
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR  = os.path.dirname(SCRIPT_DIR)
YAML_FILE   = os.path.join(MODULE_DIR, "data", "ospf_classic.yaml")
KNOWN_HOSTS = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# TERMINAL OUTPUT HELPERS
# =============================================================================
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

def passed(msg):  return f"{GREEN}  [PASS]{RESET} {msg}"
def failed(msg):  return f"{RED}  [FAIL]{RESET} {msg}"
def warned(msg):  return f"{YELLOW}  [WARN]{RESET} {msg}"
def info(msg):    return f"{CYAN}  [INFO]{RESET} {msg}"

def device_header(device_name: str, dns_name: str, oob_ip: str) -> None:
    bar = "=" * 60
    print(f"\n{BOLD}{bar}{RESET}")
    print(f"{BOLD}  Device : {device_name}   DNS : {dns_name}   OOB : {oob_ip}{RESET}")
    print(f"{BOLD}{bar}{RESET}")


# =============================================================================
# ROUTER NAME RESOLUTION
# Accepts YAML key (R1), case-insensitive short name (r1), or DNS name
# (r1.lab, R1.lab) — mirrors the alias resolution pattern used across all
# module scripts.
# =============================================================================
def resolve_router(token: str, devices: dict) -> str | None:
    """Return the YAML device key for a given input token, or None.

    Resolution order:
      1. Exact match against YAML key            (R1)
      2. Case-insensitive match against YAML key  (r1  → R1)
      3. Case-insensitive match against dns_name  (r1.lab or R1.lab → R1)
    """
    if token in devices:
        return token
    upper = token.upper()
    if upper in devices:
        return upper
    for key, dev in devices.items():
        if dev.get("dns_name", "").lower() == token.lower():
            return key
    return None


# =============================================================================
# SSH CONNECTION
# =============================================================================
def connect(device_name: str, dns_name: str, creds: dict):
    """Establish a Netmiko SSH session. Returns connection or None on failure."""
    if not os.path.isfile(KNOWN_HOSTS):
        print(warned(
            f"known_hosts not found at {KNOWN_HOSTS} — "
            f"run utils/clear_known_hosts.sh then utils/check_ssh.py first"
        ))

    params = {
        "device_type":         "cisco_ios",
        "host":                dns_name,
        "username":            creds.get("username", ""),
        "password":            creds.get("password", ""),
        # Multiplier applied to ALL of Netmiko's internal delay constants
        # (inter-command pause, post-login settling, prompt-detection loops).
        # IOL routers can respond slowly — 2.0 doubles the default delays to
        # reduce false "no prompt detected" failures without being excessively slow.
        # Current: 2.0   Range: 1.0 (fastest, may miss slow prompts) – 5.0 (very slow hosts)
        "global_delay_factor": 2.0,
    }
    try:
        conn = ConnectHandler(**params)
        print(info(f"Connected to {device_name} ({dns_name})"))
        return conn
    except NetmikoTimeoutException:
        print(failed(f"Timeout connecting to {device_name} ({dns_name})"))
    except NetmikoAuthenticationException:
        print(failed(f"Authentication failed on {device_name}"))
    except Exception as exc:
        print(failed(f"Connection error on {device_name}: {exc}"))
    return None


# =============================================================================
# CONFIG PUSH
# =============================================================================
def push_config(device_name: str, dns_name: str, oob_ip: str,
                creds: dict, commands: list, dry_run: bool) -> None:
    """Connect to a router and push a list of config lines.

    Enters configuration mode, sends each line individually, exits, and
    saves with 'write memory'. In dry-run mode the connection is skipped
    and the commands are printed for review.

    Args:
        device_name : YAML key / display name (e.g. 'R1').
        dns_name    : SSH target resolved from YAML (e.g. 'r1.lab').
        oob_ip      : OOB address — displayed in header for reference only.
        creds       : Dict with 'username' and 'password' keys.
        commands    : Ordered list of IOS config lines to send.
        dry_run     : If True, print commands and return without connecting.
    """
    device_header(device_name, dns_name, oob_ip)

    # --- Dry-run preview -----------------------------------------------------
    if dry_run:
        print(f"\n{BOLD}  DRY-RUN — commands that would be sent:{RESET}\n")
        print(f"  {DIM}configure terminal{RESET}")
        for cmd in commands:
            print(f"  {YELLOW}{cmd}{RESET}")
        print(f"  {DIM}end{RESET}")
        print(f"  {DIM}write memory{RESET}")
        print(f"\n{info('No connection made — dry-run only.')}")
        return

    # --- Live push -----------------------------------------------------------
    conn = connect(device_name, dns_name, creds)
    if conn is None:
        print(failed(f"Skipping {device_name} — connection failed."))
        return

    try:
        print(f"\n{BOLD}  Sending configuration:{RESET}\n")
        output = conn.send_config_set(commands)

        # Print each sent line with its router response
        for line in output.splitlines():
            stripped = line.strip()
            if stripped:
                print(f"  {DIM}{stripped}{RESET}")

        # Save configuration
        conn.save_config()
        print(f"\n{passed('Configuration applied and saved.')}")

        # Surface any obvious IOS error indicators
        error_markers = ["Invalid input", "Incomplete command", "Ambiguous command", "% "]
        errors_found  = [l for l in output.splitlines()
                         if any(m in l for m in error_markers)]
        if errors_found:
            print(warned("IOS reported one or more errors — review output above:"))
            for err in errors_found:
                print(f"    {RED}{err.strip()}{RESET}")

    except Exception as exc:
        print(failed(f"Error during config push on {device_name}: {exc}"))
    finally:
        conn.disconnect()
        print(info(f"Disconnected from {device_name}"))


# =============================================================================
# INTERACTIVE PROMPT
# =============================================================================
def collect_commands_interactive() -> list:
    """Prompt the user to enter config lines one at a time.

    Returns a list of non-empty lines. An empty line (Enter) signals end
    of input. Ctrl-C or Ctrl-D abort gracefully.
    """
    print(f"\n{BOLD}Enter configuration lines (blank line or Ctrl-C to finish):{RESET}\n")
    commands = []
    try:
        while True:
            line = input(f"  {CYAN}config#{RESET} ").strip()
            if not line:
                break
            commands.append(line)
    except (KeyboardInterrupt, EOFError):
        print()  # newline after ^C/^D

    return commands


# =============================================================================
# ENTRY POINT
# =============================================================================
def main() -> None:

    # -------------------------------------------------------------------------
    # Argument parsing
    # -------------------------------------------------------------------------
    EXAMPLES = (
        "Examples:\n"
        "\n"
        "  # Single command -- one router\n"
        "  python push_config.py --router R1 --cmd \"no router ospf 1\"\n"
        "\n"
        "  # Multiple commands -- one router\n"
        "  python push_config.py --router R2 --cmd \"router ospf 1\" \"no network 192.1.100.0 0.0.0.255 area 0\"\n"
        "\n"
        "  # Multiple routers -- same commands pushed to each\n"
        "  python push_config.py --router R1 R2 --cmd \"no ip domain-lookup\"\n"
        "\n"
        "  # Interactive prompt -- enter lines one at a time, blank line to finish\n"
        "  python push_config.py --router R1\n"
        "\n"
        "  # Dry-run -- preview commands without connecting\n"
        "  python push_config.py --router R1 --cmd \"no router ospf 1\" --dry-run\n"
        "\n"
        "  # List available routers from YAML\n"
        "  python push_config.py --list-routers\n"
        "\n"
        "Typical closing demo workflow:\n"
        "\n"
        "  # 1. Inject drift — remove a network statement on R1\n"
        "  python utils/push_config.py --router R1 --cmd \"router ospf 1\" \"no network 192.1.100.0 0.0.0.255 area 0\"\n"
        "\n"
        "  # 2. Observe — troubleshooter confirms protocol is partially working\n"
        "  python scripts/troubleshoot_ospf_classic.py --router R1 --check neighbors routes\n"
        "\n"
        "  # 3. Detect — verifier catches the deviation from source of truth\n"
        "  python scripts/verify_ospf_classic.py --router R1 --check routes\n"
        "\n"
        "  # 4. Restore — re-apply correct config from YAML\n"
        "  python scripts/configure_ospf_classic.py --router R1\n"
        "\n"
        "  # 5. Confirm — verifier passes clean\n"
        "  python scripts/verify_ospf_classic.py --router R1 --check routes\n"
    )

    parser = argparse.ArgumentParser(
        description=(
            "NAMS26 Module 03 Utility — Ad-hoc Configuration Push\n"
            "Send one or more config lines to one or more lab routers.\n"
            "Designed as a demonstration companion to troubleshoot_ospf_classic.py."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help=(
            "Target one or more routers. Accepts YAML key (R1), "
            "short name (r1), or DNS name (r1.lab)."
        ),
    )
    parser.add_argument(
        "--cmd",
        nargs="+",
        metavar="LINE",
        help=(
            "One or more IOS configuration lines to send. "
            "If omitted, an interactive prompt is used."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview commands that would be sent — no SSH connection.",
    )
    parser.add_argument(
        "--list-routers",
        action="store_true",
        help="List all routers available in YAML and exit.",
    )
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Load YAML
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # --list-routers
    # -------------------------------------------------------------------------
    if args.list_routers:
        print(f"\n{BOLD}Available routers (from YAML):{RESET}\n")
        for key, dev in devices.items():
            print(f"  {CYAN}{key:<6}{RESET}  dns={dev.get('dns_name',''):<16}  oob={dev.get('oob_ip','')}")
        print()
        sys.exit(0)

    # -------------------------------------------------------------------------
    # Require --router
    # -------------------------------------------------------------------------
    if not args.router:
        print("[ERROR] --router is required. Use --list-routers to see available devices.")
        parser.print_usage()
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Resolve target routers
    # -------------------------------------------------------------------------
    target_routers = []
    for token in args.router:
        resolved = resolve_router(token, devices)
        if resolved:
            target_routers.append(resolved)
        else:
            print(f"[WARNING] Router not found in YAML (skipped): '{token}'")

    if not target_routers:
        print("[ERROR] No valid target routers.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Collect commands
    # -------------------------------------------------------------------------
    if args.cmd:
        commands = args.cmd
    else:
        commands = collect_commands_interactive()

    if not commands:
        print("[ERROR] No commands provided — nothing to do.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Summary and confirmation
    # -------------------------------------------------------------------------
    mode_label = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"\n{BOLD}NAMS26 — Module 03: Ad-hoc Config Push [{mode_label}]{RESET}")
    print(f"Targets  : {', '.join(target_routers)}")
    print(f"Commands :")
    for cmd in commands:
        print(f"  {YELLOW}{cmd}{RESET}")

    if not args.dry_run:
        try:
            confirm = input(f"\n{BOLD}Proceed? [y/N]: {RESET}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{warned('Aborted.')}")
            sys.exit(0)
        if confirm != "y":
            print(warned("Aborted — no changes made."))
            sys.exit(0)

    # -------------------------------------------------------------------------
    # Push to each target router
    # -------------------------------------------------------------------------
    for device_name in target_routers:
        device_data = devices[device_name]
        dns_name    = device_data.get("dns_name", "")
        oob_ip      = device_data.get("oob_ip", "")
        creds       = device_data.get("credentials", default_creds)

        if not dns_name:
            print(failed(f"No dns_name defined for {device_name} in YAML — skipping."))
            continue

        push_config(device_name, dns_name, oob_ip, creds, commands, args.dry_run)

    print(f"\n{'=' * 60}")
    print(f"{BOLD}Push session complete.{RESET}\n")


if __name__ == "__main__":
    main()
