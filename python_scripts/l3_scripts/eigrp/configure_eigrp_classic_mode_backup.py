# python_scripts/l3_scripts/eigrp/configure_eigrp_classic_mode.py

import os
import yaml
import argparse
from jinja2 import Environment, FileSystemLoader
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# Custom filter: CIDR to netmask
def cidr_to_netmask(cidr):
    """Convert CIDR prefix to subnet mask (e.g. '24' → '255.255.255.0')"""
    try:
        cidr = int(cidr)
        if not 0 <= cidr <= 32:
            raise ValueError
        mask = (0xFFFFFFFF << (32 - cidr)) & 0xFFFFFFFF
        return f"{(mask >> 24) & 255}.{(mask >> 16) & 255}.{(mask >> 8) & 255}.{mask & 255}"
    except:
        return "255.255.255.255"  # fallback

# Parse command-line arguments
# Parse command-line arguments
parser = argparse.ArgumentParser(description="Configure EIGRP Classic Mode on lab routers")
parser.add_argument('--dry-run', action='store_true', help="Generate configs only, no SSH push")
parser.add_argument('--router', nargs='*', help="Target specific router(s) by name (e.g. --router R1 R2)")  # ← ADD THIS
args = parser.parse_args()

# Paths
PROJECT_ROOT = os.path.expanduser("~/PycharmProjects/NAMS26")
YAML_FILE_PATH = os.path.join(PROJECT_ROOT, "labs/lab_eigrp/vars/eigrp_classic_mode.yaml")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "templates/routing")
CONFIG_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "labs/lab_eigrp/configs")

# Load YAML data
try:
    with open(YAML_FILE_PATH, 'r') as f:
        data = yaml.safe_load(f)
except yaml.YAMLError as exc:
    print(f"Error loading YAML: {exc}")
    exit(1)

default_creds = data.get('default_credentials', {})
devices = data.get('devices', {})
print("DEBUG: R2 key_chains from YAML:", devices['R2']['eigrp'].get('key_chains', 'MISSING'))
print("DEBUG: R2 authentication:", devices['R2']['eigrp'].get('authentication', 'MISSING'))
print("DEBUG: Full R2 eigrp data:", devices['R2']['eigrp'])
print("DEBUG: R2 key_chains type:", type(devices['R2']['eigrp'].get('key_chains')))
print("DEBUG: R2 key_chains content:", devices['R2']['eigrp'].get('key_chains'))
print("DEBUG: Number of key chains for R2:", len(devices['R2']['eigrp'].get('key_chains', [])))
print("DEBUG: R1 loopbacks keys:", list(devices['R1']['loopbacks'].keys()))
print("DEBUG: R1 loopbacks full:", devices['R1']['loopbacks'])
print("DEBUG: R2 loopbacks keys:", list(devices['R2']['loopbacks'].keys()))


if not devices:
    print("No devices found in YAML.")
    exit(1)

# Debug yaml key chain configuration parsing
print("DEBUG: R2 key_chains:", devices['R2']['eigrp'].get('key_chains'))

# Setup Jinja2 environment
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

# Register custom filter
env.filters['cidr_to_netmask'] = cidr_to_netmask

try:
    template = env.get_template('eigrp_classic_mode.j2')
    print("DEBUG: Using template from:", template.filename)
except Exception as e:
    print(f"Error loading template 'eigrp_classic_mode.j2': {e}")
    print("Make sure templates/routing/eigrp_classic_mode.j2 exists.")
    exit(1)

# Generate config
def generate_config(device_data):
    return template.render(device_data)

# Apply config
def apply_config_to_router(device_name, device_data, config):
    oob_full = device_data.get('oob_ip', '')
    oob_ip = oob_full.split('/')[0] if '/' in oob_full else oob_full

    creds = device_data.get('credentials', default_creds)

    if not creds.get('username') or not creds.get('password'):
        print(f"Missing credentials for {device_name}")
        return

    router = {
        'device_type': 'cisco_ios',
        'host': oob_ip,
        'username': creds['username'],
        'password': creds['password'],
        'global_delay_factor': 4.0,  # Increased from 2.0
        'session_log': f"session_log_{device_name}.txt",  # Log everything for debug
    }

    try:
        print(f"Connecting to {device_name} ({oob_ip})...")
        with ConnectHandler(**router) as conn:
            print(f"Connected successfully to {device_name}")

            # Force config mode
            conn.send_command("configure terminal", expect_string=r"#")

            # Send lines one-by-one with higher delay
            print("Sending config lines one by one...")
            for line in config.splitlines():
                if line.strip():  # Skip empty lines
                    conn.send_command(line, expect_string=r"#", delay_factor=5.0)

            # Explicit end and save
            print("Ending config mode...")
            conn.send_command("end", expect_string=r"#")
            print("Saving config...")
            save_out = conn.send_command("write memory")  # No expect_string
            print(f"Save output:\n{save_out}")

            print(f"Configuration saved on {device_name}")

    except NetmikoTimeoutException:
        print(f"Timeout connecting to {device_name} ({oob_ip})")
    except NetmikoAuthenticationException:
        print(f"Authentication failed on {device_name}")
    except Exception as e:
        print(f"Error configuring {device_name}: {str(e)}")


# Main: Process target routers (or all if none specified)
target_routers = args.router if args.router else list(devices.keys())

for device_name in target_routers:
    if device_name not in devices:
        print(f"Warning: Router '{device_name}' not found in YAML - skipping")
        continue
    device_data = devices[device_name]
    print(f"\n=== Processing {device_name} ===")

    config = generate_config(device_data)

    # Always save config file
    config_file = os.path.join(CONFIG_OUTPUT_DIR, f"{device_name}_eigrp.cfg")
    with open(config_file, 'w') as f:
        f.write(config)
    print(f"Config saved to: {config_file}")

    # Debug loopbacks
    print(f"DEBUG: Loopbacks for {device_name}: {device_data.get('loopbacks', 'NOT FOUND')}")

    # Apply only if not dry-run
    if not args.dry_run:
        apply_config_to_router(device_name, device_data, config)
    else:
        print(f"DRY-RUN: Skipping SSH push to {device_name}")

print("\nScript completed.")