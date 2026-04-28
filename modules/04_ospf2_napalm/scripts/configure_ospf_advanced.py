#!/usr/bin/env python3
"""
Module   : 04 — OSPF Advanced / NAPALM
File     : modules/04_ospf2_napalm/scripts/configure_ospf_advanced.py
Purpose  : Generate and apply OSPF Advanced configurations to Cisco IOS
           routers using YAML variable data and a Jinja2 template via NAPALM.
           Covers multi-area OSPF (Area 0, Area 10, Area 20 NSSA), bidirectional
           redistribution with EIGRP 100 and EIGRP 111, LSA Type 3 filtering
           on both ABRs, and NSSA default-information-originate on R3.

Usage:
    # Apply config to all routers
    python configure_ospf_advanced.py

    # Dry-run — render configs only, no SSH push
    python configure_ospf_advanced.py --dry-run

    # Target specific routers
    python configure_ospf_advanced.py --router R1 R2

    # Combine — dry-run on specific routers
    python configure_ospf_advanced.py --dry-run --router R1

Workflow:
    YAML data  →  Jinja2 template  →  rendered config  →  NAPALM SSH push

Pre-flight requirement:
    Run utils/clear_known_hosts.sh and utils/check_ssh.py before executing
    this script after every EVE-NG lab reboot. check_ssh.py populates
    ~/.ssh/known_hosts with current host keys using StrictHostKeyChecking
    accept-new, allowing this script to connect without SSH suppression.
"""

import os
import sys
import yaml
import argparse
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from napalm import get_network_driver
from napalm.base.exceptions import (
    ConnectionException,
    CommandErrorException,
)

# =============================================================================
# PATH RESOLUTION
# All paths are resolved relative to this script's location so the script
# works regardless of which directory it is called from.
# =============================================================================
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR    = os.path.dirname(SCRIPT_DIR)                       # 04_ospf2_napalm/
MODULES_DIR   = os.path.dirname(MODULE_DIR)                       # modules/
PROJECT_ROOT  = os.path.dirname(MODULES_DIR)                      # NAMS26/

YAML_FILE     = os.path.join(MODULE_DIR, "data",      "ospf_advanced.yaml")
TEMPLATE_DIR  = os.path.join(MODULE_DIR, "templates")
TEMPLATE_FILE = "ospf_advanced.j2"
CONFIG_DIR    = os.path.join(MODULE_DIR, "configs")
LOG_DIR       = os.path.join(MODULE_DIR, "logs")

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")


# =============================================================================
# ANSI COLOR OUTPUT
# =============================================================================

def passed(msg: str) -> None: print(f"\033[92m  [PASS] {msg}\033[0m")
def failed(msg: str) -> None: print(f"\033[91m  [FAIL] {msg}\033[0m")
def warned(msg: str) -> None: print(f"\033[93m  [WARN] {msg}\033[0m")
def info(msg: str)   -> None: print(f"\033[96m  [INFO] {msg}\033[0m")


# =============================================================================
# CUSTOM JINJA2 FILTER
# =============================================================================

def cidr_to_netmask(cidr: str) -> str:
    """Convert a CIDR prefix length to a dotted-decimal subnet mask.

    Args:
        cidr: Prefix length as a string or integer (e.g. '24' or 24).

    Returns:
        Dotted-decimal subnet mask string (e.g. '255.255.255.0').
        Returns '255.255.255.255' as a fallback on invalid input.

    Example:
        cidr_to_netmask('24') → '255.255.255.0'
        cidr_to_netmask('8')  → '255.0.0.0'
    """
    try:
        cidr = int(cidr)
        if not 0 <= cidr <= 32:
            raise ValueError(f"CIDR value out of range: {cidr}")
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
# CONFIG GENERATION
# =============================================================================

def generate_config(template, device_data: dict) -> str:
    """Render the Jinja2 template with the provided device data.

    Args:
        template   : Loaded Jinja2 Template object.
        device_data: Dictionary of variables for a single device from YAML.

    Returns:
        Rendered configuration string ready to be sent to the router.
    """
    return template.render(device_data)


# =============================================================================
# CONFIG DEPLOYMENT
# =============================================================================

