#!/usr/bin/env python3
"""
File     : utils/label_interfaces.py
Purpose  : Walks all lab devices, runs 'show cdp neighbors detail',
           and applies interface descriptions based on CDP neighbor data:

             - CDP neighbor is OOB_SW01        → description OOB Management
             - CDP neighbor is any other device → description <ShortName> Eth X/X
             - No CDP neighbor found            → description UNUSED + shutdown

           Reads device list from utils/hosts.yaml — no module dependency.
           Covers R1–R12, COSW-01, COSW-02, OOB_SW01.

Usage:
    python utils/label_interfaces.py                        # Live — all devices
    python utils/label_interfaces.py --dry-run              # Preview only, no push
    python utils/label_interfaces.py --device R1 COSW-01   # Specific devices
"""

import argparse
import os
import re
import sys
import yaml
from datetime import datetime
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

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

# Netmiko timing — IOL can be slow to respond.
# Current: 2   Range: 1 – 5
GLOBAL_DELAY_FACTOR = 2

# TCP connection timeout in seconds.
# Current: 30 s   Range: 15 – 60 s
CONN_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Hostnames that always map to 'OOB Management' regardless of remote interface
# ---------------------------------------------------------------------------
OOB_HOSTNAMES = {"OOB-SW01", "OOB_SW01", "OOB_SW_01", "OOB-SW-01"}


# =============================================================================
# NAME NORMALIZATION
# =============================================================================

def normalize_hostname(raw: str) -> str:
    """
    Strip domain suffixes and normalize device names to short display form.

    Examples:
        R1.lab.local        → R1
        DC02-B005-COSW-01   → COSW-01
        DC02-B005-COSW-02   → COSW-02
        OOB_SW01            → OOB_SW01
    """
    name = raw.split(".")[0]

    # Collapse DC-site-building prefix: DC02-B005-COSW-01 → COSW-01
    cosw_match = re.search(r"(COSW-\d+)$", name, re.IGNORECASE)
    if cosw_match:
        return cosw_match.group(1).upper()

    return name


def normalize_interface(raw: str) -> str:
    """
    Normalize interface names to 'Eth X/Y' display format.

    Examples:
        Ethernet0/1   → Eth 0/1
        Eth 4/3       → Eth 4/3
    """
    raw = raw.strip()

    if re.match(r"^Eth\s+\d+/\d+$", raw, re.IGNORECASE):
        return raw

    m = re.match(r"^Ethernet(\d+/\d+)$", raw, re.IGNORECASE)
    if m:
        return f"Eth {m.group(1)}"

    m = re.match(r"^GigabitEthernet(\d+/\d+)$", raw, re.IGNORECASE)
    if m:
        return f"Gi {m.group(1)}"

    return raw


# =============================================================================
# CDP PARSING
# =============================================================================

def parse_cdp_neighbors(cdp_output: str) -> dict:
    """
    Parse 'show cdp neighbors detail' output into a dict keyed by
    local interface name.

    Returns:
        {
            "Ethernet0/0": {
                "neighbor_host": "R2",
                "remote_intf":   "Eth 0/1",
                "description":   "R2 Eth 0/1",
            },
            ...
        }
    """
    neighbors = {}
    entries = re.split(r"-{10,}", cdp_output)

    for entry in entries:
        if not entry.strip():
            continue

        local_match = re.search(
            r"Interface:\s+(Ethernet[\d/]+|GigabitEthernet[\d/]+)",
            entry, re.IGNORECASE
        )
        remote_match = re.search(
            r"Port ID \(outgoing port\):\s+(\S+)",
            entry, re.IGNORECASE
        )
        neighbor_match = re.search(
            r"Device ID:\s+(\S+)",
            entry, re.IGNORECASE
        )

        if not (local_match and remote_match and neighbor_match):
            continue

        local_intf   = local_match.group(1).strip()
        remote_intf  = normalize_interface(remote_match.group(1).strip())
        neighbor_raw = neighbor_match.group(1).strip()
        neighbor     = normalize_hostname(neighbor_raw)

        if neighbor_raw in OOB_HOSTNAMES or neighbor in OOB_HOSTNAMES:
            description = "OOB Management"
        else:
            description = f"{neighbor} {remote_intf}"

        neighbors[local_intf] = {
            "neighbor_host": neighbor,
            "remote_intf":   remote_intf,
            "description":   description,
        }

    return neighbors


