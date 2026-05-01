#!/usr/bin/env python3
"""
Module   : 04 — OSPF Advanced / NAPALM
File     : modules/04_ospf2_napalm/scripts/verify_ospf_advanced.py
Purpose  : Connect to lab routers via NAPALM and verify OSPF Advanced
           operational state. Compares live output against expected state
           defined in ospf_advanced.yaml and reports PASS / FAIL per check.
           All output is mirrored to a timestamped log file in logs/.

Usage:
    # Verify all routers — all checks
    python verify_ospf_advanced.py

    # Verify specific routers
    python verify_ospf_advanced.py --router R1 R2

    # Run specific check(s) only
    python verify_ospf_advanced.py --check neighbors
    python verify_ospf_advanced.py --check interfaces
    python verify_ospf_advanced.py --check routes
    python verify_ospf_advanced.py --check lsdb
    python verify_ospf_advanced.py --check redistribution
    python verify_ospf_advanced.py --check neighbors routes

    # Route lookup — show ip route | include <target>
    python verify_ospf_advanced.py --route 100.0.0.0
    python verify_ospf_advanced.py --route 105.1.12.0

    # List all available checks
    python verify_ospf_advanced.py --list-checks

    # Combine flags
    python verify_ospf_advanced.py --router R1 R6 --check redistribution lsdb

Checks:
    neighbors      — Verify expected OSPF neighbors are FULL (skipped on
                     EIGRP-only routers R7, R8, R9)
    interfaces     — Validate OSPF interface state: area and network type
                     against YAML (skipped on EIGRP-only routers)
    routes         — Formatted OSPF route table including external types
                     (O E1, O E2, O N1, O N2) + filtering validation +
                     network statement validation
    lsdb           — Display OSPF LSDB using targeted per-type commands:
                     show ip ospf database external
                     show ip ospf database nssa-external
                     show ip ospf database asbr-summary
                     show ip ospf database summary
                     show ip ospf database router
    redistribution — Validate bidirectional redistribution state:
                     R1/R6: OSPF routes present in EIGRP table
                     R7/R8: D EX entries present for redistributed OSPF prefixes
                     R9   : D EX entries present for redistributed OSPF prefixes

Summary:
    A per-device, per-check summary table is printed at the end of every run.
    Per-device result is the worst-case across all checks for that device.
    lsdb is always INFO.

Logging:
    A timestamped log file is written to modules/04_ospf2_napalm/logs/ on
    every run. The log captures all raw command output and all result lines
    in plain text (no ANSI color codes).
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
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)

YAML_FILE = os.path.join(MODULE_DIR, "data", "ospf_advanced.yaml")
LOG_DIR   = os.path.join(MODULE_DIR, "logs")

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# AVAILABLE CHECKS
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "interfaces", "routes", "lsdb", "redistribution"]

# Routers that run EIGRP only — no OSPF process
EIGRP_ONLY_ROUTERS = {"R7", "R8", "R9"}

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

_RESULT_PREFIXES = ("[PASS]", "[FAIL]", "[WARN]", "[INFO]")
_result_collector: list | None = None


def emit(line: str, lf=None) -> None:
    """Print a line to stdout and mirror it (without ANSI) to the log file."""
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")
    if _result_collector is not None and _strip_ansi(line).strip().startswith(_RESULT_PREFIXES):
        _result_collector.append(line)

def emit_raw(text: str, lf=None) -> None:
    """Print and log a block of raw command output."""
    print(f"\n{text}\n")
    if lf:
        lf.write(f"\n{text}\n\n")


def emit_drift(device_name: str, detail: str, lf=None) -> None:
    """Log a drift detection block with a clear delimiter to the session log.

    Format:
        === DRIFT DETECTED — <hostname> — <timestamp> ===
        <detail>
        =================================================
    """
    timestamp = datetime.now().strftime("%Y%m%d %H:%M:%S")
    bar = "=" * 51
    header = f"=== DRIFT DETECTED — {device_name} — {timestamp} ==="
    lines = [
        f"\n{RED}{header}{RESET}",
        f"{detail}",
        f"{RED}{bar}{RESET}\n",
    ]
    for line in lines:
        print(line)
        if lf:
            lf.write(_strip_ansi(line) + "\n")


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logger() -> object:
    """Create the logs directory if needed and open a timestamped log file.

    Returns:
        An open file handle for writing. Caller is responsible for closing it.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"verify_ospf_advanced_{timestamp}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 04: OSPF Advanced Verification\n")
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
            # global_delay_factor is a Netmiko parameter forwarded through NAPALM's
            # optional_args to the underlying SSH connection. Doubles all internal
            # Netmiko timing constants — needed because IOL routers respond slowly.
            # Current: 2.0   Range: 1.0 (fastest, may miss prompts) – 5.0 (slow hosts)
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

    Returns:
        Dict of interface name -> {"ip", "up", "phys", "proto"}.
    """
    intf_re = re.compile(
        r'^(?P<intf>\S+)\s+is\s+(?P<phys>\S+),\s+line protocol is\s+(?P<proto>\S+)',
        re.IGNORECASE
    )
    ip_re = re.compile(r'Internet address is\s+(?P<ip>\S+)', re.IGNORECASE)

    interfaces   = {}
    current_intf = None

    for line in raw.splitlines():
        m_intf = intf_re.match(line.strip())
        if m_intf:
            current_intf = m_intf.group("intf")
            phys  = m_intf.group("phys").lower()
            proto = m_intf.group("proto").lower()
            interfaces[current_intf] = {
                "ip"   : None,
                "up"   : (phys == "up" and proto == "up"),
                "phys" : phys,
                "proto": proto,
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
    """Return True if the interface IP falls within the OSPF network/wildcard."""
    try:
        wc_int   = int(ipaddress.IPv4Address(wildcard))
        mask_int = 0xFFFFFFFF ^ wc_int
        netmask  = str(ipaddress.IPv4Address(mask_int))
        ospf_net = ipaddress.IPv4Network(f"{network}/{netmask}", strict=False)
        intf_ip  = ipaddress.IPv4Interface(intf_ip_cidr).ip
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
# HELPER — Parse 'show ip ospf interface' output
# =============================================================================

def _parse_ospf_interfaces(raw: str) -> dict:
    """Parse 'show ip ospf interface' into a per-interface state dict.

    Returns dict keyed by interface name:
        {"area", "net_type", "priority", "dr_ip", "bdr_ip", "dr_id", "bdr_id"}
    """
    result       = {}
    current_intf = None

    intf_re = re.compile(r'^(\S+)\s+is\s+(?:up|down)', re.IGNORECASE)
    area_re = re.compile(r'Area\s+(\S+)', re.IGNORECASE)
    type_re = re.compile(r'Network\s+Type\s+(\S+)', re.IGNORECASE)
    pri_re  = re.compile(r'Transmit\s+Delay\s+is.*Priority\s+(\d+)', re.IGNORECASE)
    dr_re   = re.compile(r'^\s+Designated\s+Router\s+\(ID\)\s+(\S+),\s+Interface\s+address\s+(\S+)',
                         re.IGNORECASE)
    bdr_re  = re.compile(r'^\s+Backup\s+Designated\s+Router\s+\(ID\)\s+(\S+),\s+Interface\s+address\s+(\S+)',
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

        # BDR must be checked before DR to avoid DR regex matching the BDR line
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


# =============================================================================
# VERIFICATION CHECKS
# =============================================================================

def check_neighbors(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Verify OSPF neighbors are FULL on each active non-loopback interface.

    Skipped entirely on EIGRP-only routers (R7, R8, R9).

    Per-interface verdict:
      PASS — at least one neighbor is FULL (any DR role including FULL/-)
      PASS — all neighbors are 2WAY/DROTHER (valid DROTHER state)
      WARN — neighbors present but none are FULL and not all 2WAY/DROTHER
      FAIL — no neighbors found on the interface

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    if device_name in EIGRP_ONLY_ROUTERS:
        emit(info(f"{device_name} is EIGRP-only — OSPF neighbor check skipped."), lf)
        return "INFO"

    section("OSPF Neighbors — show ip ospf neighbor", lf)

    output = conn.cli(["show ip ospf neighbor"])["show ip ospf neighbor"]
    emit_raw(output, lf)

    oob_interface = device_data.get("oob_interface", "")
    interfaces    = device_data.get("interfaces", {})

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
        # Skip interfaces that are not in any OSPF network statement
        ospf_data = device_data.get("ospf") or {}
        networks  = ospf_data.get("networks", []) or []
        intf_ip   = intf.get("ip", "")
        if not any(ip_in_ospf_network(intf_ip, n["prefix"], n["wildcard"])
                   for n in networks):
            continue
        expected_intfs.append(intf_name)

    if not expected_intfs:
        emit(info("No active OSPF-enabled non-loopback interfaces — "
                  "skipping neighbor validation."), lf)
        return "INFO"

    # Parse neighbor table grouped by interface
    # IOS line: <rid> <pri> <state> <dead> <address> <interface>
    nbr_line_re = re.compile(
        r'^\s*(\S+)\s+\d+\s+(\S+)\s+\S+\s+\S+\s+(\S+)\s*$'
    )
    nbrs_by_intf: dict[str, list[str]] = {}
    for line in output.splitlines():
        norm = re.sub(r'FULL/\s+-', 'FULL/-', line)
        m = nbr_line_re.match(norm)
        if m:
            state = m.group(2)
            intf  = m.group(3)
            nbrs_by_intf.setdefault(intf, []).append(state)

    worst = "PASS"
    for intf_name in expected_intfs:
        states = nbrs_by_intf.get(intf_name, [])
        if not states:
            emit(failed(f"{intf_name} — no neighbors found"), lf)
            worst = _worst(worst, "FAIL")
        elif any(s.startswith("FULL") for s in states):
            emit(passed(f"{intf_name} — {', '.join(states)}"), lf)
        elif all(s == "2WAY/DROTHER" for s in states):
            emit(passed(f"{intf_name} — {', '.join(states)} (DROTHER — valid)"), lf)
        else:
            emit(warned(f"{intf_name} — {', '.join(states)} (no FULL adjacency)"), lf)
            worst = _worst(worst, "WARN")

    return worst


def check_interfaces(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Validate OSPF interface area and network type against YAML.

    Skipped entirely on EIGRP-only routers (R7, R8, R9).
    No authentication validation in Module 04 (not a module focus).

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    if device_name in EIGRP_ONLY_ROUTERS:
        emit(info(f"{device_name} is EIGRP-only — OSPF interface check skipped."), lf)
        return "INFO"

    section("OSPF Interfaces — Validation", lf)

    raw_intf = conn.cli(["show ip ospf interface"])["show ip ospf interface"]
    raw_nbr  = conn.cli(["show ip ospf neighbor"])["show ip ospf neighbor"]

    live_intfs = _parse_ospf_interfaces(raw_intf)

    # Build neighbor IP → Router ID map for DR/BDR identification
    nbr_line_re = re.compile(r'^\s*(\S+)\s+\d+\s+\S+\s+\S+\s+(\S+)\s+\S+\s*$')
    ip_to_rid: dict[str, str] = {}
    for line in raw_nbr.splitlines():
        norm = re.sub(r'FULL/\s+-', 'FULL/-', line)
        m = nbr_line_re.match(norm)
        if m:
            ip_to_rid[m.group(2)] = m.group(1)

    ospf_data     = device_data.get("ospf", {}) or {}
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
        emit(info("No active non-loopback interfaces found in YAML."), lf)
        return "INFO"

    worst = "PASS"

    for intf_name, yaml_intf in active_intfs:
        if intf_name not in intf_to_area:
            emit(info(f"{intf_name} — not covered by an OSPF network statement, skipping"), lf)
            continue
        live = live_intfs.get(intf_name)
        if live is None:
            emit(warned(f"{intf_name} — expected in OSPF (matches network statement) but not found in 'show ip ospf interface'"), lf)
            worst = _worst(worst, "WARN")
            continue

        issues    = []
        result    = "PASS"
        yaml_type = (yaml_intf.get("ospf_network_type") or "").upper().replace("-", "_")
        live_type = (live.get("net_type") or "").upper().replace("-", "_")
        is_p2p    = ("POINT" in live_type)

        # Area check
        expected_area = intf_to_area.get(intf_name)
        live_area     = live.get("area")
        if expected_area and live_area and str(expected_area) != str(live_area):
            issues.append(f"area mismatch: YAML={expected_area} live={live_area}")
            result = _worst(result, "FAIL")

        # Network type check
        if yaml_type and live_type and yaml_type not in live_type:
            issues.append(f"network-type mismatch: YAML={yaml_type} live={live_type}")
            result = _worst(result, "FAIL")

        # DR/BDR role
        if is_p2p:
            role_str = "P2P (no DR election)"
        else:
            dr_ip  = live.get("dr_ip")
            bdr_ip = live.get("bdr_ip")
            dr_id  = live.get("dr_id")  or ip_to_rid.get(dr_ip,  dr_ip  or "none")
            bdr_id = live.get("bdr_id") or ip_to_rid.get(bdr_ip, bdr_ip or "none")
            role_str = f"DR={dr_id}  BDR={bdr_id}"

        area_str = live_area or expected_area or "?"
        type_str = live_type or yaml_type or "?"
        detail   = f"area {area_str}  {type_str}  {role_str}"

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
    """Parse 'show ip route ospf' into structured route dicts.

    Handles intra-area (O), inter-area (O IA), and external types:
    O E1, O E2 (Type 5 — from ASBRs in standard areas)
    O N1, O N2 (Type 7 — NSSA external, from R6 in Area 20)

    Returns list of dicts:
        {"type", "dest", "cost", "paths": [{"via", "age", "intf"}]}
    """
    routes  = []
    current = None

    # Match: O [IA|E1|E2|N1|N2] or O*[N1|N2] (candidate default) <dest> ...
    primary_re = re.compile(
        r'^\s*O(?:\*?(?:\s+|\*)(?:IA|E1|E2|N1|N2)|\s+(?:IA|E1|E2|N1|N2))?\s*'
        r'(\S+)'
        r'\s+\[[\d]+/(\d+)\]'
        r'\s+via\s+(\S+?),'
        r'\s+(\S+),'
        r'\s+(\S+)',
        re.IGNORECASE
    )
    ecmp_re = re.compile(
        r'^\s+\[[\d]+/(\d+)\]'
        r'\s+via\s+(\S+?),'
        r'\s+(\S+),'
        r'\s+(\S+)',
        re.IGNORECASE
    )

    # Route type classification
    type_map = {
        r'^\s*O\s+IA\s+' : "Inter",
        r'^\s*O\s+E1\s+' : "E1",
        r'^\s*O\s+E2\s+' : "E2",
        r'^\s*O\s+N1\s+' : "N1",
        r'^\s*O\s+N2\s+' : "N2",
        r'^\s*O\s+\d'    : "Intra",
        r'^\s*O\s+\S'    : "Intra",
    }

    def classify(line: str) -> str:
        if re.match(r'^\s*O\s+IA\s+',    line, re.IGNORECASE): return "Inter"
        if re.match(r'^\s*O\s+E1\s+',    line, re.IGNORECASE): return "E1"
        if re.match(r'^\s*O\s+E2\s+',    line, re.IGNORECASE): return "E2"
        if re.match(r'^\s*O\*?N1[\s+]',  line, re.IGNORECASE): return "N1"
        if re.match(r'^\s*O\*?N2[\s+]',  line, re.IGNORECASE): return "N2"
        if re.match(r'^\s*O\s+N1\s+',    line, re.IGNORECASE): return "N1"
        if re.match(r'^\s*O\s+N2\s+',    line, re.IGNORECASE): return "N2"
        return "Intra"

    for line in raw.splitlines():
        m = primary_re.match(line)
        if m:
            dest = m.group(1)
            if "/" not in dest:
                try:
                    dest = str(ipaddress.IPv4Network(dest, strict=False))
                except Exception:
                    pass
            current = {
                "type" : classify(line),
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

    W_TYPE = 6
    W_DEST = 20
    W_VIA  = 15
    W_INTF = 14
    W_COST = 5
    W_AGE  = 10

    # Color external route types distinctly
    TYPE_COLOR = {
        "Intra": "",
        "Inter": CYAN,
        "E1"   : YELLOW,
        "E2"   : YELLOW,
        "N1"   : GREEN,
        "N2"   : GREEN,
    }

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
        color = TYPE_COLOR.get(rtype, "")

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
    """Display formatted OSPF route table and validate filtering behavior.

    Step 1 — Route table display (all OSPF route types including external).
    Step 2 — Filtering validation:
               Area 20 routers (R5, R6): must have O N2 0.0.0.0/0 (NSSA default)
               Area 20 routers (R5, R6): must NOT have 100.0.0.0 (R3 A20-IN filter)
               Area 0 / Area 10 routers: must NOT have 102.0.0.0 or 103.0.0.0
                                          (R2 A10-OUT filter)
    Step 3 — Network statement validation against live interface state.

    Returns: "PASS", "WARN", or "FAIL"
    """
    if device_name in EIGRP_ONLY_ROUTERS:
        emit(info(f"{device_name} is EIGRP-only — OSPF route check skipped."), lf)
        return "INFO"

    worst = "PASS"

    # Step 1 — Route table
    section("OSPF Route Table — show ip route ospf", lf)
    route_output = conn.cli(["show ip route ospf"])["show ip route ospf"]
    routes = _parse_ospf_routes(route_output)

    if not routes:
        emit(warned(f"No OSPF routes in routing table on {device_name}"), lf)
        worst = _worst(worst, "WARN")
    else:
        _print_route_table(routes, lf)
        by_type = {}
        for r in routes:
            by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        type_summary = "  ".join(f"{t}:{c}" for t, c in sorted(by_type.items()))
        emit(info(f"{len(routes)} OSPF route(s) — {type_summary}"), lf)

    # Build a set of destination prefixes for filtering checks
    route_dests = {r["dest"] for r in routes}

    # Step 2 — Filtering validation
    section("LSA Filtering Validation", lf)

    ospf_data = device_data.get("ospf") or {}
    area_types = ospf_data.get("area_types", []) or []
    in_area_20 = any(str(at.get("area", "")) == "20" for at in area_types)

    # Determine router's area membership for filtering checks
    # Pure Area 20 routers (R5, R6) — check NSSA default and A20-IN filter
    # R3 is the NSSA ABR (Area 0 + Area 20) — it generates the default and applies
    # the filter; these checks do not apply to the originating ABR itself.
    # All others — check A10-OUT filter
    in_area_0 = any(
        str(n.get("area", "")) == "0"
        for n in (ospf_data.get("networks", []) or [])
    )
    if in_area_20 and not in_area_0 and device_name not in EIGRP_ONLY_ROUTERS:
        # Must have NSSA default route (R5, R6 only)
        nssa_default = any(
            r["dest"] in ("0.0.0.0/0", "0.0.0.0") and r["type"] in ("N1", "N2")
            for r in routes
        )
        if nssa_default:
            emit(passed(f"NSSA default route (O N1/N2 0.0.0.0/0) present — R3 "
                        f"default-information-originate working"), lf)
        else:
            emit(failed(f"NSSA default route (O N1/N2 0.0.0.0/0) NOT found — "
                        f"check R3 area 20 nssa default-information-originate"), lf)
            worst = _worst(worst, "FAIL")

        # Must NOT have 100.0.0.0 (blocked by R3 A20-IN)
        blocked = any("100.0.0.0" in d for d in route_dests)
        if not blocked:
            emit(passed(f"100.0.0.0/8 absent — R3 A20-IN filter working correctly"), lf)
        else:
            emit(failed(f"100.0.0.0/8 present — R3 A20-IN filter NOT working"), lf)
            worst = _worst(worst, "FAIL")

    elif in_area_20 and in_area_0 and device_name not in EIGRP_ONLY_ROUTERS:
        # R3: NSSA ABR — originates the default and applies A20-IN; checks
        # don't apply to the router that generates/applies them.
        emit(info(f"{device_name} is the NSSA ABR (Area 0 + Area 20) — "
                  f"NSSA default and A20-IN filter checks not applicable on the originating ABR"), lf)

    elif device_name not in EIGRP_ONLY_ROUTERS:
        # A10-OUT filter check: only applies to routers with NO Area 10 membership.
        # Routers in Area 10 (R2, R4, R10) see 102.0.0.0/8 and 103.0.0.0/8 as
        # intra-area routes — the filter prevents Type 3 LSA propagation outward,
        # not the originating router's own view of its own area.
        in_area_10 = any(
            str(n.get("area", "")) == "10"
            for n in (ospf_data.get("networks", []) or [])
        )
        if in_area_10:
            emit(info(f"{device_name} is in Area 10 — A10-OUT filter check not applicable "
                      f"(intra-area routes always visible to Area 10 members)"), lf)
        else:
            # Area 0 routers (R1, R3) — must NOT have 102.0.0.0 or 103.0.0.0
            for blocked_prefix in ("102.0.0.0", "103.0.0.0"):
                present = any(blocked_prefix in d for d in route_dests)
                if not present:
                    emit(passed(f"{blocked_prefix}/8 absent — R2 A10-OUT filter working correctly"), lf)
                else:
                    emit(failed(f"{blocked_prefix}/8 present — R2 A10-OUT filter NOT working"), lf)
                    worst = _worst(worst, "FAIL")
    else:
        emit(info(f"{device_name} is EIGRP-only — LSA filtering checks not applicable."), lf)

    # Step 3 — Network statement validation
    section("OSPF Network Statement Validation", lf)

    networks = ospf_data.get("networks", []) or []

    if not networks:
        emit(info("No OSPF network statements in YAML — skipping validation."), lf)
        return worst

    intf_raw = conn.cli(["show ip interface"])["show ip interface"]
    intf_map = parse_interface_state(intf_raw)

    if not intf_map:
        emit(failed("Could not parse interface state."), lf)
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
            emit(failed(f"Network {label} — no interface found with matching IP"), lf)
            worst = _worst(worst, "FAIL")
        elif match_data["up"]:
            emit(passed(f"Network {label} — {match_intf} ({match_data['ip']}) is up/up"), lf)
        else:
            emit(warned(
                f"Network {label} — {match_intf} ({match_data['ip']}) is "
                f"{match_data['phys']}/{match_data['proto']}"
            ), lf)
            worst = _worst(worst, "WARN")

    return worst


def check_lsdb(conn, device_name: str, lf=None) -> str:
    """Display OSPF LSDB using targeted per-type commands.

    Uses separate commands for each LSA type rather than the combined
    'show ip ospf database' to make specific LSA types clearly visible:

      show ip ospf database router         — Type 1 (Router LSAs)
      show ip ospf database summary        — Type 3 (Summary LSAs)
      show ip ospf database asbr-summary   — Type 4 (ASBR Summary LSAs)
      show ip ospf database external       — Type 5 (AS External LSAs)
      show ip ospf database nssa-external  — Type 7 (NSSA External LSAs)

    Skipped on EIGRP-only routers. Returns "INFO" — always informational.
    """
    if device_name in EIGRP_ONLY_ROUTERS:
        emit(info(f"{device_name} is EIGRP-only — LSDB check skipped."), lf)
        return "INFO"

    lsdb_commands = [
        ("Type 1 — Router LSAs",       "show ip ospf database router"),
        ("Type 3 — Summary LSAs",      "show ip ospf database summary"),
        ("Type 4 — ASBR Summary LSAs", "show ip ospf database asbr-summary"),
        ("Type 5 — AS External LSAs",  "show ip ospf database external"),
        ("Type 7 — NSSA External LSAs","show ip ospf database nssa-external"),
    ]

    for title, cmd in lsdb_commands:
        section(f"LSDB — {title}", lf)
        output = conn.cli([cmd])[cmd]
        if output.strip():
            emit_raw(output, lf)
        else:
            emit(info(f"No output — {title} not present on {device_name}"), lf)

    emit(info(
        "LSDB displayed. Verify:\n"
        "  Type 1  — Router LSAs present for all OSPF routers in each area\n"
        "  Type 3  — Summary LSAs present (inter-area prefixes)\n"
        "  Type 4  — ASBR Summary LSAs present in Area 10 (R1 reachability)\n"
        "  Type 5  — External LSAs from R1 (EIGRP 100) and R3 (converted from R6 Type 7)\n"
        "  Type 7  — NSSA External LSAs on Area 20 routers (R5, R6) from R6 redistribution"
    ), lf)

    return "INFO"


def check_redistribution(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Validate bidirectional redistribution state.

    R1 — OSPF → EIGRP 100: confirm 'show ip route eigrp' has D EX entries
                            (OSPF routes redistributed into EIGRP 100)
    R6 — OSPF → EIGRP 111: confirm 'show ip route eigrp' has D EX entries
                            (OSPF routes redistributed into EIGRP 111)
    R7, R8 — EIGRP 100: confirm D EX entries exist (redistributed from OSPF via R1)
    R9     — EIGRP 111: confirm D EX entries exist (redistributed from OSPF via R6)
    R2, R3, R4, R5, R10 — OSPF-only internal routers: confirm O E1/E2 external
                           routes present (redistributed EIGRP routes in OSPF domain)

    Returns: "PASS", "WARN", or "FAIL"
    """
    section("Redistribution Validation", lf)

    worst = "PASS"

    eigrp_data = device_data.get("eigrp")

    # ------------------------------------------------------------------
    # R1 and R6: ASBRs — confirm 'redistribute ospf' is in EIGRP config
    # and OSPF table for O E1/N entries (EIGRP redistributed in)
    # NOTE: D EX routes from OSPF→EIGRP redistribution appear on the
    # receiving routers (R7/R8 for R1, R9 for R6), not on the originating
    # ASBR itself. Check the running config for the redistribute command.
    # ------------------------------------------------------------------
    if eigrp_data and device_data.get("ospf"):
        as_number = eigrp_data.get("as_number", "?")

        # Running config — confirm 'redistribute ospf' present in EIGRP process
        run_output = conn.cli(["show run | section router eigrp"])["show run | section router eigrp"]
        emit_raw(run_output, lf)

        if re.search(r'redistribute ospf', run_output, re.IGNORECASE):
            emit(passed(
                f"EIGRP AS {as_number}: 'redistribute ospf' configured "
                f"— OSPF → EIGRP redistribution present"
            ), lf)
        else:
            drift_detail = (
                f"  Router   : {device_name}\n"
                f"  Check    : redistribution\n"
                f"  Finding  : 'redistribute ospf' absent from EIGRP AS {as_number} config\n"
                f"  Impact   : OSPF routes are not being redistributed into EIGRP"
            )
            emit(failed(
                f"EIGRP AS {as_number}: 'redistribute ospf' not found in EIGRP config "
                f"— OSPF → EIGRP redistribution missing"
            ), lf)
            emit_drift(device_name, drift_detail, lf)
            worst = _worst(worst, "FAIL")

        # OSPF config — confirm 'redistribute eigrp' present in OSPF process
        # (The redistributed routes appear in neighbors' tables, not this router's own
        # OSPF table — checking the config is the correct validation here.)
        ospf_run = conn.cli(["show run | section router ospf"])["show run | section router ospf"]
        emit_raw(ospf_run, lf)

        if re.search(r'redistribute eigrp', ospf_run, re.IGNORECASE):
            emit(passed(
                f"OSPF: 'redistribute eigrp' configured "
                f"— EIGRP → OSPF redistribution present"
            ), lf)
        else:
            drift_detail = (
                f"  Router   : {device_name}\n"
                f"  Check    : redistribution\n"
                f"  Finding  : 'redistribute eigrp' absent from OSPF config\n"
                f"  Impact   : EIGRP routes are not being redistributed into OSPF domain"
            )
            emit(failed(
                f"OSPF: 'redistribute eigrp' not found in OSPF config "
                f"— EIGRP → OSPF redistribution missing"
            ), lf)
            emit_drift(device_name, drift_detail, lf)
            worst = _worst(worst, "FAIL")

    # ------------------------------------------------------------------
    # EIGRP-only routers (R7, R8, R9): check for D EX entries
    # ------------------------------------------------------------------
    elif device_name in EIGRP_ONLY_ROUTERS:
        eigrp_output = conn.cli(["show ip route eigrp"])["show ip route eigrp"]
        emit_raw(eigrp_output, lf)

        d_ex_entries = [l for l in eigrp_output.splitlines()
                        if re.match(r'^\s*D\s+EX\s+', l, re.IGNORECASE)]
        if d_ex_entries:
            emit(passed(
                f"{len(d_ex_entries)} D EX route(s) present "
                f"— redistributed OSPF routes received from ASBR"
            ), lf)
        else:
            drift_detail = (
                f"  Router   : {device_name}\n"
                f"  Check    : redistribution\n"
                f"  Finding  : no D EX routes in EIGRP table\n"
                f"  Impact   : OSPF redistribution into EIGRP is not propagating to this router"
            )
            emit(failed(
                f"No D EX routes found "
                f"— OSPF redistribution into EIGRP may not be working"
            ), lf)
            emit_drift(device_name, drift_detail, lf)
            worst = _worst(worst, "FAIL")

    # ------------------------------------------------------------------
    # Internal OSPF routers (R2, R3, R4, R5, R10):
    # check OSPF table for external routes (O E1/E2/N1/N2)
    # ------------------------------------------------------------------
    else:
        ospf_output = conn.cli(["show ip route ospf"])["show ip route ospf"]
        emit_raw(ospf_output, lf)

        ext_entries = [l for l in ospf_output.splitlines()
                       if re.match(r'^\s*O\s+(?:E1|E2|N1|N2)\s+', l, re.IGNORECASE)]
        if ext_entries:
            emit(passed(
                f"{len(ext_entries)} OSPF external route(s) (E1/E2/N1/N2) present "
                f"— redistribution visible from this router"
            ), lf)
        else:
            drift_detail = (
                f"  Router   : {device_name}\n"
                f"  Check    : redistribution\n"
                f"  Finding  : no OSPF external routes (E1/E2/N1/N2) in routing table\n"
                f"  Impact   : EIGRP → OSPF redistribution is not visible at this router"
            )
            emit(failed(
                f"No OSPF external routes (E1/E2/N1/N2) found "
                f"— redistribution may not be propagating correctly"
            ), lf)
            emit_drift(device_name, drift_detail, lf)
            worst = _worst(worst, "FAIL")

    return worst


