#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 05
File     : modules/05_ipv6_eigrp_ospf_nornir/scripts/troubleshoot_ipv6_eigrp_ospf.py
Purpose  : Two-mode troubleshooting tool for IPv6 EIGRP / OSPFv3 lab.

           Mode 1 — Live Troubleshooting (default)
           ----------------------------------------
           Connects to lab routers via Netmiko and runs targeted IPv6
           troubleshooting commands. Results are printed to terminal with
           structured analysis and remediation guidance.

           Mode 2 — Failure Demonstration (--demo-failure)
           ------------------------------------------------
           Injects a named fault into an in-memory copy of the YAML data,
           renders the broken Jinja2 config, diffs it against the correct
           config, explains the failure, and shows the CLI symptoms a
           student would see on a live router. No changes pushed to any device.

Usage:
    # Run all troubleshooting checks on all routers
    python troubleshoot_ipv6_eigrp_ospf.py

    # Run checks on specific routers
    python troubleshoot_ipv6_eigrp_ospf.py --router R1 R6

    # Run a specific check
    python troubleshoot_ipv6_eigrp_ospf.py --check neighbors
    python troubleshoot_ipv6_eigrp_ospf.py --check process
    python troubleshoot_ipv6_eigrp_ospf.py --check routes

    # Demonstrate a failure scenario (memory only — no router changes)
    python troubleshoot_ipv6_eigrp_ospf.py --demo-failure missing-redistribute
    python troubleshoot_ipv6_eigrp_ospf.py --demo-failure missing-redistribute --router R6
    python troubleshoot_ipv6_eigrp_ospf.py --demo-failure wrong-area-type
    python troubleshoot_ipv6_eigrp_ospf.py --demo-failure missing-ospf-area
    python troubleshoot_ipv6_eigrp_ospf.py --demo-failure missing-eigrp-iface

    # List available checks and failure scenarios
    python troubleshoot_ipv6_eigrp_ospf.py --list-checks
    python troubleshoot_ipv6_eigrp_ospf.py --list-failures

Troubleshooting Checks:
    neighbors   — show ipv6 eigrp neighbors detail / show ipv6 ospf neighbor detail
    process     — show ipv6 protocols — EIGRP AS and OSPF PID + router-id validation
    routes      — show ipv6 route + show ipv6 ospf border-routers (OSPF routers)

Failure Scenarios:
    missing-redistribute  — 'redistribute eigrp' removed from ASBR OSPFv3 config;
                            external routes vanish from the OSPFv3 domain
    wrong-area-type       — 'area 20 nssa' removed from an Area 20 router;
                            adjacency failure — area type mismatch in hellos
    missing-ospf-area     — 'ipv6 ospf <pid> area <area>' removed from an active
                            interface; prefix drops from OSPFv3 LSDB
    missing-eigrp-iface   — 'ipv6 eigrp <as>' removed from an active interface;
                            EIGRPv6 adjacency drops
