#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 06
File     : modules/06_ipv6_isis_nornir/scripts/verify_06_ipv6_isis_nornir.py
Purpose  : Verify IS-IS Named Mode operational state across all lab routers.
           Connects in series via Netmiko, runs show commands, and compares
           live state against expected values from the YAML inventory.
           Per-device PASS / WARN / FAIL results are printed to terminal and
           mirrored to a timestamped log in modules/06_ipv6_isis_nornir/logs/.

Usage:
    python scripts/verify_06_ipv6_isis_nornir.py
    python scripts/verify_06_ipv6_isis_nornir.py --router BB-1 ABR-1
    python scripts/verify_06_ipv6_isis_nornir.py --check neighbors lsdb
    python scripts/verify_06_ipv6_isis_nornir.py --list-checks

Checks (all apply to IS-IS routers; ospf_only router gets adapted OSPF checks):
    neighbors   — IS-IS neighbor count and state vs. expected; DIS (BR-2);
                  OSPF adjacency (ASBR-1)
    lsdb        — Own LSP present; own loopback advertised in LSP;
                  external TLVs present (ASBR-1)
    routes      — IS-IS routes in IPv4 table; IS-IS IPv6 routes (BR-4, BR-5)
    mt          — MT-IS-IS IPv6 capability (BR-4, BR-5 only)

Logging:
    A timestamped log file is written to modules/06_ipv6_isis_nornir/logs/
    on every run.
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
DATA_FILE    = os.path.join(MODULE_DIR, "data", "06_ipv6_isis_nornir.yaml")

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# AVAILABLE CHECKS
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "lsdb", "routes", "mt"]

# Expected IS-IS neighbor counts per device (from topology design)
EXPECTED_NEIGHBORS = {
    "BB-1":   3,   # ABR-1, ABR-2, ABR-3
    "BB-2":   3,   # ABR-1, ABR-2, ABR-3
    "ABR-1":  5,   # BB-1, BB-2, BR-1, BR-2, BR-3
    "ABR-2":  4,   # BB-1, BB-2, BR-4, BR-5
    "ABR-3":  3,   # BB-1, BB-2, ASBR-1
    "BR-1":   1,   # ABR-1
    "BR-2":   1,   # ABR-1
    "BR-3":   1,   # ABR-1
    "BR-4":   2,   # ABR-2, BR-5
    "BR-5":   2,   # ABR-2, BR-4
    "ASBR-1": 1,   # ABR-3
}

# =============================================================================
# ANSI COLORS
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

def passed(msg: str) -> str: return f"{GREEN}  [PASS]{RESET} {msg}"
def failed(msg: str) -> str: return f"{RED}  [FAIL]{RESET} {msg}"
def warned(msg: str) -> str: return f"{YELLOW}  [WARN]{RESET} {msg}"
def info(msg: str)   -> str: return f"{CYAN}  [INFO]{RESET} {msg}"


# =============================================================================
# OUTPUT HELPERS
# =============================================================================

def emit(line: str, lf=None) -> None:
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")


def emit_raw(text: str, lf=None) -> None:
    block = f"\n{text}\n"
    print(block)
    if lf:
        lf.write(block + "\n")


def device_header(device_name: str, role: str, area: str, lf=None) -> None:
    bar  = "=" * 60
    line = (
        f"\n{BOLD}{bar}{RESET}\n"
        f"{BOLD}MODULE 06 — IS-IS / NORNIR — VERIFICATION{RESET}\n"
        f"{BOLD}Device: {device_name}  |  Role: {role}  |  Area: {area}{RESET}\n"
        f"{BOLD}{bar}{RESET}"
    )
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")


# =============================================================================
# RESULT RANKING
# =============================================================================
_RANK = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}

def _worst(a: str, b: str) -> str:
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


# =============================================================================
# LOGGING
# =============================================================================

