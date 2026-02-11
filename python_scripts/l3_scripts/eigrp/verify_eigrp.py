# python_scripts/l3_scripts/eigrp/verify_eigrp.py

import os
import yaml
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from tabulate import tabulate

# Paths (future-proof style)
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

def get_connection(device_name, device_data):
    oob_full = device_data.get('oob_ip', '')
    oob_ip = oob_full.split('/')[0] if '/' in oob_full else oob_full

    creds = device_data.get('credentials', default_creds)

    router = {
        'device_type': 'cisco_ios',
        'host': oob_ip,
        'username': creds['username'],
        'password': creds['password'],
        'global_delay_factor': 2.0,
    }

    return router, oob_ip

def run_show_command(conn, command):
    try:
        output = conn.send_command(command, delay_factor=2.0)
        return output.strip()
    except Exception as e:
        return f"Error running '{command}': {str(e)}"

def parse_routes(output):
    """
    Advanced parser for 'show ip route eigrp'.
    - Groups by network
    - Labels primary successor first
    - Lists feasible successors immediately after
    - Includes outgoing interface
    """
    routes = []
    current_net = ""
    lines = output.splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # New network line (starts with D or D*)
        if line.startswith(('D ', 'D*')) or ('D ' in line and '/' in line):
            parts = line.split()
            network = parts[1] if len(parts) > 1 else "N/A"

            if 'is a summary' in line:
                routes.append([network, "Summary (Null0)", "N/A", "Summary"])
                current_net = network
                continue

            # Main route with metric and via
            if '[90/' in line and 'via ' in line:
                metric = line.split('[')[1].split(']')[0] if '[' in line else "N/A"
                via_part = line.split('via ')[1].strip()
                next_hop = via_part.split(',')[0].strip()
                interface = via_part.split(',')[-1].strip() if ',' in via_part else "N/A"
                routes.append([network, f"{next_hop} ({interface})", metric, "Successor"])
                current_net = network

        # Feasible successor line (starts with spaces or 'via')
        elif current_net and line.strip().startswith('via ') and '[90/' in line:
            metric = line.split('[')[1].split(']')[0] if '[' in line else "N/A"
            via_part = line.split('via ')[1].strip()
            next_hop = via_part.split(',')[0].strip()
            interface = via_part.split(',')[-1].strip() if ',' in via_part else "N/A"
            routes.append([current_net, f"{next_hop} ({interface})", metric, "Feasible Successor"])

    return routes

def verify_router(device_name, device_data):
    print(f"\n=== Verifying {device_name} ===")
    router, oob_ip = get_connection(device_name, device_data)

    try:
        with ConnectHandler(**router) as conn:
            print(f"Connected to {device_name} ({oob_ip})")

            # Neighbors
            neighbors = run_show_command(conn, "show ip eigrp neighbors")
            print("\nEIGRP Neighbors:")
            print(neighbors or "No neighbors (or error)")

            # Topology table (first 15 lines)
            topology = run_show_command(conn, "show ip eigrp topology")
            print("\nEIGRP Topology:")
            print(topology if topology else "No topology data")

            # Route table – all EIGRP routes with successors and feasible successors
            routes_output = run_show_command(conn, "show ip route eigrp")
            routes = parse_routes(routes_output)
            print("\nEIGRP Routes (Successor + Feasible Successors):")
            if routes:
                headers = ["Network", "Next Hop (Interface)", "Metric", "Status"]
                print(tabulate(routes, headers=headers, tablefmt="grid"))
            else:
                print("No EIGRP routes parsed – raw output follows:")
                print(routes_output)

            # Bandwidth check on key interfaces
            print("\nInterface Bandwidth Check (affects EIGRP metric):")
            key_intfs = ["Ethernet0/0", "Ethernet0/1", "Ethernet0/2"]  # Customize
            bw_table = []
            for intf in key_intfs:
                bw_output = run_show_command(conn, f"show interfaces {intf}")
                bw = "N/A"
                for ln in bw_output.splitlines():
                    if "BW" in ln:
                        bw = ln.split("BW")[1].split(",")[0].strip()
                        break
                bw_table.append([intf, bw])
            print(tabulate(bw_table, headers=["Interface", "Bandwidth"], tablefmt="grid"))

    except Exception as e:
        print(f"Error verifying {device_name}: {str(e)}")

# Run verification on all devices
for device_name, device_data in devices.items():
    verify_router(device_name, device_data)

print("\nVerification complete.")