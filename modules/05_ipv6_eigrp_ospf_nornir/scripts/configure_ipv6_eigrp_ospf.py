#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 05
File     : modules/05_ipv6_eigrp_ospf_nornir/scripts/configure_ipv6_eigrp_ospf.py
Purpose  : Configure IPv6 EIGRP and OSPFv3 on all lab routers using Nornir.
           Renders per-device configs from Jinja2 templates + YAML data,
           then deploys in parallel via Nornir/Netmiko tasks.

Usage:
    python configure_ipv6_eigrp_ospf.py               # deploy to all routers
    python configure_ipv6_eigrp_ospf.py --dry-run      # render configs only, no SSH
    python configure_ipv6_eigrp_ospf.py --router R1 R6 # deploy to specific routers

Workflow:
    YAML data → Jinja2 template → rendered config → Nornir/Netmiko parallel push

Pre-flight requirement:
    Run utils/clear_known_hosts.sh and utils/init_ssh.py before executing
    this script after every EVE-NG lab reboot.
"""

import ipaddress
import os
import shutil
import sys
import tempfile
import yaml
import argparse
from jinja2 import Environment, FileSystemLoader
from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir_netmiko.tasks import netmiko_send_config, netmiko_send_command
from nornir_utils.plugins.functions import print_result

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
CONFIG_DIR   = os.path.join(MODULE_DIR, "configs")

TEMPLATE_FILE = "ipv6_eigrp_ospf.j2"


# =============================================================================
# ANSI COLOR OUTPUT
# =============================================================================

def passed(msg: str) -> None: print(f"\033[92m  [PASS] {msg}\033[0m")
def failed(msg: str) -> None: print(f"\033[91m  [FAIL] {msg}\033[0m")
def warned(msg: str) -> None: print(f"\033[93m  [WARN] {msg}\033[0m")
def info(msg: str)   -> None: print(f"\033[96m  [INFO] {msg}\033[0m")


# =============================================================================
# JINJA2 FILTERS
# =============================================================================

def _ipv4_addr(cidr: str) -> str:
    """Extract host address from a CIDR string (e.g. '1.1.1.1/32' → '1.1.1.1')."""
    return str(ipaddress.ip_interface(cidr).ip)


def _ipv4_mask(cidr: str) -> str:
    """Extract subnet mask from a CIDR string (e.g. '1.1.1.1/32' → '255.255.255.255')."""
    return str(ipaddress.ip_interface(cidr).network.netmask)


def _build_jinja2_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["ipv4_addr"] = _ipv4_addr
    env.filters["ipv4_mask"] = _ipv4_mask
    return env


# =============================================================================
# NORNIR INVENTORY
# =============================================================================

def _write_nornir_inventory(devices: dict, tmp_dir: str) -> tuple[str, str, str]:
    """Write Nornir SimpleInventory YAML files to tmp_dir. Returns (hosts, groups, defaults) paths.

    Nornir's SimpleInventory plugin requires three YAML files on disk:
      hosts.yaml    — one entry per device with connection params and host-level data
      groups.yaml   — group-level defaults shared across hosts (empty here; no groups used)
      defaults.yaml — global defaults applied to every host (empty here; per-host creds used)

    The full YAML device dict is embedded in the 'data' key of each host entry so that
    configure_task can access all interface, routing, and credential fields via task.host.data.
    """
    hosts = {}
    for name, dev in devices.items():
        creds = dev.get("credentials", {})
        hosts[name] = {
            "hostname": dev["dns_name"],
            "platform": "cisco_ios",
            "username": creds.get("username", ""),
            "password": creds.get("password", ""),
            # Passes the complete device dict into Nornir's host data store.
            # Accessible inside tasks as task.host.data["interfaces"], etc.
            "data": dev,
        }

    hosts_file    = os.path.join(tmp_dir, "hosts.yaml")
    groups_file   = os.path.join(tmp_dir, "groups.yaml")
    defaults_file = os.path.join(tmp_dir, "defaults.yaml")

    with open(hosts_file, "w") as fh:
        yaml.dump(hosts, fh, default_flow_style=False)
    with open(groups_file, "w") as fh:
        # Empty dict — no shared group config for this module
        yaml.dump({}, fh)
    with open(defaults_file, "w") as fh:
        # Empty dict — credentials are per-host, not global defaults
        yaml.dump({}, fh)

    return hosts_file, groups_file, defaults_file


# =============================================================================
# NORNIR TASK
# =============================================================================

def configure_task(
    task: Task,
    template_env: Environment,
    config_dir: str,
    dry_run: bool,
) -> Result:
    """Render Jinja2 config per host and push via Netmiko (or write only for --dry-run)."""
    dev = dict(task.host.data)
    template = template_env.get_template(TEMPLATE_FILE)
    rendered = template.render(device=dev)

    config_path = os.path.join(config_dir, f"{task.host.name}_ipv6_eigrp_ospf.cfg")
    with open(config_path, "w") as fh:
        fh.write(rendered)

    if dry_run:
        return Result(host=task.host, result=f"[DRY-RUN] Config written to {config_path}", changed=True)

    commands = [
        line.rstrip()
        for line in rendered.splitlines()
        if line.strip() and not line.strip().startswith("!")
    ]

    task.run(task=netmiko_send_config, config_commands=commands)
    task.run(task=netmiko_send_command, command_string="write memory")

    return Result(host=task.host, result=f"Configured {task.host.name}", changed=True)


# =============================================================================
# ROUTER RESOLUTION
# =============================================================================

def resolve_router(token: str, devices: dict) -> str | None:
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


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "NAMS26 Module 05 — Configure IPv6 EIGRP/OSPFv3 via Nornir\n"
            "Generates and pushes configs for all 9 routers in parallel."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python configure_ipv6_eigrp_ospf.py\n"
            "  python configure_ipv6_eigrp_ospf.py --dry-run\n"
            "  python configure_ipv6_eigrp_ospf.py --router R1 R6\n"
            "  python configure_ipv6_eigrp_ospf.py --dry-run --router R1\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render configs to configs/ without connecting to routers.",
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help=(
            "Target one or more routers by hostname (e.g. --router R1 R6). "
            "Accepts: R1, r1, r1.lab, R1.lab. "
            "Defaults to all devices in YAML."
        ),
    )
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Load YAML
    # -------------------------------------------------------------------------
    if not os.path.isfile(DATA_FILE):
        failed(f"Data file not found: {DATA_FILE}")
        sys.exit(1)

    try:
        with open(DATA_FILE, "r") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        failed(f"Failed to parse YAML: {exc}")
        sys.exit(1)

    devices       = data.get("devices", {})
    default_creds = data.get("default_credentials", {})

    if not devices:
        failed("No devices found in YAML.")
        sys.exit(1)

    for dev_data in devices.values():
        if not dev_data.get("credentials"):
            dev_data["credentials"] = default_creds

    # -------------------------------------------------------------------------
    # Resolve target routers
    # -------------------------------------------------------------------------
    if args.router:
        target_routers = []
        for token in args.router:
            resolved = resolve_router(token, devices)
            if resolved:
                target_routers.append(resolved)
            else:
                warned(f"Router not found in YAML (skipped): '{token}'")
    else:
        target_routers = list(devices.keys())

    if not target_routers:
        failed("No valid target routers to process.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Jinja2 environment
    # -------------------------------------------------------------------------
    try:
        template_env = _build_jinja2_env()
        template_env.get_template(TEMPLATE_FILE)
    except Exception as exc:
        failed(f"Failed to load template '{TEMPLATE_FILE}': {exc}")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Output directories
    # -------------------------------------------------------------------------
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    mode_label = "DRY-RUN" if args.dry_run else "DEPLOY"
    print(f"\nNAMS26 — Module 05: IPv6 EIGRP/OSPFv3 / Nornir [{mode_label}]")
    print(f"Targets : {', '.join(target_routers)}")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # Write temp Nornir inventory, run tasks, clean up
    # -------------------------------------------------------------------------
    # tempfile.mkdtemp() creates a uniquely named empty directory in the OS temp
    # folder (e.g. C:\Users\tjehn\AppData\Local\Temp\nornir_m05_XXXXXXXX).
    # The prefix makes the directory identifiable in temp if something goes wrong.
    # It is always deleted in the finally block regardless of success or failure.
    tmp_dir = tempfile.mkdtemp(prefix="nornir_m05_")
    try:
        target_devices = {k: v for k, v in devices.items() if k in target_routers}
        hosts_file, groups_file, defaults_file = _write_nornir_inventory(
            target_devices, tmp_dir
        )

        # InitNornir builds the Nornir runner object from the three inventory files.
        # SimpleInventory is Nornir's built-in file-based inventory plugin — no
        # external database or API needed; inventory lives entirely in the YAML files
        # written by _write_nornir_inventory() above.
        #
        # logging={"enabled": False} — suppresses Nornir's own nornir.log file.
        # Default behavior writes a nornir.log to the current working directory,
        # which clutters the project root. Session output is already printed to the
        # terminal via print_result(); the log file adds no value here.
        nr = InitNornir(
            inventory={
                "plugin": "SimpleInventory",
                "options": {
                    "host_file": hosts_file,
                    "group_file": groups_file,
                    "defaults_file": defaults_file,
                },
            },
            logging={"enabled": False},
        )

        # nr.run() dispatches configure_task to every host in the inventory in
        # parallel. Nornir uses a ThreadPoolExecutor internally; the default
        # num_workers is 100 (effectively one thread per host for a 9-router lab).
        # Extra keyword arguments (template_env, config_dir, dry_run) are forwarded
        # to configure_task as **kwargs on every thread — each host receives the
        # same shared objects. The returned AggregatedResult maps host names to
        # MultiResult objects (one per subtask executed inside configure_task).
        result = nr.run(
            task=configure_task,
            template_env=template_env,
            config_dir=CONFIG_DIR,
            dry_run=args.dry_run,
        )

        # print_result() walks the AggregatedResult tree and prints each host's
        # outcome. It only prints the result text when changed=True — that is why
        # configure_task explicitly sets changed=True on both return paths.
        print_result(result)

        failed_hosts = [h for h, r in result.items() if r.failed]
        if failed_hosts:
            failed(f"Failed hosts: {', '.join(failed_hosts)}")
            sys.exit(1)

    finally:
        # Always remove the temp inventory directory. ignore_errors=True prevents
        # a cleanup failure from masking the real result (success or failure) of the
        # configure run that preceded it.
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\n" + "=" * 60)
    passed(f"Done. Configs saved to: {CONFIG_DIR}")
    if not args.dry_run:
        info(f"Session logs saved to : {LOG_DIR}")


if __name__ == "__main__":
    main()
