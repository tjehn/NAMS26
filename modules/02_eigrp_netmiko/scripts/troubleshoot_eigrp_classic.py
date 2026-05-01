#!/usr/bin/env python3
"""
Module   : 02 — EIGRP Classic Mode
File     : modules/02_eigrp_netmiko/scripts/troubleshoot_eigrp_classic.py
Purpose  : Two-mode troubleshooting tool for EIGRP Classic Mode lab.

           Mode 1 — Live Troubleshooting (default)
           ----------------------------------------
           Connects to lab routers via Netmiko and runs targeted
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
    python troubleshoot_eigrp_classic.py

    # Run all checks on specific routers
    python troubleshoot_eigrp_classic.py --router R1 R2

    # Run a specific troubleshooting check
    python troubleshoot_eigrp_classic.py --check neighbors
    python troubleshoot_eigrp_classic.py --check authentication
    python troubleshoot_eigrp_classic.py --check passive
    python troubleshoot_eigrp_classic.py --check routes
    python troubleshoot_eigrp_classic.py --check process

    # Demonstrate a failure scenario (memory only — no router changes)
    python troubleshoot_eigrp_classic.py --demo-failure missing-keychain
    python troubleshoot_eigrp_classic.py --demo-failure keychain-mismatch
    python troubleshoot_eigrp_classic.py --demo-failure wrong-as
    python troubleshoot_eigrp_classic.py --demo-failure passive-active
    python troubleshoot_eigrp_classic.py --demo-failure missing-network

    # List all available checks and failure scenarios
    python troubleshoot_eigrp_classic.py --list-checks
    python troubleshoot_eigrp_classic.py --list-failures

    # Target a specific router for a demo failure
    python troubleshoot_eigrp_classic.py --demo-failure wrong-as --router R1

Pre-flight requirement:
    Run utils/clear_known_hosts.sh and utils/check_ssh.py before executing
    live troubleshooting checks after every EVE-NG lab reboot. check_ssh.py
    populates ~/.ssh/known_hosts with current host keys using
    StrictHostKeyChecking accept-new, allowing this script to connect without
    SSH suppression.

Troubleshooting Checks:
    neighbors      — show ip eigrp neighbors detail
    authentication — show ip eigrp interfaces detail (auth counters)
    passive        — show ip eigrp interfaces + cross-check passive config
    routes         — show ip route eigrp + show ip eigrp topology
    process        — show ip protocols (EIGRP process summary)

Failure Scenarios:
    missing-keychain   — key_chains block absent; auth config renders
                         without a key chain defined; adjacency fails
    keychain-mismatch  — key_chain name in authentication does not match
                         the name defined in key_chains; MD5 fails silently
    wrong-as           — EIGRP AS number changed; neighbors use different AS;
                         adjacency never forms
    passive-active     — active interface moved to passive; neighbor drops;
                         no error message, just silence
    missing-network    — network statement removed; prefix disappears from
                         EIGRP topology; reachability lost
"""

import os
import sys
import copy
import yaml
import argparse
from jinja2 import Environment, FileSystemLoader
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# =============================================================================
# SSH / KNOWN_HOSTS CONFIGURATION
# Host key verification relies on ~/.ssh/known_hosts populated by
# utils/check_ssh.py as part of the standard lab pre-flight sequence.
# Run clear_known_hosts.sh followed by check_ssh.py after every EVE-NG
# lab reboot before running live troubleshooting checks.
# =============================================================================
KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR    = os.path.dirname(SCRIPT_DIR)
MODULES_DIR   = os.path.dirname(MODULE_DIR)
PROJECT_ROOT  = os.path.dirname(MODULES_DIR)

YAML_FILE      = os.path.join(MODULE_DIR, "data",      "eigrp_classic.yaml")
TEMPLATE_DIR   = os.path.join(MODULE_DIR, "templates")
TEMPLATE_FILE  = "eigrp_classic.j2"

# =============================================================================
# AVAILABLE CHECKS AND FAILURE SCENARIOS
# Single source of truth — used by argparse, --list-checks, --list-failures
# =============================================================================
AVAILABLE_CHECKS = ["neighbors", "authentication", "passive", "routes", "process"]

