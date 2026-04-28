#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 05
File     : modules/05_ipv6_eigrp_ospf_nornir/scripts/verify_ipv6_eigrp_ospf.py
Purpose  : Verify IPv6 EIGRP and OSPFv3 operational state across all lab routers.
           Connects to devices in series via Netmiko, runs IPv6 show commands,
           and compares live state against expected values from the YAML inventory.
           Per-device PASS / WARN / FAIL results are printed to terminal and
           mirrored to a timestamped log in modules/05_ipv6_eigrp_ospf_nornir/logs/.

Usage:
    python verify_ipv6_eigrp_ospf.py                         # verify all routers
    python verify_ipv6_eigrp_ospf.py --router R1 R6          # specific routers
    python verify_ipv6_eigrp_ospf.py --check neighbors routes redistribution
    python verify_ipv6_eigrp_ospf.py --list-checks

Checks:
    neighbors     — EIGRPv6 peer count and OSPFv3 adjacency state per router
    routes        — IPv6 route table: expected route types present per router role
    redistribution— EIGRPv6 ↔ OSPFv3 redistribution visible from each router
    areas         — OSPFv3 area type (stub / NSSA) applied correctly per YAML

Router roles (derived from YAML):
    ASBR        — has both eigrp and ospf blocks (R1, R6)
    EIGRP_ONLY  — has eigrp block only (R7, R8)
    OSPF_ONLY   — has ospf block only (R2, R3, R4, R5, R9)

Logging:
    A timestamped log file is written to modules/05_ipv6_eigrp_ospf_nornir/logs/
    on every run. Log captures all raw command output and result lines in plain text.