# =============================================================================
# INTERFACE INVENTORY
# =============================================================================

def get_all_interfaces(connection) -> list:
    """
    Return a list of all Ethernet interface names using
    'show interfaces description'. This works on both routers and
    IOL switches where 'show ip interface brief' may omit unrouted
    interfaces.
    """
    # Use a generous read_timeout and expect_string to handle IOL devices
    # with hostnames containing underscores that trip up prompt detection.
    output = connection.send_command(
        "show interfaces description",
        read_timeout=30,
    )
    interfaces = []
    for line in output.splitlines():
        # Match lines starting with Et (IOL switch short form) or Ethernet
        m = re.match(r"^(Et[\d/]+|Ethernet[\d/]+)\s", line.strip(), re.IGNORECASE)
        if m:
            raw = m.group(1)
            # Expand IOL switch short form: Et0/0 → Ethernet0/0
            if raw.lower().startswith("et") and not raw.lower().startswith("ethernet"):
                raw = "Ethernet" + raw[2:]
            interfaces.append(raw)
    return interfaces


# =============================================================================
# EXEMPT INTERFACES
# =============================================================================

# Interfaces that must never be shut down regardless of CDP neighbor state.
# OOB_SW01 Ethernet0/0 bridges the work PC to the EVE-NG environment via
# Cloud0 — it has no CDP neighbor but must stay up at all times.
# These interfaces receive a fixed description instead of UNUSED + shutdown.
# Keyed as {device_name: {interface_name: description}}
EXEMPT_INTERFACES = {
    "OOB_SW01": {"Ethernet0/0": "NAMS"},
}


# =============================================================================
# CONFIG GENERATION
# =============================================================================

def build_config_commands(device_name: str,
                          all_interfaces: list,
                          cdp_neighbors: dict) -> list:
    """
    Build a flat list of IOS config commands for all interfaces.

    With CDP neighbor    → description <name> Eth X/X  (or OOB Management)
    Exempt, no neighbor  → skipped entirely (no description, no shutdown)
    Without CDP neighbor → description UNUSED + shutdown
    """
    exempt = EXEMPT_INTERFACES.get(device_name, {})
    commands = []
    for intf in all_interfaces:
        if intf in cdp_neighbors:
            commands.append(f"interface {intf}")
            commands.append(f" description {cdp_neighbors[intf]['description']}")
        elif intf in exempt:
            # Infrastructure interface — apply fixed description, no shutdown.
            commands.append(f"interface {intf}")
            commands.append(f" description {exempt[intf]}")
        else:
            commands.append(f"interface {intf}")
            commands.append(f" description UNUSED")
            commands.append(f" shutdown")
    return commands


# =============================================================================
# PER-DEVICE PROCESSING
# =============================================================================

