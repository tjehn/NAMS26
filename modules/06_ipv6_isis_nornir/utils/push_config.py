#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 06 Utility
File     : modules/06_ipv6_isis_nornir/utils/push_config.py
Purpose  : Send one or more ad-hoc configuration lines to one or more lab
           routers via Netmiko. Designed as a demonstration companion to
           troubleshoot_isis.py — use it to inject a fault, run the
           troubleshooter to show the symptom, then restore with
           configure_isis.py.

           Routers are resolved from module06_isis.yaml using the same
           --router alias logic as the other module scripts (BB-1, bb-1,
           bb-1.lab are all accepted). SSH host key verification relies on
           ~/.ssh/known_hosts populated by init_ssh.py.

Input modes (combinable):
    --cmd   One or more config lines passed directly on the command line.
    prompt  If no --cmd lines are supplied, an interactive prompt collects
            lines one at a time. Enter a blank line to finish.

Usage:
    # Remove IS-IS on a link (fault injection)
    python push_config.py --router ABR-1 --cmd "interface Ethernet0/0" "no ip router isis NAMS26"

    # Dry-run — show commands that would be sent, no SSH connection
    python push_config.py --router ABR-1 --cmd "interface Ethernet0/0" "no ip router isis NAMS26" --dry-run

    # Interactive prompt — enter lines one at a time, blank line to finish
    python push_config.py --router BB-1

    # List available routers from YAML
    python push_config.py --list-routers

Pre-flight requirement:
    Run utils/clear_known_hosts.sh and utils/init_ssh.py after every
    EVE-NG lab reboot before using this script.
"""

import os
import sys
import yaml
import argparse
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR  = os.path.dirname(SCRIPT_DIR)
YAML_FILE   = os.path.join(MODULE_DIR, "data", "module06_isis.yaml")
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
# =============================================================================
def resolve_router(token: str, devices: dict) -> str | None:
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
    if not os.path.isfile(KNOWN_HOSTS):
        print(warned(
            f"known_hosts not found at {KNOWN_HOSTS} — "
            f"run utils/clear_known_hosts.sh then utils/init_ssh.py first"
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
    device_header(device_name, dns_name, oob_ip)

    if dry_run:
        print(f"\n{BOLD}  DRY-RUN — commands that would be sent:{RESET}\n")
        print(f"  {DIM}configure terminal{RESET}")
        for cmd in commands:
            print(f"  {YELLOW}{cmd}{RESET}")
        print(f"  {DIM}end{RESET}")
        print(f"  {DIM}write memory{RESET}")
        print(f"\n{info('No connection made — dry-run only.')}")
        return

    conn = connect(device_name, dns_name, creds)
    if conn is None:
        print(failed(f"Skipping {device_name} — connection failed."))
        return

    try:
        print(f"\n{BOLD}  Sending configuration:{RESET}\n")
        output = conn.send_config_set(commands)

        for line in output.splitlines():
            stripped = line.strip()
            if stripped:
                print(f"  {DIM}{stripped}{RESET}")

        conn.save_config()
        print(f"\n{passed('Configuration applied and saved.')}")

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
    print(f"\n{BOLD}Enter configuration lines (blank line or Ctrl-C to finish):{RESET}\n")
    commands = []
    try:
        while True:
            line = input(f"  {CYAN}config#{RESET} ").strip()
            if not line:
                break
            commands.append(line)
    except (KeyboardInterrupt, EOFError):
        print()
    return commands


# =============================================================================
# ENTRY POINT
# =============================================================================
def main() -> None:

    EXAMPLES = (
        "Examples:\n"
        "\n"
        "  # Inject IS-IS fault on ABR-1 — remove IS-IS from uplink\n"
        "  python push_config.py --router ABR-1 --cmd \"interface Ethernet0/0\" "
        "\"no ip router isis NAMS26\"\n"
        "\n"
        "  # Restore IS-IS on ABR-1\n"
        "  python push_config.py --router ABR-1 --cmd \"interface Ethernet0/0\" "
        "\"ip router isis NAMS26\"\n"
        "\n"
        "  # Interactive prompt — enter lines one at a time\n"
        "  python push_config.py --router BB-1\n"
        "\n"
        "  # Dry-run — preview commands without connecting\n"
        "  python push_config.py --router ABR-1 --cmd \"interface Ethernet0/0\" "
        "\"no ip router isis NAMS26\" --dry-run\n"
        "\n"
        "  # List available routers from YAML\n"
        "  python push_config.py --list-routers\n"
    )

    parser = argparse.ArgumentParser(
        description=(
            "NAMS26 Module 06 Utility — Ad-hoc Configuration Push\n"
            "Send one or more config lines to one or more lab routers.\n"
            "Designed as a demonstration companion to troubleshoot_isis.py."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help=(
            "Target one or more routers. Accepts YAML key (BB-1), "
            "short name (bb-1), or DNS name (bb-1.lab)."
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

    if args.list_routers:
        print(f"\n{BOLD}Available routers (from YAML):{RESET}\n")
        for key, dev in devices.items():
            print(f"  {CYAN}{key:<8}{RESET}  dns={dev.get('dns_name',''):<16}  oob={dev.get('oob_ip','')}")
        print()
        sys.exit(0)

    if not args.router:
        print("[ERROR] --router is required. Use --list-routers to see available devices.")
        parser.print_usage()
        sys.exit(1)

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

    if args.cmd:
        commands = args.cmd
    else:
        commands = collect_commands_interactive()

    if not commands:
        print("[ERROR] No commands provided — nothing to do.")
        sys.exit(1)

    mode_label = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"\n{BOLD}NAMS26 — Module 06: Ad-hoc Config Push [{mode_label}]{RESET}")
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
