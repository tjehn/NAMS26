#!/usr/bin/env python3
"""
Module 07 — BGP Part 1 / Ansible
SSH Initialization Script

Connects to all 12 Module 07 routers via SSH, accepts new RSA host key
fingerprints, and populates ~/.ssh/known_hosts.

Run this script after every EVE-NG Wipe+Start cycle (IOL regenerates
RSA keys on each boot).

Uses paramiko with AutoAddPolicy for cross-platform compatibility
(Windows, Linux, macOS).

Includes legacy algorithm support for older IOL images.
"""

import os
import sys
import paramiko
from pathlib import Path

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

USERNAME = "netadmin"
PASSWORD = "admin"
SSH_PORT = 22

# Path to known_hosts file
KNOWN_HOSTS_FILE = Path.home() / ".ssh" / "known_hosts"


def init_ssh_for_router(router):
    """
    Connect to a router via SSH, accept the host key, and add it to known_hosts.
    
    Uses paramiko.AutoAddPolicy to automatically accept unknown host keys.
    Includes legacy algorithm support for older Cisco IOL images.
    """
    hostname = router["hostname"]
    ip = router["ip"]
    role = router["role"]
    
    print(f"\n{'='*60}")
    print(f"Router: {role} ({hostname} / {ip})")
    print(f"{'='*60}")
    
    try:
        # Create SSH client
        client = paramiko.SSHClient()
        
        # Load existing known_hosts (if any)
        if KNOWN_HOSTS_FILE.exists():
            client.load_host_keys(str(KNOWN_HOSTS_FILE))
        
        # Auto-add unknown host keys
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        print(f"Connecting to {hostname}...")
        
        # Get default transport and enable legacy algorithms
        # This is needed for older Cisco IOL images
        transport = paramiko.Transport((hostname, SSH_PORT))
        
        # Enable legacy key exchange algorithms
        transport.get_security_options().kex = (
            transport.get_security_options().kex +
            ('diffie-hellman-group14-sha1', 'diffie-hellman-group-exchange-sha1')
        )
        
        # Enable legacy host key algorithms
        transport.get_security_options().key_types = (
            transport.get_security_options().key_types +
            ('ssh-rsa',)
        )
        
        # Start transport
        transport.start_client()
        
        # Authenticate
        transport.auth_password(USERNAME, PASSWORD)
        
        print(f"✓ Connected to {hostname}")
        
        # Get host key and save it
        host_key = transport.get_remote_server_key()
        
        # Add to paramiko's host keys
        client._host_keys.add(hostname, host_key.get_name(), host_key)
        
        # Save to known_hosts file
        client.save_host_keys(str(KNOWN_HOSTS_FILE))
        print(f"✓ Host key saved to {KNOWN_HOSTS_FILE}")
        
        # Close the connection
        transport.close()
        print(f"✓ Connection closed")
        
        return True
        
    except paramiko.AuthenticationException:
        print(f"✗ Authentication failed for {hostname}")
        print(f"  Check username/password: {USERNAME}/{PASSWORD}")
        return False
        
    except paramiko.SSHException as e:
        print(f"✗ SSH error for {hostname}: {e}")
        return False
        
    except Exception as e:
        print(f"✗ Error connecting to {hostname}: {e}")
        return False


def main():
    """
    Initialize SSH connections to all Module 07 routers.
    """
    print("\n" + "="*60)
    print("Module 07 — BGP Part 1 / Ansible")
    print("SSH Initialization Script")
    print("="*60)
    print(f"\nThis script will connect to all 12 routers and accept")
    print(f"their RSA host key fingerprints.")
    print(f"\nKnown hosts file: {KNOWN_HOSTS_FILE}")
    print(f"Username: {USERNAME}")
    print(f"Password: {PASSWORD}")
    print("="*60)
    
    # Ensure ~/.ssh directory exists
    ssh_dir = KNOWN_HOSTS_FILE.parent
    if not ssh_dir.exists():
        print(f"\nCreating {ssh_dir} directory...")
        ssh_dir.mkdir(mode=0o700, parents=True)
    
    # Connect to each router
    success_count = 0
    fail_count = 0
    
    for router in ROUTERS:
        if init_ssh_for_router(router):
            success_count += 1
        else:
            fail_count += 1
    
    # Summary
    print("\n" + "="*60)
    print("SSH Initialization Summary")
    print("="*60)
    print(f"Total routers: {len(ROUTERS)}")
    print(f"Successful:    {success_count}")
    print(f"Failed:        {fail_count}")
    print("="*60)
    
    if fail_count == 0:
        print("\n✓ All routers initialized successfully!")
        print("\nNext step: Run ping_hosts.py to verify ICMP reachability")
        return 0
    else:
        print(f"\n✗ {fail_count} router(s) failed initialization")
        print("\nCheck network connectivity and router configurations")
        return 1


if __name__ == "__main__":
    sys.exit(main())