"""

import os
import re
import sys
import copy
import yaml
import argparse
import ipaddress
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
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
TEMPLATE_DIR = os.path.join(MODULE_DIR, "templates")
TEMPLATE_FILE = "ipv6_eigrp_ospf.j2"

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# AVAILABLE CHECKS AND FAILURE SCENARIOS
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "process", "routes"]

FAILURE_SCENARIOS = {
    "missing-redistribute": {
        "title"      : "Redistribution Statement Removed from ASBR",
        "description": (
            "The 'redistribute eigrp' statement is removed from the OSPFv3 process "
            "on an ASBR (R1 or R6). External routes from that EIGRPv6 domain "
            "immediately disappear from the OSPFv3 LSDB — no Type 5 LSAs (or Type 7 "
            "on R6 in Area 20 NSSA) are originated. All OSPF routers lose reachability "
            "to those EIGRPv6 prefixes. OSPFv3 adjacencies remain fully up. The "
            "troubleshooter will pass all neighbor and process checks — only the "
            "verifier catches the missing external routes."
        ),
        "symptoms"   : [
            "show ipv6 route ospf on R2/R3/R4 — OE2/ON2 routes absent",
            "show ipv6 ospf database — no external LSAs from the ASBR router-id",
            "show ipv6 ospf neighbor — all adjacencies remain FULL (no impact)",
            "show ipv6 protocols — OSPF process running but 'Redistributing: eigrp' absent",
            "ping <EIGRPv6 prefix> from Area 0 router — fails",
        ],
        "fix"        : (
            "Restore 'redistribute_eigrp' in the YAML ospf block for the ASBR. "
            "Re-run configure_ipv6_eigrp_ospf.py on the affected router. "
            "Verify with: show ipv6 ospf database and show ipv6 route ospf on R2"
        ),
        "cli_commands": [
            "show ipv6 route ospf",
            "show ipv6 ospf database",
            "show ipv6 ospf neighbor",
            "show ipv6 protocols",
            "show run | section ipv6 router ospf",
        ],
        "target_hint": "R1 or R6 (ASBRs)",
    },
    "wrong-area-type": {
        "title"      : "NSSA Declaration Removed from Area 20 Router",
        "description": (
            "The 'area 20 nssa' statement is removed from a non-ABR Area 20 router "
            "(R6). That router treats Area 20 as a standard area and rejects Type 7 "
            "LSAs. The OSPFv3 adjacency with R4 drops because the area type in Hello "
            "packets no longer matches. This is an adjacency-breaking fault — unlike "
            "missing redistribution, neighbors will drop."
        ),
        "symptoms"   : [
            "show ipv6 ospf neighbor on R6 — adjacency to R4 drops",
            "show ipv6 ospf on R6 — Area 20 no longer listed as NSSA",
            "show ipv6 ospf database — Type 7 LSAs absent",
            "debug ipv6 ospf hello — 'area type mismatch' in hello packets",
        ],
        "fix"        : (
            "Restore the area_types entry (area: 20, type: nssa) in YAML for the "
            "affected router. Re-run configure_ipv6_eigrp_ospf.py. "
            "Verify with: show ipv6 ospf on R6 — 'NSSA' must appear in Area 20 block"
        ),
        "cli_commands": [
            "show ipv6 ospf neighbor",
            "show ipv6 ospf",
            "show ipv6 ospf database",
            "show run | section ipv6 router ospf",
        ],
        "target_hint": "R4, R6 (Area 20 NSSA members)",
    },
    "missing-ospf-area": {
        "title"      : "OSPFv3 Interface Area Assignment Removed",
        "description": (
            "The 'ipv6 ospf <pid> area <area>' command is removed from an active "
            "physical interface. OSPFv3 stops sending Hellos on that interface — "
            "the adjacency with the connected neighbor drops, and the interface "
            "prefix disappears from the LSDB. The physical interface remains up/up; "
            "only the OSPFv3 advertisement is lost."
        ),
        "symptoms"   : [
            "show ipv6 ospf neighbor — adjacency to the connected neighbor drops",
            "show ipv6 ospf interface — affected interface not listed as OSPF-active",
            "show ipv6 ospf database — Router LSA for affected router missing that network",
            "show ipv6 route ospf on remote routers — prefix absent",
        ],
        "fix"        : (
            "Restore ospf_area on the affected interface in YAML. "
            "Re-run configure_ipv6_eigrp_ospf.py on the affected router. "
            "Verify with: show ipv6 ospf interface — interface must reappear"
        ),
        "cli_commands": [
            "show ipv6 ospf neighbor",
            "show ipv6 ospf interface",
            "show ipv6 ospf database",
            "show run interface <intf>",
        ],
        "target_hint": "Any OSPF router with active physical OSPF interfaces",
    },
    "missing-eigrp-iface": {
        "title"      : "EIGRPv6 Interface Assignment Removed",
        "description": (
            "The 'ipv6 eigrp <as>' command is removed from an active EIGRPv6 "
            "interface. EIGRPv6 stops sending Hellos on that interface — the "
            "adjacency with the connected neighbor drops, and the interface prefix "
            "is withdrawn from the EIGRPv6 topology. The redistribution into "
            "OSPFv3 may still be configured but the withdrawn prefixes become "
            "unreachable across the boundary."
        ),
        "symptoms"   : [
            "show ipv6 eigrp neighbors — neighbor entry for connected router drops",
            "show ipv6 route eigrp on R1/R6 — route for removed prefix disappears",
            "show ipv6 route ospf on remote routers — redistributed prefix vanishes",
            "ping <EIGRPv6 prefix> from OSPFv3 domain — fails",
        ],
        "fix"        : (
            "Restore eigrp_as on the affected interface in YAML. "
            "Re-run configure_ipv6_eigrp_ospf.py on the affected router. "
            "Verify with: show ipv6 eigrp neighbors — adjacency must reform"
        ),
        "cli_commands": [
            "show ipv6 eigrp neighbors",
            "show ipv6 route eigrp",
            "show ipv6 protocols",
            "show run interface <intf>",
        ],
        "target_hint": "R1 (EIGRP100 iface to R7), R6 (EIGRP111 iface to R8), R7, R8",
    },
}

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

def demo_header(scenario_key: str, title: str) -> None:
    bar = "=" * 60
    print(f"\n{BOLD}{bar}{RESET}")
    print(f"{BOLD}  FAILURE DEMO : {scenario_key}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{bar}{RESET}")

def emit(line: str, lf=None) -> None:
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")

def emit_raw(text: str, lf=None) -> None:
    print(f"\n{text}\n")
    if lf:
        lf.write(f"\n{text}\n\n")


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"troubleshoot_ipv6_eigrp_ospf_{timestamp}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 05: IPv6 EIGRP/OSPFv3 Troubleshooting\n")
    lf.write(f"Log created : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write(f"Log file    : {log_path}\n")
    lf.write("=" * 60 + "\n\n")
    print(info(f"Logging to  : {log_path}"))
    return lf


# =============================================================================
# JINJA2 FILTERS (mirror configure_ipv6_eigrp_ospf.py)
# =============================================================================

def _ipv4_addr(cidr: str) -> str:
    return str(ipaddress.ip_interface(cidr).ip)

def _ipv4_mask(cidr: str) -> str:
    return str(ipaddress.ip_interface(cidr).network.netmask)


# =============================================================================
# HELPERS
# =============================================================================

_RANK = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}

def _worst(a: str, b: str) -> str:
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


def _get_role(device_data: dict) -> str:
    has_eigrp = device_data.get("eigrp") is not None
    has_ospf  = device_data.get("ospf") is not None
    if has_eigrp and has_ospf:
        return "ASBR"
    if has_eigrp:
        return "EIGRP_ONLY"
    return "OSPF_ONLY"


# =============================================================================
# CONFIG DIFF
# =============================================================================

def diff_configs(correct: str, broken: str) -> None:
    """Print a simple line-level diff between correct and broken configs."""
    correct_lines = correct.splitlines()
    broken_lines  = broken.splitlines()
    correct_set   = set(correct_lines)
    broken_set    = set(broken_lines)

    print(f"\n{BOLD}  Config Diff  (- correct / + broken){RESET}")
    print(f"{BOLD}  {'─' * 54}{RESET}")

    for line in correct_lines:
        if line not in broken_set:
            print(f"{GREEN}  - {line}{RESET}")
        else:
            print(f"{DIM}    {line}{RESET}")
    for line in broken_lines:
        if line not in correct_set:
            print(f"{RED}  + {line}{RESET}")


# =============================================================================
# FAULT INJECTORS
# Each function deep-copies the device dict, mutates it to introduce the fault,
# and returns the broken copy. The original data is never modified.
# =============================================================================

def inject_missing_redistribute(device_data: dict) -> dict:
    """Remove redistribute_eigrp from the OSPFv3 block (target ASBR: R1 or R6)."""
    broken = copy.deepcopy(device_data)
    ospf   = broken.get("ospf") or {}
    if ospf.get("redistribute_eigrp"):
        broken["_removed_redistribute"] = ospf["redistribute_eigrp"]
        ospf["redistribute_eigrp"] = None
    broken["ospf"] = ospf
    return broken


def inject_wrong_area_type(device_data: dict) -> dict:
    """Remove the nssa declaration from the area_types list."""
    broken     = copy.deepcopy(device_data)
    ospf       = broken.get("ospf") or {}
    area_types = ospf.get("area_types") or []
    new_types  = []
    removed    = None
    for at in area_types:
        if at.get("type") == "nssa":
            removed = at
        else:
            new_types.append(at)
    ospf["area_types"]          = new_types
    broken["ospf"]              = ospf
    broken["_removed_area_type"] = removed
    return broken


def inject_missing_ospf_area(device_data: dict) -> dict:
    """Remove ospf_area from the first active non-loopback, non-OOB OSPF interface."""
    broken  = copy.deepcopy(device_data)
    oob_iface = broken.get("oob_interface", "")
    for intf_name, intf in broken.get("interfaces", {}).items():
        if intf_name == oob_iface:
            continue
        if intf.get("shutdown", True):
            continue
        area = intf.get("ospf_area")
        if area is not None and area != "":
            broken["_removed_intf"]       = intf_name
            broken["_removed_ospf_area"] = area
            intf["ospf_area"] = ""
            break
    return broken


def inject_missing_eigrp_iface(device_data: dict) -> dict:
    """Remove eigrp_as from the first active non-loopback, non-OOB EIGRP interface."""
    broken    = copy.deepcopy(device_data)
    oob_iface = broken.get("oob_interface", "")
    for intf_name, intf in broken.get("interfaces", {}).items():
        if intf_name == oob_iface:
            continue
        if intf.get("shutdown", True):
            continue
        if "Loopback" in intf_name:
            continue
        as_val = intf.get("eigrp_as")
        if as_val is not None and as_val != "":
            broken["_removed_intf"]      = intf_name
            broken["_removed_eigrp_as"] = as_val
            intf["eigrp_as"] = ""
            break
    return broken


FAULT_INJECTORS = {
    "missing-redistribute": inject_missing_redistribute,
    "wrong-area-type"     : inject_wrong_area_type,
    "missing-ospf-area"   : inject_missing_ospf_area,
    "missing-eigrp-iface" : inject_missing_eigrp_iface,
}


# =============================================================================
# FAILURE DEMONSTRATION MODE
# =============================================================================

def run_demo_failure(
    scenario_key: str,
    devices: dict,
    target_routers: list,
    template,
) -> None:
    """Execute a full failure demonstration cycle for the named scenario.

    For each target router:
      1. Render correct config from clean YAML data
      2. Inject the fault into an in-memory copy of the device data
      3. Render broken config from the mutated data
      4. Diff correct vs broken — show exactly what changed
      5. Print the failure description and expected CLI symptoms
      6. Print the fix and verification commands

    No changes are pushed to any device at any point.
    """
    scenario = FAILURE_SCENARIOS[scenario_key]
    injector = FAULT_INJECTORS[scenario_key]

    demo_header(scenario_key, scenario["title"])

    section("What This Failure Demonstrates")
    print(f"\n  {scenario['description']}\n")
    print(f"  {YELLOW}Suggested target:{RESET}  {scenario['target_hint']}\n")

    for device_name in target_routers:
        device_data = devices[device_name]

        print(f"\n{BOLD}  [ Demonstrating on {device_name} ]{RESET}")

        correct_config = template.render(device=device_data)
        broken_data    = injector(device_data)
        broken_config  = template.render(device=broken_data)

        section("Fault Injected (in-memory only — router not changed)")

        if scenario_key == "missing-redistribute":
            removed = broken_data.get("_removed_redistribute")
            if removed:
                as_num = removed.get("as_number", "?")
                print(info(
                    f"'redistribute eigrp {as_num}' removed from OSPFv3 config"
                ))
                print(info(
                    "EIGRPv6 routes will no longer be redistributed into OSPFv3 domain"
                ))
            else:
                print(info(
                    f"No redistribute_eigrp found on {device_name} — "
                    "choose R1 or R6 for this demo (--router R1 or --router R6)"
                ))

        elif scenario_key == "wrong-area-type":
            removed = broken_data.get("_removed_area_type")
            if removed:
                print(info(
                    f"area {removed.get('area', '?')} nssa declaration removed"
                ))
                print(info(
                    "This router will treat Area 20 as a standard area — "
                    "adjacency with NSSA neighbors will drop"
                ))
            else:
                print(info(
                    f"No nssa area_type found on {device_name} — "
                    "choose R4, R6 (--router R4 or --router R6)"
                ))

        elif scenario_key == "missing-ospf-area":
            intf = broken_data.get("_removed_intf", "?")
            area = broken_data.get("_removed_ospf_area", "?")
            print(info(
                f"'ipv6 ospf 1 area {area}' removed from interface {intf}"
            ))
            print(info(
                "OSPFv3 will stop sending Hellos on that interface — "
                "adjacency drops and prefix disappears from LSDB"
            ))

        elif scenario_key == "missing-eigrp-iface":
            intf  = broken_data.get("_removed_intf", "?")
            as_n  = broken_data.get("_removed_eigrp_as", "?")
            print(info(f"'ipv6 eigrp {as_n}' removed from interface {intf}"))
            print(info(
                "EIGRPv6 will stop forming an adjacency on that interface — "
                "neighbor drops and prefix is withdrawn from the topology"
            ))

        section("Configuration Diff")
        diff_configs(correct_config, broken_config)

        section("CLI Symptoms — What You Would See on the Router")
        print()
        for symptom in scenario["symptoms"]:
            print(f"  {YELLOW}▸{RESET}  {symptom}")

        section("Troubleshooting Commands to Run")
        print()
        for cmd in scenario["cli_commands"]:
            print(f"  {CYAN}>{RESET}  {cmd}")

        section("The Fix")
        print(f"\n  {scenario['fix']}\n")

    print(f"\n{'=' * 60}")
    print(f"{BOLD}Demo complete. No changes were pushed to any router.{RESET}\n")


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
# LIVE TROUBLESHOOTING CHECKS
# =============================================================================

def check_neighbors(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Detailed adjacency diagnostics.

    Runs 'show ipv6 eigrp neighbors' (EIGRP-capable) and
    'show ipv6 ospf neighbor detail' (OSPF-capable). Flags any
    non-FULL OSPFv3 adjacency states.

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    worst = "PASS"
    role  = _get_role(device_data)

    if role in ("ASBR", "EIGRP_ONLY"):
        section("EIGRPv6 Neighbors — show ipv6 eigrp neighbors", lf)
        output = conn.send_command("show ipv6 eigrp neighbors")
        emit_raw(output, lf)

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
        section("OSPFv3 Neighbors — show ipv6 ospf neighbor detail", lf)
        output = conn.send_command("show ipv6 ospf neighbor detail")
        emit_raw(output, lf)

        problem_states = re.compile(r'\b(EXSTART|EXCHANGE|INIT|LOADING)\b', re.IGNORECASE)
        full_re        = re.compile(r'\bFULL\b', re.IGNORECASE)

        if problem_states.search(output):
            states = list(set(problem_states.findall(output)))
            emit(warned(
                f"OSPFv3: Stuck state detected — {', '.join(states)}. "
                "Possible area type mismatch, MTU issue, or NSSA misconfiguration."
            ), lf)
            worst = _worst(worst, "WARN")
        elif full_re.search(output):
            emit(passed("OSPFv3: At least one FULL adjacency confirmed"), lf)
        elif output.strip():
            emit(failed(
                "OSPFv3: No FULL adjacencies — OSPF not converged. "
                "Check area type, 'ipv6 ospf' on interfaces, and process config."
            ), lf)
            worst = _worst(worst, "FAIL")
        else:
            emit(failed(
                "OSPFv3: No neighbors at all — "
                "check 'ipv6 ospf <pid> area <area>' on interfaces"
            ), lf)
            worst = _worst(worst, "FAIL")

    return worst


def check_process(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Validate IPv6 protocol process state via 'show ipv6 protocols'.

    For EIGRPv6 routers: confirms EIGRP AS number is running.
    For OSPFv3 routers: confirms OSPF process ID and router-id are active.
    For both (ASBRs): validates redistribute statements are present.

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    section("IPv6 Protocols — show ipv6 protocols", lf)
    output = conn.send_command("show ipv6 protocols")
    emit_raw(output, lf)

    result     = "PASS"
    eigrp_data = device_data.get("eigrp")
    ospf_data  = device_data.get("ospf")

    if eigrp_data:
        as_number = str(eigrp_data.get("as_number", ""))
        if as_number and re.search(rf'EIGRP\s+{re.escape(as_number)}\b', output, re.IGNORECASE):
            emit(passed(f"EIGRPv6 AS {as_number} confirmed running"), lf)
        elif as_number:
            emit(failed(
                f"EIGRPv6 AS {as_number} NOT found in 'show ipv6 protocols' — "
                "EIGRP process may not be running"
            ), lf)
            result = _worst(result, "FAIL")

    if ospf_data:
        process_id = str(ospf_data.get("process_id", ""))
        router_id  = ospf_data.get("router_id", "")

        if process_id and re.search(rf'OSPFv3\s+{re.escape(process_id)}\b', output, re.IGNORECASE):
            emit(passed(f"OSPFv3 PID {process_id} confirmed running"), lf)
        elif process_id:
            emit(failed(
                f"OSPFv3 PID {process_id} NOT found in 'show ipv6 protocols' — "
                "OSPF process may not be running"
            ), lf)
            result = _worst(result, "FAIL")

        if router_id and router_id in output:
            emit(passed(f"OSPFv3 Router ID {router_id} confirmed"), lf)
        elif router_id:
            emit(failed(
                f"OSPFv3 Router ID {router_id} NOT found — "
                "router-id mismatch or OSPF process not running"
            ), lf)
            result = _worst(result, "FAIL")

        # Redistribution check for ASBRs
        ospf_redist = ospf_data.get("redistribute_eigrp")
        if ospf_redist:
            if re.search(r'Redistributing.*?eigrp', output, re.IGNORECASE):
                emit(passed(
                    "OSPFv3: 'Redistributing: eigrp' found in protocols output"
                ), lf)
            else:
                emit(warned(
                    "OSPFv3: Redistribution of EIGRP not shown in 'show ipv6 protocols' — "
                    "verify 'redistribute eigrp' in OSPFv3 config"
                ), lf)
                result = _worst(result, "WARN")

    return result


def check_routes(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Route table health check.

    Runs 'show ipv6 route' for all routers.
    Runs 'show ipv6 ospf border-routers' for OSPF-capable routers.
    Flags missing expected route types based on router role.

    Returns: "PASS", "WARN", "FAIL", or "INFO"
    """
    section("IPv6 Route Table — show ipv6 route", lf)
    route_output = conn.send_command("show ipv6 route")
    emit_raw(route_output, lf)

    result = "PASS"
    role   = _get_role(device_data)

    if not route_output.strip():
        emit(warned(
            "Empty routing table — check protocol processes and interface state"
        ), lf)
        result = _worst(result, "WARN")
    else:
        type_counts: dict = {}
        for prefix, label in [
            (r'^\s*C\s+',    "C"),
            (r'^\s*L\s+',    "L"),
            (r'^\s*D\s+EX',  "D EX"),
            (r'^\s*D\s+',    "D"),
            (r'^\s*OI\s+',   "OI"),
            (r'^\s*OE[12]',  "OE"),
            (r'^\s*ON[12]',  "ON"),
            (r'^\s*O\s+',    "O"),
        ]:
            count = len([l for l in route_output.splitlines()
                         if re.match(prefix, l, re.IGNORECASE)])
            if count:
                type_counts[label] = count
        summary = "  ".join(f"{k}:{v}" for k, v in type_counts.items())
        emit(info(f"Route types: {summary}" if summary else "No routes found"), lf)

    # NSSA default check for pure Area 20 routers (R6)
    ospf_data = device_data.get("ospf") or {}
    area_types = ospf_data.get("area_types") or []
    has_nssa   = any(at.get("type") == "nssa" for at in area_types)
    has_area_0 = any(
        intf.get("ospf_area") == 0 or str(intf.get("ospf_area", "")) == "0"
        for intf in device_data.get("interfaces", {}).values()
    )

    if has_nssa and not has_area_0 and role == "ASBR":
        # R6 is NSSA ASBR — it originates Type 7 LSAs but does not receive its own default
        emit(info(
            f"{device_name} is an NSSA ASBR — NSSA default route check not applicable "
            "(R6 originates Type 7 LSAs; R3 translates them to Type 5)"
        ), lf)

    # Border router check for OSPF-capable routers
    if role in ("ASBR", "OSPF_ONLY"):
        section("Border Routers — show ipv6 ospf border-routers", lf)
        br_output = conn.send_command("show ipv6 ospf border-routers")
        emit_raw(br_output, lf)

        if br_output.strip():
            emit(passed(
                "Border router entries present — ABR/ASBR reachability confirmed"
            ), lf)
        else:
            emit(info(
                "No border router entries — "
                "expected only if this router is in a non-backbone area; "
                "backbone-only routers (R1, R2, R3) may not list entries"
            ), lf)

    return result


