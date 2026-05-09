#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 06
File     : modules/06_ipv6_isis_nornir/scripts/troubleshoot_06_ipv6_isis_nornir.py
Purpose  : IS-IS Named Mode troubleshooting tool for the Module 06 lab.

           Connects to lab routers via Netmiko and runs targeted IS-IS
           troubleshooting commands. Results are printed to terminal with
           structured analysis and remediation guidance. All output is
           mirrored to a timestamped log file in modules/06_ipv6_isis_nornir/logs/.

Checks:
    process      — show clns protocol — IS-IS process running, NET, IS type
    adjacency    — show isis neighbors — Up/Down/Init state, DIS election
    interfaces   — show isis interface brief — IS-IS active interfaces
    lsdb         — show isis database — own LSP presence, LSDB size
    reachability — ping neighbor IPs derived from YAML subnet topology
    mt           — show isis neighbors detail — MT-IS-IS capability (BR-4, BR-5)
    ospf         — show ip ospf neighbor + show ip route ospf (ASBR-1, OSPF-1)

Usage:
    python scripts/troubleshoot_06_ipv6_isis_nornir.py
    python scripts/troubleshoot_06_ipv6_isis_nornir.py --router BB-1
    python scripts/troubleshoot_06_ipv6_isis_nornir.py --check adjacency lsdb
    python scripts/troubleshoot_06_ipv6_isis_nornir.py --list-checks

Pre-flight:
    Run utils/clear_known_hosts.sh then utils/init_ssh.py after every
    EVE-NG lab reboot before executing this script.
