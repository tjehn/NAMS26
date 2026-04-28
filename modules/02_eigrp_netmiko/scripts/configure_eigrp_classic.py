#!/usr/bin/env python3
"""
Module   : 02 — EIGRP Classic Mode
File     : modules/02_eigrp_netmiko/scripts/configure_eigrp_classic.py
Purpose  : Generate and apply EIGRP Classic Mode configurations to Cisco IOS
           routers using YAML variable data and a Jinja2 template via Netmiko.

Usage:
    # Apply config to all routers
    python configure_eigrp_classic.py

    # Dry-run — render configs only, no SSH push
    python configure_eigrp_classic.py --dry-run

    # Target specific routers
    python configure_eigrp_classic.py --router R1 R2

    # Combine — dry-run on specific routers
    python configure_eigrp_classic.py --dry-run --router R1

Workflow:
    YAML data  →  Jinja2 template  →  rendered config  →  Netmiko SSH push

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
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# =============================================================================
# PATH RESOLUTION
# All paths are resolved relative to this script's location so the script
# works regardless of which directory it is called from.
# =============================================================================
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR    = os.path.dirname(SCRIPT_DIR)                       # 02_eigrp_netmiko/
MODULES_DIR   = os.path.dirname(MODULE_DIR)                       # modules/
PROJECT_ROOT  = os.path.dirname(MODULES_DIR)                      # NAMS26/

YAML_FILE     = os.path.join(MODULE_DIR, "data",      "eigrp_classic.yaml")
TEMPLATE_DIR  = os.path.join(MODULE_DIR, "templates")
TEMPLATE_FILE = "eigrp_classic.j2"
CONFIG_DIR    = os.path.join(MODULE_DIR, "configs")
LOG_DIR       = os.path.join(MODULE_DIR, "logs")


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
        cidr_to_netmask('19') → '255.255.224.0'
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
    """Connect to a router via SSH and apply the rendered configuration.

    Establishes a Netmiko SSH session, enters configuration mode, sends
    each config line individually, then saves the running configuration.

    The SSH target is resolved via the lab DNS server (192.168.1.12) using
    the dns_name field from YAML (e.g. r1.lab). oob_ip is retained in the
    YAML for documentation and reference only — it is not used for connections.

    SSH host key verification relies on ~/.ssh/known_hosts populated by
    utils/check_ssh.py as part of the standard lab pre-flight sequence.
    Run clear_known_hosts.sh followed by check_ssh.py after every EVE-NG
    lab reboot before executing this script.

    A timestamped session log is written to the project logs/ directory
    for each device connection.

    Args:
        device_name : Router hostname string (e.g. 'R1'). Used for logging.
        device_data : Device dictionary from YAML (contains dns_name, credentials).
        config      : Rendered configuration string to apply.
    """
    # Use dns_name as the SSH target — resolved by the lab DNS at 192.168.1.12
    dns_name = device_data.get("dns_name", "")
    if not dns_name:
        print(f"  [ERROR] No dns_name defined for {device_name} in YAML — skipping.")
        return

    # Resolve credentials — fall back to default_creds if not device-specific
    creds = device_data.get("credentials", {})
    username = creds.get("username", "")
    password = creds.get("password", "")

    if not username or not password:
        print(f"  [ERROR] Missing credentials for {device_name} — skipping.")
        return

    # Ensure logs directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_log_path = os.path.join(LOG_DIR, f"session_{device_name}_{timestamp}.txt")

    # Netmiko connection parameters — host resolves via lab DNS (192.168.1.12)
    # SSH host key verification uses ~/.ssh/known_hosts (populated by check_ssh.py)
    connection_params = {
        "device_type":         "cisco_ios",
        "host":                dns_name,
        "username":            username,
        "password":            password,
        # Multiplier applied to ALL of Netmiko's internal delay constants
        # (post-login settling, inter-command pause, prompt-detection loops).
        # Set higher here than in push_config.py (2.0) because this script
        # sends lines individually via send_command(), which is more sensitive
        # to timing than send_config_set() — each line needs its own prompt detection.
        # Current: 4.0   Range: 1.0 (fastest, may miss prompts) – 5.0 (slow/remote hosts)
        "global_delay_factor": 4.0,
        "session_log":         session_log_path,
    }

    try:
        print(f"  Connecting to {device_name} ({dns_name})...")
        with ConnectHandler(**connection_params) as conn:
            print(f"  Connected to {device_name}.")

            # Enter global configuration mode
            conn.send_command("configure terminal", expect_string=r"#")

            # Send config lines individually — avoids buffer issues on IOL
            print(f"  Sending configuration lines...")
            for line in config.splitlines():
                if line.strip():
                    # delay_factor multiplies Netmiko's per-send_command wait time
                    # independently of global_delay_factor. The two stack multiplicatively:
                    # effective wait = base_delay × global_delay_factor × delay_factor.
                    # 5.0 provides extra headroom for slow IOL config-mode command processing.
                    # Current: 5.0   Range: 1.0 (fast) – 10.0 (very slow or remote routers)
                    conn.send_command(line, expect_string=r"#", delay_factor=5.0)

            # Exit config mode and save
            conn.send_command("end", expect_string=r"#")
            save_output = conn.send_command("write memory")
            print(f"  Configuration saved on {device_name}.")
            print(f"  Save output: {save_output.strip()}")

    except NetmikoTimeoutException:
        print(f"  [ERROR] Timeout connecting to {device_name} ({dns_name}).")
    except NetmikoAuthenticationException:
        print(f"  [ERROR] Authentication failed on {device_name}.")
    except Exception as exc:
        print(f"  [ERROR] Unexpected error on {device_name}: {exc}")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    # -------------------------------------------------------------------------
    # Argument parsing
    # -------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description=(
            "Module 02 — EIGRP Classic Mode\n"
            "Generates and applies EIGRP Classic Mode configurations to Cisco "
            "IOS routers using YAML data and a Jinja2 template via Netmiko."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        help="Target one or more routers by hostname (e.g. --router R1 R2). "
             "Defaults to all devices in YAML.",
    )
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Load YAML data
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

    # Inject default credentials into any device not defining its own
    for device_data in devices.values():
        if not device_data.get("credentials"):
            device_data["credentials"] = default_creds

    # -------------------------------------------------------------------------
    # Load Jinja2 template
    # -------------------------------------------------------------------------
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True)
    env.filters["cidr_to_netmask"] = cidr_to_netmask

    try:
        template = env.get_template(TEMPLATE_FILE)
    except Exception as exc:
        print(f"[ERROR] Failed to load template '{TEMPLATE_FILE}': {exc}")
        print(f"        Expected location: {os.path.join(TEMPLATE_DIR, TEMPLATE_FILE)}")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Resolve target routers
    # Accepts YAML key (R1), case-insensitive short name (r1), or DNS name
    # (r1.lab) — mirrors the alias resolution pattern in check_ssh.py.
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
        print("[ERROR] No valid target routers to process.")
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
    print(f"\nNAMS26 — Module 02: EIGRP Classic Mode [{mode_label}]")
    print(f"Targets : {', '.join(target_routers)}")
    print("=" * 60)

    for device_name in target_routers:
        device_data = devices[device_name]
        print(f"\n[{device_name}]")

        # Render configuration from template
        config = generate_config(template, device_data)

        # Write rendered config to configs/ directory
        config_path = os.path.join(CONFIG_DIR, f"{run_date}_{device_name}_eigrp_classic.cfg")
        with open(config_path, "w") as fh:
            fh.write(config)
        print(f"  Config written : {config_path}")

        # Deploy or skip based on --dry-run flag
        if args.dry_run:
            print(f"  DRY-RUN        : SSH push skipped.")
        else:
            apply_config(device_name, device_data, config)

    print("\n" + "=" * 60)
    print(f"Done. Configs saved to: {CONFIG_DIR}")
    if not args.dry_run:
        print(f"Session logs saved to : {LOG_DIR}")


if __name__ == "__main__":
    main()