def process_device(device_name: str, host_data: dict,
                   default_creds: dict, dry_run: bool) -> bool:
    """
    Connect to a single device, parse CDP, build and optionally push config.
    Returns True on success, False on failure.
    """
    dns_name = host_data.get("dns_name", "")
    creds    = host_data.get("credentials", default_creds)
    username = creds.get("username", "netadmin")
    password = creds.get("password", "admin")

    print(f"\n{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  {device_name}  ({dns_name}){RESET}")
    print(f"{CYAN}{'='*60}{RESET}")

    conn_params = {
        "device_type":         "cisco_ios",
        "host":                dns_name,
        "username":            username,
        "password":            password,
        "global_delay_factor": GLOBAL_DELAY_FACTOR,
        "conn_timeout":        CONN_TIMEOUT,
        # Disable fast_cli — IOL devices are slow and fast_cli can cause
        # prompt detection failures, especially on hostnames with underscores.
        "fast_cli":            False,
    }

    try:
        print(f"  {CYAN}[INFO]{RESET} Connecting...")
        connection = ConnectHandler(**conn_params)
        connection.enable()

        # Pull CDP neighbors
        print(f"  {CYAN}[INFO]{RESET} Running: show cdp neighbors detail")
        cdp_output    = connection.send_command(
            "show cdp neighbors detail",
            read_timeout=60,
        )
        cdp_neighbors = parse_cdp_neighbors(cdp_output)
        print(f"  {CYAN}[INFO]{RESET} CDP neighbors found: {len(cdp_neighbors)}")
        for intf, info in cdp_neighbors.items():
            print(f"    {intf:20s} → {info['description']}")

        # Pull all interfaces
        all_interfaces = get_all_interfaces(connection)
        print(f"  {CYAN}[INFO]{RESET} Total Ethernet interfaces: {len(all_interfaces)}")

        # Build config
        exempt       = EXEMPT_INTERFACES.get(device_name, {})
        commands     = build_config_commands(device_name, all_interfaces, cdp_neighbors)
        unused_count = sum(
            1 for i in all_interfaces
            if i not in cdp_neighbors and i not in exempt
        )
        print(f"  {CYAN}[INFO]{RESET} Interfaces to label UNUSED + shutdown: {unused_count}")

        if dry_run:
            print(f"\n  {YELLOW}--- DRY RUN: commands that would be pushed ---{RESET}")
            for cmd in commands:
                print(f"    {cmd}")
        else:
            print(f"  {CYAN}[INFO]{RESET} Pushing interface descriptions...")
            # OOB_SW01 (and potentially other IOL switches) drop the SSH
            # session when receiving large config blocks. Write the config
            # to a file for console paste instead.
            console_devices = {"OOB_SW01", "OOB-SW01"}
            if device_name in console_devices:
                config_file = os.path.join(SCRIPT_DIR, f"{device_name}_label_config.txt")
                with open(config_file, "w") as f:
                    f.write("configure terminal\n")
                    for cmd in commands:
                        f.write(f"{cmd}\n")
                    f.write("end\n")
                    f.write("write memory\n")
                print(f"  {YELLOW}[WARN]{RESET} {device_name} drops SSH on large config pushes.")
                print(f"  {CYAN}[INFO]{RESET} Config written to: {config_file}")
                print(f"  {CYAN}[INFO]{RESET} Paste this file into the EVE-NG console to apply.")
            else:
                connection.send_config_set(
                    commands,
                    cmd_verify=False,
                    delay_factor=4,
                    read_timeout=120,
                )
                connection.send_command("write memory", read_timeout=30)
            print(f"  {CYAN}[INFO]{RESET} Configuration saved.")

        connection.disconnect()
        print(f"  {GREEN}{BOLD}[PASS]{RESET} {device_name} complete.")
        return True

    except NetmikoTimeoutException:
        print(f"  {RED}[FAIL]{RESET} {device_name} — connection timed out ({dns_name})")
        return False
    except NetmikoAuthenticationException:
        print(f"  {RED}[FAIL]{RESET} {device_name} — authentication failed")
        return False
    except Exception as exc:
        print(f"  {RED}[FAIL]{RESET} {device_name} — {exc}")
        return False


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="NAMS26 Utility — Label all interfaces via CDP neighbor discovery."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print commands only — no SSH push.",
    )
    parser.add_argument(
        "--device",
        nargs="+",
        metavar="NAME",
        help="Target specific devices by name (e.g. --device R1 COSW-01).",
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
    if args.device:
        targets = {}
        for name in args.device:
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
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode      = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{CYAN}{BOLD}  NAMS26 — Interface Labeling via CDP{RESET}")
    print(f"{CYAN}{BOLD}  Mode    : {mode}{RESET}")
    print(f"{CYAN}{BOLD}  Started : {timestamp}{RESET}")
    print(f"{CYAN}{BOLD}  Devices : {', '.join(targets.keys())}{RESET}")
    print(f"{CYAN}{BOLD}{'='*60}{RESET}")

    results = {}
    for device_name, host_data in targets.items():
        ok = process_device(device_name, host_data, default_creds, dry_run=args.dry_run)
        results[device_name] = "PASS" if ok else "FAIL"

    # Summary
    print(f"\n{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{CYAN}{'='*60}{RESET}")
    for name, status in results.items():
        color = GREEN if status == "PASS" else RED
        print(f"  {color}{BOLD}{status}{RESET}  {name}")

    failed = [n for n, s in results.items() if s == "FAIL"]
    print(f"{CYAN}{'─'*60}{RESET}")
    if failed:
        print(f"  {RED}{len(failed)} device(s) failed: {', '.join(failed)}{RESET}\n")
        sys.exit(1)
    else:
        print(f"  {GREEN}{BOLD}All devices completed successfully.{RESET}\n")


if __name__ == "__main__":
    main()
