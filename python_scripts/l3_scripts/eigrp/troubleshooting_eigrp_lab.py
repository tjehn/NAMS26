# troubleshooting_eigrp_lab.py
# Quick health check for EIGRP lab after rebuild / config push

import os
import yaml
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
import subprocess

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────

PROJECT_ROOT = os.path.expanduser("~/PycharmProjects/NAMS26")
YAML_PATH = os.path.join(PROJECT_ROOT, "labs/lab_eigrp/vars/eigrp_classic_mode.yaml")

# Which show commands to run
SHOW_COMMANDS = [
    "show version | include Version",
    "show ip interface brief",
    "show run | section router eigrp",
    "show ip eigrp neighbors",
    "show ip route eigrp | begin Gateway"
]

# ────────────────────────────────────────────────

def ping_test(ip):
    """Simple ping -c 2 test"""
    try:
        result = subprocess.run(["ping", "-c", "2", "-W", "2", ip],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except:
        return False

def load_yaml():
    try:
        with open(YAML_PATH, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR loading YAML: {e}")
        exit(1)

data = load_yaml()
devices = data.get('devices', {})
default_creds = data.get('default_credentials', {})

if not devices:
    print("No devices in YAML")
    exit(1)

print("═" * 70)
print("  EIGRP Lab Troubleshooting Report")
print("═" * 70)
print()

for name, dev in devices.items():
    ip_full = dev.get('oob_ip', 'MISSING')
    ip = ip_full.split('/')[0] if '/' in ip_full else ip_full

    print(f"Router: {name:6}   IP: {ip:15}", end="  ")

    # 1. Ping
    ping_ok = ping_test(ip)
    print(f"Ping: {'OK' if ping_ok else 'FAIL'}   ", end="")

    if not ping_ok:
        print("→ Cannot reach device → skipping SSH checks")
        print("-" * 70)
        continue

    # 2. SSH & show commands
    creds = dev.get('credentials', default_creds)
    if not creds.get('username') or not creds.get('password'):
        print("Missing credentials → skipping")
        continue

    router = {
        'device_type': 'cisco_ios',
        'host': ip,
        'username': creds['username'],
        'password': creds['password'],
        'global_delay_factor': 3.0,
    }

    try:
        with ConnectHandler(**router) as conn:
            print("SSH: OK")

            for cmd in SHOW_COMMANDS:
                print(f"  {cmd}")
                try:
                    out = conn.send_command(cmd, delay_factor=3.0)
                    lines = out.splitlines()
                    # Show first 8 lines + ... if long
                    preview = "\n    ".join(lines[:8])
                    if len(lines) > 8:
                        preview += "\n    ... (truncated)"
                    print(f"    {preview}")
                except Exception as e:
                    print(f"    ERROR running '{cmd}': {e}")
                print()

    except NetmikoTimeoutException:
        print("SSH: TIMEOUT")
    except NetmikoAuthenticationException:
        print("SSH: AUTH FAIL")
    except Exception as e:
        print(f"SSH: ERROR - {e}")

    print("-" * 70)
    print()

print("Troubleshooting complete.")