def apply_config(device_name: str, device_data: dict, config: str) -> None:
    """Connect to a router via NAPALM and apply the rendered configuration.

    Establishes a NAPALM IOS driver session, loads the rendered config as
    a merge candidate, commits it to the device, and saves the running
    configuration.

    The SSH target is resolved via the lab DNS server (192.168.1.12) using
    the dns_name field from YAML (e.g. r1.lab). oob_ip is retained in the
    YAML for documentation and reference only — it is not used for connections.

    SSH host key verification relies on ~/.ssh/known_hosts populated by
    utils/check_ssh.py as part of the standard lab pre-flight sequence.
    Run clear_known_hosts.sh followed by check_ssh.py after every EVE-NG
    lab reboot before executing this script.

    A timestamped session log is written to the module logs/ directory
    for each device connection.

    Args:
        device_name : Router hostname string (e.g. 'R1'). Used for logging.
        device_data : Device dictionary from YAML (contains dns_name, credentials).
        config      : Rendered configuration string to apply.
    """
    # Warn if known_hosts is missing — operator should run pre-flight first
    if not os.path.isfile(KNOWN_HOSTS_FILE):
        warned(
            f"~/.ssh/known_hosts not found. "
            f"Run utils/clear_known_hosts.sh then utils/check_ssh.py "
            f"before deploying."
        )

    # Use dns_name as the SSH target — resolved by the lab DNS at 192.168.1.12
    dns_name = device_data.get("dns_name", "")
    if not dns_name:
        failed(f"No dns_name defined for {device_name} in YAML — skipping.")
        return

    # Resolve credentials
    creds    = device_data.get("credentials", {})
    username = creds.get("username", "")
    password = creds.get("password", "")

    if not username or not password:
        failed(f"Missing credentials for {device_name} — skipping.")
        return

    # Ensure logs directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    timestamp        = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_log_path = os.path.join(LOG_DIR, f"session_{device_name}_{timestamp}.txt")

    driver = get_network_driver("ios")

    optional_args = {
        "ssh_config_file": None,
        "session_log":     session_log_path,
        # IOL routers have no flash: filesystem. NAPALM checks available space on
        # the destination filesystem before transferring config. Pointing it to
        # nvram: prevents a "No such file or directory" error on every connect.
        "dest_file_system": "nvram:",
        # NAPALM normally transfers config via SCP. IOL does not support SCP.
        # inline_transfer=True sends the config directly over the SSH session
        # instead — the only method that works on IOL. Must always be True here.
        "inline_transfer":  True,
        # Belt-and-suspenders: IOL raises MD5 checksum errors when SCP is attempted
        # against nvram: on some image versions. inline_transfer already prevents
        # SCP, but enable_scp=False makes the intent explicit and guards against
        # a future NAPALM version re-enabling SCP independently.
        "enable_scp":       False,
    }

    try:
        info(f"Connecting to {device_name} ({dns_name})...")

        with driver(
            hostname=dns_name,
            username=username,
            password=password,
            optional_args=optional_args,
        ) as device:

            passed(f"Connected to {device_name}.")

            # Load config as merge candidate — additive, preserves existing config
            info(f"Loading configuration candidate...")
            device.load_merge_candidate(config=config)

            # Display diff before committing
            diff = device.compare_config()
            if diff:
                info(f"Configuration diff for {device_name}:")
                print(diff)
            else:
                info(f"No diff detected — config may already be present.")

            # Commit the candidate configuration
            # IOL does not support nvram:/rollback_config.txt — NAPALM raises
            # an exception after a successful commit when it cannot save the
            # rollback file. We catch that specific error and warn rather than
            # reporting a false FAIL.
            info(f"Committing configuration...")
            try:
                device.commit_config()
                passed(f"Configuration committed on {device_name}.")
            except Exception as exc:
                exc_str = str(exc)
                if "rollback" in exc_str.lower():
                    # Uncomment the line below to surface this warning in an
                    # IOL/lab environment — suppressed by default for clean output.
                    # warned(f"Commit succeeded on {device_name} but rollback file "
                    #        f"could not be saved (expected on IOL — nvram: limitation).")
                    pass
                else:
                    raise

            # Save running config to startup config
            device.cli(["write memory"])
            passed(f"Configuration saved on {device_name}.")

    except ConnectionException as exc:
        failed(f"Connection failed to {device_name} ({dns_name}): {exc}")
    except CommandErrorException as exc:
        failed(f"Command error on {device_name}: {exc}")
    except Exception as exc:
        failed(f"Unexpected error on {device_name}: {exc}")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    # -------------------------------------------------------------------------
    # Argument parsing
    # -------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description=(
            "Module 04 — OSPF Advanced / NAPALM\n"
            "Generates and applies OSPF Advanced configurations to Cisco IOS\n"
            "routers using YAML data and a Jinja2 template via NAPALM.\n"
            "Covers multi-area OSPF, EIGRP redistribution, LSA filtering,\n"
            "and NSSA configuration."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python configure_ospf_advanced.py\n"
            "  python configure_ospf_advanced.py --dry-run\n"
            "  python configure_ospf_advanced.py --router R1 R2\n"
            "  python configure_ospf_advanced.py --dry-run --router R1\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render and save configs locally only — no SSH connection.",
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help=(
            "Target one or more routers by hostname (e.g. --router R1 R2). "
            "Accepts: R1, r1, r1.lab, R1.lab. "
            "Defaults to all devices in YAML."
        ),
    )
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Load YAML data
    # -------------------------------------------------------------------------
    if not os.path.isfile(YAML_FILE):
        failed(f"YAML file not found: {YAML_FILE}")
        sys.exit(1)

    try:
        with open(YAML_FILE, "r") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        failed(f"Failed to parse YAML: {exc}")
        sys.exit(1)

    devices       = data.get("devices", {})
    default_creds = data.get("default_credentials", {})

    if not devices:
        failed("No devices found in YAML.")
        sys.exit(1)

    # Inject default credentials into any device not defining its own
    for device_data in devices.values():
        if not device_data.get("credentials"):
            device_data["credentials"] = default_creds

    # -------------------------------------------------------------------------
    # Load Jinja2 template
    # -------------------------------------------------------------------------
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["cidr_to_netmask"] = cidr_to_netmask

    try:
        template = env.get_template(TEMPLATE_FILE)
    except Exception as exc:
        failed(f"Failed to load template '{TEMPLATE_FILE}': {exc}")
        info(f"Expected location: {os.path.join(TEMPLATE_DIR, TEMPLATE_FILE)}")
        sys.exit(1)

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
                warned(f"Router not found in YAML (skipped): '{token}'")
    else:
        target_routers = list(devices.keys())

    if not target_routers:
        failed("No valid target routers to process.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Ensure configs output directory exists
    # -------------------------------------------------------------------------
    os.makedirs(CONFIG_DIR, exist_ok=True)
    run_date = datetime.now().strftime("%y%m%d_%H%M%S")

    # -------------------------------------------------------------------------
    # Process each target router
    # -------------------------------------------------------------------------
    mode_label = "DRY-RUN" if args.dry_run else "DEPLOY"
    print(f"\nNAMS26 — Module 04: OSPF Advanced / NAPALM [{mode_label}]")
    print(f"Targets : {', '.join(target_routers)}")
    print("=" * 60)

    for device_name in target_routers:
        device_data = devices[device_name]
        print(f"\n[{device_name}]")

        # Render configuration from template
        config = generate_config(template, device_data)

        # Write rendered config to configs/ directory
        config_path = os.path.join(CONFIG_DIR, f"{run_date}_{device_name}_ospf_advanced.cfg")
        with open(config_path, "w") as fh:
            fh.write(config)
        info(f"Config written : {config_path}")

        # Deploy or skip based on --dry-run flag
        if args.dry_run:
            info(f"DRY-RUN        : SSH push skipped.")
        else:
            apply_config(device_name, device_data, config)

    print("\n" + "=" * 60)
    passed(f"Done. Configs saved to: {CONFIG_DIR}")
    if not args.dry_run:
        info(f"Session logs saved to : {LOG_DIR}")


if __name__ == "__main__":
    main()
