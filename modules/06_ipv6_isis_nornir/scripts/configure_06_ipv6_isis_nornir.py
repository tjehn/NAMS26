#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 06
File     : modules/06_ipv6_isis_nornir/scripts/configure_06_ipv6_isis_nornir.py
Purpose  : Configure IPv6 IS-IS Named Mode on all lab routers using Nornir.

           Pre-renders all device configs from YAML + Jinja2 templates before
           opening any SSH connections, then deploys in four sequential phases
           using nr.filter() to enforce IS-IS convergence order:

             Phase 1 — backbone (BB-1, BB-2)
             Phase 2 — ABRs    (ABR-1, ABR-2, ABR-3)
             Phase 3 — leaves + ASBR (BR-1..5, ASBR-1)
             Phase 4 — OSPF-only stub (OSPF-1)

           The phased nr.filter() pattern is the core Nornir teaching point
           for Module 06 — do not collapse into a single nr.run().

Usage:
    python scripts/configure_06_ipv6_isis_nornir.py --dry-run
    python scripts/configure_06_ipv6_isis_nornir.py
    python scripts/configure_06_ipv6_isis_nornir.py --router BB-1 BB-2

Pre-flight:
    Run utils/clear_known_hosts.sh then utils/init_ssh.py after every
    EVE-NG lab reboot before executing this script.