def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    ts       = datetime.now().strftime("%y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, f"verify_06_ipv6_isis_{ts}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 06: IPv6 IS-IS Verification\n")
    lf.write(f"Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write("=" * 60 + "\n\n")
    print(info(f"Logging to: {log_path}"))
    return lf


# =============================================================================
# NETMIKO CONNECTION
# =============================================================================

def connect(device_name: str, dns_name: str, creds: dict, lf=None):
    if not os.path.isfile(KNOWN_HOSTS_FILE):
        emit(warned(
            f"known_hosts not found — run utils/clear_known_hosts.sh "
            "then utils/init_ssh.py first"
        ), lf)
    try:
        conn = ConnectHandler(
            device_type="cisco_ios",
            host=dns_name,
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            # global_delay_factor doubles all Netmiko internal timing constants.
            # Current: 2.0   Range: 1.0 (fastest) – 5.0 (very slow hosts)
            global_delay_factor=2.0,
        )
        emit(info(f"Connected to {device_name} ({dns_name})"), lf)
        return conn
    except NetmikoTimeoutException:
        emit(failed(f"Connection timeout to {device_name} ({dns_name})"), lf)
    except NetmikoAuthenticationException:
        emit(failed(f"Authentication failed on {device_name}"), lf)
    except Exception as exc:
        emit(failed(f"Connection error on {device_name}: {exc}"), lf)
    return None


# =============================================================================
# IS-IS VERIFICATION CHECKS
# =============================================================================

def check_neighbors(conn, device_name: str, dev: dict, lf=None) -> str:
    """show isis neighbors — count, state, and role-specific sub-checks.

    Sub-checks:
      BR-2   — DIS role confirmed if its own system ID appears in Circuit Id column
      ASBR-1 — OSPF adjacency to OSPF-1 must be FULL
    """
    worst  = "PASS"
    output = conn.send_command("show isis neighbors")
    emit_raw(output, lf)

    # Parse UP neighbors: split each line, check State field (index 4)
    nbr_up = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[4] == "UP":
            nbr_up.append(parts[0])

    count    = len(nbr_up)
    expected = EXPECTED_NEIGHBORS.get(device_name, -1)
    names    = ", ".join(nbr_up) if nbr_up else "none"

    if expected < 0:
        emit(info(f"IS-IS neighbors: {count} UP ({names})"), lf)
    elif count == expected:
        emit(passed(f"IS-IS neighbors: {count} UP ({names})"), lf)
    elif count > 0:
        emit(warned(
            f"IS-IS neighbors: {count}/{expected} UP ({names}) — expected {expected}"
        ), lf)
        worst = _worst(worst, "WARN")
    else:
        emit(failed(f"IS-IS neighbors: 0 UP — expected {expected}"), lf)
        worst = _worst(worst, "FAIL")

    # DIS check — BR-2 should be elected DIS on the Area 49.0002 LAN segment.
    # When BR-2 is DIS, its own system ID appears in the Circuit Id column of
    # neighbor entries (the DIS pseudonode ID begins with the DIS system ID).
    if device_name == "BR-2":
        dis_pattern   = re.compile(r'BR-2\.', re.IGNORECASE)
        dis_confirmed = dis_pattern.search(output) is not None
        if dis_confirmed:
            emit(passed("DIS role confirmed: BR-2 is DIS on Area 49.0002 LAN segment"), lf)
        else:
            emit(warned(
                "DIS role not confirmed — BR-2 not seen in Circuit Id column. "
                "Check isis priority 100 on Ethernet0/0"
            ), lf)
            worst = _worst(worst, "WARN")

    # OSPF adjacency check for ASBR-1
    if device_name == "ASBR-1":
        ospf_out = conn.send_command("show ip ospf neighbor")
        emit_raw(ospf_out, lf)
        if re.search(r'\bFULL\b', ospf_out, re.IGNORECASE):
            emit(passed("OSPF neighbor: OSPF-1 in FULL state"), lf)
        else:
            emit(failed(
                "OSPF neighbor: OSPF-1 not in FULL state — "
                "check 'ip ospf network point-to-point' and OSPF process on both ends"
            ), lf)
            worst = _worst(worst, "FAIL")

    return worst


def check_lsdb(conn, device_name: str, dev: dict, lf=None) -> str:
    """Own LSP in LSDB, own loopback advertised, and external TLVs (ASBR-1)."""
    worst = "PASS"

    # Own LSP — the local router's LSP is marked with * in 'show isis database'
    db_out = conn.send_command("show isis database")
    emit_raw(db_out, lf)

    if re.search(rf'{re.escape(device_name)}\.00-00\s+\*', db_out):
        emit(passed(f"Own LSP present in LSDB ({device_name}.00-00)"), lf)
    else:
        emit(failed(
            f"Own LSP NOT found in LSDB — IS-IS process may not be running "
            "or hostname mismatch"
        ), lf)
        worst = _worst(worst, "FAIL")

    # Own loopback and external TLVs — from detailed LSP
    detail_out = conn.send_command(f"show isis database {device_name}.00-00 detail")
    emit_raw(detail_out, lf)

    lo_ip = dev["loopbacks"]["Loopback0"]["ip"].split("/")[0]
    if lo_ip in detail_out:
        emit(passed(f"Loopback {lo_ip} advertised in LSDB"), lf)
    else:
        emit(warned(
            f"Loopback {lo_ip} NOT found in LSDB — "
            "check 'ip router isis' and 'isis passive' on Loopback0"
        ), lf)
        worst = _worst(worst, "WARN")

    # External TLVs — ASBR-1 redistributes OSPF into IS-IS;
    # redistributed prefixes appear as external reachability entries in the LSP.
    if device_name == "ASBR-1":
        if re.search(r'External|IP-External', detail_out, re.IGNORECASE):
            emit(passed(
                "External TLVs present in LSDB — "
                "OSPF-to-IS-IS redistribution confirmed"
            ), lf)
        else:
            emit(warned(
                "External TLVs NOT found in LSDB — "
                "check 'redistribute ospf' under 'router isis NAMS26' on ASBR-1"
            ), lf)
            worst = _worst(worst, "WARN")

    return worst


def check_routes(conn, device_name: str, dev: dict, lf=None) -> str:
    """IS-IS IPv4 routes in routing table; IS-IS IPv6 routes for MT routers."""
    worst  = "PASS"
    output = conn.send_command("show ip route isis")
    emit_raw(output, lf)

    # IS-IS route lines begin with 'i' (i L1, i L2, i ia, i su)
    route_lines = [l for l in output.splitlines() if re.match(r'^\s+i\b', l)]
    if route_lines:
        emit(passed(f"IS-IS routes in routing table ({len(route_lines)} prefix(es))"), lf)
    else:
        emit(warned(
            "No IS-IS routes in routing table — "
            "IS-IS may not have converged or neighbors are not forming"
        ), lf)
        worst = _worst(worst, "WARN")

    # IPv6 IS-IS routes for MT-capable routers (BR-4, BR-5)
    if dev.get("isis", {}).get("ipv6_multitopology"):
        ipv6_out = conn.send_command("show ipv6 route isis")
        emit_raw(ipv6_out, lf)

        ipv6_lines = [l for l in ipv6_out.splitlines() if re.match(r'^\s+I\b', l)]
        if ipv6_lines:
            emit(passed(f"IS-IS IPv6 routes present ({len(ipv6_lines)} prefix(es))"), lf)
        else:
            emit(warned(
                "No IS-IS IPv6 routes — "
                "check 'ipv6 router isis NAMS26' on interfaces and MT-IS-IS config"
            ), lf)
            worst = _worst(worst, "WARN")

    return worst


def check_mt(conn, device_name: str, dev: dict, lf=None) -> str:
    """MT-IS-IS IPv6 capability check — applies to BR-4 and BR-5 only."""
    if not dev.get("isis", {}).get("ipv6_multitopology"):
        emit(info(f"{device_name} does not have ipv6_multitopology — MT check skipped"), lf)
        return "INFO"

    worst = "PASS"

    # MT capability visible in neighbor detail output
    nbr_detail = conn.send_command("show isis neighbors detail")
    emit_raw(nbr_detail, lf)

    if re.search(r'(MT IPv6|Multi-Topology|Topology.*IPv6)', nbr_detail, re.IGNORECASE):
        emit(passed("MT-IS-IS IPv6 capability confirmed in neighbor detail"), lf)
    else:
        emit(warned(
            "MT-IS-IS IPv6 capability NOT found in neighbor detail — "
            "check 'multi-topology' under 'address-family ipv6' in router isis"
        ), lf)
        worst = _worst(worst, "WARN")

    # IPv6 loopback in own LSP
    lo_ipv6 = dev["loopbacks"]["Loopback0"].get("ipv6", "")
    if lo_ipv6:
        lo_ipv6_addr = lo_ipv6.split("/")[0]
        detail_out = conn.send_command(f"show isis database {device_name}.00-00 detail")
        emit_raw(detail_out, lf)

        if lo_ipv6_addr in detail_out:
            emit(passed(f"IPv6 loopback {lo_ipv6_addr} advertised in LSDB"), lf)
        else:
            emit(warned(
                f"IPv6 loopback {lo_ipv6_addr} NOT found in LSDB — "
                "check 'ipv6 router isis NAMS26' on Loopback0"
            ), lf)
            worst = _worst(worst, "WARN")

    return worst


# =============================================================================
# OSPF-ONLY ROUTER CHECKS (OSPF-1)
# =============================================================================

def check_ospf_only(conn, device_name: str, dev: dict, checks_to_run: list, lf=None) -> str:
    """OSPF adjacency and route checks for the ospf_only stub router (OSPF-1).

    neighbors → OSPF adjacency to ASBR-1 must be FULL
    routes    → OSPF routes present in IPv4 table (ASBR-1 loopback expected)
    lsdb/mt   → not applicable; INFO returned
    """
    worst = "PASS"

    if "neighbors" in checks_to_run:
        ospf_out = conn.send_command("show ip ospf neighbor")
        emit_raw(ospf_out, lf)
        if re.search(r'\bFULL\b', ospf_out, re.IGNORECASE):
            emit(passed("OSPF neighbor: ASBR-1 in FULL state"), lf)
        else:
            emit(failed(
                "OSPF neighbor: ASBR-1 not in FULL state — "
                "check OSPF process and 'ip ospf network point-to-point' on Ethernet0/0"
            ), lf)
            worst = _worst(worst, "FAIL")

    if "routes" in checks_to_run:
        route_out = conn.send_command("show ip route ospf")
        emit_raw(route_out, lf)
        ospf_lines = [l for l in route_out.splitlines() if re.match(r'^\s+O\b', l)]
        if ospf_lines:
            emit(passed(f"OSPF routes present ({len(ospf_lines)} prefix(es))"), lf)
        else:
            emit(warned(
                "No OSPF routes in table — check OSPF adjacency with ASBR-1"
            ), lf)
            worst = _worst(worst, "WARN")

    if "lsdb" in checks_to_run:
        emit(info("IS-IS LSDB check not applicable for ospf_only router — skipped"), lf)

    if "mt" in checks_to_run:
        emit(info("MT-IS-IS check not applicable for ospf_only router — skipped"), lf)

    return worst


# =============================================================================
# ROUTER RESOLUTION
# =============================================================================

def resolve_router(token: str, devices: dict) -> str | None:
    if token in devices:
        return token
    if token.upper() in devices:
        return token.upper()
    for key, dev in devices.items():
        if dev.get("dns_name", "").lower() == token.lower():
            return key
    return None


# =============================================================================
# SUMMARY
# =============================================================================

def print_summary(results: dict, devices: dict, target_routers: list, lf=None) -> None:
    bar  = "=" * 60
    div  = "-" * 60
    _RESULT_COLOR = {"PASS": GREEN, "WARN": YELLOW, "FAIL": RED, "INFO": CYAN}

    for line in [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}VERIFICATION SUMMARY{RESET}",
        f"{BOLD}{bar}{RESET}",
        f"{'Device':<10}{'Role':<12}{'Area':<12}Result",
        div,
    ]:
        emit(line, lf)

    overall_worst = "PASS"
    for name in target_routers:
        dev    = devices[name]
        role   = dev.get("isis_role", "unknown")
        area   = dev.get("isis_area", "N/A")
        result = results.get(name, "—")
        color  = _RESULT_COLOR.get(result, "")
        colored_result = f"{color}{result}{RESET}" if color else result
        row = f"{name:<10}{role:<12}{area:<12}{colored_result}"
        emit(row, lf)
        overall_worst = _worst(overall_worst, result)

    emit(div, lf)
    worst_color = _RESULT_COLOR.get(overall_worst, "")
    emit(
        f"Worst case: {worst_color}{overall_worst}{RESET}",
        lf,
    )
    emit(f"{BOLD}{bar}{RESET}\n", lf)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "NAMS26 Module 06 — Verify IS-IS Named Mode\n"
            "Connects to lab routers and verifies IS-IS operational state\n"
            "against expected values in 06_ipv6_isis_nornir.yaml.\n"
            "All output is mirrored to a timestamped log in logs/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/verify_06_ipv6_isis_nornir.py\n"
            "  python scripts/verify_06_ipv6_isis_nornir.py --router BB-1 ABR-1\n"
            "  python scripts/verify_06_ipv6_isis_nornir.py --check neighbors lsdb\n"
            "  python scripts/verify_06_ipv6_isis_nornir.py --list-checks\n"
        ),
    )
    parser.add_argument(
        "--router", nargs="*", metavar="HOSTNAME",
        help="Target one or more routers. Defaults to all devices in YAML.",
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
        descriptions = {
            "neighbors": "IS-IS neighbor count/state vs. expected; DIS (BR-2); OSPF adj (ASBR-1)",
            "lsdb"     : "Own LSP in LSDB; own loopback in LSP; external TLVs (ASBR-1)",
            "routes"   : "IS-IS IPv4 routes; IS-IS IPv6 routes (BR-4, BR-5)",
            "mt"       : "MT-IS-IS IPv6 capability and IPv6 loopback in LSP (BR-4, BR-5)",
        }
        print(f"\n{BOLD}Available verification checks:{RESET}\n")
        for name, desc in descriptions.items():
            print(f"  {CYAN}{name:<12}{RESET} {desc}")
        print()
        sys.exit(0)

    if args.check:
        invalid = [c for c in args.check if c not in AVAILABLE_CHECKS]
        if invalid:
            print(f"[ERROR] Unknown check(s): {invalid}  Valid: {AVAILABLE_CHECKS}")
            sys.exit(1)
        checks_to_run = args.check
    else:
        checks_to_run = AVAILABLE_CHECKS

    if not os.path.isfile(DATA_FILE):
        print(f"[ERROR] Data file not found: {DATA_FILE}")
        sys.exit(1)
    try:
        with open(DATA_FILE, "r") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        print(f"[ERROR] YAML parse error: {exc}")
        sys.exit(1)

    devices       = data.get("devices", {})
    default_creds = data.get("default_credentials", {})
    if not devices:
        print("[ERROR] No devices found in YAML.")
        sys.exit(1)
    for dev_data in devices.values():
        if not dev_data.get("credentials"):
            dev_data["credentials"] = default_creds

    if args.router:
        target_routers = []
        for token in args.router:
            resolved = resolve_router(token, devices)
            if resolved:
                target_routers.append(resolved)
            else:
                print(f"[WARNING] Router not found in YAML (skipped): '{token}'")
    else:
        target_routers = list(devices.keys())

    if not target_routers:
        print("[ERROR] No valid target routers.")
        sys.exit(1)

    lf = setup_logger()

    header_lines = [
        f"\nNAMS26 — Module 06: IPv6 IS-IS Verification",
        f"Targets : {', '.join(target_routers)}",
        f"Checks  : {', '.join(checks_to_run)}",
    ]
    for line in header_lines:
        emit(line, lf)

    results: dict = {}

    try:
        for device_name in target_routers:
            dev      = devices[device_name]
            role     = dev.get("isis_role", "unknown")
            area     = dev.get("isis_area", "N/A")
            dns_name = dev.get("dns_name", "")
            creds    = dev.get("credentials", default_creds)

            device_header(device_name, role, area, lf)

            if not dns_name:
                emit(failed(f"No dns_name defined for {device_name} — skipping."), lf)
                results[device_name] = "FAIL"
                continue

            conn = connect(device_name, dns_name, creds, lf)
            if conn is None:
                results[device_name] = "FAIL"
                continue

            try:
                device_worst = "PASS"

                if role == "ospf_only":
                    device_worst = check_ospf_only(conn, device_name, dev, checks_to_run, lf)
                else:
                    if "neighbors" in checks_to_run:
                        r = check_neighbors(conn, device_name, dev, lf)
                        device_worst = _worst(device_worst, r)

                    if "lsdb" in checks_to_run:
                        r = check_lsdb(conn, device_name, dev, lf)
                        device_worst = _worst(device_worst, r)

                    if "routes" in checks_to_run:
                        r = check_routes(conn, device_name, dev, lf)
                        device_worst = _worst(device_worst, r)

                    if "mt" in checks_to_run:
                        r = check_mt(conn, device_name, dev, lf)
                        device_worst = _worst(device_worst, r)

                results[device_name] = device_worst

            finally:
                conn.disconnect()
                emit(info(f"Disconnected from {device_name}"), lf)

        print_summary(results, devices, target_routers, lf)
        emit("Verification complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
