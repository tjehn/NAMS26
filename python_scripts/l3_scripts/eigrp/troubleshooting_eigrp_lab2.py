#!/usr/bin/env python3
"""
Simple script: Assign random IP to Ethernet0/0 on R1 and R2
"""

import random
from netmiko import ConnectHandler

# Fixed credentials (change if needed)
USERNAME = "netadmin"
PASSWORD = "admin"

# Router IPs (your OOB IPs)
ROUTERS = {
    "R1": "192.168.1.101",
    "R2": "192.168.1.102",
}


def get_random_ip():
    """Generate random IP in 10.99.0.0/24 range (safe lab range)"""
    third_octet = random.randint(1, 254)
    fourth_octet = random.randint(1, 254)
    return f"10.99.{third_octet}.{fourth_octet}", "255.255.255.0"


def apply_random_ip(router_name, ip):
    print(f"\n=== {router_name} ===")
    print(f"Applying random IP: {ip}/24 to Ethernet0/0")

    device = {
        "device_type": "cisco_ios",
        "host": ROUTERS[router_name],
        "username": USERNAME,
        "password": PASSWORD,
        "global_delay_factor": 2.0,
    }

    try:
        with ConnectHandler(**device) as conn:
            print("Connected successfully")

            commands = [
                "interface Ethernet0/0",
                f"ip address {ip} 255.255.255.0",
                "no shutdown",
                "exit",
                "write memory"
            ]

            output = conn.send_config_set(commands, delay_factor=2.0)
            print("Config applied:")
            print(output)

            print("Saving config... done")

    except Exception as e:
        print(f"Error on {router_name}: {e}")


# Main
if __name__ == "__main__":
    for router in ["R1", "R2"]:
        ip, mask = get_random_ip()
        apply_random_ip(router, ip)

    print("\nDone.")