#!/usr/bin/env python3
"""
Module   : 02 — EIGRP Classic Mode
File     : modules/02_eigrp_netmiko/scripts/verify_eigrp_classicB.py
Purpose  : Connect to lab routers via Netmiko and verify EIGRP Classic Mode
           operational state. Compares live output against expected state
           defined in eigrp_classic.yaml and reports PASS / FAIL per check.
           All output is mirrored to a timestamped log file in logs/.

Usage:
    # Verify all routers — all checks
    python verify_eigrp_classicB.py

    # Verify specific routers
    python verify_eigrp_classicB.py --router R1 R2

    # Run specific check(s) only
    python verify_eigrp_classicB.py --check neighbors
    python verify_eigrp_classicB.py --check interfaces
    python verify_eigrp_classicB.py --check routes
    python verify_eigrp_classicB.py --check neighbors routes

    # Route lookup — show ip route | include <target>
    python verify_eigrp_classicB.py --route 101.1.4.0
    python verify_eigrp_classicB.py --route 10.1.1.1

    # List all available checks
    python verify_eigrp_classicB.py --list-checks

    # Combine flags
    python verify_eigrp_classicB.py --router R1 R4 --check neighbors --route 101.1.4.0

Checks:
    neighbors  — Verify expected EIGRP neighbors are present (from YAML)
    interfaces — Display EIGRP-enabled interfaces and their state
    routes     — Verify EIGRP network statements against live interface state
    route      — Show ip route output filtered by a specific IP or network

Validation Logic:
    - neighbors : Cross-references static_neighbors in YAML against
                  live 'show ip eigrp neighbors' output. Reports PASS if
                  all expected neighbor IPs are present, FAIL with detail
                  for any that are missing.
    - routes    : Posts 'show ip route eigrp' for informational review.
                  Then runs 'show run | s router eigrp' to collect advertised
                  network/wildcard pairs, and 'show ip interface' to collect
                  live interface state and IP assignments. For each advertised
                  network, finds the matching interface by subnet containment
                  (wildcard-aware IP math) and reports:
                    PASS — interface owning that network is up/up
                    WARN — interface exists but is not up/up
                    FAIL — no interface found that matches the network
    - interfaces: Collects and displays 'show ip eigrp interfaces' output.
                  No PASS/FAIL — informational display for visual verification.
    - route     : Runs 'show ip route | include <target>' and displays raw
                  output. Useful for spot-checking a specific prefix or host.

Logging:
    A timestamped log file is written to modules/02_eigrp_netmiko/logs/ on
    every run. The log captures the full run summary, all raw command output,
    and all PASS / WARN / FAIL / INFO result lines in plain text (no ANSI
    color codes).
"""

import os
import re
import sys
import yaml
import argparse
import ipaddress
from datetime import datetime
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR    = os.path.dirname(SCRIPT_DIR)
MODULES_DIR   = os.path.dirname(MODULE_DIR)
PROJECT_ROOT  = os.path.dirname(MODULES_DIR)

YAML_FILE     = os.path.join(MODULE_DIR, "data", "eigrp_classic.yaml")
LOG_DIR       = os.path.join(MODULE_DIR, "logs")

# =============================================================================
# AVAILABLE CHECKS
# Defined here so --list-checks and argparse validation both reference
# the same single source of truth.
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "interfaces", "routes"]

# =============================================================================
# OUTPUT FORMATTING HELPERS
# =============================================================================

# Terminal color codes — degrade gracefully if terminal doesn't support them
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# Strip ANSI escape codes for clean plain-text log output
_ANSI_RE = re.compile(r'\033\[[0-9;]*m')

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)

def passed(msg: str) -> str:
    return f"{GREEN}  [PASS]{RESET} {msg}"

def failed(msg: str) -> str:
    return f"{RED}  [FAIL]{RESET} {msg}"

def warned(msg: str) -> str:
    return f"{YELLOW}  [WARN]{RESET} {msg}"

def info(msg: str) -> str:
    return f"{CYAN}  [INFO]{RESET} {msg}"

