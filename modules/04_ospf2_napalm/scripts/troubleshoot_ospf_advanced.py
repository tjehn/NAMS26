#!/usr/bin/env python3
"""
Module   : 04 — OSPF Advanced / NAPALM
File     : modules/04_ospf2_napalm/scripts/troubleshoot_ospf_advanced.py
Purpose  : Two-mode troubleshooting tool for OSPF Advanced lab.

           Mode 1 — Live Troubleshooting (default)
           ----------------------------------------
           Connects to lab routers via NAPALM and runs targeted
           troubleshooting commands. Results are printed to terminal
           with structured analysis and remediation guidance.

           Mode 2 — Failure Demonstration (--demo-failure)
           ------------------------------------------------
           Injects a named fault into an in-memory copy of the YAML data,
           renders the broken Jinja2 config, diffs it against the correct
           config, explains the failure, and shows the CLI symptoms a
           student would see on a live router. No changes are pushed to
           any device.

Usage:
    # Run all troubleshooting checks on all routers
    python troubleshoot_ospf_advanced.py

    # Run all checks on specific routers
    python troubleshoot_ospf_advanced.py --router R1 R6

    # Run a specific troubleshooting check
    python troubleshoot_ospf_advanced.py --check neighbors
    python troubleshoot_ospf_advanced.py --check database
    python troubleshoot_ospf_advanced.py --check routes
    python troubleshoot_ospf_advanced.py --check redistribution
    python troubleshoot_ospf_advanced.py --check process

    # Demonstrate a failure scenario (memory only — no router changes)
    python troubleshoot_ospf_advanced.py --demo-failure missing-network
    python troubleshoot_ospf_advanced.py --demo-failure wrong-router-id
    python troubleshoot_ospf_advanced.py --demo-failure missing-redistribute
    python troubleshoot_ospf_advanced.py --demo-failure wrong-area-type
    python troubleshoot_ospf_advanced.py --demo-failure missing-nssa

    # List all available checks and failure scenarios
    python troubleshoot_ospf_advanced.py --list-checks
    python troubleshoot_ospf_advanced.py --list-failures

    # Target a specific router for a demo failure
    python troubleshoot_ospf_advanced.py --demo-failure missing-redistribute --router R1

Pre-flight requirement:
    Run utils/clear_known_hosts.sh and utils/check_ssh.py before executing
    live troubleshooting checks after every EVE-NG lab reboot.

Troubleshooting Checks:
    neighbors      — show ip ospf neighbor detail
    database       — show ip ospf database (Type 1/3/4/5/7 LSA health)
    routes         — show ip route ospf + show ip ospf border-routers
    redistribution — show ip route eigrp / show ip route ospf (per router role)
    process        — show ip protocols (OSPF and EIGRP process validation)

Failure Scenarios:
    missing-network      — network statement removed; prefix drops from LSDB
    wrong-router-id      — router-id changed to a duplicate; LSA conflicts
    missing-redistribute — redistribute statement removed from OSPF or EIGRP;
                           external routes disappear from the domain
    wrong-area-type      — area 20 nssa removed from an Area 20 router;
                           adjacency failure or LSA type mismatch
    missing-nssa         — default-information-originate removed from R3;
                           Area 20 routers lose their default route
"""

import os
import re
import sys
import copy
import yaml
import argparse
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from napalm import get_network_driver
from napalm.base.exceptions import ConnectionException

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)

YAML_FILE     = os.path.join(MODULE_DIR, "data",      "ospf_advanced.yaml")
TEMPLATE_DIR  = os.path.join(MODULE_DIR, "templates")
TEMPLATE_FILE = "ospf_advanced.j2"
LOG_DIR       = os.path.join(MODULE_DIR, "logs")

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# AVAILABLE CHECKS AND FAILURE SCENARIOS
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "database", "routes", "redistribution", "process"]

# Routers that run EIGRP only — no OSPF process
EIGRP_ONLY_ROUTERS = {"R7", "R8", "R9"}