def check_route_lookup(conn, device_name: str, target: str, lf=None) -> None:
    """Run a filtered route lookup for a specific IP or prefix."""
    section(f"Route Lookup — show ip route | include {target}", lf)

    output = conn.cli([f"show ip route | include {target}"])[f"show ip route | include {target}"]

    if output.strip():
        emit_raw(output, lf)
        emit(passed(f"'{target}' found in routing table on {device_name}"), lf)
    else:
        emit("\n  (no output)\n", lf)
        emit(failed(f"'{target}' NOT found in routing table on {device_name}"), lf)


# =============================================================================
# DETAIL + SUMMARY
# =============================================================================

def _print_detail(detail: dict, lf=None) -> None:
    """Print a per-device list of all INFO/PASS/WARN/FAIL lines before the summary."""
    bar = "=" * 60
    for line in [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}  Verification Detail{RESET}",
        f"{BOLD}{bar}{RESET}",
    ]:
        emit(line, lf)

    for device_name, dev_info in detail.items():
        device_header(device_name, dev_info["dns_name"], dev_info["oob_ip"], lf)
        for msg in dev_info["messages"]:
            indented = f"  {msg}"
            print(indented)
            if lf:
                lf.write(_strip_ansi(indented) + "\n")

    footer = f"{BOLD}{bar}{RESET}"
    print(footer)
    if lf:
        lf.write(_strip_ansi(footer) + "\n")