"""

import ipaddress
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
AVAILABLE_CHECKS = ["process", "adjacency", "interfaces", "lsdb", "reachability", "mt", "ospf"]

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

_ANSI_RE = re.compile(r'\033\[[0-9;]*m')

_RESULT_PREFIXES = ("[PASS]", "[FAIL]", "[WARN]", "[INFO]")

_result_collector: list | None = None


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def passed(msg: str) -> str:  return f"{GREEN}  [PASS]{RESET} {msg}"
def failed(msg: str) -> str:  return f"{RED}  [FAIL]{RESET} {msg}"
def warned(msg: str) -> str:  return f"{YELLOW}  [WARN]{RESET} {msg}"
def info(msg: str)   -> str:  return f"{CYAN}  [INFO]{RESET} {msg}"


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
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")
    if _result_collector is not None and _strip_ansi(line).strip().startswith(_RESULT_PREFIXES):
        _result_collector.append(line)


def emit_raw(text: str, lf=None) -> None:
    print(f"\n{text}\n")
    if lf:
        lf.write(f"\n{text}\n\n")


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"{timestamp}_troubleshoot_isis.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 06: IS-IS Named Mode Troubleshooting\n")
    lf.write(f"Log created : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write(f"Log file    : {log_path}\n")
    lf.write("=" * 60 + "\n\n")
    print(info(f"Logging to  : {log_path}"))
    return lf


# =============================================================================
# HELPERS
# =============================================================================

_RANK = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}


def _worst(a: str, b: str) -> str:
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


def _neighbor_ips(device_name: str, device_data: dict, all_devices: dict) -> list:
    """Return [(neighbor_name, neighbor_ip)] by matching subnets across all devices.

    Excludes Ethernet1/3 (OOB) and shutdown interfaces.
    """
    neighbors = []
    for intf_name, intf in device_data.get("interfaces", {}).items():
        if intf_name == "Ethernet1/3":
            continue
        if intf.get("shutdown", True):
            continue
        my_cidr = intf.get("ip")
        if not my_cidr:
            continue
        try:
            my_net = ipaddress.ip_interface(my_cidr).network
        except ValueError:
            continue
        for other_name, other_dev in all_devices.items():
            if other_name == device_name:
                continue
            for other_intf_name, other_intf in other_dev.get("interfaces", {}).items():
                if other_intf_name == "Ethernet1/3":
                    continue
                if other_intf.get("shutdown", True):
                    continue
                other_cidr = other_intf.get("ip")
                if not other_cidr:
                    continue
                try:
                    other_ip  = ipaddress.ip_interface(other_cidr).ip
                    other_net = ipaddress.ip_interface(other_cidr).network
                except ValueError:
                    continue
                if my_net == other_net:
                    neighbors.append((other_name, str(other_ip)))
    return neighbors


# =============================================================================
# NETMIKO CONNECTION
# =============================================================================

def connect(device_name: str, dns_name: str, creds: dict, lf=None):
    """Establish a Netmiko session. Returns ConnectHandler or None on failure."""
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
            # Multiplier applied to all Netmiko internal delay constants.
            # Current: 2.0   Range: 1.0 (fastest) – 5.0 (very slow hosts)
            global_delay_factor=2.0,
            # TCP handshake timeout in seconds.
            # Current: 30   Range: 10 – 60
            conn_timeout=30,
        )
        emit(info(f"Connected to {device_name} ({dns_name})"), lf)
        return conn
    except NetmikoTimeoutException:
        emit(failed(f"Connection timeout to {device_name} ({dns_name})"), lf)
    except NetmikoAuthenticationException:
        emit(failed(f"Authentication failed to {device_name}"), lf)
    except Exception as exc:
        emit(failed(f"Connection error on {device_name}: {exc}"), lf)
    return None


# =============================================================================
# LIVE TROUBLESHOOTING CHECKS
# =============================================================================

def check_process(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Validate IS-IS process state via 'show clns protocol'.

    OSPF-1 (isis_role='ospf_only') does not run IS-IS — returns INFO.
    All others: confirm IS-IS process name, NET address, and IS type.
    """
    role = device_data.get("isis_role", "")
    if role == "ospf_only":
        emit(info(f"{device_name} is OSPF-only — IS-IS process check not applicable"), lf)
        return "INFO"

    section("IS-IS Process — show clns protocol", lf)
    output = conn.send_command("show clns protocol")
    emit_raw(output, lf)

    result    = "PASS"
    isis_data = device_data.get("isis", {})
    process_name = isis_data.get("process_name", "")
    net          = isis_data.get("net", "")

    if not output.strip() or "IS-IS" not in output:
        emit(failed(
            f"No IS-IS process found — IS-IS may not be running. "
            f"Check 'router isis {process_name}' and NET configuration."
        ), lf)
        return "FAIL"

    if process_name and process_name in output:
        emit(passed(f"IS-IS process '{process_name}' confirmed running"), lf)
    elif process_name:
        emit(warned(
            f"IS-IS process name '{process_name}' not found in output — "
            "process may be running under a different name"
        ), lf)
        result = _worst(result, "WARN")

    if net and net.upper() in output.upper():
        emit(passed(f"NET {net} confirmed"), lf)
    elif net:
        emit(failed(
            f"NET {net} not found in 'show clns protocol' — "
            f"check 'net {net}' under 'router isis {process_name}'"
        ), lf)
        result = _worst(result, "FAIL")

    is_type = isis_data.get("is_type", "")
    if is_type:
        if re.search(re.escape(is_type), output, re.IGNORECASE):
            emit(passed(f"IS type '{is_type}' confirmed"), lf)
        else:
            emit(warned(
                f"IS type '{is_type}' not found in protocol output — "
                "check 'is-type' under IS-IS process"
            ), lf)
            result = _worst(result, "WARN")

    return result