"""

import os
import re
import sys
import yaml
import argparse
from datetime import datetime
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)
LOG_DIR      = os.path.join(MODULE_DIR, "logs")
DATA_FILE    = os.path.join(MODULE_DIR, "data", "ipv6_eigrp_ospf.yaml")

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# AVAILABLE CHECKS
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "routes", "redistribution", "areas"]

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
    """Print to stdout and mirror (without ANSI) to log file."""
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")

def emit_raw(text: str, lf=None) -> None:
    """Print and log a block of raw command output."""
    print(f"\n{text}\n")
    if lf:
        lf.write(f"\n{text}\n\n")

def emit_drift(device_name: str, detail: str, lf=None) -> None:
    """Log a drift detection block with a clear delimiter to the session log."""
    timestamp = datetime.now().strftime("%Y%m%d %H:%M:%S")
    bar       = "=" * 51
    header    = f"=== DRIFT DETECTED — {device_name} — {timestamp} ==="
    lines = [
        f"\n{RED}{header}{RESET}",
        detail,
        f"{RED}{bar}{RESET}\n",
    ]
    for line in lines:
        print(line)
        if lf:
            lf.write(_strip_ansi(line) + "\n")


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"verify_ipv6_eigrp_ospf_{timestamp}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 05: IPv6 EIGRP/OSPFv3 Verification\n")
    lf.write(f"Log created : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write(f"Log file    : {log_path}\n")
    lf.write("=" * 60 + "\n\n")
    print(info(f"Logging to  : {log_path}"))
    return lf


# =============================================================================
# NETMIKO CONNECTION
# =============================================================================

def connect(device_name: str, dns_name: str, creds: dict, lf=None):
    """Establish a Netmiko session to the target device.

    Returns an open ConnectHandler or None on failure.
    """
    if not os.path.isfile(KNOWN_HOSTS_FILE):
        emit(warned(
            f"known_hosts not found at {KNOWN_HOSTS_FILE} — "
            "run utils/clear_known_hosts.sh then utils/init_ssh.py first"
        ), lf)

    try:
        conn = ConnectHandler(
            device_type="cisco_ios",
            host=dns_name,
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            # global_delay_factor doubles all internal Netmiko timing constants.
            # Needed because IOL routers respond slowly.
            # Current: 2.0   Range: 1.0 (fastest) – 5.0 (very slow hosts)
            global_delay_factor=2.0,
        )
        emit(info(f"Connected to {device_name} ({dns_name})"), lf)
        return conn
    except NetmikoTimeoutException as exc:
        emit(failed(f"Connection timeout to {device_name} ({dns_name}): {exc}"), lf)
    except NetmikoAuthenticationException as exc:
        emit(failed(f"Authentication failed to {device_name}: {exc}"), lf)
    except Exception as exc:
        emit(failed(f"Connection error on {device_name}: {exc}"), lf)
    return None


# =============================================================================
# HELPERS
# =============================================================================

_RANK = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}

def _worst(a: str, b: str) -> str:
    """Return the worse of two result tokens. FAIL > WARN > PASS/INFO."""
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


def _get_role(device_data: dict) -> str:
    """Return ASBR, EIGRP_ONLY, or OSPF_ONLY from YAML routing block presence."""
    has_eigrp = device_data.get("eigrp") is not None
    has_ospf  = device_data.get("ospf") is not None
    if has_eigrp and has_ospf:
        return "ASBR"
    if has_eigrp:
        return "EIGRP_ONLY"
    return "OSPF_ONLY"


def _is_stub_area(device_data: dict) -> bool:
    """Return True if the device is configured as a stub area member."""
    ospf = device_data.get("ospf") or {}
    return any(at.get("type") == "stub" for at in (ospf.get("area_types") or []))


def _is_backbone_connected(device_data: dict) -> bool:
    """Return True if any interface is assigned to Area 0 (device is an ABR)."""
    interfaces = device_data.get("interfaces") or {}
    return any(
        str(iface.get("ospf_area", "")).strip() == "0"
        for iface in interfaces.values()
    )


# =============================================================================
# VERIFICATION CHECKS
# =============================================================================

def check_neighbors(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Verify EIGRPv6 peer count and OSPFv3 adjacency state.

    EIGRPv6: At least one active neighbor required.
    OSPFv3: At least one FULL adjacency required (WARN if stuck in
            EXSTART/EXCHANGE/INIT/LOADING; FAIL if no neighbors at all).

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    worst = "PASS"
    role  = _get_role(device_data)

    if role in ("ASBR", "EIGRP_ONLY"):
        section("EIGRPv6 Neighbors — show ipv6 eigrp neighbors", lf)
        output = conn.send_command("show ipv6 eigrp neighbors")
        emit_raw(output, lf)

        # Neighbor lines begin with a link-local or global IPv6 address
        nbr_lines = [l for l in output.splitlines()
                     if re.match(r'^\s*[Ff][Ee]80|^\s*[Ff][Cc]|^\s*[Ff][Dd]', l)
                     or re.match(r'^\s*[0-9A-Fa-f]{1,4}:', l)]
        if nbr_lines:
            emit(passed(f"EIGRPv6: {len(nbr_lines)} neighbor(s) active"), lf)
        else:
            emit(failed(
                "EIGRPv6: No neighbors found — "
                "check 'ipv6 eigrp <as>' on interfaces and EIGRP process"
            ), lf)
            worst = _worst(worst, "FAIL")

    if role in ("ASBR", "OSPF_ONLY"):
        section("OSPFv3 Neighbors — show ipv6 ospf neighbor", lf)
        output = conn.send_command("show ipv6 ospf neighbor")
        emit_raw(output, lf)

        problem_states = re.compile(r'\b(EXSTART|EXCHANGE|INIT|LOADING)\b', re.IGNORECASE)
        full_re        = re.compile(r'\bFULL\b', re.IGNORECASE)

        if full_re.search(output):
            count = len(full_re.findall(output))
            emit(passed(f"OSPFv3: {count} FULL adjacency(ies)"), lf)
        elif problem_states.search(output):
            states = list(set(problem_states.findall(output)))
            emit(warned(
                f"OSPFv3: Stuck state detected — {', '.join(states)}. "
                "Check area type and interface MTU."
            ), lf)
            worst = _worst(worst, "WARN")
        elif output.strip():
            emit(warned(
                "OSPFv3: Neighbors present but no FULL state — adjacency not converged"
            ), lf)
            worst = _worst(worst, "WARN")
        else:
            emit(failed(
                "OSPFv3: No neighbors found — "
                "check 'ipv6 ospf <pid> area <area>' on interfaces and area type"
            ), lf)
            worst = _worst(worst, "FAIL")

    return worst


def check_routes(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Display IPv6 route table and validate route types per router role.

    EIGRP-only (R7, R8):
        D EX entries required — proves OSPFv3 routes are redistributed into EIGRPv6.
    OSPF stub leaf (R5, R9 — Area 10 totally stubby, no backbone interface):
        OI ::/0 default route required. No individual OE2/ON2 expected (by design).
    OSPF ABR / non-stub (R2, R3, R4 — backbone-connected):
        At least some OSPFv3 routes required in table.
    ASBRs (R1, R6):
        Both EIGRPv6 and OSPFv3 routes expected.

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    worst = "PASS"
    role  = _get_role(device_data)

    section("IPv6 Route Table — show ipv6 route", lf)
    output = conn.send_command("show ipv6 route")
    emit_raw(output, lf)

    if role == "EIGRP_ONLY":
        # IOL displays EIGRPv6 external routes as 'EX' (not 'D EX' as in IPv4 EIGRP).
        d_ex = [l for l in output.splitlines()
                if re.match(r'^\s*(D\s+EX|EX)\s+[0-9A-Fa-f:]', l, re.IGNORECASE)]
        d    = [l for l in output.splitlines()
                if re.match(r'^\s*D\s+[0-9A-Fa-f:]', l, re.IGNORECASE)
                and not re.match(r'^\s*(D\s+EX|EX)\s+[0-9A-Fa-f:]', l, re.IGNORECASE)]

        if d_ex:
            emit(passed(
                f"EIGRPv6: {len(d_ex)} EX route(s) — "
                "OSPFv3 redistributed into EIGRPv6 confirmed"
            ), lf)
        elif d:
            emit(warned(
                f"EIGRPv6: {len(d)} D route(s) present but no EX — "
                "OSPFv3 → EIGRPv6 redistribution may not be working"
            ), lf)
            worst = _worst(worst, "WARN")
        else:
            emit(failed(
                "EIGRPv6: No EIGRP routes found — "
                "check EIGRP process and 'ipv6 eigrp <as>' on interfaces"
            ), lf)
            worst = _worst(worst, "FAIL")

    elif role == "OSPF_ONLY" and _is_stub_area(device_data) and not _is_backbone_connected(device_data):
        # Stub area leaf (R5, R9) — expects OI ::/0 default from ABR; no external routes.
        oi_default = bool(re.search(r'^\s*OI\s+::/0', output, re.MULTILINE | re.IGNORECASE))
        if oi_default:
            emit(passed(
                "OSPFv3: OI ::/0 default route present — "
                "stub ABR is advertising the summary default correctly"
            ), lf)
        else:
            emit(failed(
                f"OSPFv3: OI ::/0 default route NOT found — "
                f"check stub ABR 'area stub no-summary' and Area 10 adjacency"
            ), lf)
            worst = _worst(worst, "FAIL")

        ext = [l for l in output.splitlines()
               if re.match(r'^\s*O(E[12]|N[12])\s+[0-9A-Fa-f:]', l, re.IGNORECASE)]
        if ext:
            emit(warned(
                f"{len(ext)} OE/ON external route(s) in stub area — "
                "unexpected; verify 'area stub' is configured on this router"
            ), lf)
            worst = _worst(worst, "WARN")
        else:
            emit(passed("No OE2/ON2 routes — correct for stub/totally-stubby area"), lf)

    elif role == "OSPF_ONLY":
        ospf_routes = [l for l in output.splitlines()
                       if re.match(r'^\s*O[^B]?\s+[0-9A-Fa-f:]', l)]
        if ospf_routes:
            emit(passed(f"OSPFv3: {len(ospf_routes)} OSPFv3 route(s) present in table"), lf)
        else:
            emit(warned(
                "OSPFv3: No OSPFv3 routes found — "
                "check neighbors and 'ipv6 ospf <pid> area <area>' on interfaces"
            ), lf)
            worst = _worst(worst, "WARN")

    elif role == "ASBR":
        d_routes = [l for l in output.splitlines()
                    if re.match(r'^\s*D(\s+EX)?\s+[0-9A-Fa-f:]', l, re.IGNORECASE)]
        o_routes = [l for l in output.splitlines()
                    if re.match(r'^\s*O[^B]?\s+[0-9A-Fa-f:]', l)]

        if d_routes:
            emit(passed(f"EIGRPv6: {len(d_routes)} EIGRP route(s) in table"), lf)
        else:
            emit(warned("EIGRPv6: No EIGRP routes in table — check EIGRP adjacency"), lf)
            worst = _worst(worst, "WARN")

        if o_routes:
            emit(passed(f"OSPFv3: {len(o_routes)} OSPFv3 route(s) in table"), lf)
        else:
            emit(warned("OSPFv3: No OSPF routes in table — check OSPFv3 adjacency"), lf)
            worst = _worst(worst, "WARN")

    return worst


def check_redistribution(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Validate EIGRPv6 ↔ OSPFv3 redistribution per router role.

    ASBRs (R1, R6):   config check for 'redistribute ospf' in EIGRP and
                       'redistribute eigrp' in OSPF.
    EIGRP-only (R7, R8): D EX entries in EIGRPv6 table — redistributed from OSPFv3.
    OSPF stub (R5, R9):  skip — stub area blocks external routes by design;
                          validated via 'routes' check (default OI ::/0).
    OSPF non-stub (R2, R3, R4): OE2 or ON2 routes in OSPFv3 table.

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    section("Redistribution Validation", lf)

    role  = _get_role(device_data)
    worst = "PASS"

    if role == "ASBR":
        eigrp_data = device_data.get("eigrp") or {}
        ospf_data  = device_data.get("ospf")  or {}
        as_number  = eigrp_data.get("as_number", "?")
        process_id = ospf_data.get("process_id", "?")

        eigrp_run = conn.send_command("show run | section ipv6 router eigrp")
        emit_raw(eigrp_run, lf)

        if re.search(r'redistribute ospf', eigrp_run, re.IGNORECASE):
            emit(passed(
                f"EIGRPv6 AS {as_number}: 'redistribute ospf' configured — "
                "OSPFv3 → EIGRPv6 redistribution present"
            ), lf)
        else:
            drift_detail = (
                f"  Router   : {device_name}\n"
                f"  Check    : redistribution\n"
                f"  Finding  : 'redistribute ospf' absent from EIGRPv6 AS {as_number} config\n"
                f"  Impact   : OSPFv3 routes are not being redistributed into EIGRPv6"
            )
            emit(failed(
                f"EIGRPv6 AS {as_number}: 'redistribute ospf' NOT found — "
                "OSPFv3 → EIGRPv6 redistribution missing"
            ), lf)
            emit_drift(device_name, drift_detail, lf)
            worst = _worst(worst, "FAIL")

        ospf_run = conn.send_command("show run | section ipv6 router ospf")
        emit_raw(ospf_run, lf)

        if re.search(r'redistribute eigrp', ospf_run, re.IGNORECASE):
            emit(passed(
                f"OSPFv3 PID {process_id}: 'redistribute eigrp' configured — "
                "EIGRPv6 → OSPFv3 redistribution present"
            ), lf)
        else:
            drift_detail = (
                f"  Router   : {device_name}\n"
                f"  Check    : redistribution\n"
                f"  Finding  : 'redistribute eigrp' absent from OSPFv3 PID {process_id}\n"
                f"  Impact   : EIGRPv6 routes are not being redistributed into OSPFv3 domain"
            )
            emit(failed(
                f"OSPFv3 PID {process_id}: 'redistribute eigrp' NOT found — "
                "EIGRPv6 → OSPFv3 redistribution missing"
            ), lf)
            emit_drift(device_name, drift_detail, lf)
            worst = _worst(worst, "FAIL")

    elif role == "EIGRP_ONLY":
        eigrp_output = conn.send_command("show ipv6 route eigrp")
        emit_raw(eigrp_output, lf)

        # IOL displays EIGRPv6 external routes as 'EX' (not 'D EX' as in IPv4 EIGRP).
        d_ex = [l for l in eigrp_output.splitlines()
                if re.match(r'^\s*(D\s+EX|EX)\s+[0-9A-Fa-f:]', l, re.IGNORECASE)]
        if d_ex:
            emit(passed(
                f"{len(d_ex)} EX route(s) in EIGRPv6 table — "
                "redistributed OSPFv3 routes received from ASBR"
            ), lf)
        else:
            drift_detail = (
                f"  Router   : {device_name}\n"
                f"  Check    : redistribution\n"
                f"  Finding  : no EX routes in EIGRPv6 table\n"
                f"  Impact   : OSPFv3 → EIGRPv6 redistribution not propagating to this router"
            )
            emit(failed(
                "No EX routes in EIGRPv6 table — "
                "check ASBR 'redistribute ospf' in EIGRPv6"
            ), lf)
            emit_drift(device_name, drift_detail, lf)
            worst = _worst(worst, "FAIL")

    elif _is_stub_area(device_data) and not _is_backbone_connected(device_data):
        emit(info(
            f"{device_name} is in a stub/totally-stubby area — "
            "external OSPFv3 routes are filtered by design. "
            "See 'routes' check for OI ::/0 default route validation."
        ), lf)
        return "INFO"

    else:
        # Non-stub OSPF-only routers (R2, R3, R4): check for OE2 or ON2
        ospf_output = conn.send_command("show ipv6 route ospf")
        emit_raw(ospf_output, lf)

        ext = [l for l in ospf_output.splitlines()
               if re.match(r'^\s*O(E[12]|N[12])\s+[0-9A-Fa-f:]', l, re.IGNORECASE)]
        if ext:
            emit(passed(
                f"{len(ext)} OSPFv3 external route(s) (OE2/ON2) present — "
                "EIGRPv6 redistribution visible from this router"
            ), lf)
        else:
            drift_detail = (
                f"  Router   : {device_name}\n"
                f"  Check    : redistribution\n"
                f"  Finding  : no OE2/ON2 routes in OSPFv3 table\n"
                f"  Impact   : EIGRPv6 → OSPFv3 redistribution not visible at this router"
            )
            emit(failed(
                "No OSPFv3 external routes (OE2/ON2) in table — "
                "check ASBR 'redistribute eigrp' in OSPFv3"
            ), lf)
            emit_drift(device_name, drift_detail, lf)
            worst = _worst(worst, "FAIL")

    return worst


def check_areas(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Verify OSPFv3 area type (stub / NSSA) applied correctly per YAML.

    Reads 'show ipv6 ospf' and checks each area declared in YAML area_types
    is reflected correctly in the live OSPFv3 process. Skipped on EIGRP-only
    routers. Returns INFO for routers with no area_types in YAML.

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    role = _get_role(device_data)

    if role == "EIGRP_ONLY":
        emit(info(f"{device_name} is EIGRP-only — area type check skipped."), lf)
        return "INFO"

    ospf_data  = device_data.get("ospf") or {}
    area_types = ospf_data.get("area_types") or []

    if not area_types:
        emit(info(
            f"{device_name}: no area_types in YAML — "
            "backbone-only router; area type check not applicable"
        ), lf)
        return "INFO"

    section("OSPFv3 Area Types — show ipv6 ospf", lf)
    output = conn.send_command("show ipv6 ospf")
    emit_raw(output, lf)

    worst = "PASS"

    for at in area_types:
        area_id   = str(at.get("area", "?"))
        area_type = at.get("type", "").lower()

        area_present = bool(re.search(
            rf'Area\s+(?:BACKBONE\(0\)|{re.escape(area_id)})\b',
            output, re.IGNORECASE
        ))

        if not area_present:
            emit(failed(
                f"Area {area_id}: not found in 'show ipv6 ospf' — "
                "OSPFv3 process may not be active in this area"
            ), lf)
            worst = _worst(worst, "FAIL")
            continue

        if area_type == "stub":
            # IOS shows "Stub area" in the area block
            if re.search(r'Stub\s+area', output, re.IGNORECASE):
                emit(passed(f"Area {area_id}: stub confirmed in OSPFv3 process"), lf)
            else:
                emit(failed(
                    f"Area {area_id}: YAML declares stub but 'Stub area' not found — "
                    "check 'area 10 stub' in OSPFv3 config"
                ), lf)
                worst = _worst(worst, "FAIL")

        elif area_type == "nssa":
            # IOS shows "NSSA" in the area block
            if re.search(r'\bNSSA\b', output, re.IGNORECASE):
                emit(passed(f"Area {area_id}: NSSA confirmed in OSPFv3 process"), lf)
            else:
                emit(failed(
                    f"Area {area_id}: YAML declares NSSA but 'NSSA' not found — "
                    "check 'area 20 nssa' in OSPFv3 config"
                ), lf)
                worst = _worst(worst, "FAIL")

    return worst


# =============================================================================
# SUMMARY
# =============================================================================

def _print_summary(results: dict, checks_to_run: list, lf=None) -> None:
    """Print a per-device, per-check summary table with totals row."""
    _TOKEN_COLOR = {
        "PASS": GREEN, "WARN": YELLOW, "FAIL": RED, "INFO": CYAN, "—": "",
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

    for line in [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}  Verification Summary{RESET}",
        f"{BOLD}{bar}{RESET}",
        f"{BOLD}{header_line}{RESET}",
        divider,
    ]:
        emit(line, lf)

    totals: dict = {chk: {"PASS": 0, "WARN": 0, "FAIL": 0, "INFO": 0}
                    for chk in checks_to_run}

    for device_name, chk_results in results.items():
        row = f"  {device_name:<{W_DEVICE}}"
        for chk in checks_to_run:
            token  = chk_results.get(chk, "—")
            if token in totals[chk]:
                totals[chk][token] += 1
            colored = _colored_token(token)
            pad     = W_CHECK + (len(colored) - len(token))
            row    += f"  {colored:<{pad}}"
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
            "NAMS26 Module 05 — Verify IPv6 EIGRP/OSPFv3\n"
            "Connects to lab routers and verifies EIGRPv6 and OSPFv3 state\n"
            "against expected values in ipv6_eigrp_ospf.yaml.\n"
            "All output is mirrored to a timestamped log in logs/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python verify_ipv6_eigrp_ospf.py\n"
            "  python verify_ipv6_eigrp_ospf.py --router R1 R6\n"
            "  python verify_ipv6_eigrp_ospf.py --check neighbors redistribution\n"
            "  python verify_ipv6_eigrp_ospf.py --list-checks\n"
        ),
    )
    parser.add_argument(
        "--router", nargs="*", metavar="HOSTNAME",
        help="Target one or more routers by hostname. Defaults to all devices in YAML.",
    )
    parser.add_argument(
        "--check", nargs="*", metavar="CHECK",
        help=f"Checks to run: {', '.join(AVAILABLE_CHECKS)}. Defaults to all.",
    )
    parser.add_argument(
        "--list-checks", action="store_true",
        help="List all available verification checks and exit.",
    )
    args = parser.parse_args()

    if args.list_checks:
        print(f"\n{BOLD}Available verification checks:{RESET}\n")
        descriptions = {
            "neighbors"     : "EIGRPv6 peer count and OSPFv3 adjacency FULL state",
            "routes"        : "IPv6 route table — expected route types per router role",
            "redistribution": "EIGRPv6 ↔ OSPFv3 redistribution state (config + table)",
            "areas"         : "OSPFv3 area type (stub / NSSA) confirmed in live process",
        }
        for name, desc in descriptions.items():
            print(f"  {CYAN}{name:<16}{RESET} {desc}")
        print()
        sys.exit(0)

    if args.check:
        invalid = [c for c in args.check if c not in AVAILABLE_CHECKS]
        if invalid:
            print(f"[ERROR] Unknown check(s): {invalid}")
            print(f"        Valid options: {AVAILABLE_CHECKS}")
            sys.exit(1)
        checks_to_run = args.check
    else:
        checks_to_run = AVAILABLE_CHECKS

    if not os.path.isfile(DATA_FILE):
        print(f"[ERROR] YAML file not found: {DATA_FILE}")
        sys.exit(1)

    try:
        with open(DATA_FILE, "r") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        print(f"[ERROR] Failed to parse YAML: {exc}")
        sys.exit(1)

    devices       = data.get("devices", {})
    default_creds = data.get("default_credentials", {})

    if not devices:
        print("[ERROR] No devices found in YAML.")
        sys.exit(1)

    for dev_data in devices.values():
        if not dev_data.get("credentials"):
            dev_data["credentials"] = default_creds

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

    lf = setup_logger()

    summary_lines = [
        f"\nNAMS26 — Module 05: IPv6 EIGRP/OSPFv3 Verification",
        f"Targets : {', '.join(target_routers)}",
        f"Checks  : {', '.join(checks_to_run)}",
    ]
    for line in summary_lines:
        emit(line, lf)

    results: dict = {}

    try:
        for device_name in target_routers:
            device_data = devices[device_name]
            oob_ip      = device_data.get("oob_ip", "")
            dns_name    = device_data.get("dns_name", "")
            creds       = device_data.get("credentials", default_creds)

            results[device_name] = {}

            if not dns_name:
                emit(failed(f"No dns_name defined for {device_name} — skipping."), lf)
                for chk in checks_to_run:
                    results[device_name][chk] = "FAIL"
                continue

            device_header(device_name, dns_name, oob_ip, lf)

            conn = connect(device_name, dns_name, creds, lf)
            if conn is None:
                emit(failed(f"Skipping all checks on {device_name} — connection failed."), lf)
                for chk in checks_to_run:
                    results[device_name][chk] = "FAIL"
                continue

            try:
                if "neighbors" in checks_to_run:
                    results[device_name]["neighbors"] = check_neighbors(
                        conn, device_name, device_data, lf)

                if "routes" in checks_to_run:
                    results[device_name]["routes"] = check_routes(
                        conn, device_name, device_data, lf)

                if "redistribution" in checks_to_run:
                    results[device_name]["redistribution"] = check_redistribution(
                        conn, device_name, device_data, lf)

                if "areas" in checks_to_run:
                    results[device_name]["areas"] = check_areas(
                        conn, device_name, device_data, lf)

            finally:
                conn.disconnect()
                lf.write(f"  [INFO] Disconnected from {device_name}\n")

        _print_summary(results, checks_to_run, lf)
        emit(f"\n{'=' * 60}\nVerification complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
