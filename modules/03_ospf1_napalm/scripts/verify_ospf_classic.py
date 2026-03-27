#!/usr/bin/env python3
"""
Module   : 03 — OSPF Classic Mode
File     : modules/03_ospf1_napalm/scripts/verify_ospf_classic.py
Purpose  : Connect to lab routers via NAPALM and verify OSPF Classic Mode
           operational state. Compares live output against expected state
           defined in ospf_classic.yaml and reports PASS / FAIL per check.
           All output is mirrored to a timestamped log file in logs/.

Usage:
    # Verify all routers — all checks
    python verify_ospf_classic.py

    # Verify specific routers
    python verify_ospf_classic.py --router R1 R2

    # Run specific check(s) only
    python verify_ospf_classic.py --check neighbors
    python verify_ospf_classic.py --check interfaces
    python verify_ospf_classic.py --check routes
    python verify_ospf_classic.py --check lsdb
    python verify_ospf_classic.py --check neighbors routes

    # Route lookup — show ip route | include <target>
    python verify_ospf_classic.py --route 192.1.100.0
    python verify_ospf_classic.py --route 1.1.1.1

    # List all available checks
    python verify_ospf_classic.py --list-checks

    # Combine flags
    python verify_ospf_classic.py --router R1 R8 --check neighbors lsdb --route 9.0.0.0

Checks:
    neighbors  — Verify expected OSPF neighbors are FULL (from YAML networks)
    interfaces — Validate OSPF interface state: area, network type, priority,
                 and DR/BDR role against YAML. Reports PASS/WARN/FAIL per
                 interface with DR/BDR Router ID identification.
    routes     — Formatted OSPF route table (Intra/Inter) + validate network
                 statements against live interface state.
    lsdb       — Display OSPF Link State Database (informational)

Validation Logic:
    - neighbors : Runs 'show ip ospf neighbor' and validates that each
                  OSPF-enabled interface (non-OOB, non-loopback, non-shutdown)
                  has at least one neighbor in FULL state. Reports PASS if
                  FULL adjacency exists on the interface, WARN if neighbors
                  exist but none are FULL, FAIL if no neighbors are present.
                  2WAY/DROTHER between DROTHERs on multi-access segments is
                  correctly identified as PASS. FULL/-  on point-to-point
                  interfaces (no DR election) is normalised and reported PASS.
    - interfaces: Runs 'show ip ospf interface' (full) and 'show ip ospf
                  neighbor' per device. Validates area, network type, and
                  priority (when set in YAML) against live state. Identifies
                  DR and BDR by Router ID. Point-to-point interfaces report
                  P2P/PASS. Priority mismatches are WARN; area or network-type
                  mismatches are FAIL.
    - routes    : Fetches 'show ip route ospf' and reformats into a structured
                  table (Type | Destination | Via | Interface | Cost | Age).
                  ECMP paths shown as additional indented rows. No OSPF routes
                  is WARN. Then validates each OSPF network statement from YAML
                  against live interface state. Reports PASS/WARN/FAIL per
                  network based on interface up/up status.
    - lsdb      : Runs 'show ip ospf database' (informational). Displays the
                  full LSDB for visual verification of LSA types and counts.

Summary:
    A per-device, per-check summary table is printed at the end of every run.
    Per-device result is the worst-case across all interfaces for that check
    (FAIL beats WARN beats PASS). lsdb is always INFO.

Logging:
    A timestamped log file is written to NAMS26/logs/ on every run.
    The log captures the full run summary, all raw command output, and all
    PASS / WARN / FAIL / INFO result lines in plain text (no ANSI color codes).
"""

import os
import re
import sys
import yaml
import argparse
import ipaddress
from datetime import datetime
from napalm import get_network_driver
from napalm.base.exceptions import ConnectionException

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(MODULE_DIR)

YAML_FILE    = os.path.join(MODULE_DIR, "data", "ospf_classic.yaml")
LOG_DIR      = os.path.join(PROJECT_ROOT, "logs")

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# AVAILABLE CHECKS
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "interfaces", "routes", "lsdb"]