def check_adjacency(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Check IS-IS neighbor states and DIS election via 'show isis neighbors'.

    OSPF-1: IS-IS not applicable — returns INFO.
    All others: parse Up/Down/Init states; flag non-Up neighbors and unexpected DIS.
    """
    role = device_data.get("isis_role", "")
    if role == "ospf_only":
        emit(info(f"{device_name} is OSPF-only — IS-IS adjacency check not applicable"), lf)
        return "INFO"

    section("IS-IS Neighbors — show isis neighbors", lf)
    output = conn.send_command("show isis neighbors")
    emit_raw(output, lf)

    result     = "PASS"
    up_count   = 0
    down_count = 0
    init_count = 0

    for line in output.splitlines():
        if re.match(r'^\s*(Tag|System\s+Id|[-=]+)', line, re.IGNORECASE):
            continue
        parts = line.split()
        # Neighbor data lines: SystemId Type Interface IPAddress State Holdtime CircuitId
        if len(parts) >= 6:
            state = parts[4].lower()
            if state == "up":
                up_count += 1
            elif state == "down":
                down_count += 1
            elif state == "init":
                init_count += 1

    if up_count == 0 and down_count == 0 and init_count == 0:
        if not output.strip() or "IS-IS" not in output:
            emit(failed(
                "No IS-IS neighbor table — IS-IS may not be running. "
                "Check process config and interface IS-IS assignments."
            ), lf)
            return "FAIL"
        emit(warned(
            "No IS-IS neighbors detected — expected at least one adjacency. "
            "Check IS-IS interface config and link state on adjacent routers."
        ), lf)
        result = _worst(result, "WARN")
    else:
        emit(passed(f"IS-IS adjacencies: {up_count} Up, {down_count} Down, {init_count} Init"), lf)

    if down_count > 0:
        emit(warned(
            f"{down_count} neighbor(s) in Down state — "
            "check interface IS-IS assignment and link state on the adjacent router"
        ), lf)
        result = _worst(result, "WARN")

    if init_count > 0:
        emit(warned(
            f"{init_count} neighbor(s) in Init state — "
            "possible Hello auth mismatch, area type mismatch, or MTU issue"
        ), lf)
        result = _worst(result, "WARN")

    # DIS check — only relevant if this device has isis_priority configured (LAN segment)
    # The Circuit Id column shows DIS.pseudonode (e.g. BB-2.01) for LAN segments.
    # If device_name appears in a Circuit Id entry, this router won DIS election.
    if up_count > 0:
        has_priority = any(
            idata.get("isis_priority") is not None
            for idata in device_data.get("isis", {}).get("interfaces", {}).values()
        )
        if has_priority:
            section("DIS State — Circuit Id column of show isis neighbors", lf)
            dis_pattern = re.compile(rf'{re.escape(device_name)}\.', re.IGNORECASE)
            if dis_pattern.search(output):
                emit(passed(
                    f"{device_name} is acting as DIS on at least one LAN segment "
                    "(own name found in Circuit Id column)"
                ), lf)
            else:
                emit(warned(
                    f"{device_name} has isis_priority configured but does not appear "
                    "as DIS in any Circuit Id entry — another router won DIS election "
                    "or the segment is P2P (no DIS election occurs)"
                ), lf)
                result = _worst(result, "WARN")

    return result


def check_interfaces(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Check IS-IS interface state via 'show isis interface brief'.

    OSPF-1: IS-IS not applicable — returns INFO.
    All others: verify expected ISIS-enabled interfaces are active in IS-IS.
    """
    role = device_data.get("isis_role", "")
    if role == "ospf_only":
        emit(info(f"{device_name} is OSPF-only — IS-IS interface check not applicable"), lf)
        return "INFO"

    section("IS-IS Interfaces — show isis interface brief", lf)
    output = conn.send_command("show isis interface brief")
    emit_raw(output, lf)

    result = "PASS"

    if not output.strip() or ("Interface" not in output and "isis" not in output.lower()):
        emit(failed(
            "No IS-IS interfaces found — IS-IS may not be running or no interfaces "
            "have 'ip router isis' / 'ipv6 router isis' configured"
        ), lf)
        return "FAIL"

    isis_data = device_data.get("isis", {})
    expected_intfs = [
        intf_name
        for intf_name, idata in isis_data.get("interfaces", {}).items()
        if idata.get("isis_enable", False)
    ]

    missing = []
    for intf_name in expected_intfs:
        # IOS may abbreviate interface names (Et0/0, Lo0) — match on full or first two chars + number
        short = re.sub(
            r'^([A-Za-z]+)(\d.*)$',
            lambda m: m.group(1)[:2] + m.group(2),
            intf_name,
        )
        if intf_name not in output and short not in output:
            missing.append(intf_name)

    if missing:
        emit(failed(
            f"Expected IS-IS interfaces not in 'show isis interface brief': "
            f"{', '.join(missing)} — check 'ip router isis' on these interfaces"
        ), lf)
        result = _worst(result, "FAIL")
    elif expected_intfs:
        emit(passed(f"{len(expected_intfs)} expected IS-IS interface(s) confirmed active"), lf)
    else:
        emit(info("No expected IS-IS interfaces found in YAML for this device"), lf)

    return result


def check_lsdb(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Check IS-IS LSDB health via 'show isis database'.

    OSPF-1: IS-IS not applicable — returns INFO.
    All others: verify own LSP (* marker) is present and LSDB is non-trivial.
    """
    role = device_data.get("isis_role", "")
    if role == "ospf_only":
        emit(info(f"{device_name} is OSPF-only — IS-IS LSDB check not applicable"), lf)
        return "INFO"

    section("IS-IS LSDB — show isis database", lf)
    output = conn.send_command("show isis database")
    emit_raw(output, lf)

    result = "PASS"

    if not output.strip() or "LSP" not in output.upper():
        emit(failed(
            "IS-IS LSDB is empty — IS-IS not converged or process not running. "
            "Check IS-IS process, interface assignments, and adjacency state."
        ), lf)
        return "FAIL"

    own_lsp_star = re.compile(rf'{re.escape(device_name)}\.00-00\s+\*', re.IGNORECASE)
    own_lsp_any  = re.compile(rf'{re.escape(device_name)}\.00-00', re.IGNORECASE)

    if own_lsp_star.search(output):
        emit(passed(f"Own LSP ({device_name}.00-00 *) present and self-originated"), lf)
    elif own_lsp_any.search(output):
        emit(warned(
            f"{device_name}.00-00 found but not marked as own (* missing) — "
            "IS-IS may still be converging or process just started"
        ), lf)
        result = _worst(result, "WARN")
    else:
        emit(failed(
            f"Own LSP ({device_name}.00-00) not in LSDB — "
            "IS-IS process has not generated a self-originated LSP. "
            "Check 'router isis', NET, and IS-IS interface assignments."
        ), lf)
        result = _worst(result, "FAIL")

    lsp_count = len([l for l in output.splitlines() if re.search(r'\.\d{2}-\d{2}\b', l)])
    if lsp_count < 3:
        emit(warned(
            f"LSDB contains only {lsp_count} LSP(s) — expected more if multiple routers "
            "are active. Possible missing adjacencies or IS-IS still converging."
        ), lf)
        result = _worst(result, "WARN")
    else:
        emit(info(f"LSDB contains {lsp_count} LSP entries"), lf)

    return result


def check_reachability(conn, device_name: str, device_data: dict, all_devices: dict, lf=None) -> str:
    """Ping neighbor IPs derived from shared subnets in the YAML topology.

    Identifies neighbors by matching interface subnets across all devices.
    Success requires at least one '!' in the IOS ping output.
    """
    section("Neighbor Reachability — ping neighbor IPs", lf)

    neighbors = _neighbor_ips(device_name, device_data, all_devices)

    if not neighbors:
        emit(info(
            "No neighbor IPs derived from YAML — check interface IP assignments "
            "and that adjacent devices are present in the data file"
        ), lf)
        return "INFO"

    result     = "PASS"
    fail_count = 0

    for nbr_name, nbr_ip in neighbors:
        ping_out = conn.send_command(f"ping {nbr_ip} repeat 3")
        if "!" in ping_out:
            emit(passed(f"Ping {nbr_name} ({nbr_ip}) — reachable"), lf)
        else:
            emit(failed(
                f"Ping {nbr_name} ({nbr_ip}) — UNREACHABLE. "
                "Check interface state, IP address config, and IS-IS adjacency."
            ), lf)
            result = _worst(result, "FAIL")
            fail_count += 1

    if fail_count == 0:
        emit(passed(f"All {len(neighbors)} neighbor IP(s) reachable"), lf)

    return result


def check_mt(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Check MT-IS-IS IPv6 capability via 'show isis neighbors detail'.

    Only meaningful for routers with isis.ipv6_multitopology: true (BR-4, BR-5).
    For OSPF-1 and non-MT IS-IS routers: returns INFO.
    """
    role     = device_data.get("isis_role", "")
    isis_data = device_data.get("isis", {})
    is_mt    = isis_data.get("ipv6_multitopology", False)

    if role == "ospf_only":
        emit(info(f"{device_name} is OSPF-only — MT check not applicable"), lf)
        return "INFO"

    if not is_mt:
        emit(info(
            f"{device_name} does not have ipv6_multitopology — MT check not applicable"
        ), lf)
        return "INFO"

    section("MT-IS-IS — show isis neighbors detail", lf)
    output = conn.send_command("show isis neighbors detail")
    emit_raw(output, lf)

    result = "PASS"

    if re.search(r'IPv6\s+Unicast', output, re.IGNORECASE):
        emit(passed("MT-IS-IS: IPv6 Unicast topology confirmed in neighbor detail"), lf)
    elif re.search(r'Multi.Topology|MT\s+ISIS', output, re.IGNORECASE):
        emit(passed("MT-IS-IS: Multi-Topology capability confirmed in neighbor detail"), lf)
    else:
        emit(warned(
            "MT-IS-IS: IPv6 topology capability not found in neighbor detail — "
            "check 'address-family ipv6 multi-topology' under 'router isis' on "
            "this router and its IS-IS neighbors"
        ), lf)
        result = _worst(result, "WARN")

    # Check that the IPv6 loopback prefix appears in the LSDB
    section("MT-IS-IS — IPv6 loopback in LSDB detail", lf)
    db_out = conn.send_command("show isis database detail")

    ipv6_lo = None
    for lo_data in device_data.get("loopbacks", {}).values():
        if lo_data.get("ipv6"):
            # Strip prefix length — loopback IPv6 stored as "FC00::X/128"
            ipv6_lo = lo_data["ipv6"].split("/")[0]
            break

    if ipv6_lo:
        if ipv6_lo.lower() in db_out.lower():
            emit(passed(f"IPv6 loopback {ipv6_lo} present in IS-IS LSDB detail"), lf)
        else:
            emit(warned(
                f"IPv6 loopback {ipv6_lo} not found in IS-IS LSDB detail — "
                "check 'ipv6 router isis' on the loopback and MT address-family config"
            ), lf)
            result = _worst(result, "WARN")

    return result


def check_ospf(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Check OSPF neighbor and route state.

    ASBR-1: verify OSPF neighbor FULL and OSPF routes present for redistribution.
    OSPF-1: verify OSPF neighbor FULL.
    Other IS-IS routers: returns INFO (OSPF not applicable).
    """
    role = device_data.get("isis_role", "")

    if role not in ("asbr", "ospf_only"):
        emit(info(f"{device_name} is not ASBR or OSPF-only — OSPF check not applicable"), lf)
        return "INFO"

    result = "PASS"

    section("OSPF Neighbors — show ip ospf neighbor", lf)
    nbr_out = conn.send_command("show ip ospf neighbor")
    emit_raw(nbr_out, lf)

    if not nbr_out.strip():
        emit(failed(
            "No OSPF neighbors — OSPF process may not be running or no active OSPF "
            "interfaces. Check 'router ospf' and network statements."
        ), lf)
        return "FAIL"

    full_count   = len(re.findall(r'\bFULL\b', nbr_out))
    other_states = re.findall(r'\b(EXSTART|EXCHANGE|INIT|LOADING|ATTEMPT|2WAY)\b', nbr_out)

    if full_count > 0:
        emit(passed(f"OSPF: {full_count} FULL adjacency/ies confirmed"), lf)
    else:
        emit(failed(
            "OSPF: No FULL adjacencies — OSPF not converged. "
            "Check area config, network statements, and link state."
        ), lf)
        result = _worst(result, "FAIL")

    if other_states:
        unique_states = list(set(other_states))
        emit(warned(
            f"OSPF: Non-FULL state(s) detected: {', '.join(unique_states)} — "
            "OSPF still converging or misconfigured"
        ), lf)
        result = _worst(result, "WARN")

    if role == "asbr":
        section("OSPF Routes for Redistribution — show ip route ospf", lf)
        route_out = conn.send_command("show ip route ospf")
        emit_raw(route_out, lf)

        ospf_routes = [l for l in route_out.splitlines() if re.match(r'^\s+O\b', l)]
        if ospf_routes:
            emit(passed(
                f"OSPF: {len(ospf_routes)} OSPF route(s) present — "
                "routes available for redistribution into IS-IS"
            ), lf)
        else:
            emit(warned(
                "OSPF: No OSPF routes in routing table — nothing to redistribute "
                "into IS-IS. Check OSPF network statements and OSPF-1 adjacency."
            ), lf)
            result = _worst(result, "WARN")

    return result


# =============================================================================
# CHECK DISPATCH TABLE
# check_reachability has a different signature (needs all_devices) and is
# called separately in the main loop.
# =============================================================================

LIVE_CHECKS = {
    "process"    : check_process,
    "adjacency"  : check_adjacency,
    "interfaces" : check_interfaces,
    "lsdb"       : check_lsdb,
    "mt"         : check_mt,
    "ospf"       : check_ospf,
}


# =============================================================================
# DETAIL + SUMMARY
# =============================================================================

def _print_detail(detail: dict, lf=None) -> None:
    bar = "=" * 60
    for line in [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}  Troubleshooting Detail{RESET}",
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


def _print_summary(results: dict, checks_to_run: list, all_devices: dict, lf=None) -> None:
    _TOKEN_COLOR = {
        "PASS": GREEN, "WARN": YELLOW, "FAIL": RED, "INFO": CYAN, "—": "",
    }

    def _colored_token(token: str) -> str:
        color = _TOKEN_COLOR.get(token, "")
        return f"{color}{token}{RESET}" if color else token

    bar      = "=" * 60
    W_DEVICE = 8
    W_ROLE   = 10
    W_CHECK  = 13

    header_line = (
        f"  {'Device':<{W_DEVICE}}  {'Role':<{W_ROLE}}"
        + "".join(f"  {chk:<{W_CHECK}}" for chk in checks_to_run)
    )
    divider = "  " + "─" * (W_DEVICE + 2 + W_ROLE + (W_CHECK + 2) * len(checks_to_run))

    for line in [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}  Troubleshooting Summary{RESET}",
        f"{BOLD}{bar}{RESET}",
        f"{BOLD}{header_line}{RESET}",
        divider,
    ]:
        emit(line, lf)

    worst_overall = "PASS"

    for device_name, chk_results in results.items():
        role = all_devices.get(device_name, {}).get("isis_role", "")
        row  = f"  {device_name:<{W_DEVICE}}  {role:<{W_ROLE}}"
        for chk in checks_to_run:
            token   = chk_results.get(chk, "—")
            colored = _colored_token(token)
            pad     = W_CHECK + (len(colored) - len(token))
            row    += f"  {colored:<{pad}}"
            if token not in ("INFO", "—"):
                worst_overall = _worst(worst_overall, token)
        emit(row, lf)

    emit(divider, lf)
    emit(f"  Worst case: {_colored_token(worst_overall)}", lf)
    emit(f"{BOLD}{bar}{RESET}\n", lf)


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
# ENTRY POINT
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "NAMS26 Module 06 — Troubleshoot IS-IS Named Mode\n"
            "Live troubleshooting checks against lab routers via Netmiko."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/troubleshoot_06_ipv6_isis_nornir.py\n"
            "  python scripts/troubleshoot_06_ipv6_isis_nornir.py --router BB-1\n"
            "  python scripts/troubleshoot_06_ipv6_isis_nornir.py --check adjacency lsdb\n"
            "  python scripts/troubleshoot_06_ipv6_isis_nornir.py --list-checks\n"
        ),
    )
    parser.add_argument(
        "--router", nargs="*", metavar="HOSTNAME",
        help=(
            "Target one or more routers. Accepts BB-1, bb-1, or bb-1.lab. "
            "Defaults to all devices in YAML."
        ),
    )
    parser.add_argument(
        "--check", nargs="*", metavar="CHECK",
        help=f"Checks to run: {', '.join(AVAILABLE_CHECKS)}. Defaults to all.",
    )
    parser.add_argument(
        "--list-checks", action="store_true",
        help="List all available troubleshooting checks and exit.",
    )
    args = parser.parse_args()

    if args.list_checks:
        print(f"\n{BOLD}Available troubleshooting checks:{RESET}\n")
        descriptions = {
            "process"     : "show clns protocol — IS-IS process name, NET, IS type",
            "adjacency"   : "show isis neighbors — Up/Down/Init state, DIS election check",
            "interfaces"  : "show isis interface brief — IS-IS active interfaces",
            "lsdb"        : "show isis database — own LSP presence, LSDB size",
            "reachability": "ping neighbor IPs derived from YAML subnet topology",
            "mt"          : "show isis neighbors detail — MT-IS-IS (BR-4, BR-5 only)",
            "ospf"        : "show ip ospf neighbor + route ospf (ASBR-1, OSPF-1 only)",
        }
        for name, desc in descriptions.items():
            print(f"  {CYAN}{name:<14}{RESET} {desc}")
        print()
        sys.exit(0)

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

    if args.check:
        invalid = [c for c in args.check if c not in AVAILABLE_CHECKS]
        if invalid:
            print(f"[ERROR] Unknown check(s): {invalid}")
            print(f"        Valid options: {AVAILABLE_CHECKS}")
            sys.exit(1)
        checks_to_run = args.check
    else:
        checks_to_run = AVAILABLE_CHECKS

    print(f"\n{BOLD}NAMS26 — Module 06: IS-IS Named Mode Troubleshooting{RESET}")
    print(f"Targets : {', '.join(target_routers)}")
    print(f"Checks  : {', '.join(checks_to_run)}")

    global _result_collector
    results: dict = {}
    detail:  dict = {}
    lf = setup_logger()

    try:
        for line in [
            f"\nNAMS26 — Module 06: IS-IS Named Mode Troubleshooting",
            f"Targets : {', '.join(target_routers)}",
            f"Checks  : {', '.join(checks_to_run)}",
        ]:
            lf.write(line + "\n")
        lf.write("\n")

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

            conn = connect(device_name, dns_name, creds, lf)
            if conn is None:
                emit(failed(f"Skipping all checks on {device_name} — connection failed."), lf)
                for chk in checks_to_run:
                    results[device_name][chk] = "FAIL"
                continue

            try:
                for check_name in checks_to_run:
                    if check_name == "reachability":
                        results[device_name][check_name] = check_reachability(
                            conn, device_name, device_data, devices, lf)
                    else:
                        results[device_name][check_name] = LIVE_CHECKS[check_name](
                            conn, device_name, device_data, lf)
            finally:
                conn.disconnect()
                lf.write(f"  [INFO] Disconnected from {device_name}\n")

        _result_collector = None
        _print_detail(detail, lf)
        _print_summary(results, checks_to_run, devices, lf)
        emit(f"\n{'=' * 60}\nTroubleshooting session complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
