#!/usr/bin/env python3
"""
Module   : 03 — OSPF Classic Mode
File     : modules/03_ospf1_napalm/scripts/troubleshoot_ospf_classic.py
Purpose  : Two-mode troubleshooting tool for OSPF Classic Mode lab.

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
    python troubleshoot_ospf_classic.py

    # Run all checks on specific routers
    python troubleshoot_ospf_classic.py --router R1 R8

    # Run a specific troubleshooting check
    python troubleshoot_ospf_classic.py --check neighbors
    python troubleshoot_ospf_classic.py --check authentication
    python troubleshoot_ospf_classic.py --check database
    python troubleshoot_ospf_classic.py --check routes
    python troubleshoot_ospf_classic.py --check process

    # Demonstrate a failure scenario (memory only — no router changes)
    python troubleshoot_ospf_classic.py --demo-failure missing-network
    python troubleshoot_ospf_classic.py --demo-failure wrong-router-id
    python troubleshoot_ospf_classic.py --demo-failure auth-mismatch
    python troubleshoot_ospf_classic.py --demo-failure wrong-area
    python troubleshoot_ospf_classic.py --demo-failure missing-auth-key

    # List all available checks and failure scenarios
    python troubleshoot_ospf_classic.py --list-checks
    python troubleshoot_ospf_classic.py --list-failures

    # Target a specific router for a demo failure
    python troubleshoot_ospf_classic.py --demo-failure auth-mismatch --router R2

Pre-flight requirement:
    Run utils/clear_known_hosts.sh and utils/check_ssh.py before executing
    live troubleshooting checks after every EVE-NG lab reboot. check_ssh.py
    populates ~/.ssh/known_hosts with current host keys using
    StrictHostKeyChecking accept-new, allowing this script to connect without
    SSH suppression.

Troubleshooting Checks:
    neighbors      — show ip ospf neighbor detail
    authentication — show ip ospf interface (auth state per interface)
    database       — show ip ospf database (LSDB summary + LSA type counts)
    routes         — show ip route ospf + show ip ospf border-routers
    process        — show ip protocols (OSPF process summary)

Failure Scenarios:
    missing-network  — network statement removed; prefix drops from LSDB
                       and routing table on all routers
    wrong-router-id  — router-id changed to a duplicate; adjacency instability
                       and unpredictable SPF behavior
    auth-mismatch    — authentication key changed on one side; adjacency
                       fails with no clear error message
    wrong-area       — interface placed in wrong area; area mismatch detected
                       by OSPF, adjacency stuck in ExStart/Exchange
    missing-auth-key — authentication type configured but key omitted;
                       adjacency fails immediately on affected segment
"""

import os
import re
import sys
import copy
import yaml
import argparse
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

YAML_FILE     = os.path.join(MODULE_DIR, "data",      "ospf_classic.yaml")
TEMPLATE_DIR  = os.path.join(MODULE_DIR, "templates")
TEMPLATE_FILE = "ospf_classic.j2"
LOG_DIR       = os.path.join(MODULE_DIR, "logs")

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# AVAILABLE CHECKS AND FAILURE SCENARIOS
# Single source of truth — used by argparse, --list-checks, --list-failures
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "authentication", "database", "routes", "process"]