def section(title: str, lf=None) -> None:
    lines = [
        f"\n{BOLD}  {'─' * 54}{RESET}",
        f"{BOLD}  {title}{RESET}",
        f"{BOLD}  {'─' * 54}{RESET}",
    ]
    for line in lines:
        print(line)
        if lf:
            lf.write(_strip_ansi(line) + "\n")

def device_header(device_name: str, dns_name: str, oob_ip: str, lf=None) -> None:
    bar = "=" * 60
    lines = [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}  Device : {device_name}   DNS : {dns_name}   OOB : {oob_ip}{RESET}",
        f"{BOLD}{bar}{RESET}",
    ]
    for line in lines:
        print(line)
        if lf:
            lf.write(_strip_ansi(line) + "\n")

def emit(line: str, lf=None) -> None:
    """Print a line to stdout and mirror it (without ANSI) to the log file."""
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")

def emit_raw(text: str, lf=None) -> None:
    """Print and log a block of raw command output."""
    print(f"\n{text}\n")
    if lf:
        lf.write(f"\n{text}\n\n")


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logger() -> object:
    """Create the logs directory if needed and open a timestamped log file.

    Log file path:
        modules/02_eigrp_netmiko/logs/verify_eigrp_classic_YYYYMMDD_HHMMSS.log

    Returns:
        An open file handle for writing. Caller is responsible for closing it.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"verify_eigrp_classic_{timestamp}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 02: EIGRP Classic Mode Verification\n")
    lf.write(f"Log created : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write(f"Log file    : {log_path}\n")
    lf.write("=" * 60 + "\n\n")
    print(info(f"Logging to  : {log_path}"))
    return lf


# =============================================================================
# SSH CONNECTION
# =============================================================================

def connect(device_name: str, dns_name: str, creds: dict, lf=None):
    """Establish a Netmiko SSH session to the target device.

    The SSH target is resolved via the lab DNS server (192.168.1.12) using
    the dns_name field from YAML (e.g. r1.lab). oob_ip is not used for
    connections — it is retained in YAML for documentation only.

    SSH host key verification uses ~/.ssh/known_hosts populated by
    utils/check_ssh.py as part of the standard lab pre-flight sequence.
    Run clear_known_hosts.sh followed by check_ssh.py after every EVE-NG
    lab reboot before executing verification checks.

    Args:
        device_name : Router hostname (used for error messages only).
        dns_name    : DNS name to connect to (e.g. 'r1.lab').
        creds       : Dict containing 'username' and 'password'.
        lf          : Open log file handle, or None.

    Returns:
        An open Netmiko BaseConnection object, or None on failure.
    """
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    if not os.path.isfile(known_hosts):
        emit(warned(
            f"known_hosts not found at {known_hosts} — "
            f"run utils/clear_known_hosts.sh then utils/check_ssh.py first"
        ), lf)

    params = {
        "device_type":         "cisco_ios",
        "host":                dns_name,
        "username":            creds.get("username", ""),
        "password":            creds.get("password", ""),
        # Multiplier applied to ALL of Netmiko's internal delay constants
        # (post-login settling, inter-command pause, prompt-detection loops).
        # 2.0 doubles the defaults — enough headroom for IOL without excessive waits.
        # Current: 2.0   Range: 1.0 (fastest, may miss prompts) – 5.0 (slow/remote hosts)
        "global_delay_factor": 2.0,
    }

    try:
        conn = ConnectHandler(**params)
        emit(info(f"Connected to {device_name} ({dns_name})"), lf)
        return conn
    except NetmikoTimeoutException:
        emit(failed(f"Timeout connecting to {device_name} ({dns_name})"), lf)
    except NetmikoAuthenticationException:
        emit(failed(f"Authentication failed on {device_name}"), lf)
    except Exception as exc:
        emit(failed(f"Connection error on {device_name}: {exc}"), lf)
    return None


# =============================================================================
# VERIFICATION CHECKS
# =============================================================================

def check_neighbors(conn, device_name: str, eigrp_data: dict, lf=None) -> None:
    """Verify expected EIGRP neighbors are present in live output.

    Runs 'show ip eigrp neighbors' and checks each expected neighbor IP
    (sourced from eigrp.static_neighbors in YAML) against the output.
    Reports PASS for each neighbor found, FAIL for each that is missing.

    Args:
        conn        : Active Netmiko connection.
        device_name : Router hostname (display only).
        eigrp_data  : eigrp block from YAML for this device.
        lf          : Open log file handle, or None.
    """
    section("EIGRP Neighbors — show ip eigrp neighbors", lf)

    output = conn.send_command("show ip eigrp neighbors")
    emit_raw(output, lf)

    expected_neighbors = eigrp_data.get("static_neighbors", []) or []

    if not expected_neighbors:
        emit(info("No static neighbors defined in YAML for this device — skipping validation."), lf)
        return

    for neighbor in expected_neighbors:
        expected_ip   = neighbor.get("ip", "")
        expected_intf = neighbor.get("interface", "")
        if expected_ip and expected_ip in output:
            emit(passed(f"Neighbor {expected_ip} ({expected_intf}) — PRESENT"), lf)
        else:
            emit(failed(f"Neighbor {expected_ip} ({expected_intf}) — NOT FOUND in output"), lf)


def check_interfaces(conn, device_name: str, eigrp_data: dict, lf=None) -> None:
    """Display EIGRP interface state from live output.

    Runs 'show ip eigrp interfaces' and displays the raw output.
    This is an informational check — no PASS/FAIL validation is applied.
    The student visually confirms which interfaces are EIGRP-active and
    compares against the no_passive_interfaces list in the YAML.

    Args:
        conn        : Active Netmiko connection.
        device_name : Router hostname (display only).
        eigrp_data  : eigrp block from YAML for this device.
        lf          : Open log file handle, or None.
    """
    section("EIGRP Interfaces — show ip eigrp interfaces", lf)

    output = conn.send_command("show ip eigrp interfaces")
    emit_raw(output, lf)

    # Informational: show which interfaces should be active per YAML
    no_passive      = eigrp_data.get("no_passive_interfaces", []) or []
    passive_default = eigrp_data.get("passive_default", False) or False
    passive_list    = eigrp_data.get("passive_interfaces", []) or []

    if passive_default:
        emit(info("YAML: passive-interface default is SET"), lf)
        if no_passive:
            emit(info(f"YAML: Expected active interfaces: {', '.join(no_passive)}"), lf)
    elif passive_list:
        emit(info(f"YAML: Explicitly passive interfaces: {', '.join(passive_list)}"), lf)
    else:
        emit(info("YAML: No passive-interface configuration defined."), lf)


# =============================================================================
# HELPER — Parse live interface state from 'show ip interface'
# =============================================================================

def parse_interface_state(raw: str) -> dict:
    """Parse 'show ip interface' output into a per-interface state dict.

    Walks the output line by line, tracking the current interface name.
    Two line patterns are matched:

        Ethernet0/0 is up, line protocol is up
          Internet address is 10.12.12.1/24

    Builds a dict keyed by interface name:
        {
            "Ethernet0/0": {"ip": "10.12.12.1/24", "up": True,
                            "phys": "up", "proto": "up"},
            ...
        }

    Interfaces without an IP line are recorded with ip=None and up=False.

    Args:
        raw : Raw string output from 'show ip interface'.

    Returns:
        Dict of interface name -> state dict.
    """
    intf_re = re.compile(
        r'^(?P<intf>\S+)\s+is\s+(?P<phys>\S+),\s+line protocol is\s+(?P<proto>\S+)',
        re.IGNORECASE
    )
    ip_re = re.compile(
        r'Internet address is\s+(?P<ip>\S+)',
        re.IGNORECASE
    )

    interfaces   = {}
    current_intf = None

    for line in raw.splitlines():
        m_intf = intf_re.match(line.strip())
        if m_intf:
            current_intf = m_intf.group("intf")
            phys  = m_intf.group("phys").lower()
            proto = m_intf.group("proto").lower()
            up    = (phys == "up" and proto == "up")
            interfaces[current_intf] = {
                "ip"    : None,
                "up"    : up,
                "phys"  : phys,
                "proto" : proto,
            }
            continue

        m_ip = ip_re.search(line)
        if m_ip and current_intf:
            interfaces[current_intf]["ip"] = m_ip.group("ip")

    return interfaces


# =============================================================================
# HELPER — Wildcard-aware subnet containment check
# =============================================================================

def ip_in_eigrp_network(intf_ip_cidr: str, network: str, wildcard: str) -> bool:
    """Return True if the interface IP falls within the EIGRP network/wildcard.

    Converts the wildcard mask to a netmask by bitwise inversion, then uses
    Python's ipaddress library for subnet containment.

    Example:
        intf_ip_cidr = "150.1.32.1/19"
        network      = "150.1.32.0"
        wildcard     = "0.0.31.255"
        -> True  (0.0.31.255 inverted = 255.255.224.0 = /19)

    Args:
        intf_ip_cidr : Interface IP in CIDR notation, e.g. "10.12.12.1/24".
        network      : EIGRP network address, e.g. "10.12.12.0".
        wildcard     : EIGRP wildcard mask, e.g. "0.0.0.255".

    Returns:
        True if the interface IP belongs to the EIGRP network, else False.
    """
    try:
        wc_int    = int(ipaddress.IPv4Address(wildcard))
        mask_int  = 0xFFFFFFFF ^ wc_int
        netmask   = str(ipaddress.IPv4Address(mask_int))
        eigrp_net = ipaddress.IPv4Network(f"{network}/{netmask}", strict=False)
        intf_ip   = ipaddress.IPv4Interface(intf_ip_cidr).ip
        return intf_ip in eigrp_net
    except Exception:
        return False


# =============================================================================
# HELPER — Classful default wildcard inference
# =============================================================================

def classful_wildcard(network: str) -> str:
    """Return the classful default wildcard mask for a network address.

    IOS omits the wildcard from 'show run | s router eigrp' when auto-summary
    is active and the network is a classful boundary. In that case the implied
    wildcard is the inverse of the classful default mask:

        Class A (1–126)   → 255.0.0.0   → wildcard 0.255.255.255
        Class B (128–191) → 255.255.0.0 → wildcard 0.0.255.255
        Class C (192–223) → 255.255.255.0 → wildcard 0.0.0.255

    Args:
        network : Network address string, e.g. "2.0.0.0" or "192.1.23.0".

    Returns:
        Wildcard mask string, e.g. "0.255.255.255".
    """
    try:
        first_octet = int(network.split(".")[0])
        if 1 <= first_octet <= 126:
            return "0.255.255.255"
        elif 128 <= first_octet <= 191:
            return "0.0.255.255"
        else:
            return "0.0.0.255"
    except Exception:
        return "0.0.0.255"


# =============================================================================
# MAIN CHECK — Routes
# =============================================================================

def check_routes(conn, device_name: str, eigrp_data: dict, lf=None) -> None:
    """Verify EIGRP advertised networks against live interface state.

    Step 1 — Posts 'show ip route eigrp' for informational review.
              No validation is applied to this output.

    Step 2 — Runs 'show run | s router eigrp' to collect the live
              network/wildcard statements actually configured on the device.

    Step 3 — Runs 'show ip interface' to build a map of every interface ->
              IP address + up/up state.

    Step 4 — For each advertised network/wildcard, finds the interface whose
              IP falls within that network using wildcard-aware IP math, then
              reports:
                PASS — interface is up/up
                WARN — interface exists but is not up/up (up/down or down/down)
                FAIL — no interface on this device matches the network

    Args:
        conn        : Active Netmiko connection.
        device_name : Router hostname (display only).
        eigrp_data  : eigrp block from YAML for this device.
        lf          : Open log file handle, or None.
    """

    # -------------------------------------------------------------------------
    # Step 1 — Informational: EIGRP route table
    # -------------------------------------------------------------------------
    section("EIGRP Route Table — show ip route eigrp  (informational)", lf)
    route_output = conn.send_command("show ip route eigrp")
    emit_raw(route_output, lf)

    # -------------------------------------------------------------------------
    # Step 2 — Live EIGRP network statements from running config
    # -------------------------------------------------------------------------
    section("EIGRP Network / Interface State Validation", lf)

    eigrp_run = conn.send_command("show run | s router eigrp")
    emit_raw(eigrp_run, lf)

    # Parse network statements — two forms exist on IOS:
    #   With wildcard    : "  network 10.1.1.0 0.0.0.255"
    #   Without wildcard : "  network 2.0.0.0"  (classful / auto-summary)
    # Two-token form captured first; single-token falls back to classful
    # default wildcard inference via classful_wildcard().
    net_re_wc = re.compile(
        r'^\s+network\s+(?P<network>\S+)\s+(?P<wildcard>\d+\.\d+\.\d+\.\d+)',
        re.MULTILINE
    )
    net_re_cls = re.compile(
        r'^\s+network\s+(?P<network>\d+\.\d+\.\d+\.\d+)\s*$',
        re.MULTILINE
    )

    advertised      = []
    matched_with_wc = set()

    for m in net_re_wc.finditer(eigrp_run):
        advertised.append({
            "network"  : m.group("network"),
            "wildcard" : m.group("wildcard"),
            "classful" : False,
        })
        matched_with_wc.add(m.group("network"))

    for m in net_re_cls.finditer(eigrp_run):
        net = m.group("network")
        if net in matched_with_wc:
            continue
        advertised.append({
            "network"  : net,
            "wildcard" : classful_wildcard(net),
            "classful" : True,
        })

    if not advertised:
        emit(info("No network statements found in 'show run | s router eigrp' — skipping validation."), lf)
        return

    # -------------------------------------------------------------------------
    # Step 3 — Live interface state and IP assignments
    # -------------------------------------------------------------------------
    intf_raw = conn.send_command("show ip interface")
    intf_map = parse_interface_state(intf_raw)

    if not intf_map:
        emit(failed("Could not parse interface state — 'show ip interface' returned no usable output."), lf)
        return

    # -------------------------------------------------------------------------
    # Step 4 — Cross-reference each network against interface state
    # -------------------------------------------------------------------------
    for entry in advertised:
        network  = entry["network"]
        wildcard = entry["wildcard"]
        classful = entry["classful"]
        label    = f"{network} {wildcard}" + (" (classful inferred)" if classful else "")

        match_intf = None
        match_data = None
        for intf_name, intf_data in intf_map.items():
            if intf_data["ip"] and ip_in_eigrp_network(intf_data["ip"], network, wildcard):
                match_intf = intf_name
                match_data = intf_data
                break

        if match_intf is None:
            emit(failed(
                f"Network {label} — "
                f"no interface found with a matching IP on {device_name}"
            ), lf)
        elif match_data["up"]:
            emit(passed(
                f"Network {label} — "
                f"{match_intf} ({match_data['ip']}) is up/up"
            ), lf)
        else:
            emit(warned(
                f"Network {label} — "
                f"{match_intf} ({match_data['ip']}) is "
                f"{match_data['phys']}/{match_data['proto']}"
            ), lf)


def check_route_lookup(conn, device_name: str, target: str, lf=None) -> None:
    """Run a filtered route lookup for a specific IP or network prefix.

    Runs 'show ip route | include <target>' and displays the raw output.
    Useful for spot-checking reachability to a specific destination during
    live lab demonstration.

    Args:
        conn        : Active Netmiko connection.
        device_name : Router hostname (display only).
        target      : IP address or network prefix string to filter on.
        lf          : Open log file handle, or None.
    """
    section(f"Route Lookup — show ip route | include {target}", lf)

    output = conn.send_command(f"show ip route | include {target}")

    if output.strip():
        emit_raw(output, lf)
        emit(passed(f"'{target}' found in routing table on {device_name}"), lf)
    else:
        emit("\n  (no output)\n", lf)
        emit(failed(f"'{target}' NOT found in routing table on {device_name}"), lf)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:

    # -------------------------------------------------------------------------
    # Argument parsing
    # -------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description=(
            "Module 02 — EIGRP Classic Mode Verification (B)\n"
            "Connects to lab routers and verifies EIGRP operational state\n"
            "against expected values defined in eigrp_classic.yaml.\n"
            "All output is mirrored to a timestamped log file in logs/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help="Target one or more routers by hostname (e.g. --router R1 R2). "
             "Defaults to all devices in YAML.",
    )
    parser.add_argument(
        "--check",
        nargs="*",
        metavar="CHECK",
        help=(
            f"One or more verification checks to run: "
            f"{', '.join(AVAILABLE_CHECKS)}. "
            f"Defaults to all checks."
        ),
    )
    parser.add_argument(
        "--route",
        metavar="IP_OR_PREFIX",
        help="Run 'show ip route | include <IP_OR_PREFIX>' on target routers.",
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="List all available verification checks and exit.",
    )
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # --list-checks (no log file needed)
    # -------------------------------------------------------------------------
    if args.list_checks:
        print(f"\n{BOLD}Available verification checks:{RESET}\n")
        descriptions = {
            "neighbors"  : "Verify expected EIGRP neighbors (validated against YAML static_neighbors)",
            "interfaces" : "Display EIGRP-active interfaces (informational — compares to YAML passive config)",
            "routes"     : "Post EIGRP route table (informational) + validate advertised networks against live interface UP/UP state",
        }
        for name, desc in descriptions.items():
            print(f"  {CYAN}{name:<14}{RESET} {desc}")
        print(f"\n  {CYAN}--route <IP>{RESET}   Filtered route lookup: show ip route | include <IP>\n")
        sys.exit(0)

    # -------------------------------------------------------------------------
    # Validate --check values
    # -------------------------------------------------------------------------
    if args.check:
        invalid_checks = [c for c in args.check if c not in AVAILABLE_CHECKS]
        if invalid_checks:
            print(f"[ERROR] Unknown check(s): {invalid_checks}")
            print(f"        Valid options: {AVAILABLE_CHECKS}")
            print(f"        Run with --list-checks to see descriptions.")
            sys.exit(1)
        checks_to_run = args.check
    else:
        checks_to_run = AVAILABLE_CHECKS

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

    # Inject default credentials for devices not defining their own
    for device_data in devices.values():
        if not device_data.get("credentials"):
            device_data["credentials"] = default_creds

    # -------------------------------------------------------------------------
    # Resolve target routers
    # Accepts YAML key (R1), case-insensitive short name (r1), or DNS name
    # (r1.lab) — mirrors the alias resolution pattern in check_ssh.py.
    # -------------------------------------------------------------------------
    def resolve_router(token: str) -> str | None:
        """Return the YAML device key for a given input token, or None.

        Resolution order:
          1. Exact match against YAML key           (R1)
          2. Case-insensitive match against YAML key (r1 → R1)
          3. Case-insensitive match against dns_name (r1.lab or R1.lab → R1)
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
        print("[ERROR] No valid target routers to process.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Open log file
    # -------------------------------------------------------------------------
    lf = setup_logger()

    # -------------------------------------------------------------------------
    # Print and log run summary
    # -------------------------------------------------------------------------
    summary_lines = [
        f"\nNAMS26 — Module 02: EIGRP Classic Mode Verification (B)",
        f"Targets : {', '.join(target_routers)}",
        f"Checks  : {', '.join(checks_to_run)}"
        + (f"  +  route lookup: {args.route}" if args.route else ""),
    ]
    for line in summary_lines:
        emit(line, lf)

    # -------------------------------------------------------------------------
    # Per-device verification loop
    # -------------------------------------------------------------------------
    try:
        for device_name in target_routers:
            device_data = devices[device_name]
            oob_ip      = device_data.get("oob_ip", "")
            dns_name    = device_data.get("dns_name", "")
            creds       = device_data.get("credentials", default_creds)
            eigrp_data  = device_data.get("eigrp", {})

            if not dns_name:
                emit(failed(f"No dns_name defined for {device_name} in YAML — skipping."), lf)
                continue

            device_header(device_name, dns_name, oob_ip, lf)

            conn = connect(device_name, dns_name, creds, lf)
            if conn is None:
                emit(failed(f"Skipping all checks on {device_name} — connection failed."), lf)
                continue

            try:
                if "neighbors" in checks_to_run:
                    check_neighbors(conn, device_name, eigrp_data, lf)

                if "interfaces" in checks_to_run:
                    check_interfaces(conn, device_name, eigrp_data, lf)

                if "routes" in checks_to_run:
                    check_routes(conn, device_name, eigrp_data, lf)

                if args.route:
                    check_route_lookup(conn, device_name, args.route, lf)

            finally:
                conn.disconnect()
                emit(info(f"Disconnected from {device_name}"), lf)

        emit(f"\n{'=' * 60}\nVerification complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