def _print_summary(
    results: dict[str, dict[str, str]],
    checks_to_run: list[str],
    lf=None,
) -> None:
    """Print a per-device, per-check summary table with totals row."""
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

    bar      = "=" * 60
    W_DEVICE = 8
    W_CHECK  = 14

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
            pad = W_CHECK + (len(colored) - len(token))
            row += f"  {colored:<{pad}}"
        emit(row, lf)

    emit(divider, lf)

    totals_row = f"  {'Totals':<{W_DEVICE}}"
    for chk in checks_to_run:
        parts = []
        for token in ("PASS", "WARN", "FAIL", "INFO"):
            count = totals[chk].get(token, 0)
            if count:
                parts.append(f"{_colored_token(token)}:{count}")
        cell = "  ".join(parts) if parts else "—"
        raw_len = (
            sum(len(t) + 1 + len(str(totals[chk][t]))
                for t in ("PASS", "WARN", "FAIL", "INFO")
                if totals[chk].get(t, 0))
            + (2 * (len(parts) - 1))
            if parts else 1
        )
        pad = W_CHECK + (len(cell) - raw_len)
        totals_row += f"  {cell:<{pad}}"
    emit(totals_row, lf)
    emit(f"{BOLD}{bar}{RESET}\n", lf)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Module 04 — OSPF Advanced Verification\n"
            "Connects to lab routers and verifies OSPF Advanced operational\n"
            "state against expected values defined in ospf_advanced.yaml.\n"
            "All output is mirrored to a timestamped log file in logs/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python verify_ospf_advanced.py\n"
            "  python verify_ospf_advanced.py --router R1 R6\n"
            "  python verify_ospf_advanced.py --check neighbors redistribution\n"
            "  python verify_ospf_advanced.py --route 100.0.0.0\n"
            "  python verify_ospf_advanced.py --router R5 --check routes lsdb\n"
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

    # --list-checks
    if args.list_checks:
        print(f"\n{BOLD}Available verification checks:{RESET}\n")
        descriptions = {
            "neighbors"     : "Verify OSPF neighbors are FULL (skipped on R7/R8/R9)",
            "interfaces"    : "Validate area and network type (skipped on R7/R8/R9)",
            "routes"        : "Route table (all types) + filtering + network statement validation",
            "lsdb"          : "OSPF LSDB — per-type display (Type 1/3/4/5/7) — informational",
            "redistribution": "Validate EIGRP ↔ OSPF redistribution on all routers",
        }
        for name, desc in descriptions.items():
            print(f"  {CYAN}{name:<16}{RESET} {desc}")
        print(f"\n  {CYAN}--route <IP>{RESET}   Filtered route lookup: show ip route | include <IP>\n")
        sys.exit(0)

    # Validate --check
    if args.check:
        invalid = [c for c in args.check if c not in AVAILABLE_CHECKS]
        if invalid:
            print(f"[ERROR] Unknown check(s): {invalid}")
            print(f"        Valid options: {AVAILABLE_CHECKS}")
            sys.exit(1)
        checks_to_run = args.check
    else:
        checks_to_run = AVAILABLE_CHECKS

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
        print("[ERROR] No valid target routers to process.")
        sys.exit(1)

    # Open log file
    global _result_collector
    lf = setup_logger()

    # Run header
    summary_lines = [
        f"\nNAMS26 — Module 04: OSPF Advanced Verification",
        f"Targets : {', '.join(target_routers)}",
        f"Checks  : {', '.join(checks_to_run)}"
        + (f"  +  route lookup: {args.route}" if args.route else ""),
    ]
    for line in summary_lines:
        emit(line, lf)

    results: dict[str, dict[str, str]] = {}
    detail:  dict = {}

    try:
        for device_name in target_routers:
            device_data = devices[device_name]
            oob_ip      = device_data.get("oob_ip", "")
            dns_name    = device_data.get("dns_name", "")
            creds       = device_data.get("credentials", default_creds)

            results[device_name] = {}
            _result_collector = []
            detail[device_name] = {
                "dns_name": dns_name,
                "oob_ip":   oob_ip,
                "messages": _result_collector,
            }

            if not dns_name:
                emit(failed(f"No dns_name defined for {device_name} — skipping."), lf)
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

                if "redistribution" in checks_to_run:
                    results[device_name]["redistribution"] = check_redistribution(
                        device, device_name, device_data, lf)

                if args.route:
                    check_route_lookup(device, device_name, args.route, lf)

            finally:
                device.close()
                lf and lf.write(f"  [INFO] Disconnected from {device_name}\n")

        _result_collector = None
        _print_detail(detail, lf)
        _print_summary(results, checks_to_run, lf)
        emit(f"\n{'=' * 60}\nVerification complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