FAILURE_SCENARIOS = {
    "missing-network": {
        "title"      : "Missing OSPF Network Statement",
        "description": (
            "A network statement is removed from the YAML networks list for the "
            "target device. OSPF will not originate a Router LSA (Type 1) for "
            "that interface — the prefix disappears from the LSDB and from the "
            "routing table on all routers in the area. The interface remains up; "
            "only the OSPF advertisement is lost. Reachability to that prefix "
            "from remote routers will fail."
        ),
        "symptoms"   : [
            "show ip route ospf — prefix absent on all other routers in the area",
            "show ip ospf database — Router LSA for affected router missing the network",
            "show ip ospf interface brief — affected interface not listed as OSPF-active",
            "ping <missing prefix> sourced from remote router — fails",
        ],
        "fix"        : (
            "Restore the missing network statement in the YAML networks list. "
            "Re-run configure_ospf_classic.py. "
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
            "The OSPF router-id is changed to a value that duplicates another "
            "router in the same area. OSPF uses the router-id as a unique "
            "identifier for LSA origination — a duplicate causes LSA conflicts, "
            "SPF instability, and unpredictable routing behavior. The adjacency "
            "may form initially but will destabilize as conflicting LSAs are "
            "flooded. IOS will log a duplicate router-id warning."
        ),
        "symptoms"   : [
            "show ip ospf — duplicate router-id warning in log",
            "show ip ospf database — two Router LSAs with the same router-id",
            "show ip ospf neighbor — adjacency may flap or stabilize incorrectly",
            "show ip route ospf — unpredictable or missing routes",
        ],
        "fix"        : (
            "Correct the router_id in YAML to a unique value. "
            "Re-run configure_ospf_classic.py then clear ip ospf process on "
            "the affected router to force LSA re-origination. "
            "Verify with: show ip ospf | include Router ID"
        ),
        "cli_commands": [
            "show ip ospf",
            "show ip ospf database",
            "show ip ospf neighbor",
        ],
    },
    "auth-mismatch": {
        "title"      : "Authentication Key Mismatch",
        "description": (
            "The authentication key on one side of an OSPF adjacency is changed "
            "to a value that does not match its neighbor. For plain-text "
            "authentication the mismatch is immediately fatal — hellos are "
            "rejected and the adjacency drops. For MD5 the adjacency drops after "
            "the dead interval expires. In both cases no explicit error appears "
            "in 'show ip ospf neighbor' — the neighbor simply disappears. "
            "This is one of the most common OSPF failures in production."
        ),
        "symptoms"   : [
            "show ip ospf neighbor — neighbor absent or drops after dead interval",
            "show ip ospf interface — auth type shown but adjacency not forming",
            "debug ip ospf adj — 'authentication failed' or 'mismatched key'",
            "show ip ospf — interface listed but neighbor count 0",
        ],
        "fix"        : (
            "Align the authentication key in YAML on both sides of the link. "
            "Re-run configure_ospf_classic.py on both routers. "
            "Verify with: show ip ospf neighbor and show ip ospf interface"
        ),
        "cli_commands": [
            "show ip ospf neighbor",
            "show ip ospf interface",
            "show run | section router ospf",
            "show run | include authentication",
        ],
    },
    "wrong-area": {
        "title"      : "Interface Placed in Wrong OSPF Area",
        "description": (
            "A network statement is moved to the wrong area number in the YAML. "
            "The two routers sharing that link will advertise different area IDs "
            "in their Hello packets. OSPF requires both sides of a link to agree "
            "on the area — a mismatch causes the adjacency to remain stuck in "
            "ExStart or never progress past Init. The router-id and process ID "
            "are both correct; only the area disagrees."
        ),
        "symptoms"   : [
            "show ip ospf neighbor — neighbor stuck in ExStart or Init state",
            "show ip ospf interface — area mismatch visible in interface detail",
            "debug ip ospf adj — 'area mismatch' or 'hello packet ignored'",
            "show ip ospf database — no LSA from the affected neighbor",
        ],
        "fix"        : (
            "Correct the area value in the YAML networks list for the affected "
            "interface. Re-run configure_ospf_classic.py. "
            "Verify with: show ip ospf interface <intf> and show ip ospf neighbor"
        ),
        "cli_commands": [
            "show ip ospf neighbor",
            "show ip ospf interface",
            "show ip ospf database",
            "show run | section router ospf",
        ],
    },
    "missing-auth-key": {
        "title"      : "Authentication Type Set but Key Omitted",
        "description": (
            "Authentication is enabled on an interface (type plaintext or md5) "
            "but the key value is removed from the YAML. The router will send "
            "hellos with authentication enabled but with an empty or null key. "
            "The neighbor, which has a valid key configured, will reject the "
            "hellos immediately. The adjacency never forms. This is a common "
            "misconfiguration when authentication is added to an existing lab "
            "and the key is forgotten."
        ),
        "symptoms"   : [
            "show ip ospf neighbor — neighbor never appears",
            "show ip ospf interface — authentication type shown on interface",
            "show run | include authentication-key — key line absent or null",
            "debug ip ospf adj — 'authentication failed' from first hello",
        ],
        "fix"        : (
            "Add the correct key value to the ospf_authentication block in YAML. "
            "Re-run configure_ospf_classic.py. "
            "Verify with: show ip ospf interface and show ip ospf neighbor"
        ),
        "cli_commands": [
            "show ip ospf neighbor",
            "show ip ospf interface",
            "show run | include authentication",
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


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logger() -> object:
    """Create the logs directory if needed and open a timestamped log file.

    Log file path:
        NAMS26/logs/troubleshoot_ospf_classic_YYYYMMDD_HHMMSS.log

    Returns:
        An open file handle for writing. Caller is responsible for closing it.
    """
    from datetime import datetime
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"troubleshoot_ospf_classic_{timestamp}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — Module 03: OSPF Classic Mode Troubleshooting\n")
    lf.write(f"Log created : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write(f"Log file    : {log_path}\n")
    lf.write("=" * 60 + "\n\n")
    print(info(f"Logging to  : {log_path}"))
    return lf

def diff_configs(correct: str, broken: str) -> None:
    """Print a simple line-level diff between correct and broken configs.

    Lines present in correct but absent in broken are shown in green (removed
    by the fault). Lines present in broken but absent in correct are shown in
    red (added or changed by the fault). Unchanged lines are shown dimmed.
    """
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
# CUSTOM JINJA2 FILTER  (mirrors configure_ospf_classic.py)
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
    """Remove the first non-loopback network statement from the OSPF networks list."""
    broken   = copy.deepcopy(device_data)
    networks = broken["ospf"].get("networks") or []
    # Find first non-loopback network (wildcard 0.255.255.255 = loopback /8)
    for i, net in enumerate(networks):
        if net.get("wildcard") != "0.255.255.255":
            broken["_removed_network"] = networks.pop(i)
            break
    broken["ospf"]["networks"] = networks
    return broken


def inject_wrong_router_id(device_data: dict) -> dict:
    """Change the router-id to 0.0.0.99 — likely a duplicate in any topology."""
    broken = copy.deepcopy(device_data)
    broken["_original_router_id"] = broken["ospf"]["router_id"]
    broken["ospf"]["router_id"]   = "0.0.0.99"
    return broken


def inject_auth_mismatch(device_data: dict) -> dict:
    """Append '_WRONG' to the authentication key on the first auth-enabled interface."""
    broken     = copy.deepcopy(device_data)
    interfaces = broken.get("interfaces", {})
    for intf_name, intf in interfaces.items():
        auth = intf.get("ospf_authentication", {})
        if auth.get("type", "none") not in ("none", "") and auth.get("key"):
            auth["key"] = auth["key"] + "_WRONG"
            broken["_mismatch_intf"] = intf_name
            broken["_mismatch_key"]  = auth["key"]
            break
    return broken


def inject_wrong_area(device_data: dict) -> dict:
    """Move the first non-loopback network statement to area 99."""
    broken   = copy.deepcopy(device_data)
    networks = broken["ospf"].get("networks") or []
    for net in networks:
        if net.get("wildcard") != "0.255.255.255":
            broken["_original_area"] = net["area"]
            net["area"] = 99
            broken["_wrong_area_network"] = net["prefix"]
            break
    broken["ospf"]["networks"] = networks
    return broken


def inject_missing_auth_key(device_data: dict) -> dict:
    """Clear the key value on the first authentication-enabled interface."""
    broken     = copy.deepcopy(device_data)
    interfaces = broken.get("interfaces", {})
    for intf_name, intf in interfaces.items():
        auth = intf.get("ospf_authentication", {})
        if auth.get("type", "none") not in ("none", "") and auth.get("key"):
            broken["_missing_key_intf"] = intf_name
            broken["_missing_key_type"] = auth["type"]
            auth["key"] = ""
            break
    return broken


FAULT_INJECTORS = {
    "missing-network" : inject_missing_network,
    "wrong-router-id" : inject_wrong_router_id,
    "auth-mismatch"   : inject_auth_mismatch,
    "wrong-area"      : inject_wrong_area,
    "missing-auth-key": inject_missing_auth_key,
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

    Args:
        scenario_key   : Key from FAILURE_SCENARIOS dict.
        devices        : Full devices dict loaded from YAML.
        target_routers : List of device names to demonstrate against.
        template       : Loaded Jinja2 Template object.
    """
    scenario = FAILURE_SCENARIOS[scenario_key]
    injector = FAULT_INJECTORS[scenario_key]

    demo_header(scenario_key, scenario["title"])

    section("What This Failure Demonstrates")
    print(f"\n  {scenario['description']}\n")

    for device_name in target_routers:
        device_data = devices[device_name]

        print(f"\n{BOLD}  [ Demonstrating on {device_name} ]{RESET}")

        # Render correct config
        correct_config = template.render(device_data)

        # Inject fault and render broken config
        broken_data   = injector(device_data)
        broken_config = template.render(broken_data)

        # Show injected fault detail
        section("Fault Injected (in-memory only — router not changed)")

        if scenario_key == "missing-network":
            removed = broken_data.get("_removed_network", {})
            print(info(
                f"Network statement removed: "
                f"{removed.get('prefix', '?')} {removed.get('wildcard', '?')} "
                f"area {removed.get('area', '?')}"
            ))
            print(info("This prefix will not be originated in any OSPF LSA"))

        elif scenario_key == "wrong-router-id":
            orig = broken_data.get("_original_router_id", "?")
            print(info(f"router-id changed from {orig} → 0.0.0.99"))
            print(info("0.0.0.99 may duplicate another router — LSA conflicts will follow"))

        elif scenario_key == "auth-mismatch":
            intf = broken_data.get("_mismatch_intf", "unknown")
            key  = broken_data.get("_mismatch_key", "?")
            print(info(f"Interface {intf}: authentication key changed to '{key}'"))
            print(info("Neighbor still uses the original key — hello packets will be rejected"))

        elif scenario_key == "wrong-area":
            net  = broken_data.get("_wrong_area_network", "?")
            orig = broken_data.get("_original_area", "?")
            print(info(f"Network {net}: area changed from {orig} → 99"))
            print(info("Neighbor advertising this network in a different area — ExStart/Init loop"))

        elif scenario_key == "missing-auth-key":
            intf = broken_data.get("_missing_key_intf", "unknown")
            atype = broken_data.get("_missing_key_type", "?")
            print(info(f"Interface {intf}: {atype} authentication type set but key cleared"))
            print(info("Router will send hellos with auth enabled but null key — rejected immediately"))

        # Config diff
        section("Configuration Diff")
        diff_configs(correct_config, broken_config)

        # CLI symptoms
        section("CLI Symptoms — What You Would See on the Router")
        print()
        for symptom in scenario["symptoms"]:
            print(f"  {YELLOW}▸{RESET}  {symptom}")

        # Troubleshooting commands
        section("Troubleshooting Commands to Run")
        print()
        for cmd in scenario["cli_commands"]:
            print(f"  {CYAN}>{RESET}  {cmd}")

        # Fix
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
# LIVE TROUBLESHOOTING CHECKS
# =============================================================================

def ios_abbrev(intf: str) -> str:
    """Return the IOS abbreviated interface name used in show output.

    IOS truncates interface names in show output to a short form
    (e.g. Ethernet0/0 → Et0/0, Serial2/0 → Se2/0).
    """
    abbrevs = [
        ("GigabitEthernet", "Gi"),
        ("FastEthernet",    "Fa"),
        ("Ethernet",        "Et"),
        ("Serial",          "Se"),
        ("Loopback",        "Lo"),
        ("Tunnel",          "Tu"),
        ("Vlan",            "Vl"),
    ]
    for full, short in abbrevs:
        if intf.startswith(full):
            return short + intf[len(full):]
    return intf


def check_neighbors(conn, device_name: str, device_data: dict, lf=None) -> str:
    """show ip ospf neighbor detail — checks for adjacency state issues.

    Returns: "PASS", "WARN", or "FAIL".
    """
    section("Neighbors — show ip ospf neighbor detail", lf)
    output = conn.cli(["show ip ospf neighbor detail"])["show ip ospf neighbor detail"]
    emit_raw(output, lf)

    result = "PASS"

    problem_states = ["EXSTART", "EXCHANGE", "INIT", "LOADING"]
    for state in problem_states:
        if state in output.upper():
            emit(warned(
                f"Neighbor in {state} state detected — "
                f"possible MTU mismatch, authentication failure, or area mismatch"
            ), lf)
            result = _worst(result, "WARN")

    if "FULL" in output.upper():
        emit(passed("At least one FULL adjacency confirmed"), lf)
    elif output.strip():
        emit(failed("No FULL adjacencies found — OSPF is not converged"), lf)
        result = _worst(result, "FAIL")
    else:
        emit(failed("No OSPF neighbors — check network statements, authentication, and interface state"), lf)
        result = _worst(result, "FAIL")

    return result


def _parse_ospf_intf_blocks(raw: str) -> dict:
    """Split 'show ip ospf interface' output into per-interface text blocks.

    IOS starts each interface section with a line like:
        Ethernet0/0 is up, line protocol is up
        Serial2/0 is up, line protocol is up

    Returns a dict keyed by full interface name:
        { "Ethernet0/0": "<block text>", "Serial2/0": "<block text>", ... }

    The block for each interface contains all lines up to (but not including)
    the next interface header line. Both the full name and the IOS abbreviated
    name (Et0/0, Se2/0) are used as keys so lookups work either way.
    """
    blocks: dict = {}
    current_name: str | None = None
    current_lines: list = []

    # IOS interface header: <IntfName> is <phys>, line protocol is <proto>
    hdr_re = re.compile(r'^(\S+)\s+is\s+\S+,\s+line protocol is', re.IGNORECASE)

    for line in raw.splitlines():
        m = hdr_re.match(line.strip())
        if m:
            if current_name:
                block_text = "\n".join(current_lines)
                blocks[current_name] = block_text
                blocks[ios_abbrev(current_name)] = block_text
            current_name = m.group(1)
            current_lines = [line]
        elif current_name:
            current_lines.append(line)

    if current_name:
        block_text = "\n".join(current_lines)
        blocks[current_name] = block_text
        blocks[ios_abbrev(current_name)] = block_text

    return blocks


def check_authentication(conn, device_name: str, device_data: dict, lf=None) -> str:
    """show ip ospf interface — per-interface authentication validation.

    Returns: "PASS", "WARN", "FAIL", or "INFO".
    """
    section("Authentication — show ip ospf interface", lf)
    output = conn.cli(["show ip ospf interface"])["show ip ospf interface"]
    emit_raw(output, lf)

    oob_interface = device_data.get("oob_interface", "")
    interfaces    = device_data.get("interfaces", {})
    result        = "PASS"
    auth_intfs    = 0

    intf_blocks = _parse_ospf_intf_blocks(output)

    for intf_name, intf in interfaces.items():
        if intf_name == oob_interface or "Loopback" in intf_name:
            continue
        if intf.get("shutdown", True) or not intf.get("ip", ""):
            continue

        auth = intf.get("ospf_authentication", {})
        auth_type = auth.get("type", "none")

        if auth_type == "none":
            continue

        auth_intfs += 1
        abbrev = ios_abbrev(intf_name)
        block  = intf_blocks.get(intf_name) or intf_blocks.get(abbrev)

        if block is None:
            emit(failed(
                f"{intf_name} — not found in 'show ip ospf interface' output — "
                f"interface may not be OSPF-active"
            ), lf)
            result = _worst(result, "FAIL")
            continue

        if auth_type == "plaintext" and "Simple password authentication" in block:
            emit(passed(f"{intf_name} — plain-text authentication confirmed"), lf)
        elif auth_type == "md5" and (
            "Message digest authentication" in block
            or "Cryptographic authentication enabled" in block
        ):
            if "Youngest key id" in block:
                emit(passed(f"{intf_name} — MD5 authentication confirmed"), lf)
            else:
                emit(warned(
                    f"{intf_name} — MD5 authentication enabled but no key configured "
                    f"(missing ip ospf message-digest-key)"
                ), lf)
                result = _worst(result, "WARN")
        else:
            emit(warned(
                f"{intf_name} — interface present but expected "
                f"{auth_type} authentication not confirmed in interface block"
            ), lf)
            result = _worst(result, "WARN")

    if auth_intfs == 0:
        emit(info("No authentication-configured interfaces found in YAML for this device"), lf)
        return "INFO"

    ospf_data  = device_data.get("ospf", {})
    area_auths = ospf_data.get("area_authentication", []) or []
    for entry in area_auths:
        area      = entry.get("area", "?")
        auth_type = entry.get("type", "none")
        emit(info(f"YAML: area {area} authentication {auth_type} — confirm in 'show ip ospf'"), lf)

    return result


def check_database(conn, device_name: str, device_data: dict, lf=None) -> str:
    """show ip ospf database — validates LSDB health and LSA counts.

    Returns: "PASS", "WARN", or "FAIL".
    """
    section("OSPF Database — show ip ospf database", lf)
    output = conn.cli(["show ip ospf database"])["show ip ospf database"]
    emit_raw(output, lf)

    ospf_data = device_data.get("ospf", {})
    router_id = ospf_data.get("router_id", "")
    result    = "PASS"

    if router_id and router_id in output:
        emit(passed(f"Router LSA for {router_id} present in LSDB"), lf)
    elif router_id:
        emit(failed(
            f"Router LSA for {router_id} NOT found in LSDB — "
            f"OSPF process may not be running or router-id mismatch"
        ), lf)
        result = _worst(result, "FAIL")

    area_range = ospf_data.get("area_range", []) or []
    if area_range:
        if "Summary Net Link States" in output:
            emit(passed("Summary Net LSAs (Type 3) present — inter-area summarization active"), lf)
        else:
            emit(warned(
                "area range configured in YAML but no Summary Net LSAs found — "
                "verify ABR is operational and area range is correct"
            ), lf)
            result = _worst(result, "WARN")

    if "Router Link States" in output:
        emit(passed("Router LSA section present in LSDB"), lf)
    else:
        emit(failed("No Router Link States section — LSDB may be empty"), lf)
        result = _worst(result, "FAIL")

    return result


def check_routes(conn, device_name: str, device_data: dict, lf=None) -> str:
    """show ip route ospf + show ip ospf border-routers — route table health.

    Returns: "PASS", "WARN", or "FAIL".
    """
    section("Route Table — show ip route ospf", lf)
    route_output = conn.cli(["show ip route ospf"])["show ip route ospf"]
    emit_raw(route_output, lf)

    result = "PASS"

    if not route_output.strip():
        emit(warned(
            "No OSPF routes in routing table — "
            "check neighbors, network statements, and area configuration"
        ), lf)
        result = _worst(result, "WARN")
    else:
        emit(passed("OSPF routes present in routing table"), lf)

    ospf_data = device_data.get("ospf", {})
    networks  = ospf_data.get("networks", []) or []
    areas     = set(net.get("area") for net in networks)

    if len(areas) == 1 and 0 not in areas:
        if "O IA" in route_output:
            emit(passed("Inter-area routes (O IA) present — connectivity to Area 0 confirmed"), lf)
        else:
            emit(warned(
                "No inter-area routes (O IA) found on Area 10 router — "
                "check ABR (R8) configuration and area range"
            ), lf)
            result = _worst(result, "WARN")

    section("Border Routers — show ip ospf border-routers", lf)
    br_output = conn.cli(["show ip ospf border-routers"])["show ip ospf border-routers"]
    emit_raw(br_output, lf)

    if br_output.strip():
        emit(passed("Border router entries present — ABR/ASBR reachability confirmed"), lf)
    else:
        emit(info("No border routers found — expected on pure Area 0 or Area 10 internal routers"), lf)

    return result


def check_process(conn, device_name: str, device_data: dict, lf=None) -> str:
    """show ip protocols — validates OSPF process ID, router-id, and networks.

    Returns: "PASS", "WARN", or "FAIL".
    """
    section("OSPF Process — show ip protocols", lf)
    output = conn.cli(["show ip protocols"])["show ip protocols"]
    emit_raw(output, lf)

    ospf_data  = device_data.get("ospf", {})
    process_id = str(ospf_data.get("process_id", ""))
    router_id  = ospf_data.get("router_id", "")
    result     = "PASS"

    if process_id and f"ospf {process_id}" in output.lower():
        emit(passed(f"OSPF process {process_id} confirmed running"), lf)
    elif process_id:
        emit(failed(
            f"OSPF process {process_id} NOT found in show ip protocols — "
            f"process may not be running"
        ), lf)
        result = _worst(result, "FAIL")

    if router_id and router_id in output:
        emit(passed(f"Router ID {router_id} confirmed"), lf)
    elif router_id:
        emit(failed(
            f"Router ID {router_id} NOT found — "
            f"router-id mismatch or OSPF process not running"
        ), lf)
        result = _worst(result, "FAIL")

    return result


LIVE_CHECKS = {
    "neighbors"     : check_neighbors,
    "authentication": check_authentication,
    "database"      : check_database,
    "routes"        : check_routes,
    "process"       : check_process,
}


# =============================================================================
# RESULT RANKING
# =============================================================================

_RANK = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}

def _worst(a: str, b: str) -> str:
    """Return the worse of two result tokens. FAIL > WARN > PASS/INFO."""
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


# =============================================================================
# DETAIL + SUMMARY
# =============================================================================

def _print_detail(detail: dict, lf=None) -> None:
    """Print a per-device list of all INFO/PASS/WARN/FAIL lines before the summary."""
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


def _print_summary(
    results: dict,
    checks_to_run: list,
    lf=None,
) -> None:
    """Print a per-device, per-check summary table."""
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

    # -------------------------------------------------------------------------
    # Argument parsing
    # -------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description=(
            "Module 03 — OSPF Classic Mode Troubleshooting\n"
            "Live troubleshooting checks and in-memory failure demonstrations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python troubleshoot_ospf_classic.py\n"
            "  python troubleshoot_ospf_classic.py --router R1 R8\n"
            "  python troubleshoot_ospf_classic.py --check neighbors authentication\n"
            "  python troubleshoot_ospf_classic.py --demo-failure auth-mismatch\n"
            "  python troubleshoot_ospf_classic.py --demo-failure auth-mismatch --router R2\n"
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

    # -------------------------------------------------------------------------
    # --list-checks
    # -------------------------------------------------------------------------
    if args.list_checks:
        print(f"\n{BOLD}Available live troubleshooting checks:{RESET}\n")
        descriptions = {
            "neighbors"     : "show ip ospf neighbor detail — adjacency state analysis",
            "authentication": "show ip ospf interface — per-interface auth type validation",
            "database"      : "show ip ospf database — LSDB health and LSA count validation",
            "routes"        : "show ip route ospf + show ip ospf border-routers — route table health",
            "process"       : "show ip protocols — OSPF process ID and router-id validation",
        }
        for name, desc in descriptions.items():
            print(f"  {CYAN}{name:<16}{RESET} {desc}")
        print()
        sys.exit(0)

    # -------------------------------------------------------------------------
    # --list-failures
    # -------------------------------------------------------------------------
    if args.list_failures:
        print(f"\n{BOLD}Available failure demonstration scenarios:{RESET}\n")
        for key, scenario in FAILURE_SCENARIOS.items():
            print(f"  {CYAN}{key:<20}{RESET} {scenario['title']}")
            print(f"  {DIM}{'':20}  {scenario['description'][:80]}...{RESET}\n")
        sys.exit(0)

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
        print("[ERROR] No valid target routers.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # --demo-failure mode
    # -------------------------------------------------------------------------
    if args.demo_failure:
        scenario_key = args.demo_failure

        if scenario_key not in FAILURE_SCENARIOS:
            print(f"[ERROR] Unknown failure scenario: '{scenario_key}'")
            print(f"        Available: {', '.join(FAILURE_SCENARIOS.keys())}")
            print(f"        Run with --list-failures to see descriptions.")
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

    # -------------------------------------------------------------------------
    # Live troubleshooting mode
    # -------------------------------------------------------------------------
    if args.check:
        invalid_checks = [c for c in args.check if c not in AVAILABLE_CHECKS]
        if invalid_checks:
            print(f"[ERROR] Unknown check(s): {invalid_checks}")
            print(f"        Valid options: {AVAILABLE_CHECKS}")
            sys.exit(1)
        checks_to_run = args.check
    else:
        checks_to_run = AVAILABLE_CHECKS

    print(f"\n{BOLD}NAMS26 — Module 03: OSPF Classic Mode Troubleshooting{RESET}")
    print(f"Targets : {', '.join(target_routers)}")
    print(f"Checks  : {', '.join(checks_to_run)}")

    # results: { "R1": {"neighbors": "PASS", "routes": "WARN", ...}, ... }
    global _result_collector
    results: dict = {}
    detail:  dict = {}

    lf = setup_logger()

    try:
        summary_lines = [
            f"\nNAMS26 — Module 03: OSPF Classic Mode Troubleshooting",
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
            _result_collector = []
            detail[device_name] = {
                "dns_name": dns_name,
                "oob_ip":   oob_ip,
                "messages": _result_collector,
            }

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
                for check_name in checks_to_run:
                    results[device_name][check_name] = LIVE_CHECKS[check_name](
                        device, device_name, device_data, lf)
            finally:
                device.close()
                lf and lf.write(f"  [INFO] Disconnected from {device_name}\n")

        _result_collector = None
        _print_detail(detail, lf)
        _print_summary(results, checks_to_run, lf)
        emit(f"\n{'=' * 60}\nTroubleshooting session complete.\n", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