FAILURE_SCENARIOS = {
    "missing-network": {
        "title"      : "Missing OSPF Network Statement",
        "description": (
            "A network statement is removed from the YAML networks list for the "
            "target device. OSPF will not originate a Router LSA (Type 1) for "
            "that interface — the prefix disappears from the LSDB and from the "
            "routing table on all routers in the area. The interface remains up; "
            "only the OSPF advertisement is lost."
        ),
        "symptoms"   : [
            "show ip route ospf — prefix absent on all other routers in the area",
            "show ip ospf database — Router LSA for affected router missing that network",
            "show ip ospf interface brief — affected interface not listed as OSPF-active",
            "ping <missing prefix> sourced from remote router — fails",
        ],
        "fix"        : (
            "Restore the missing network statement in the YAML networks list. "
            "Re-run configure_ospf_advanced.py. "
            "Verify with: show ip ospf database | begin <router-id>"
        ),
        "cli_commands": [
            "show ip route ospf",
            "show ip ospf database",
            "show ip ospf interface brief",
            "show ip protocols",
        ],
    },
    "wrong-router-id": {
        "title"      : "Duplicate or Incorrect Router ID",
        "description": (
            "The OSPF router-id is changed to 0.0.0.99, which duplicates no "
            "current router but causes LSA conflicts as soon as OSPF re-originates "
            "its Router LSA with the wrong ID. SPF recalculations become "
            "unpredictable. The adjacency may form initially but routing will "
            "be unstable. IOS will log a warning if a true duplicate exists."
        ),
        "symptoms"   : [
            "show ip ospf — router-id shows 0.0.0.99 instead of expected value",
            "show ip ospf database — Router LSA with unexpected router-id",
            "show ip ospf neighbor — adjacency may be unstable",
            "show ip route ospf — routes may be missing or incorrect",
        ],
        "fix"        : (
            "Correct the router_id in YAML to the proper unique value. "
            "Re-run configure_ospf_advanced.py then clear ip ospf process. "
            "Verify with: show ip ospf | include Router ID"
        ),
        "cli_commands": [
            "show ip ospf",
            "show ip ospf database",
            "show ip ospf neighbor",
        ],
    },
    "missing-redistribute": {
        "title"      : "Redistribution Statement Removed",
        "description": (
            "The 'redistribute eigrp' statement is removed from the OSPF process "
            "on an ASBR (R1 or R6). External routes from that EIGRP domain "
            "immediately disappear from the OSPF LSDB — no Type 5 LSAs (or Type 7 "
            "on R6) are originated. All OSPF routers lose reachability to those "
            "EIGRP prefixes. OSPF adjacencies remain fully up. The troubleshooter "
            "will pass all neighbor and process checks — only the verifier "
            "catches the missing external routes."
        ),
        "symptoms"   : [
            "show ip route ospf — O E1/E2 routes from affected domain absent on all routers",
            "show ip ospf database external — no Type 5 LSAs from the ASBR router-id",
            "show ip ospf database nssa-external — no Type 7 LSAs (R6 fault only)",
            "show ip ospf neighbor — all adjacencies remain FULL (no impact on neighbors)",
            "ping <EIGRP prefix> from Area 0 router — fails",
        ],
        "fix"        : (
            "Restore the redistribute statement in the YAML ospf block. "
            "Re-run configure_ospf_advanced.py on the affected ASBR. "
            "Verify with: show ip ospf database external and show ip route ospf"
        ),
        "cli_commands": [
            "show ip route ospf",
            "show ip ospf database external",
            "show ip ospf database nssa-external",
            "show ip ospf border-routers",
            "show run | section router ospf",
        ],
    },
    "wrong-area-type": {
        "title"      : "NSSA Declaration Removed from Area 20 Router",
        "description": (
            "The 'area 20 nssa' statement is removed from a non-ABR Area 20 "
            "router (R5 or R6). That router will treat Area 20 as a standard "
            "area and reject Type 7 LSAs. The adjacency with R3 or R5 will fail "
            "because the area type in Hello packets will not match. This is an "
            "adjacency-breaking fault — unlike missing redistribution, neighbors "
            "will drop."
        ),
        "symptoms"   : [
            "show ip ospf neighbor — adjacency to Area 20 neighbor drops",
            "show ip ospf — area 20 no longer listed as NSSA on affected router",
            "show ip ospf database — Type 7 LSAs absent or causing errors",
            "debug ip ospf adj — 'area type mismatch' in hello packets",
        ],
        "fix"        : (
            "Restore the area_types entry (area: 20, type: nssa) in YAML for the "
            "affected router. Re-run configure_ospf_advanced.py. "
            "Verify with: show ip ospf | include Area and show ip ospf neighbor"
        ),
        "cli_commands": [
            "show ip ospf neighbor",
            "show ip ospf",
            "show ip ospf database nssa-external",
            "show run | section router ospf",
        ],
    },
    "missing-nssa": {
        "title"      : "NSSA Default-Information-Originate Removed from R3",
        "description": (
            "The 'default-information-originate' flag is removed from R3's "
            "'area 20 nssa' statement. R3 stops injecting a Type 7 default route "
            "into Area 20. R5 and R6 lose their default path toward Area 0 — "
            "they can no longer reach external prefixes or Area 0 destinations "
            "unless they have a specific route. OSPF adjacencies remain fully up. "
            "This is a subtle misconfiguration — the NSSA is still operational, "
            "only the default injection is missing."
        ),
        "symptoms"   : [
            "show ip route ospf on R5/R6 — no O N2 0.0.0.0/0 default route",
            "show ip ospf database nssa-external on R5/R6 — no default Type 7 LSA",
            "show ip ospf neighbor — all adjacencies remain FULL",
            "ping 1.0.0.1 from R5 — fails (no default route to reach Area 0)",
        ],
        "fix"        : (
            "Restore default_information_originate: true in the area_types entry "
            "for area 20 on R3 in YAML. Re-run configure_ospf_advanced.py on R3. "
            "Verify with: show ip route ospf on R5 — O N2 0.0.0.0/0 should reappear"
        ),
        "cli_commands": [
            "show ip route ospf",
            "show ip ospf database nssa-external",
            "show ip ospf neighbor",
            "show run | section router ospf",
        ],
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

def passed(msg):  return f"{GREEN}  [PASS]{RESET} {msg}"
def failed(msg):  return f"{RED}  [FAIL]{RESET} {msg}"
def warned(msg):  return f"{YELLOW}  [WARN]{RESET} {msg}"
def info(msg):    return f"{CYAN}  [INFO]{RESET} {msg}"

def section(title, lf=None):
    lines = [
        f"\n{BOLD}  {'─' * 54}{RESET}",
        f"{BOLD}  {title}{RESET}",
        f"{BOLD}  {'─' * 54}{RESET}",
    ]
    for line in lines:
        print(line)
        if lf:
            lf.write(_strip_ansi(line) + "\n")

def device_header(device_name, dns_name, oob_ip, lf=None):
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

def demo_header(scenario_key, title):
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

def setup_logger() -> object:
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"troubleshoot_ospf_advanced_{timestamp}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 04: OSPF Advanced Troubleshooting\n")
    lf.write(f"Log created : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write(f"Log file    : {log_path}\n")
    lf.write("=" * 60 + "\n\n")
    print(info(f"Logging to  : {log_path}"))
    return lf


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

    all_lines = []
    for line in correct_lines:
        if line not in broken_set:
            all_lines.append(("removed", line))
        else:
            all_lines.append(("same", line))
    for line in broken_lines:
        if line not in correct_set:
            all_lines.append(("added", line))

    for kind, line in all_lines:
        if kind == "removed":
            print(f"{GREEN}  - {line}{RESET}")
        elif kind == "added":
            print(f"{RED}  + {line}{RESET}")
        else:
            print(f"{DIM}    {line}{RESET}")


# =============================================================================
# CUSTOM JINJA2 FILTER  (mirrors configure_ospf_advanced.py)
# =============================================================================

def cidr_to_netmask(cidr: str) -> str:
    try:
        cidr = int(cidr)
        if not 0 <= cidr <= 32:
            raise ValueError
        mask = (0xFFFFFFFF << (32 - cidr)) & 0xFFFFFFFF
        return (
            f"{(mask >> 24) & 255}."
            f"{(mask >> 16) & 255}."
            f"{(mask >> 8) & 255}."
            f"{mask & 255}"
        )
    except Exception:
        return "255.255.255.255"


# =============================================================================
# FAULT INJECTORS
# Each function receives a deep copy of a single device's data dict,
# mutates it to introduce the named fault, and returns the broken copy.
# The original data is never modified.
# =============================================================================

def inject_missing_network(device_data: dict) -> dict:
    """Remove the first non-loopback (/8 wildcard) network statement."""
    broken   = copy.deepcopy(device_data)
    ospf     = broken.get("ospf") or {}
    networks = ospf.get("networks") or []
    for i, net in enumerate(networks):
        if net.get("wildcard") != "0.255.255.255":
            broken["_removed_network"] = networks.pop(i)
            break
    ospf["networks"] = networks
    broken["ospf"]   = ospf
    return broken


def inject_wrong_router_id(device_data: dict) -> dict:
    """Change the router-id to 0.0.0.99."""
    broken = copy.deepcopy(device_data)
    ospf   = broken.get("ospf") or {}
    broken["_original_router_id"] = ospf.get("router_id", "?")
    ospf["router_id"] = "0.0.0.99"
    broken["ospf"]    = ospf
    return broken


def inject_missing_redistribute(device_data: dict) -> dict:
    """Remove the redistribute_eigrp statement from the OSPF block."""
    broken = copy.deepcopy(device_data)
    ospf   = broken.get("ospf") or {}
    if ospf.get("redistribute_eigrp"):
        broken["_removed_redistribute"] = ospf["redistribute_eigrp"]
        ospf["redistribute_eigrp"] = None
    broken["ospf"] = ospf
    return broken


def inject_wrong_area_type(device_data: dict) -> dict:
    """Remove the nssa area type declaration from the area_types list."""
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
    ospf["area_types"]         = new_types
    broken["ospf"]             = ospf
    broken["_removed_area_type"] = removed
    return broken


def inject_missing_nssa(device_data: dict) -> dict:
    """Remove default_information_originate from the nssa area type on the ABR."""
    broken     = copy.deepcopy(device_data)
    ospf       = broken.get("ospf") or {}
    area_types = ospf.get("area_types") or []
    for at in area_types:
        if at.get("type") == "nssa" and at.get("default_information_originate"):
            at["default_information_originate"] = False
            broken["_removed_default_originate"] = True
    broken["ospf"] = ospf
    return broken


FAULT_INJECTORS = {
    "missing-network"     : inject_missing_network,
    "wrong-router-id"     : inject_wrong_router_id,
    "missing-redistribute": inject_missing_redistribute,
    "wrong-area-type"     : inject_wrong_area_type,
    "missing-nssa"        : inject_missing_nssa,
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
      1. Render the correct config from clean YAML data
      2. Inject the fault into an in-memory copy of the device data
      3. Render the broken config from the mutated data
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

    for device_name in target_routers:
        device_data = devices[device_name]

        # Skip EIGRP-only routers for OSPF-specific demos
        if device_name in EIGRP_ONLY_ROUTERS and scenario_key not in ("missing-network",):
            ospf = device_data.get("ospf")
            if not ospf:
                print(info(
                    f"  {device_name} is EIGRP-only — "
                    f"skipping OSPF failure demo"
                ))
                continue

        print(f"\n{BOLD}  [ Demonstrating on {device_name} ]{RESET}")

        correct_config = template.render(device_data)
        broken_data    = injector(device_data)
        broken_config  = template.render(broken_data)

        section("Fault Injected (in-memory only — router not changed)")

        if scenario_key == "missing-network":
            removed = broken_data.get("_removed_network", {})
            print(info(
                f"Network statement removed: "
                f"{removed.get('prefix', '?')} {removed.get('wildcard', '?')} "
                f"area {removed.get('area', '?')}"
            ))
            print(info("This prefix will not appear in any Router LSA"))

        elif scenario_key == "wrong-router-id":
            orig = broken_data.get("_original_router_id", "?")
            print(info(f"router-id changed from {orig} → 0.0.0.99"))
            print(info("OSPF LSAs will be originated with the wrong router-id"))

        elif scenario_key == "missing-redistribute":
            removed = broken_data.get("_removed_redistribute")
            if removed:
                print(info(
                    f"redistribute eigrp {removed.get('as_number', '?')} "
                    f"metric-type {removed.get('metric_type', '?')} subnets — REMOVED"
                ))
                print(info("External routes from that EIGRP domain will vanish from OSPF"))
            else:
                print(info(f"No redistribute_eigrp found on {device_name} — "
                           f"choose R1 or R6 for this demo"))

        elif scenario_key == "wrong-area-type":
            removed = broken_data.get("_removed_area_type")
            if removed:
                print(info(
                    f"area {removed.get('area', '?')} nssa declaration removed"
                ))
                print(info("This router will treat Area 20 as standard — "
                           "adjacency with NSSA neighbors will drop"))
            else:
                print(info(f"No nssa area_type found on {device_name} — "
                           f"choose R3, R5, or R6 for this demo"))

        elif scenario_key == "missing-nssa":
            if broken_data.get("_removed_default_originate"):
                print(info("default-information-originate removed from area 20 nssa on R3"))
                print(info("Area 20 routers (R5, R6) will lose O N2 0.0.0.0/0 default route"))
            else:
                print(info(f"No default_information_originate found on {device_name} — "
                           f"use --router R3 for this demo"))

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
# NAPALM CONNECTION
# =============================================================================

def connect(device_name: str, dns_name: str, creds: dict, lf=None):
    """Establish a NAPALM IOS driver session. Returns device or None on failure."""
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
# LIVE TROUBLESHOOTING CHECKS
# =============================================================================

_RANK = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}

def _worst(a: str, b: str) -> str:
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


def check_neighbors(conn, device_name: str, device_data: dict, lf=None) -> str:
    """show ip ospf neighbor detail — adjacency state analysis.

    Skipped on EIGRP-only routers. Flags any non-FULL adjacency states.

    Returns: "PASS", "WARN", "FAIL", or "INFO".
    """
    if device_name in EIGRP_ONLY_ROUTERS:
        emit(info(f"{device_name} is EIGRP-only — neighbor check skipped."), lf)
        return "INFO"

    section("Neighbors — show ip ospf neighbor detail", lf)
    output = conn.cli(["show ip ospf neighbor detail"])["show ip ospf neighbor detail"]
    emit_raw(output, lf)

    result = "PASS"

    problem_states = ["EXSTART", "EXCHANGE", "INIT", "LOADING"]
    for state in problem_states:
        if state in output.upper():
            emit(warned(
                f"Neighbor in {state} state detected — "
                f"possible area type mismatch, MTU issue, or NSSA misconfiguration"
            ), lf)
            result = _worst(result, "WARN")

    if "FULL" in output.upper():
        emit(passed("At least one FULL adjacency confirmed"), lf)
    elif output.strip():
        emit(failed("No FULL adjacencies found — OSPF is not converged"), lf)
        result = _worst(result, "FAIL")
    else:
        emit(failed("No OSPF neighbors — check network statements, area type, and interface state"), lf)
        result = _worst(result, "FAIL")

    return result


def check_database(conn, device_name: str, device_data: dict, lf=None) -> str:
    """OSPF database health check — validates presence of key LSA types.

    Runs targeted per-type commands to check for:
      Type 1 (Router)         — own router-id must be present
      Type 4 (ASBR Summary)   — expected on Area 10 routers (R4, R10)
      Type 5 (AS External)    — expected on all OSPF routers in the domain
      Type 7 (NSSA External)  — expected only on Area 20 routers (R5, R6)

    Skipped on EIGRP-only routers. Returns: "PASS", "WARN", or "FAIL".
    """
    if device_name in EIGRP_ONLY_ROUTERS:
        emit(info(f"{device_name} is EIGRP-only — LSDB check skipped."), lf)
        return "INFO"

    section("OSPF Database — LSA Health Check", lf)

    ospf_data = device_data.get("ospf") or {}
    router_id = ospf_data.get("router_id", "")
    area_types = ospf_data.get("area_types", []) or []
    in_area_20 = any(str(at.get("area", "")) == "20" for at in area_types)
    result     = "PASS"

    # --- Type 1: Router LSAs — own router-id must be present
    section("Type 1 — Router LSAs", lf)
    t1_output = conn.cli(["show ip ospf database router"])["show ip ospf database router"]
    emit_raw(t1_output, lf)

    if router_id and router_id in t1_output:
        emit(passed(f"Router LSA for {router_id} present in LSDB"), lf)
    elif router_id:
        emit(failed(
            f"Router LSA for {router_id} NOT found — "
            f"OSPF process may not be running or router-id mismatch"
        ), lf)
        result = _worst(result, "FAIL")

    # --- Type 4: ASBR Summary LSAs — expected on Area 10 routers
    # Area 10 internal routers (R4, R10) should see Type 4 for R1's reachability
    if not in_area_20 and device_name not in ("R1", "R2", "R3"):
        section("Type 4 — ASBR Summary LSAs", lf)
        t4_output = conn.cli(
            ["show ip ospf database asbr-summary"]
        )["show ip ospf database asbr-summary"]
        emit_raw(t4_output, lf)

        if t4_output.strip() and "ASBR Summary" in t4_output or \
           "Link State ID" in t4_output:
            emit(passed("Type 4 ASBR Summary LSAs present — ASBR reachability confirmed"), lf)
        else:
            emit(warned(
                "No Type 4 ASBR Summary LSAs found — "
                "R1 ASBR reachability may not be advertised into this area"
            ), lf)
            result = _worst(result, "WARN")

    # --- Type 5: AS External LSAs — expected on all OSPF routers EXCEPT Area 20 (NSSA).
    # NSSA blocks Type 5 LSAs from entering the area by design.
    if in_area_20:
        emit(info(
            f"{device_name} is in NSSA Area 20 — Type 5 LSAs are blocked by design; "
            f"check Type 7 LSAs instead"
        ), lf)
    else:
        section("Type 5 — AS External LSAs", lf)
        t5_output = conn.cli(["show ip ospf database external"])["show ip ospf database external"]
        emit_raw(t5_output, lf)

        if t5_output.strip() and "Link State ID" in t5_output:
            emit(passed("Type 5 AS External LSAs present — redistribution from EIGRP 100 working"), lf)
        else:
            emit(failed(
                "No Type 5 AS External LSAs found — "
                "check R1 'redistribute eigrp 100' in OSPF and R3 Type 7→5 conversion"
            ), lf)
            result = _worst(result, "FAIL")

    # --- Type 7: NSSA External LSAs — expected only on Area 20 routers
    if in_area_20:
        section("Type 7 — NSSA External LSAs", lf)
        t7_output = conn.cli(
            ["show ip ospf database nssa-external"]
        )["show ip ospf database nssa-external"]
        emit_raw(t7_output, lf)

        if t7_output.strip() and "Link State ID" in t7_output:
            emit(passed("Type 7 NSSA External LSAs present — R6 redistribution working"), lf)
        else:
            emit(failed(
                "No Type 7 NSSA External LSAs found — "
                "check R6 'redistribute eigrp 111' and 'area 20 nssa' on all Area 20 routers"
            ), lf)
            result = _worst(result, "FAIL")

    return result


def check_routes(conn, device_name: str, device_data: dict, lf=None) -> str:
    """show ip route ospf + show ip ospf border-routers — route table health.

    Returns: "PASS", "WARN", or "FAIL".
    """
    if device_name in EIGRP_ONLY_ROUTERS:
        emit(info(f"{device_name} is EIGRP-only — OSPF route check skipped."), lf)
        return "INFO"

    section("Route Table — show ip route ospf", lf)
    route_output = conn.cli(["show ip route ospf"])["show ip route ospf"]
    emit_raw(route_output, lf)

    result = "PASS"

    if not route_output.strip():
        emit(warned(
            "No OSPF routes in routing table — "
            "check neighbors, network statements, and area type configuration"
        ), lf)
        result = _worst(result, "WARN")
    else:
        # Count route types
        type_counts = {}
        for prefix in ("O E1", "O E2", "O N1", "O N2", "O IA", "^O "):
            pattern = re.compile(r'^\s*' + re.escape(prefix.strip()), re.MULTILINE)
            count   = len(pattern.findall(route_output))
            if count:
                label = prefix.strip() or "O"
                type_counts[label] = count
        emit(passed(
            f"OSPF routes present — "
            + "  ".join(f"{t}:{c}" for t, c in type_counts.items())
        ), lf)

        # NSSA default check: only pure Area 20 routers (R5, R6).
        # R3 is the NSSA ABR that generates the default — it won't receive it back.
        ospf_data  = device_data.get("ospf") or {}
        area_types = ospf_data.get("area_types", []) or []
        networks   = ospf_data.get("networks", []) or []
        in_area_20 = any(str(at.get("area", "")) == "20" for at in area_types)
        in_area_0  = any(str(n.get("area", "")) == "0" for n in networks)
        if in_area_20 and not in_area_0:
            # IOS prints candidate defaults as O*N2 (no space before N)
            has_default = bool(re.search(r'O\*?N[12]\s+0\.0\.0\.0', route_output))
            if has_default:
                emit(passed("NSSA default route (O N1/N2 0.0.0.0/0) present"), lf)
            else:
                emit(failed(
                    "NSSA default route missing — "
                    "check R3 'area 20 nssa default-information-originate'"
                ), lf)
                result = _worst(result, "FAIL")

    section("Border Routers — show ip ospf border-routers", lf)
    br_output = conn.cli(["show ip ospf border-routers"])["show ip ospf border-routers"]
    emit_raw(br_output, lf)

    if br_output.strip():
        emit(passed("Border router entries present — ABR/ASBR reachability confirmed"), lf)
    elif device_name not in EIGRP_ONLY_ROUTERS:
        emit(info("No border routers found — expected only on pure backbone internal routers"), lf)

    return result


def check_redistribution(conn, device_name: str, device_data: dict, lf=None) -> str:
    """Validate redistribution state per router role.

    ASBRs (R1, R6)        — check EIGRP table for D EX routes
    EIGRP-only (R7/R8/R9) — check EIGRP table for D EX routes
    Internal OSPF routers  — check OSPF table for O E1/E2/N1/N2 routes

    Returns: "PASS", "WARN", or "FAIL".
    """
    section("Redistribution — Route Table Check", lf)

    result     = "PASS"
    eigrp_data = device_data.get("eigrp")
    ospf_data  = device_data.get("ospf") or {}

    if eigrp_data and ospf_data:
        # ASBR (R1, R6): originates redistribution — D EX routes appear on
        # receiving neighbors, not on the ASBR itself. Check config instead.
        run_eigrp = conn.cli(["show run | section router eigrp"])["show run | section router eigrp"]
        emit_raw(run_eigrp, lf)
        if re.search(r'redistribute ospf', run_eigrp, re.IGNORECASE):
            emit(passed("'redistribute ospf' present in EIGRP config — OSPF → EIGRP configured"), lf)
        else:
            emit(failed("'redistribute ospf' missing from EIGRP config"), lf)
            result = _worst(result, "FAIL")

        run_ospf = conn.cli(["show run | section router ospf"])["show run | section router ospf"]
        emit_raw(run_ospf, lf)
        if re.search(r'redistribute eigrp', run_ospf, re.IGNORECASE):
            emit(passed("'redistribute eigrp' present in OSPF config — EIGRP → OSPF configured"), lf)
        else:
            emit(failed("'redistribute eigrp' missing from OSPF config"), lf)
            result = _worst(result, "FAIL")

    elif eigrp_data:
        # EIGRP-only routers (R7, R8, R9): should receive D EX from ASBR
        eigrp_output = conn.cli(["show ip route eigrp"])["show ip route eigrp"]
        emit_raw(eigrp_output, lf)

        d_ex_lines = [l for l in eigrp_output.splitlines()
                      if re.match(r'^\s*D\s+EX\s+', l, re.IGNORECASE)]
        if d_ex_lines:
            emit(passed(
                f"{len(d_ex_lines)} D EX route(s) in EIGRP table — "
                f"OSPF routes redistributed into EIGRP confirmed"
            ), lf)
        else:
            emit(failed(
                "No D EX routes in EIGRP table — "
                "OSPF → EIGRP redistribution may have failed on the ASBR"
            ), lf)
            result = _worst(result, "FAIL")

    # Internal OSPF routers: check for external routes in OSPF table
    # IOS prints NSSA candidate defaults as O*N2 (no space before N)
    if device_name not in EIGRP_ONLY_ROUTERS and not (eigrp_data and ospf_data):
        ospf_output = conn.cli(["show ip route ospf"])["show ip route ospf"]
        emit_raw(ospf_output, lf)

        ext_lines = [l for l in ospf_output.splitlines()
                     if re.match(r'^\s*O\s+(?:E1|E2|N1|N2)\s+|^\s*O\*?N[12]\s+',
                                 l, re.IGNORECASE)]
        if ext_lines:
            emit(passed(
                f"{len(ext_lines)} external OSPF route(s) (E1/E2/N1/N2) present — "
                f"redistribution visible from this router"
            ), lf)
        else:
            emit(failed(
                "No external OSPF routes (E1/E2/N1/N2) found — "
                "check ASBR redistribution and NSSA configuration"
            ), lf)
            result = _worst(result, "FAIL")

    return result


def check_process(conn, device_name: str, device_data: dict, lf=None) -> str:
    """show ip protocols — validates OSPF and EIGRP process state.

    Returns: "PASS", "WARN", or "FAIL".
    """
    section("Protocols — show ip protocols", lf)
    output = conn.cli(["show ip protocols"])["show ip protocols"]
    emit_raw(output, lf)

    result = "PASS"

    # OSPF process check
    ospf_data  = device_data.get("ospf")
    if ospf_data:
        process_id = str(ospf_data.get("process_id", ""))
        router_id  = ospf_data.get("router_id", "")

        if process_id and f"ospf {process_id}" in output.lower():
            emit(passed(f"OSPF process {process_id} confirmed running"), lf)
        elif process_id:
            emit(failed(
                f"OSPF process {process_id} NOT found in show ip protocols — "
                f"process may not be running"
            ), lf)
            result = _worst(result, "FAIL")

        if router_id and router_id in output:
            emit(passed(f"OSPF Router ID {router_id} confirmed"), lf)
        elif router_id:
            emit(failed(
                f"OSPF Router ID {router_id} NOT found — "
                f"router-id mismatch or OSPF process not running"
            ), lf)
            result = _worst(result, "FAIL")

    # EIGRP process check
    eigrp_data = device_data.get("eigrp")
    if eigrp_data:
        as_number = str(eigrp_data.get("as_number", ""))
        if as_number and f"eigrp {as_number}" in output.lower():
            emit(passed(f"EIGRP AS {as_number} confirmed running"), lf)
        elif as_number:
            emit(failed(
                f"EIGRP AS {as_number} NOT found in show ip protocols — "
                f"EIGRP process may not be running"
            ), lf)
            result = _worst(result, "FAIL")

    return result


LIVE_CHECKS = {
    "neighbors"     : check_neighbors,
    "database"      : check_database,
    "routes"        : check_routes,
    "redistribution": check_redistribution,
    "process"       : check_process,
}


# =============================================================================
# SUMMARY
# =============================================================================

def _print_summary(results: dict, checks_to_run: list, lf=None) -> None:
    """Print a per-device, per-check summary table."""
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

    totals: dict = {
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
        ) if parts else 1
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
            "Module 04 — OSPF Advanced Troubleshooting\n"
            "Live troubleshooting checks and in-memory failure demonstrations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python troubleshoot_ospf_advanced.py\n"
            "  python troubleshoot_ospf_advanced.py --router R1 R6\n"
            "  python troubleshoot_ospf_advanced.py --check database redistribution\n"
            "  python troubleshoot_ospf_advanced.py --demo-failure missing-redistribute\n"
            "  python troubleshoot_ospf_advanced.py --demo-failure missing-nssa --router R3\n"
        ),
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help="Target one or more routers by hostname. Defaults to all devices.",
    )
    parser.add_argument(
        "--check",
        nargs="*",
        metavar="CHECK",
        help=(
            f"Live troubleshooting checks to run: "
            f"{', '.join(AVAILABLE_CHECKS)}. Defaults to all."
        ),
    )
    parser.add_argument(
        "--demo-failure",
        metavar="SCENARIO",
        help=(
            f"Inject a named failure scenario in memory and walk through "
            f"the full diagnostic cycle. No changes pushed to routers. "
            f"Scenarios: {', '.join(FAILURE_SCENARIOS.keys())}."
        ),
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="List all available live troubleshooting checks and exit.",
    )
    parser.add_argument(
        "--list-failures",
        action="store_true",
        help="List all available failure demonstration scenarios and exit.",
    )
    args = parser.parse_args()

    # --list-checks
    if args.list_checks:
        print(f"\n{BOLD}Available live troubleshooting checks:{RESET}\n")
        descriptions = {
            "neighbors"     : "show ip ospf neighbor detail — adjacency state analysis",
            "database"      : "Type 1/4/5/7 LSA health check (targeted commands per type)",
            "routes"        : "show ip route ospf + border-routers — route table health",
            "redistribution": "EIGRP table (D EX) + OSPF table (O E1/E2/N1/N2) validation",
            "process"       : "show ip protocols — OSPF and EIGRP process ID validation",
        }
        for name, desc in descriptions.items():
            print(f"  {CYAN}{name:<16}{RESET} {desc}")
        print()
        sys.exit(0)

    # --list-failures
    if args.list_failures:
        print(f"\n{BOLD}Available failure demonstration scenarios:{RESET}\n")
        for key, scenario in FAILURE_SCENARIOS.items():
            print(f"  {CYAN}{key:<22}{RESET} {scenario['title']}")
            print(f"  {DIM}{'':22}  {scenario['description'][:80]}...{RESET}\n")
        sys.exit(0)

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
        env.filters["cidr_to_netmask"] = cidr_to_netmask

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

    print(f"\n{BOLD}NAMS26 — Module 04: OSPF Advanced Troubleshooting{RESET}")
    print(f"Targets : {', '.join(target_routers)}")
    print(f"Checks  : {', '.join(checks_to_run)}")

    results: dict = {}
    lf = setup_logger()

    try:
        summary_lines = [
            f"\nNAMS26 — Module 04: OSPF Advanced Troubleshooting",
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

            device = connect(device_name, dns_name, creds, lf)
            if device is None:
                emit(failed(f"Skipping all checks on {device_name} — connection failed."), lf)
                for chk in checks_to_run:
                    results[device_name][chk] = "FAIL"
                continue

            try:
                for check_name in checks_to_run:
                    results[device_name][check_name] = LIVE_CHECKS[check_name](
                        device, device_name, device_data, lf)
            finally:
                device.close()
                lf and lf.write(f"  [INFO] Disconnected from {device_name}\n")

        _print_summary(results, checks_to_run, lf)
        emit(f"\n{'=' * 60}\nTroubleshooting session complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