LIVE_CHECKS = {
    "neighbors": check_neighbors,
    "process"  : check_process,
    "routes"   : check_routes,
}


# =============================================================================
# SUMMARY
# =============================================================================

def _print_summary(results: dict, checks_to_run: list, lf=None) -> None:
    _TOKEN_COLOR = {
        "PASS": GREEN, "WARN": YELLOW, "FAIL": RED, "INFO": CYAN, "—": "",
    }

    def _colored_token(token: str) -> str:
        color = _TOKEN_COLOR.get(token, "")
        return f"{color}{token}{RESET}" if color else token

    bar      = "=" * 60
    W_DEVICE = 8
    W_CHECK  = 16

    header_line = f"  {'Device':<{W_DEVICE}}" + "".join(
        f"  {chk:<{W_CHECK}}" for chk in checks_to_run
    )
    divider = "  " + "─" * (W_DEVICE + (W_CHECK + 2) * len(checks_to_run))

    for line in [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}  Troubleshooting Summary{RESET}",
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
            "NAMS26 Module 05 — Troubleshoot IPv6 EIGRP/OSPFv3\n"
            "Live troubleshooting checks and in-memory failure demonstrations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python troubleshoot_ipv6_eigrp_ospf.py\n"
            "  python troubleshoot_ipv6_eigrp_ospf.py --router R6\n"
            "  python troubleshoot_ipv6_eigrp_ospf.py --check neighbors process\n"
            "  python troubleshoot_ipv6_eigrp_ospf.py --demo-failure missing-redistribute\n"
            "  python troubleshoot_ipv6_eigrp_ospf.py --demo-failure missing-redistribute "
            "--router R6\n"
            "  python troubleshoot_ipv6_eigrp_ospf.py --list-failures\n"
        ),
    )
    parser.add_argument(
        "--router", nargs="*", metavar="HOSTNAME",
        help="Target one or more routers by hostname. Defaults to all devices.",
    )
    parser.add_argument(
        "--check", nargs="*", metavar="CHECK",
        help=f"Live checks to run: {', '.join(AVAILABLE_CHECKS)}. Defaults to all.",
    )
    parser.add_argument(
        "--demo-failure", metavar="SCENARIO",
        help=(
            f"Inject a named failure in memory and walk through the diagnostic cycle. "
            f"No changes pushed to routers. "
            f"Scenarios: {', '.join(FAILURE_SCENARIOS.keys())}."
        ),
    )
    parser.add_argument(
        "--list-checks", action="store_true",
        help="List all available live troubleshooting checks and exit.",
    )
    parser.add_argument(
        "--list-failures", action="store_true",
        help="List all available failure demonstration scenarios and exit.",
    )
    args = parser.parse_args()

    if args.list_checks:
        print(f"\n{BOLD}Available live troubleshooting checks:{RESET}\n")
        descriptions = {
            "neighbors": "EIGRPv6 neighbors + OSPFv3 neighbor detail — adjacency diagnostics",
            "process"  : "show ipv6 protocols — EIGRP AS, OSPF PID, router-id, redistribution",
            "routes"   : "show ipv6 route + show ipv6 ospf border-routers — route health",
        }
        for name, desc in descriptions.items():
            print(f"  {CYAN}{name:<12}{RESET} {desc}")
        print()
        sys.exit(0)

    if args.list_failures:
        print(f"\n{BOLD}Available failure demonstration scenarios:{RESET}\n")
        for key, scenario in FAILURE_SCENARIOS.items():
            print(f"  {CYAN}{key:<22}{RESET} {scenario['title']}")
            print(f"  {DIM}{'':22}  Target: {scenario['target_hint']}{RESET}\n")
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
        print("[ERROR] No valid target routers.")
        sys.exit(1)

    # --demo-failure mode
    if args.demo_failure:
        scenario_key = args.demo_failure

        if scenario_key not in FAILURE_SCENARIOS:
            print(f"[ERROR] Unknown failure scenario: '{scenario_key}'")
            print(f"        Available: {', '.join(FAILURE_SCENARIOS.keys())}")
            sys.exit(1)

        env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.filters["ipv4_addr"] = _ipv4_addr
        env.filters["ipv4_mask"] = _ipv4_mask

        try:
            template = env.get_template(TEMPLATE_FILE)
        except Exception as exc:
            print(f"[ERROR] Failed to load template '{TEMPLATE_FILE}': {exc}")
            sys.exit(1)

        run_demo_failure(scenario_key, devices, target_routers, template)
        sys.exit(0)

    # Live troubleshooting mode
    if args.check:
        invalid = [c for c in args.check if c not in AVAILABLE_CHECKS]
        if invalid:
            print(f"[ERROR] Unknown check(s): {invalid}")
            print(f"        Valid options: {AVAILABLE_CHECKS}")
            sys.exit(1)
        checks_to_run = args.check
    else:
        checks_to_run = AVAILABLE_CHECKS

    print(f"\n{BOLD}NAMS26 — Module 05: IPv6 EIGRP/OSPFv3 Troubleshooting{RESET}")
    print(f"Targets : {', '.join(target_routers)}")
    print(f"Checks  : {', '.join(checks_to_run)}")

    results: dict = {}
    lf = setup_logger()

    try:
        summary_lines = [
            f"\nNAMS26 — Module 05: IPv6 EIGRP/OSPFv3 Troubleshooting",
            f"Targets : {', '.join(target_routers)}",
            f"Checks  : {', '.join(checks_to_run)}",
        ]
        for line in summary_lines:
            lf.write(line + "\n")
        lf.write("\n")

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
                for check_name in checks_to_run:
                    results[device_name][check_name] = LIVE_CHECKS[check_name](
                        conn, device_name, device_data, lf)
            finally:
                conn.disconnect()
                lf.write(f"  [INFO] Disconnected from {device_name}\n")

        _print_summary(results, checks_to_run, lf)
        emit(f"\n{'=' * 60}\nTroubleshooting session complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