"""

import ipaddress
import os
import sys
import yaml
import argparse
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from nornir.core import Nornir
from nornir.core.filter import F
from nornir.core.inventory import (
    Inventory, Host, Hosts, Groups, Defaults, ConnectionOptions,
)
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
DATA_FILE    = os.path.join(MODULE_DIR, "data", "06_ipv6_isis_nornir.yaml")
TEMPLATE_DIR = os.path.join(MODULE_DIR, "templates")
CONFIG_DIR   = os.path.join(MODULE_DIR, "configs")

TEMPLATE_ISIS = "06_ipv6_isis_nornir_named.j2"
TEMPLATE_OSPF = "06_ipv6_isis_nornir_ospf_stub.j2"

# =============================================================================
# ANSI COLOR OUTPUT
# =============================================================================
def passed(msg): print(f"\033[92m  [PASS] {msg}\033[0m")
def failed(msg): print(f"\033[91m  [FAIL] {msg}\033[0m")
def warned(msg): print(f"\033[93m  [WARN] {msg}\033[0m")
def info(msg):   print(f"\033[96m  [INFO] {msg}\033[0m")


# =============================================================================
# JINJA2 ENVIRONMENT
# =============================================================================

def _ip_address(cidr: str) -> str:
    return str(ipaddress.ip_interface(cidr).ip)


def _netmask(cidr: str) -> str:
    return str(ipaddress.ip_interface(cidr).network.netmask)


def _network_prefix(cidr: str) -> str:
    # Derives the network address with prefix from a host CIDR.
    # Used in ASBR-1's OSPF-ROUTES prefix list to build the link network entry.
    # Example: 10.6.30.1/30 → 10.6.30.0/30
    return str(ipaddress.ip_interface(cidr).network.with_prefixlen)


def _build_jinja2_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["ip_address"]     = _ip_address
    env.filters["netmask"]        = _netmask
    env.filters["network_prefix"] = _network_prefix
    return env


# =============================================================================
# TEMPLATE RENDERING
# Pre-render all configs before any SSH connections.
# =============================================================================

def render_all_configs(target_devices: dict, env: Environment, all_devices: dict) -> dict:
    """Return {device_name: rendered_config_str} for all target devices.

    Rendering rules:
      - ospf_only  → ospf_stub.j2 only
      - asbr       → named.j2 + ospf_stub.j2 concatenated (IS-IS config + OSPF process block)
      - all others → named.j2 only

    all_devices is passed as template context so named.j2 can locate OSPF-1's loopback
    IP when building ASBR-1's OSPF-ROUTES prefix list.
    """
    isis_tmpl = env.get_template(TEMPLATE_ISIS)
    ospf_tmpl = env.get_template(TEMPLATE_OSPF)
    rendered  = {}

    for name, dev in target_devices.items():
        ctx  = dict(dev)
        ctx["all_devices"] = all_devices
        role = dev.get("isis_role", "")

        if role == "ospf_only":
            rendered[name] = ospf_tmpl.render(**ctx)
        elif role == "asbr":
            isis_out = isis_tmpl.render(**ctx)
            ospf_out = ospf_tmpl.render(**ctx)
            rendered[name] = isis_out + "\n" + ospf_out
        else:
            rendered[name] = isis_tmpl.render(**ctx)

    return rendered


# =============================================================================
# NORNIR INVENTORY — built from YAML, no temp files
# =============================================================================

def _build_nornir(target_devices: dict) -> Nornir:
    """Build a Nornir instance directly from the YAML devices dict.

    Builds Host objects from YAML data and wraps them in an Inventory —
    no hosts.yaml / groups.yaml files written to disk. This is the Module 06
    teaching point: programmatic inventory construction vs. file-based (Module 05).
    """
    defaults = Defaults()
    host_dict = {}

    for name, dev in target_devices.items():
        creds = dev.get("credentials", {})
        host_dict[name] = Host(
            name=name,
            hostname=dev["dns_name"],
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            platform="ios",
            # Full device dict stored in host data — accessible in tasks as
            # task.host.data; also exposes isis_role to nr.filter(F(isis_role=...)).
            data=dict(dev),
            connection_options={
                "netmiko": ConnectionOptions(
                    extras={
                        "device_type": "cisco_ios",
                        # Multiplies all Netmiko internal delay constants.
                        # Current: 2.0   Range: 1.0 (fast) – 5.0 (very slow hosts)
                        "global_delay_factor": 2.0,
                        # TCP handshake timeout in seconds.
                        # Current: 30   Range: 10 – 60
                        "conn_timeout": 30,
                    }
                )
            },
            defaults=defaults,
        )

    inventory = Inventory(
        hosts=Hosts(host_dict),
        groups=Groups({}),
        defaults=defaults,
    )
    return Nornir(inventory=inventory)


# =============================================================================
# NORNIR TASKS
# =============================================================================

def configure_isis_task(task: Task, rendered: dict) -> Result:
    """Push IS-IS Named Mode config to a single IS-IS router via Netmiko."""
    config   = rendered[task.host.name]
    commands = [line.rstrip() for line in config.splitlines() if line.strip()]
    task.run(task=netmiko_send_config, config_commands=commands)
    return Result(host=task.host, result=f"IS-IS configured on {task.host.name}", changed=True)


def configure_ospf_task(task: Task, rendered: dict) -> Result:
    """Push full OSPF config to the OSPF-only stub router via Netmiko."""
    config   = rendered[task.host.name]
    commands = [line.rstrip() for line in config.splitlines() if line.strip()]
    task.run(task=netmiko_send_config, config_commands=commands)
    return Result(host=task.host, result=f"OSPF configured on {task.host.name}", changed=True)


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
# ENTRY POINT
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "NAMS26 Module 06 — Configure IPv6 IS-IS Named Mode via Nornir\n"
            "Deploys in four phases: backbone → ABRs → leaves/ASBR → OSPF-only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/configure_06_ipv6_isis_nornir.py --dry-run\n"
            "  python scripts/configure_06_ipv6_isis_nornir.py\n"
            "  python scripts/configure_06_ipv6_isis_nornir.py --router BB-1 BB-2\n"
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
            "Target specific routers. Accepts BB-1, bb-1, or bb-1.lab. "
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
        failed(f"YAML parse error: {exc}")
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
        failed("No valid target routers.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Jinja2 environment and template validation
    # -------------------------------------------------------------------------
    try:
        env = _build_jinja2_env()
        env.get_template(TEMPLATE_ISIS)
        env.get_template(TEMPLATE_OSPF)
    except Exception as exc:
        failed(f"Template load error: {exc}")
        sys.exit(1)

    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    mode_label = "DRY-RUN" if args.dry_run else "DEPLOY"
    print(f"\nNAMS26 — Module 06: IPv6 IS-IS Named Mode / Nornir [{mode_label}]")
    print(f"Targets : {', '.join(target_routers)}")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # Pre-render ALL configs before any SSH connections
    # -------------------------------------------------------------------------
    target_devices = {k: v for k, v in devices.items() if k in target_routers}
    timestamp      = datetime.now().strftime("%y%m%d")

    try:
        rendered_configs = render_all_configs(target_devices, env, devices)
    except Exception as exc:
        failed(f"Template render error: {exc}")
        sys.exit(1)

    info(f"Pre-rendered {len(rendered_configs)} config(s).")

    # -------------------------------------------------------------------------
    # Dry-run: write configs to configs/ and exit — no SSH
    # -------------------------------------------------------------------------
    if args.dry_run:
        for name, config in rendered_configs.items():
            cfg_path = os.path.join(CONFIG_DIR, f"{timestamp}_{name}.cfg")
            with open(cfg_path, "w") as fh:
                fh.write(config)
            info(f"Written: {cfg_path}")
        print("=" * 60)
        passed(f"Dry-run complete. {len(rendered_configs)} config(s) written to {CONFIG_DIR}")
        return

    # -------------------------------------------------------------------------
    # Build Nornir inventory from YAML (programmatic — no temp files)
    # -------------------------------------------------------------------------
    nr = _build_nornir(target_devices)

    # -------------------------------------------------------------------------
    # Four-phase deployment via nr.filter()
    #
    # Phase ordering enforces IS-IS convergence:
    #   Backbone adjacencies must form before ABRs can reach backbone L2 routes.
    #   ABRs must be up before leaves register in the correct IS-IS area.
    #   OSPF stub is independent — configured last for narrative clarity.
    # -------------------------------------------------------------------------
    any_failed = False

    print("\n[Phase 1] Backbone routers (BB-1, BB-2)")
    backbone = nr.filter(F(isis_role="backbone"))
    if backbone.inventory.hosts:
        r1 = backbone.run(task=configure_isis_task, rendered=rendered_configs)
        print_result(r1)
        if any(r.failed for r in r1.values()):
            warned("One or more backbone routers failed — check output above.")
            any_failed = True
    else:
        info("No backbone routers in target set — skipping Phase 1.")

    print("\n[Phase 2] ABRs (ABR-1, ABR-2, ABR-3) — backbone must be up first")
    abrs = nr.filter(F(isis_role="abr"))
    if abrs.inventory.hosts:
        r2 = abrs.run(task=configure_isis_task, rendered=rendered_configs)
        print_result(r2)
        if any(r.failed for r in r2.values()):
            warned("One or more ABRs failed — check output above.")
            any_failed = True
    else:
        info("No ABRs in target set — skipping Phase 2.")

    print("\n[Phase 3] Leaf routers and ASBR (BR-1..5, ASBR-1)")
    leaves = nr.filter(F(isis_role__in=["leaf", "asbr"]))
    if leaves.inventory.hosts:
        r3 = leaves.run(task=configure_isis_task, rendered=rendered_configs)
        print_result(r3)
        if any(r.failed for r in r3.values()):
            warned("One or more leaf/ASBR routers failed — check output above.")
            any_failed = True
    else:
        info("No leaf/ASBR routers in target set — skipping Phase 3.")

    print("\n[Phase 4] OSPF-only stub router (OSPF-1)")
    ospf_only = nr.filter(F(isis_role="ospf_only"))
    if ospf_only.inventory.hosts:
        r4 = ospf_only.run(task=configure_ospf_task, rendered=rendered_configs)
        print_result(r4)
        if any(r.failed for r in r4.values()):
            warned("OSPF-only router failed — check output above.")
            any_failed = True
    else:
        info("No OSPF-only routers in target set — skipping Phase 4.")

    # -------------------------------------------------------------------------
    # Write memory on all deployed routers
    # -------------------------------------------------------------------------
    print("\n[Save] Writing memory on all routers")
    all_isis = nr.filter(F(isis_role__ne="ospf_only"))
    if all_isis.inventory.hosts:
        all_isis.run(task=netmiko_send_command, command_string="write memory")
    if ospf_only.inventory.hosts:
        ospf_only.run(task=netmiko_send_command, command_string="write memory")

    print("\n" + "=" * 60)
    if any_failed:
        warned("Deployment complete with errors — review output above.")
        sys.exit(1)
    else:
        passed("Deployment complete.")


if __name__ == "__main__":
    main()
