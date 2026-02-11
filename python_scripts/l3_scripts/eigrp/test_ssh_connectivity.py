# python_scripts/l3_scripts/eigrp/test_ssh_connectivity.py

import os
import yaml
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# Paths (matches your configure script)
PROJECT_ROOT = os.path.expanduser("~/PycharmProjects/NAMS26")
YAML_FILE_PATH = os.path.join(PROJECT_ROOT, "labs/lab_eigrp/vars/eigrp_classic_mode.yaml")

# Load YAML
try:
    with open(YAML_FILE_PATH, 'r') as f:
        data = yaml.safe_load(f)
except yaml.YAMLError as exc:
    print(f"Error loading YAML: {exc}")
    exit(1)

default_creds = data.get('default_credentials', {})
devices = data.get('devices', {})

if not devices:
    print("No devices found in YAML.")
    exit(1)


def test_ssh_to_device(device_name, device_data):
    print(f"\nTesting SSH to {device_name}...")

    oob_full = device_data.get('oob_ip', '')
    oob_ip = oob_full.split('/')[0] if '/' in oob_full else oob_full

    creds = device_data.get('credentials', default_creds)

    if not creds.get('username') or not creds.get('password'):
        print(f"  → Missing credentials for {device_name}")
        return

    router = {
        'device_type': 'cisco_ios',
        'host': oob_ip,
        'username': creds['username'],
        'password': creds['password'],
        'global_delay_factor': 2.0,
    }

    try:
        with ConnectHandler(**router) as conn:
            print(f"  → SUCCESS: Connected to {device_name} ({oob_ip})")
            # Immediately disconnect (no commands needed)
            print(f"  → Logged out cleanly")
    except NetmikoTimeoutException:
        print(f"  → FAILED: Timeout connecting to {device_name} ({oob_ip}) - check reachability")
    except NetmikoAuthenticationException:
        print(f"  → FAILED: Authentication failed on {device_name} - check username/password")
    except Exception as e:
        print(f"  → FAILED: Error on {device_name}: {str(e)}")


# Test all devices
for device_name, device_data in devices.items():
    test_ssh_to_device(device_name, device_data)

print("\nSSH connectivity test complete.")