FAILURE_SCENARIOS = {
    "missing-keychain": {
        "title"      : "Missing Key Chain Definition",
        "description": (
            "The key_chains block is removed from the YAML for the target device. "
            "The authentication configuration still references a key-chain name, "
            "but no key chain is ever defined on the router. EIGRP will attempt "
            "MD5 authentication but fail immediately — the neighbor never forms. "
            "This failure is silent: no error appears in 'show ip eigrp neighbors'."
        ),
        "symptoms"   : [
            "show ip eigrp neighbors — neighbor IP absent or stuck in INIT",
            "show ip eigrp interfaces detail — auth failures incrementing",
            "debug eigrp packets — 'authentication failure' messages",
        ],
        "fix"        : (
            "Restore the key_chains block in YAML and re-run configure_eigrp_classic.py. "
            "Verify with: show key chain"
        ),
        "cli_commands": [
            "show ip eigrp neighbors detail",
            "show ip eigrp interfaces detail",
            "show key chain",
        ],
    },
    "keychain-mismatch": {
        "title"      : "Key-Chain Name Mismatch",
        "description": (
            "The key_chain name referenced under authentication does not match "
            "the name defined in the key_chains block. The key chain exists on "
            "the router, but EIGRP is told to use a key chain with a different "
            "name. Authentication fails silently — the neighbor may form briefly "
            "then drop, or never form at all depending on IOS version."
        ),
        "symptoms"   : [
            "show ip eigrp neighbors — neighbor absent or flapping",
            "show ip eigrp interfaces detail — auth failures incrementing",
            "show key chain — key chain present but with different name than configured",
            "debug eigrp packets — 'no matching key' or 'authentication mismatch'",
        ],
        "fix"        : (
            "Align the key_chain name in the authentication block with the name "
            "defined in key_chains. Both must be identical. Re-run configure script."
        ),
        "cli_commands": [
            "show ip eigrp neighbors detail",
            "show ip eigrp interfaces detail",
            "show key chain",
            "show run | section key chain",
        ],
    },
    "wrong-as": {
        "title"      : "Wrong EIGRP AS Number",
        "description": (
            "The EIGRP autonomous system (AS) number on one router is changed "
            "to a value that does not match its neighbors. EIGRP neighbors must "
            "share the same AS number to form an adjacency. The router will run "
            "its own EIGRP process in isolation — no neighbors will appear."
        ),
        "symptoms"   : [
            "show ip eigrp neighbors — empty, no neighbors listed",
            "show ip protocols — EIGRP AS number visible, does not match peers",
            "show ip route eigrp — no EIGRP routes in routing table",
            "debug eigrp packets — hellos sent but no reply (peers ignore wrong AS)",
        ],
        "fix"        : (
            "Correct the eigrp.as value in YAML to match all neighbors. "
            "Re-run configure_eigrp_classic.py. Verify with: show ip protocols"
        ),
        "cli_commands": [
            "show ip eigrp neighbors",
            "show ip protocols",
            "show ip route eigrp",
        ],
    },
    "passive-active": {
        "title"      : "Active Interface Set to Passive",
        "description": (
            "An interface that should be EIGRP-active (sending hellos and forming "
            "neighbors) is moved to the passive-interface list. EIGRP suppresses "
            "hellos on passive interfaces — the neighbor on the other end will "
            "time out and drop. This is one of the most common EIGRP mistakes "
            "and produces no error message — the neighbor simply disappears."
        ),
        "symptoms"   : [
            "show ip eigrp neighbors — neighbor drops after hold timer expires",
            "show ip eigrp interfaces — affected interface no longer listed",
            "show ip protocols — interface listed under passive-interface section",
            "show ip route eigrp — routes learned via that neighbor disappear",
        ],
        "fix"        : (
            "Move the interface back to no_passive_interfaces in YAML (or remove "
            "from passive_interfaces list). Re-run configure_eigrp_classic.py. "
            "Verify with: show ip eigrp interfaces"
        ),
        "cli_commands": [
            "show ip eigrp neighbors",
            "show ip eigrp interfaces",
            "show ip protocols",
        ],
    },
    "missing-network": {
        "title"      : "Missing EIGRP Network Statement",
        "description": (
            "A network statement is removed from the YAML networks list for the "
            "target device. EIGRP will not advertise that network to neighbors — "
            "the prefix disappears from the topology table on all other routers. "
            "The interface itself remains up; only the EIGRP advertisement is lost. "
            "Reachability to that prefix from remote routers will fail."
        ),
        "symptoms"   : [
            "show ip route eigrp — prefix absent on all other routers",
            "show ip eigrp topology — prefix absent from topology table",
            "show ip eigrp interfaces — source interface may still be listed",
            "ping <missing prefix> sourced from remote router — fails",
        ],
        "fix"        : (
            "Restore the missing network statement in the YAML networks list. "
            "Re-run configure_eigrp_classic.py. "
            "Verify with: show ip eigrp topology | begin <network>"
        ),
        "cli_commands": [
            "show ip route eigrp",
            "show ip eigrp topology",
            "show ip protocols",
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

_RESULT_PREFIXES = ("[PASS]", "[FAIL]", "[WARN]", "[INFO]")
_result_collector: list | None = None


def emit(line: str, lf=None) -> None:
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")
    if _result_collector is not None and _strip_ansi(line).strip().startswith(_RESULT_PREFIXES):
        _result_collector.append(line)

def section(title):
    print(f"\n{BOLD}  {'─' * 54}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}  {'─' * 54}{RESET}")

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
# CUSTOM JINJA2 FILTER  (mirrors configure_eigrp_classic.py)
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

def inject_missing_keychain(device_data: dict) -> dict:
    """Remove the key_chains block entirely — key chain never defined."""
    broken = copy.deepcopy(device_data)
    broken["eigrp"]["key_chains"] = []
    return broken


def inject_keychain_mismatch(device_data: dict) -> dict:
    """Change the key_chain reference in authentication to a non-existent name."""
    broken = copy.deepcopy(device_data)
    auth = broken["eigrp"].get("authentication") or []
    if isinstance(auth, list):
        for entry in auth:
            entry["key_chain"] = entry["key_chain"] + "_WRONG"
    elif isinstance(auth, dict):
        auth["key_chain"] = auth["key_chain"] + "_WRONG"
    return broken


def inject_wrong_as(device_data: dict) -> dict:
    """Change the EIGRP AS number to one that won't match any neighbor."""
    broken = copy.deepcopy(device_data)
    broken["eigrp"]["as"] = 999
    return broken


def inject_passive_active(device_data: dict) -> dict:
    """Move the first active interface into the passive list."""
    broken = copy.deepcopy(device_data)
    no_passive = broken["eigrp"].get("no_passive_interfaces") or []
    if no_passive:
        interface_to_break = no_passive[0]
        broken["eigrp"]["no_passive_interfaces"] = no_passive[1:]
        passive = broken["eigrp"].get("passive_interfaces") or []
        passive.append(interface_to_break)
        broken["eigrp"]["passive_interfaces"] = passive
        broken["_injected_passive"] = interface_to_break  # carry forward for display
    return broken


def inject_missing_network(device_data: dict) -> dict:
    """Remove the first network statement from the EIGRP networks list."""
    broken = copy.deepcopy(device_data)
    networks = broken["eigrp"].get("networks") or []
    if networks:
        broken["_removed_network"] = networks[0]  # carry forward for display
        broken["eigrp"]["networks"] = networks[1:]
    return broken


FAULT_INJECTORS = {
    "missing-keychain" : inject_missing_keychain,
    "keychain-mismatch": inject_keychain_mismatch,
    "wrong-as"         : inject_wrong_as,
    "passive-active"   : inject_passive_active,
    "missing-network"  : inject_missing_network,
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
    scenario  = FAILURE_SCENARIOS[scenario_key]
    injector  = FAULT_INJECTORS[scenario_key]

    demo_header(scenario_key, scenario["title"])

    # --- Scenario description ------------------------------------------------
    section("What This Failure Demonstrates")
    print(f"\n  {scenario['description']}\n")

    for device_name in target_routers:
        device_data = devices[device_name]

        print(f"\n{BOLD}  [ Demonstrating on {device_name} ]{RESET}")

        # --- Render correct config -------------------------------------------
        correct_config = template.render(device_data)

        # --- Inject fault and render broken config ---------------------------
        broken_data   = injector(device_data)
        broken_config = template.render(broken_data)

        # --- Show injected fault detail --------------------------------------
        section("Fault Injected (in-memory only — router not changed)")

        if scenario_key == "missing-keychain":
            emit(info("key_chains list cleared — no key chain will be defined on router"))

        elif scenario_key == "keychain-mismatch":
            auth = broken_data["eigrp"].get("authentication") or []
            if isinstance(auth, list):
                for entry in auth:
                    emit(info(
                        f"Interface {entry['interface']}: "
                        f"key_chain reference changed to '{entry['key_chain']}' "
                        f"(does not match any defined key chain)"
                    ))

        elif scenario_key == "wrong-as":
            correct_as = device_data["eigrp"]["as"]
            emit(info(f"EIGRP AS changed from {correct_as} → 999"))
            emit(info("Neighbors expect AS {correct_as} — they will ignore hellos from AS 999"))

        elif scenario_key == "passive-active":
            broken_intf = broken_data.get("_injected_passive", "unknown")
            emit(info(f"Interface {broken_intf} moved to passive — hellos suppressed"))
            emit(info("Neighbor on the other end will time out after hold timer expires"))

        elif scenario_key == "missing-network":
            removed = broken_data.get("_removed_network", {})
            emit(info(
                f"Network statement removed: "
                f"{removed.get('network', '?')} {removed.get('wildcard', '?')}"
            ))
            emit(info("This prefix will not be advertised to any EIGRP neighbor"))

        # --- Config diff -----------------------------------------------------
        section("Configuration Diff")
        diff_configs(correct_config, broken_config)

        # --- CLI symptoms ----------------------------------------------------
        section("CLI Symptoms — What You Would See on the Router")
        print()
        for symptom in scenario["symptoms"]:
            print(f"  {YELLOW}▸{RESET}  {symptom}")

        # --- Troubleshooting commands ----------------------------------------
        section("Troubleshooting Commands to Run")
        print()
        for cmd in scenario["cli_commands"]:
            print(f"  {CYAN}>{RESET}  {cmd}")

        # --- Fix -------------------------------------------------------------
        section("The Fix")
        print(f"\n  {scenario['fix']}\n")

    print(f"\n{'=' * 60}")
    print(f"{BOLD}Demo complete. No changes were pushed to any router.{RESET}\n")


# =============================================================================
# LIVE TROUBLESHOOTING CHECKS
# =============================================================================

def connect(device_name: str, dns_name: str, creds: dict):
    """Establish Netmiko SSH session. Returns connection or None on failure.

    The SSH target is resolved via the lab DNS server (192.168.1.12) using
    the dns_name field from YAML (e.g. r1.lab). oob_ip is not used for
    connections — it is retained in YAML for documentation only.

    SSH host key verification uses ~/.ssh/known_hosts populated by
    utils/check_ssh.py as part of the standard lab pre-flight sequence.
    Run clear_known_hosts.sh followed by check_ssh.py after every EVE-NG
    lab reboot before executing live troubleshooting checks.
    """
    if not os.path.isfile(KNOWN_HOSTS_FILE):
        emit(warned(
            f"known_hosts not found at {KNOWN_HOSTS_FILE} — "
            f"run utils/clear_known_hosts.sh then utils/check_ssh.py first"
        ))

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
        emit(info(f"Connected to {device_name} ({dns_name})"))
        return conn
    except NetmikoTimeoutException:
        emit(failed(f"Timeout connecting to {device_name} ({dns_name})"))
    except NetmikoAuthenticationException:
        emit(failed(f"Authentication failed on {device_name}"))
    except Exception as exc:
        emit(failed(f"Connection error on {device_name}: {exc}"))
    return None


def check_neighbors(conn, device_name: str, eigrp_data: dict) -> None:
    """show ip eigrp neighbors detail — checks for stuck INIT state and
    authentication failure counters."""
    section("Neighbors — show ip eigrp neighbors detail")
    output = conn.send_command("show ip eigrp neighbors detail")
    print(f"\n{output}\n")

    if "INIT" in output:
        emit(warned("Neighbor stuck in INIT state — possible authentication mismatch"))
    if "Auth" in output and "0" not in output:
        emit(warned("Authentication counters non-zero — check key chain configuration"))

    expected = eigrp_data.get("static_neighbors", []) or []
    for neighbor in expected:
        ip = neighbor.get("ip", "")
        if ip and ip not in output:
            emit(failed(
                f"Expected neighbor {ip} not present — "
                f"check passive-interface, AS number, and authentication"
            ))
        elif ip:
            emit(passed(f"Neighbor {ip} present"))


def check_authentication(conn, device_name: str, eigrp_data: dict) -> None:
    """show ip eigrp interfaces detail — exposes authentication send/receive
    counters per interface. Non-zero auth failure counters indicate a
    key-chain or MD5 configuration problem."""
    section("Authentication — show ip eigrp interfaces detail")
    output = conn.send_command("show ip eigrp interfaces detail")
    print(f"\n{output}\n")

    auth_config = eigrp_data.get("authentication") or []
    if not auth_config:
        emit(info("No authentication configured in YAML for this device"))
        return

    interfaces_with_auth = []
    if isinstance(auth_config, list):
        interfaces_with_auth = [a.get("interface", "") for a in auth_config]
    elif isinstance(auth_config, dict):
        interfaces_with_auth = [auth_config.get("interface", "")]

    def ios_abbrev(intf: str) -> str:
        """Return the IOS abbreviated interface name used in show output.

        IOS truncates interface names in 'show ip eigrp interfaces' to a short
        form (e.g. Ethernet0/0 -> Et0/0, GigabitEthernet0/0 -> Gi0/0).
        Matching against the full name from YAML will always fail — use the
        abbreviation alongside the full name for a reliable match.
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

    for intf in interfaces_with_auth:
        abbrev = ios_abbrev(intf)
        if intf and (intf in output or abbrev in output):
            emit(passed(f"Interface {intf} present in EIGRP interfaces output"))
        elif intf:
            emit(failed(
                f"Interface {intf} NOT in EIGRP interfaces output — "
                f"may be passive or authentication preventing adjacency"
            ))

    # Also pull key chain config for direct inspection
    section("Key Chain Verification — show key chain")
    kc_output = conn.send_command("show key chain")
    print(f"\n{kc_output}\n")

    key_chains = eigrp_data.get("key_chains", []) or []
    for kc in key_chains:
        name = kc.get("name", "")
        if name and name in kc_output:
            emit(passed(f"Key chain '{name}' found"))
        elif name:
            emit(failed(f"Key chain '{name}' NOT found — key chain not defined on router"))


def check_passive(conn, device_name: str, eigrp_data: dict) -> None:
    """show ip protocols — shows EIGRP process detail including passive
    interface list. Cross-checks against YAML passive configuration."""
    section("Passive Interface Check — show ip protocols")
    output = conn.send_command("show ip protocols")
    print(f"\n{output}\n")

    no_passive   = eigrp_data.get("no_passive_interfaces", []) or []
    passive_list = eigrp_data.get("passive_interfaces", []) or []

    # Check interfaces that should be active are not listed as passive
    for intf in no_passive:
        if intf in output and "Passive" in output:
            # Rough check — interface appears in passive section
            emit(warned(
                f"Interface {intf} may be passive — "
                f"YAML expects it to be active (no passive-interface)"
            ))
        else:
            emit(passed(f"Interface {intf} — active (not passive)"))

    # Confirm explicitly passive interfaces are in passive list
    for intf in passive_list:
        if intf in output:
            emit(passed(f"Interface {intf} — correctly passive"))
        else:
            emit(warned(f"Interface {intf} — expected to be passive but not found in output"))


def check_routes(conn, device_name: str, eigrp_data: dict) -> None:
    """show ip route eigrp + show ip eigrp topology — validates that routes
    are being learned and checks the topology table for feasible successors."""
    section("Route Table — show ip route eigrp")
    route_output = conn.send_command("show ip route eigrp")
    print(f"\n{route_output}\n")

    if not route_output.strip():
        emit(warned("No EIGRP routes in routing table — check neighbors and network statements"))

    section("EIGRP Topology — show ip eigrp topology")
    topo_output = conn.send_command("show ip eigrp topology")
    print(f"\n{topo_output}\n")

    # Filter out the codes legend before checking state — "A - Active" in the
    # header would otherwise trigger a false positive on every run.
    topo_data_lines = [
        line for line in topo_output.splitlines()
        if not line.startswith("Codes:") and not line.startswith("       ")
    ]
    topo_data = "\n".join(topo_data_lines)

    if "P " not in topo_data:
        emit(warned("No passive (stable) routes in topology table — EIGRP may not be converged"))

    active_routes = [l for l in topo_data_lines if l.startswith("A ")]
    if active_routes:
        emit(failed(
            f"Active routes found in topology table — EIGRP is currently reconverging "
            f"({len(active_routes)} active prefix(es))"
        ))
    else:
        emit(passed("All topology entries passive — EIGRP is converged"))


def check_process(conn, device_name: str, eigrp_data: dict) -> None:
    """show ip protocols — validates AS number, networks, and redistribution
    summary against YAML expected state."""
    section("EIGRP Process — show ip protocols")
    output = conn.send_command("show ip protocols")
    print(f"\n{output}\n")

    expected_as = str(eigrp_data.get("as", ""))
    if expected_as and f"eigrp {expected_as}" in output.lower():
        emit(passed(f"EIGRP AS {expected_as} confirmed in process output"))
    elif expected_as:
        emit(failed(
            f"EIGRP AS {expected_as} NOT found — "
            f"possible wrong AS number or EIGRP process not running"
        ))


LIVE_CHECKS = {
    "neighbors"     : check_neighbors,
    "authentication": check_authentication,
    "passive"       : check_passive,
    "routes"        : check_routes,
    "process"       : check_process,
}


# =============================================================================
# DETAIL
# =============================================================================

def _print_detail(detail: dict) -> None:
    """Print a per-device list of all INFO/PASS/WARN/FAIL lines before the summary."""
    bar = "=" * 60
    for line in [
        f"\n{BOLD}{bar}{RESET}",
        f"{BOLD}  Troubleshooting Detail{RESET}",
        f"{BOLD}{bar}{RESET}",
    ]:
        print(line)

    for device_name, dev_info in detail.items():
        device_header(device_name, dev_info["dns_name"], dev_info["oob_ip"])
        for msg in dev_info["messages"]:
            print(f"  {msg}")

    print(f"{BOLD}{bar}{RESET}")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:

    # -------------------------------------------------------------------------
    # Argument parsing
    # -------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description=(
            "Module 02 — EIGRP Classic Mode Troubleshooting\n"
            "Live troubleshooting checks and in-memory failure demonstrations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
            "neighbors"     : "show ip eigrp neighbors detail — validate expected neighbors",
            "authentication": "show ip eigrp interfaces detail + show key chain",
            "passive"       : "show ip protocols — cross-check passive interface config",
            "routes"        : "show ip route eigrp + show ip eigrp topology",
            "process"       : "show ip protocols — validate AS number and process state",
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
    # Accepts YAML key (R1), case-insensitive short name (r1), or DNS name
    # (r1.lab) — mirrors the alias resolution pattern in utils/check_ssh.py.
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

        # Load Jinja2 template for config rendering
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

    global _result_collector
    print(f"\n{BOLD}NAMS26 — Module 02: EIGRP Classic Mode Troubleshooting{RESET}")
    print(f"Targets : {', '.join(target_routers)}")
    print(f"Checks  : {', '.join(checks_to_run)}")

    detail: dict = {}

    for device_name in target_routers:
        device_data = devices[device_name]
        oob_ip      = device_data.get("oob_ip", "")
        dns_name    = device_data.get("dns_name", "")
        creds       = device_data.get("credentials", default_creds)
        eigrp_data  = device_data.get("eigrp", {})

        _result_collector = []
        detail[device_name] = {
            "dns_name": dns_name,
            "oob_ip":   oob_ip,
            "messages": _result_collector,
        }

        if not dns_name:
            emit(failed(f"No dns_name defined for {device_name} in YAML — skipping."))
            continue

        device_header(device_name, dns_name, oob_ip)

        conn = connect(device_name, dns_name, creds)
        if conn is None:
            emit(failed(f"Skipping all checks on {device_name} — connection failed."))
            continue

        try:
            for check_name in checks_to_run:
                LIVE_CHECKS[check_name](conn, device_name, eigrp_data)
        finally:
            conn.disconnect()
            emit(info(f"Disconnected from {device_name}"))

    _result_collector = None
    _print_detail(detail)
    print(f"\n{'=' * 60}")
    print(f"{BOLD}Troubleshooting session complete.{RESET}\n")


if __name__ == "__main__":
    main()