# =============================================================================
# OUTPUT FORMATTING HELPERS
# =============================================================================

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

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
        NAMS26/logs/verify_ospf_classic_YYYYMMDD_HHMMSS.log

    Returns:
        An open file handle for writing. Caller is responsible for closing it.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"verify_ospf_classic_{timestamp}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 03: OSPF Classic Mode Verification\n")
    lf.write(f"Log created : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write(f"Log file    : {log_path}\n")
    lf.write("=" * 60 + "\n\n")
    print(info(f"Logging to  : {log_path}"))
    return lf


# =============================================================================
# NAPALM CONNECTION
# =============================================================================

def connect(device_name: str, dns_name: str, creds: dict, lf=None):
    """Establish a NAPALM IOS driver session to the target device.

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
        An open NAPALM NetworkDriver object, or None on failure.
    """
    if not os.path.isfile(KNOWN_HOSTS_FILE):
        emit(warned(
            f"known_hosts not found at {KNOWN_HOSTS_FILE} — "
            f"run utils/clear_known_hosts.sh then utils/check_ssh.py first"
        ), lf)

    driver = get_network_driver("ios")

    try:
        device = driver(
            hostname=dns_name,
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            optional_args={"global_delay_factor": 2.0},
        )
        device.open()
        emit(info(f"Connected to {device_name} ({dns_name})"), lf)
        return device
    except ConnectionException as exc:
        emit(failed(f"Connection failed to {device_name} ({dns_name}): {exc}"), lf)
    except Exception as exc:
        emit(failed(f"Connection error on {device_name}: {exc}"), lf)
    return None


# =============================================================================
# HELPER — Parse live interface state from 'show ip interface'
# =============================================================================

def parse_interface_state(raw: str) -> dict:
    """Parse 'show ip interface' output into a per-interface state dict.

    Walks the output line by line, tracking the current interface name.
    Two line patterns are matched:

        Ethernet0/0 is up, line protocol is up
          Internet address is 192.1.100.1/24

    Builds a dict keyed by interface name:
        {
            "Ethernet0/0": {"ip": "192.1.100.1/24", "up": True,
                            "phys": "up", "proto": "up"},
            ...
        }

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

def ip_in_ospf_network(intf_ip_cidr: str, network: str, wildcard: str) -> bool:
    """Return True if the interface IP falls within the OSPF network/wildcard.

    Converts the wildcard mask to a netmask by bitwise inversion, then uses
    Python's ipaddress library for subnet containment.

    Example:
        intf_ip_cidr = "192.1.100.1/24"
        network      = "192.1.100.0"
        wildcard     = "0.0.0.255"
        -> True

    Args:
        intf_ip_cidr : Interface IP in CIDR notation, e.g. "192.1.100.1/24".
        network      : OSPF network address, e.g. "192.1.100.0".
        wildcard     : OSPF wildcard mask, e.g. "0.0.0.255".

    Returns:
        True if the interface IP belongs to the OSPF network, else False.
    """
    try:
        wc_int    = int(ipaddress.IPv4Address(wildcard))
        mask_int  = 0xFFFFFFFF ^ wc_int
        netmask   = str(ipaddress.IPv4Address(mask_int))
        ospf_net  = ipaddress.IPv4Network(f"{network}/{netmask}", strict=False)
        intf_ip   = ipaddress.IPv4Interface(intf_ip_cidr).ip
        return intf_ip in ospf_net
    except Exception:
        return False


# =============================================================================
# HELPERS — Result ranking
# =============================================================================

_RANK = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}

def _worst(a: str, b: str) -> str:
    """Return the worse of two result tokens. FAIL > WARN > PASS/INFO."""
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


# =============================================================================
# VERIFICATION CHECKS
# =============================================================================

def check_neighbors(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Verify OSPF neighbors are in expected state on each active interface.

    Runs 'show ip ospf neighbor' and validates that each OSPF-enabled
    interface (non-OOB, non-loopback, non-shutdown, with an IP) has at least
    one neighbor in an acceptable adjacency state.

    The neighbor table is parsed line by line and grouped by interface.
    Per-interface verdict:

      PASS — at least one neighbor is FULL (any DR role, including FULL/-)
             This covers FULL/DR, FULL/BDR, FULL/DROTHER, and FULL/-
             (point-to-point, no DR election).
      PASS — all neighbors are 2WAY/DROTHER (valid on multi-access segments
             where this router is also a DROTHER; the DR/BDR adjacencies are
             FULL as seen from those routers).
      WARN — neighbors present but none are FULL and not all are 2WAY/DROTHER.
      FAIL — no neighbors found on the interface.

    IOS quirk: point-to-point interfaces show the state as "FULL/  -" with
    embedded spaces. These are normalised to "FULL/-" before parsing so the
    regex and startswith("FULL") check work correctly.

    Returns the worst-case result token across all interfaces:
        "PASS", "WARN", "FAIL", or "INFO" (no active interfaces found).

    Args:
        conn        : Open NAPALM device object.
        device_name : Router hostname (display only).
        device_data : Full device dict from YAML.
        lf          : Open log file handle, or None.
    """
    section("OSPF Neighbors — show ip ospf neighbor", lf)

    output = conn.cli(["show ip ospf neighbor"])["show ip ospf neighbor"]
    emit_raw(output, lf)

    oob_interface = device_data.get("oob_interface", "")
    interfaces    = device_data.get("interfaces", {})

    # Build list of interfaces expected to have OSPF neighbors:
    # active (not shutdown), has an IP, not OOB, not loopback
    expected_intfs = []
    for intf_name, intf in interfaces.items():
        if intf_name == oob_interface:
            continue
        if "Loopback" in intf_name:
            continue
        if intf.get("shutdown", True):
            continue
        if not intf.get("ip", ""):
            continue
        expected_intfs.append(intf_name)

    if not expected_intfs:
        emit(info("No active non-loopback OSPF interfaces found in YAML — "
                  "skipping neighbor validation."), lf)
        return "INFO"

    # Parse neighbor table into dict keyed by interface name.
    # IOS line format:
    #   <neighbor-id>  <pri>  <state>  <dead-time>  <address>  <interface>
    # "FULL/  -" (p2p, no DR role) contains spaces — normalise to "FULL/-"
    # before applying the regex so group(3) captures the full state token.
    neighbor_line_re = re.compile(
        r'^\s*(\S+)\s+(\d+)\s+(\S+)\s+\S+\s+\S+\s+(\S+)\s*$'
    )

    # neighbors_by_intf: { "Ethernet0/0": ["FULL/DR", "2WAY/DROTHER", ...] }
    neighbors_by_intf: dict[str, list[str]] = {}

    for line in output.splitlines():
        # Normalise IOS p2p state "FULL/  -" → "FULL/-"
        normalized = re.sub(r'FULL/\s+-', 'FULL/-', line)
        m = neighbor_line_re.match(normalized)
        if not m:
            continue
        state = m.group(3)   # e.g. "FULL/DR", "FULL/-", "2WAY/DROTHER"
        intf  = m.group(4)   # e.g. "Ethernet0/0", "Serial2/0"
        neighbors_by_intf.setdefault(intf, []).append(state)

    worst = "PASS"

    for intf_name in expected_intfs:
        states = neighbors_by_intf.get(intf_name, [])

        if not states:
            emit(failed(f"{intf_name} — no OSPF neighbor found"), lf)
            worst = _worst(worst, "FAIL")
            continue

        has_full    = any(s.upper().startswith("FULL") for s in states)
        all_2way_dr = all(s.upper() == "2WAY/DROTHER" for s in states)

        if has_full:
            emit(passed(f"{intf_name} — FULL adjacency present"), lf)
        elif all_2way_dr:
            # All neighbours are DROTHERs — valid on a multi-access segment
            # when this router is also a DROTHER (DR/BDR seen from others).
            emit(passed(
                f"{intf_name} — all neighbors 2WAY/DROTHER "
                f"(valid DROTHER-to-DROTHER state on multi-access segment)"
            ), lf)
        else:
            emit(warned(
                f"{intf_name} — neighbor(s) present but none in FULL state "
                f"(states: {', '.join(states)})"
            ), lf)
            worst = _worst(worst, "WARN")

    return worst


def _parse_ospf_interfaces(raw: str) -> dict:
    """Parse 'show ip ospf interface' (full) into a per-interface dict.

    Extracts area, network type, priority, DR address, and BDR address
    from the verbose IOS OSPF interface output.

    Returns dict keyed by interface name:
        {
            "Ethernet0/0": {
                "area"        : "0",
                "net_type"    : "BROADCAST",
                "priority"    : 1,
                "dr_ip"       : "192.1.100.2",
                "bdr_ip"      : "192.1.100.3",
            },
            ...
        }
    """
    result       = {}
    current_intf = None

    intf_re    = re.compile(r'^(\S+)\s+is\s+(?:up|down)', re.IGNORECASE)
    area_re    = re.compile(r'Area\s+(\S+),', re.IGNORECASE)
    type_re    = re.compile(r'Network\s+Type\s+(\S+?)(?:[,\s]|$)', re.IGNORECASE)
    pri_re     = re.compile(r'Transmit\s+Delay\s+.*?Priority\s+(\d+)', re.IGNORECASE)
    dr_re      = re.compile(r'^\s+Designated\s+Router\s+\(ID\)\s+(\S+),\s+Interface\s+address\s+(\S+)',
                            re.IGNORECASE)
    bdr_re     = re.compile(r'^\s+Backup\s+Designated\s+Router\s+\(ID\)\s+(\S+),\s+Interface\s+address\s+(\S+)',
                            re.IGNORECASE)

    for line in raw.splitlines():
        m = intf_re.match(line.strip())
        if m:
            current_intf = m.group(1)
            result[current_intf] = {
                "area"    : None,
                "net_type": None,
                "priority": None,
                "dr_ip"   : None,
                "bdr_ip"  : None,
                "dr_id"   : None,
                "bdr_id"  : None,
            }
            continue

        if current_intf is None:
            continue

        if result[current_intf]["area"] is None:
            m2 = area_re.search(line)
            if m2:
                result[current_intf]["area"] = m2.group(1).rstrip(",")

        if result[current_intf]["net_type"] is None:
            m3 = type_re.search(line)
            if m3:
                result[current_intf]["net_type"] = m3.group(1).upper()

        if result[current_intf]["priority"] is None:
            m4 = pri_re.search(line)
            if m4:
                result[current_intf]["priority"] = int(m4.group(1))

        # BDR must be checked before DR — both lines contain "Designated Router"
        # and the DR regex would otherwise match the BDR line too.
        m6 = bdr_re.match(line)
        if m6:
            result[current_intf]["bdr_id"] = m6.group(1)
            result[current_intf]["bdr_ip"] = m6.group(2)
        else:
            m5 = dr_re.match(line)
            if m5:
                result[current_intf]["dr_id"] = m5.group(1)
                result[current_intf]["dr_ip"] = m5.group(2)

    return result


def check_interfaces(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Validate OSPF interface state against YAML expected configuration.

    Runs 'show ip ospf interface' (full) and 'show ip ospf neighbor' and
    validates each active non-OOB non-loopback interface:

      Area        — live area must match YAML ospf network area  → FAIL on mismatch
      Network type— live type must match YAML ospf_network_type  → FAIL on mismatch
      Priority    — validated only when ospf_priority is set in YAML → WARN on mismatch
      DR/BDR role — identified by Router ID from neighbor table
                    Point-to-point interfaces report P2P (no DR election) → PASS
                    Priority-0 interfaces that became DR/BDR             → WARN

    Returns the worst-case result token across all interfaces:
        "PASS", "WARN", "FAIL", or "INFO" (no active interfaces found).

    Args:
        conn        : Open NAPALM device object.
        device_name : Router hostname (display only).
        device_data : Full device dict from YAML.
        lf          : Open log file handle, or None.
    """
    section("OSPF Interfaces — Validation", lf)

    raw_intf = conn.cli(["show ip ospf interface"])["show ip ospf interface"]
    raw_nbr  = conn.cli(["show ip ospf neighbor"])["show ip ospf neighbor"]

    live_intfs = _parse_ospf_interfaces(raw_intf)

    # Build neighbor IP → Router ID map for DR/BDR identification
    # IOS neighbor line: <rid> <pri> <state> <dead> <address> <interface>
    nbr_line_re = re.compile(
        r'^\s*(\S+)\s+\d+\s+\S+\s+\S+\s+(\S+)\s+\S+\s*$'
    )
    ip_to_rid: dict[str, str] = {}
    for line in raw_nbr.splitlines():
        norm = re.sub(r'FULL/\s+-', 'FULL/-', line)
        m = nbr_line_re.match(norm)
        if m:
            ip_to_rid[m.group(2)] = m.group(1)   # address → router-id

    ospf_data     = device_data.get("ospf", {})
    oob_interface = device_data.get("oob_interface", "")
    interfaces    = device_data.get("interfaces", {})
    networks      = ospf_data.get("networks", []) or []

    # Build interface → expected area map from YAML network statements
    intf_state_map = parse_interface_state(
        conn.cli(["show ip interface"])["show ip interface"]
    )
    intf_to_area: dict[str, str] = {}
    for intf_name, intf_data in intf_state_map.items():
        if not intf_data.get("ip"):
            continue
        for net_entry in networks:
            if ip_in_ospf_network(intf_data["ip"],
                                  net_entry.get("prefix", ""),
                                  net_entry.get("wildcard", "")):
                intf_to_area[intf_name] = str(net_entry.get("area", "?"))
                break

    emit(info(f"YAML: OSPF process {ospf_data.get('process_id', '?')}  "
              f"router-id {ospf_data.get('router_id', '?')}"), lf)

    # Collect active interfaces to validate
    active_intfs = []
    for intf_name, intf in interfaces.items():
        if intf_name == oob_interface:
            continue
        if "Loopback" in intf_name:
            continue
        if intf.get("shutdown", True):
            continue
        if not intf.get("ip", ""):
            continue
        active_intfs.append((intf_name, intf))

    if not active_intfs:
        emit(info("No active non-loopback OSPF interfaces found in YAML."), lf)
        return "INFO"

    worst = "PASS"

    for intf_name, yaml_intf in active_intfs:
        live = live_intfs.get(intf_name)
        if live is None:
            emit(warned(f"{intf_name} — not found in 'show ip ospf interface' output"), lf)
            worst = _worst(worst, "WARN")
            continue

        issues    = []
        result    = "PASS"
        # Normalise separators: IOS uses POINT_TO_POINT, YAML may use POINT-TO-POINT
        yaml_type = (yaml_intf.get("ospf_network_type") or "").upper().replace("-", "_")
        live_type = (live.get("net_type") or "").upper().replace("-", "_")
        is_p2p    = ("POINT" in live_type)   # POINT_TO_POINT

        # --- Area check ---
        expected_area = intf_to_area.get(intf_name)
        live_area     = live.get("area")
        if expected_area and live_area and str(expected_area) != str(live_area):
            issues.append(f"area mismatch: YAML={expected_area} live={live_area}")
            result = _worst(result, "FAIL")

        # --- Network type check ---
        if yaml_type and live_type and yaml_type not in live_type:
            issues.append(f"network-type mismatch: YAML={yaml_type} live={live_type}")
            result = _worst(result, "FAIL")

        # --- Priority check (only when explicitly set in YAML) ---
        yaml_pri = yaml_intf.get("ospf_priority")
        if yaml_pri is not None and yaml_pri != "":
            live_pri = live.get("priority")
            if live_pri is not None and int(yaml_pri) != int(live_pri):
                issues.append(f"priority mismatch: YAML={yaml_pri} live={live_pri}")
                result = _worst(result, "WARN")

        # --- DR/BDR role ---
        if is_p2p:
            role_str = "P2P (no DR election)"
        else:
            dr_ip  = live.get("dr_ip")
            bdr_ip = live.get("bdr_ip")
            dr_id  = live.get("dr_id")  or ip_to_rid.get(dr_ip,  dr_ip  or "none")
            bdr_id = live.get("bdr_id") or ip_to_rid.get(bdr_ip, bdr_ip or "none")

            # Flag priority-0 interface that won DR or BDR election
            live_pri = live.get("priority", 1)
            if live_pri == 0:
                my_ip = (yaml_intf.get("ip") or "").split("/")[0]
                if my_ip and (my_ip == dr_ip or my_ip == bdr_ip):
                    issues.append(f"priority 0 interface elected as DR/BDR")
                    result = _worst(result, "WARN")

            role_str = f"DR={dr_id}  BDR={bdr_id}"

        # --- Emit result line ---
        area_str = live_area or expected_area or "?"
        type_str = live_type or yaml_type or "?"
        pri_str  = ""
        if yaml_pri is not None and yaml_pri != "":
            pri_str = f"  pri={live.get('priority', '?')}"

        detail = f"area {area_str}  {type_str}{pri_str}  {role_str}"
        if issues:
            issue_str = " | ".join(issues)
            if result == "FAIL":
                emit(failed(f"{intf_name} — {detail}  ⚠  {issue_str}"), lf)
            else:
                emit(warned(f"{intf_name} — {detail}  ⚠  {issue_str}"), lf)
        else:
            emit(passed(f"{intf_name} — {detail}"), lf)

        worst = _worst(worst, result)

    return worst


def _parse_ospf_routes(raw: str) -> list:
    """Parse 'show ip route ospf' into a list of structured route dicts.

    Handles both single and ECMP (multi-path) entries. IOS formats:

      O    1.0.0.0 [110/11] via 192.1.100.2, 00:14:32, Ethernet0/0
      O IA 9.0.0.0 [110/21] via 192.1.100.2, 00:14:32, Ethernet0/0
               [110/21] via 192.1.100.3, 00:12:01, Ethernet0/0   ← ECMP

    Returns list of dicts:
        [
            {
                "type"  : "Intra" | "Inter",
                "dest"  : "1.0.0.0/8",
                "cost"  : "11",
                "paths" : [
                    {"via": "192.1.100.2", "intf": "Ethernet0/0", "age": "00:14:32"},
                    ...
                ],
            },
            ...
        ]
    """
    routes = []
    current = None

    # Primary route line:  O [IA] <dest> [<ad>/<cost>] via <nh>, <age>, <intf>
    primary_re = re.compile(
        r'^\s*O(?:\s+IA)?\s+'
        r'(\S+)'                        # destination (may include /prefix)
        r'\s+\[[\d]+/(\d+)\]'          # [AD/cost]
        r'\s+via\s+(\S+?),'            # next-hop
        r'\s+(\S+),'                   # age
        r'\s+(\S+)',                   # interface
        re.IGNORECASE
    )
    # ECMP continuation line (indented, no O prefix):
    ecmp_re = re.compile(
        r'^\s+\[[\d]+/(\d+)\]'
        r'\s+via\s+(\S+?),'
        r'\s+(\S+),'
        r'\s+(\S+)',
        re.IGNORECASE
    )
    # Detect route type
    ia_re = re.compile(r'^\s*O\s+IA\s+', re.IGNORECASE)

    for line in raw.splitlines():
        m = primary_re.match(line)
        if m:
            rtype = "Inter" if ia_re.match(line) else "Intra"
            dest  = m.group(1)
            # Normalise destination: IOS may omit prefix length for classful
            if "/" not in dest:
                try:
                    dest = str(ipaddress.IPv4Network(dest, strict=False))
                except Exception:
                    pass
            current = {
                "type" : rtype,
                "dest" : dest,
                "cost" : m.group(2),
                "paths": [{"via": m.group(3), "age": m.group(4), "intf": m.group(5)}],
            }
            routes.append(current)
            continue

        if current:
            m2 = ecmp_re.match(line)
            if m2:
                current["paths"].append(
                    {"via": m2.group(2), "age": m2.group(3), "intf": m2.group(4)}
                )

    return routes


def _print_route_table(routes: list, lf=None) -> None:
    """Render the parsed OSPF route list as a formatted table."""
    if not routes:
        return

    # Column widths
    W_TYPE = 5    # Intra / Inter
    W_DEST = 18
    W_VIA  = 15
    W_INTF = 14
    W_COST = 5
    W_AGE  = 10

    header = (
        f"  {'Type':<{W_TYPE}}  {'Destination':<{W_DEST}}  "
        f"{'Via':<{W_VIA}}  {'Interface':<{W_INTF}}  "
        f"{'Cost':<{W_COST}}  {'Age':<{W_AGE}}"
    )
    divider = "  " + "─" * (W_TYPE + W_DEST + W_VIA + W_INTF + W_COST + W_AGE + 12)

    emit(f"\n{BOLD}{header}{RESET}", lf)
    emit(divider, lf)

    for route in routes:
        rtype = route["type"]
        dest  = route["dest"]
        cost  = route["cost"]
        color = CYAN if rtype == "Inter" else ""

        for idx, path in enumerate(route["paths"]):
            if idx == 0:
                type_col = f"{color}{rtype:<{W_TYPE}}{RESET}"
                dest_col = f"{dest:<{W_DEST}}"
            else:
                type_col = f"{'':<{W_TYPE}}"
                dest_col = f"{'':<{W_DEST}}"

            line = (
                f"  {type_col}  {dest_col}  "
                f"{path['via']:<{W_VIA}}  "
                f"{path['intf']:<{W_INTF}}  "
                f"{cost:<{W_COST}}  "
                f"{path['age']:<{W_AGE}}"
            )
            emit(line, lf)

    emit(divider, lf)


def check_routes(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Display formatted OSPF route table and validate network statements.

    Step 1 — Fetches 'show ip route ospf', parses it into structured rows,
             and renders a formatted table:
               Type | Destination | Via | Interface | Cost | Age
             ECMP paths appear as additional indented rows.
             No OSPF routes at all is reported as WARN.

    Step 2 — Validates each OSPF network statement from YAML against live
             interface state using wildcard-aware IP math:
               PASS — interface owning that network is up/up
               WARN — interface exists but is not up/up
               FAIL — no interface found matching the network

    Step 3 — Reports inter-area summarization (area range) if configured.

    Returns the worst-case result token: "PASS", "WARN", or "FAIL".

    Args:
        conn        : Open NAPALM device object.
        device_name : Router hostname (display only).
        device_data : Full device dict from YAML.
        lf          : Open log file handle, or None.
    """
    worst = "PASS"

    # Step 1 — Formatted OSPF route table
    section("OSPF Route Table", lf)
    route_output = conn.cli(["show ip route ospf"])["show ip route ospf"]
    routes = _parse_ospf_routes(route_output)

    if not routes:
        emit(warned(f"No OSPF routes in routing table on {device_name}"), lf)
        worst = _worst(worst, "WARN")
    else:
        _print_route_table(routes, lf)
        emit(info(f"{len(routes)} OSPF route(s) — "
                  f"{sum(1 for r in routes if r['type'] == 'Intra')} Intra  "
                  f"{sum(1 for r in routes if r['type'] == 'Inter')} Inter"), lf)

    # Step 2 — Validate YAML network statements against live interface state
    section("OSPF Network Statement Validation", lf)

    ospf_data = device_data.get("ospf", {})
    networks  = ospf_data.get("networks", []) or []

    if not networks:
        emit(info("No network statements found in YAML — skipping validation."), lf)
        return worst

    intf_raw = conn.cli(["show ip interface"])["show ip interface"]
    intf_map = parse_interface_state(intf_raw)

    if not intf_map:
        emit(failed("Could not parse interface state — 'show ip interface' returned no usable output."), lf)
        return _worst(worst, "FAIL")

    for entry in networks:
        network  = entry.get("prefix", "")
        wildcard = entry.get("wildcard", "")
        area     = entry.get("area", "?")
        label    = f"{network} {wildcard} area {area}"

        match_intf = None
        match_data = None
        for intf_name, intf_data in intf_map.items():
            if intf_data["ip"] and ip_in_ospf_network(intf_data["ip"], network, wildcard):
                match_intf = intf_name
                match_data = intf_data
                break

        if match_intf is None:
            emit(failed(
                f"Network {label} — "
                f"no interface found with a matching IP on {device_name}"
            ), lf)
            worst = _worst(worst, "FAIL")
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
            worst = _worst(worst, "WARN")

    # Step 3 — Area range summarization
    area_range = ospf_data.get("area_range", []) or []
    if area_range:
        section("OSPF Area Range (Summarization)", lf)
        for rng in area_range:
            emit(info(
                f"YAML: area {rng['area']} range {rng['prefix']} {rng['mask']} — "
                f"verify summary LSA in adjacent area"
            ), lf)

    return worst


def check_lsdb(conn, device_name: str, lf=None) -> str:
    """Display the OSPF Link State Database for informational verification.

    Runs 'show ip ospf database' and displays the raw output. No PASS/FAIL
    validation is applied — the student visually verifies LSA types and counts
    against the expected topology.

    For the ABR (R8), both Area 0 and Area 10 LSDBs will be present.
    Summary LSAs (Type 3) and the area range summary should be visible
    in the inter-area section.

    Returns "INFO" — lsdb is always informational.

    Args:
        conn        : Open NAPALM device object.
        device_name : Router hostname (display only).
        lf          : Open log file handle, or None.
    """
    section("OSPF Link State Database — show ip ospf database", lf)

    output = conn.cli(["show ip ospf database"])["show ip ospf database"]
    emit_raw(output, lf)
    emit(info("LSDB displayed — verify Router LSAs (Type 1), Network LSAs (Type 2), "
              "and Summary LSAs (Type 3) match expected topology."), lf)
    return "INFO"


def check_route_lookup(conn, device_name: str, target: str, lf=None) -> None:
    """Run a filtered route lookup for a specific IP or network prefix.

    Runs 'show ip route | include <target>' and displays the raw output.
    Useful for spot-checking reachability to a specific destination during
    live lab demonstration.

    Args:
        conn        : Open NAPALM device object.
        device_name : Router hostname (display only).
        target      : IP address or network prefix string to filter on.
        lf          : Open log file handle, or None.
    """
    section(f"Route Lookup — show ip route | include {target}", lf)

    output = conn.cli([f"show ip route | include {target}"])[f"show ip route | include {target}"]

    if output.strip():
        emit_raw(output, lf)
        emit(passed(f"'{target}' found in routing table on {device_name}"), lf)
    else:
        emit("\n  (no output)\n", lf)
        emit(failed(f"'{target}' NOT found in routing table on {device_name}"), lf)


# =============================================================================
# SUMMARY
# =============================================================================

def _print_summary(
    results: dict[str, dict[str, str]],
    checks_to_run: list[str],
    lf=None,
) -> None:
    """Print a per-device, per-check summary table.

    Each cell shows the worst-case result for that device/check combination.
    A totals row at the bottom counts PASS / WARN / FAIL / INFO per check.

    Colour coding:
        PASS → green   WARN → yellow   FAIL → red   INFO → cyan

    Args:
        results       : { device_name: { check: result_token, ... }, ... }
        checks_to_run : Ordered list of check names that were executed.
        lf            : Open log file handle, or None.
    """
    _TOKEN_COLOR = {
        "PASS": GREEN,
        "WARN": YELLOW,
        "FAIL": RED,
        "INFO": CYAN,
        "—"   : "",
    }

    def _colored_token(token: str) -> str:
        color = _TOKEN_COLOR.get(token, "")
        return f"{color}{token}{RESET}" if color else token

    bar       = "=" * 60
    W_DEVICE  = 8
    W_CHECK   = 12

    header_line = f"  {'Device':<{W_DEVICE}}" + "".join(
        f"  {chk:<{W_CHECK}}" for chk in checks_to_run
    )
    divider = "  " + "─" * (W_DEVICE + (W_CHECK + 2) * len(checks_to_run))

    lines = [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}  Verification Summary{RESET}",
        f"{BOLD}{bar}{RESET}",
        f"{BOLD}{header_line}{RESET}",
        divider,
    ]
    for line in lines:
        emit(line, lf)

    # Per-device rows
    totals: dict[str, dict[str, int]] = {
        chk: {"PASS": 0, "WARN": 0, "FAIL": 0, "INFO": 0} for chk in checks_to_run
    }

    for device_name, chk_results in results.items():
        row = f"  {device_name:<{W_DEVICE}}"
        for chk in checks_to_run:
            token = chk_results.get(chk, "—")
            if token in totals[chk]:
                totals[chk][token] += 1
            colored = _colored_token(token)
            # Pad accounting for invisible ANSI escape chars
            pad = W_CHECK + (len(colored) - len(token))
            row += f"  {colored:<{pad}}"
        emit(row, lf)

    emit(divider, lf)

    # Totals row — show non-zero counts only
    totals_row = f"  {'Totals':<{W_DEVICE}}"
    for chk in checks_to_run:
        parts = []
        for token in ("PASS", "WARN", "FAIL", "INFO"):
            count = totals[chk].get(token, 0)
            if count:
                parts.append(f"{_colored_token(token)}:{count}")
        cell = "  ".join(parts) if parts else "—"
        # Raw length for padding
        raw_len  = sum(len(t) + 1 + len(str(totals[chk][t]))
                       for t in ("PASS","WARN","FAIL","INFO")
                       if totals[chk].get(t, 0)) + (2 * (len(parts) - 1)) if parts else 1
        pad = W_CHECK + (len(cell) - raw_len)
        totals_row += f"  {cell:<{pad}}"
    emit(totals_row, lf)
    emit(f"{BOLD}{bar}{RESET}\n", lf)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:

    # -------------------------------------------------------------------------
    # Argument parsing
    # -------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description=(
            "Module 03 — OSPF Classic Mode Verification\n"
            "Connects to lab routers and verifies OSPF operational state\n"
            "against expected values defined in ospf_classic.yaml.\n"
            "All output is mirrored to a timestamped log file in logs/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python verify_ospf_classic.py\n"
            "  python verify_ospf_classic.py --router R1 R8\n"
            "  python verify_ospf_classic.py --check neighbors lsdb\n"
            "  python verify_ospf_classic.py --route 192.1.100.0\n"
            "  python verify_ospf_classic.py --router R8 --check lsdb --route 9.0.0.0\n"
        ),
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
    # --list-checks
    # -------------------------------------------------------------------------
    if args.list_checks:
        print(f"\n{BOLD}Available verification checks:{RESET}\n")
        descriptions = {
            "neighbors"  : "Verify OSPF neighbors are FULL on all active interfaces",
            "interfaces" : "Validate area, network type, priority, DR/BDR role — PASS/WARN/FAIL per interface",
            "routes"     : "Formatted OSPF route table (Intra/Inter) + network statement validation",
            "lsdb"       : "Display OSPF Link State Database — LSA types and counts (informational)",
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

    for device_data in devices.values():
        if not device_data.get("credentials"):
            device_data["credentials"] = default_creds

    # -------------------------------------------------------------------------
    # Resolve target routers
    # -------------------------------------------------------------------------
    def resolve_router(token: str) -> str | None:
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
        f"\nNAMS26 — Module 03: OSPF Classic Mode Verification",
        f"Targets : {', '.join(target_routers)}",
        f"Checks  : {', '.join(checks_to_run)}"
        + (f"  +  route lookup: {args.route}" if args.route else ""),
    ]
    for line in summary_lines:
        emit(line, lf)

    # -------------------------------------------------------------------------
    # Per-device verification loop
    # -------------------------------------------------------------------------
    # results: { "R1": {"neighbors": "PASS", "interfaces": "WARN", ...}, ... }
    results: dict[str, dict[str, str]] = {}

    try:
        for device_name in target_routers:
            device_data = devices[device_name]
            oob_ip      = device_data.get("oob_ip", "")
            dns_name    = device_data.get("dns_name", "")
            creds       = device_data.get("credentials", default_creds)

            results[device_name] = {}

            if not dns_name:
                emit(failed(f"No dns_name defined for {device_name} in YAML — skipping."), lf)
                for chk in checks_to_run:
                    results[device_name][chk] = "FAIL"
                continue

            device_header(device_name, dns_name, oob_ip, lf)

            device = connect(device_name, dns_name, creds, lf)
            if device is None:
                emit(failed(f"Skipping all checks on {device_name} — connection failed."), lf)
                for chk in checks_to_run:
                    results[device_name][chk] = "FAIL"
                continue

            try:
                if "neighbors" in checks_to_run:
                    results[device_name]["neighbors"] = check_neighbors(
                        device, device_name, device_data, lf)

                if "interfaces" in checks_to_run:
                    results[device_name]["interfaces"] = check_interfaces(
                        device, device_name, device_data, lf)

                if "routes" in checks_to_run:
                    results[device_name]["routes"] = check_routes(
                        device, device_name, device_data, lf)

                if "lsdb" in checks_to_run:
                    results[device_name]["lsdb"] = check_lsdb(
                        device, device_name, lf)

                if args.route:
                    check_route_lookup(device, device_name, args.route, lf)

            finally:
                device.close()
                lf and lf.write(f"  [INFO] Disconnected from {device_name}\n")

        # ---------------------------------------------------------------------
        # Summary block
        # ---------------------------------------------------------------------
        _print_summary(results, checks_to_run, lf)

        emit(f"\n{'=' * 60}\nVerification complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
