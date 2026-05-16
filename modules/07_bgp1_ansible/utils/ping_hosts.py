#!/usr/bin/env python3
"""
Module 07 — BGP Part 1 / Ansible
ICMP Reachability Check

Pings all 12 Module 07 routers to verify network connectivity.

Platform-aware: detects Windows vs Linux/macOS and uses appropriate
ping command syntax.
"""

import subprocess
import platform
import sys

# Module 07 router inventory
ROUTERS = [
    {"hostname": "core-rr1.lab", "ip": "192.168.1.101", "role": "CORE-RR1"},
    {"hostname": "core-pe1.lab", "ip": "192.168.1.102", "role": "CORE-PE1"},
    {"hostname": "core-pe2.lab", "ip": "192.168.1.103", "role": "CORE-PE2"},
    {"hostname": "core-p1.lab",  "ip": "192.168.1.104", "role": "CORE-P1"},
    {"hostname": "core-p2.lab",  "ip": "192.168.1.105", "role": "CORE-P2"},
    {"hostname": "edge-pe1.lab", "ip": "192.168.1.106", "role": "EDGE-PE1"},
    {"hostname": "edge-pe2.lab", "ip": "192.168.1.107", "role": "EDGE-PE2"},
    {"hostname": "edge-p1.lab",  "ip": "192.168.1.108", "role": "EDGE-P1"},
    {"hostname": "edge-p2.lab",  "ip": "192.168.1.109", "role": "EDGE-P2"},
    {"hostname": "stub-br1.lab", "ip": "192.168.1.110", "role": "STUB-BR1"},
    {"hostname": "stub-br2.lab", "ip": "192.168.1.111", "role": "STUB-BR2"},
    {"hostname": "stub-br3.lab", "ip": "192.168.1.112", "role": "STUB-BR3"},
]


def ping(host):
    """
    Ping a host (platform-aware).
    
    Returns tuple: (reachable: bool, packet_loss: str)
    
    Reachability threshold: <50% loss = UP, >=50% loss = DOWN
    """
    system = platform.system()
    
    if system == "Windows":
        # Windows: ping -n 3 -w 2000 <host>
        cmd = ["ping", "-n", "3", "-w", "2000", host]
    else:
        # Linux/macOS: ping -c 3 -W 2 <host>
        cmd = ["ping", "-c", "3", "-W", "2", host]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        
        output = result.stdout
        
        # Parse packet loss
        if system == "Windows":
            # Windows output: "... (X% loss)"
            for line in output.splitlines():
                if "Loss" in line or "loss" in line:
                    # Extract percentage
                    import re
                    match = re.search(r'\((\d+)%.*loss\)', line, re.IGNORECASE)
                    if match:
                        loss_pct = int(match.group(1))
                        loss_str = f"{loss_pct}% loss"
                        
                        # Threshold: <50% loss = reachable
                        if loss_pct < 50:
                            return (True, loss_str)
                        else:
                            return (False, loss_str)
            return (False, "unknown")
        else:
            # Linux/macOS output: "X packets transmitted, Y received, Z% packet loss"
            for line in output.splitlines():
                if "packet loss" in line:
                    parts = line.split(",")
                    if len(parts) >= 3:
                        loss_str = parts[2].strip()
                        # Extract percentage
                        import re
                        match = re.search(r'(\d+)%', loss_str)
                        if match:
                            loss_pct = int(match.group(1))
                            # Threshold: <50% loss = reachable
                            if loss_pct < 50:
                                return (True, loss_str)
                            else:
                                return (False, loss_str)
            return (False, "unknown")
    
    except subprocess.TimeoutExpired:
        return (False, "timeout")
    except Exception as e:
        return (False, f"error: {e}")


def main():
    """
    Ping all Module 07 routers and report reachability.
    """
    print("\n" + "="*70)
    print("Module 07 — BGP Part 1 / Ansible")
    print("ICMP Reachability Check")
    print("="*70)
    print(f"Platform: {platform.system()}")
    print("="*70 + "\n")
    
    results = []
    
    for router in ROUTERS:
        hostname = router["hostname"]
        ip = router["ip"]
        role = router["role"]
        
        print(f"Pinging {role:12} ({hostname:16} / {ip:15})...", end=" ", flush=True)
        
        reachable, loss = ping(hostname)
        
        if reachable:
            print(f"✓ UP   ({loss})")
            results.append((role, True))
        else:
            print(f"✗ DOWN ({loss})")
            results.append((role, False))
    
    # Summary
    print("\n" + "="*70)
    print("Reachability Summary")
    print("="*70)
    
    up_count = sum(1 for _, status in results if status)
    down_count = len(results) - up_count
    
    print(f"Total routers: {len(ROUTERS)}")
    print(f"Reachable:     {up_count}")
    print(f"Unreachable:   {down_count}")
    print("="*70)
    
    if down_count == 0:
        print("\n✓ All routers are reachable!")
        print("\nReady to deploy BGP configuration with Ansible")
        return 0
    else:
        print(f"\n✗ {down_count} router(s) unreachable")
        print("\nCheck network connectivity and EVE-NG lab status")
        return 1


if __name__ == "__main__":
    sys.exit(main())
