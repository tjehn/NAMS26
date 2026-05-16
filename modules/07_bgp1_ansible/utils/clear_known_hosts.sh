#!/bin/bash

# Module 07 — BGP Part 1 / Ansible
# Clear SSH known_hosts entries for lab routers
# Run this script after EVE-NG Wipe+Start (IOL regenerates RSA keys)

KNOWN_HOSTS="$HOME/.ssh/known_hosts"

if [ ! -f "$KNOWN_HOSTS" ]; then
    echo "known_hosts file not found at $KNOWN_HOSTS"
    echo "Nothing to clear."
    exit 0
fi

echo "Clearing Module 07 router entries from $KNOWN_HOSTS..."

# Remove entries for all 12 Module 07 routers
ssh-keygen -f "$KNOWN_HOSTS" -R "core-rr1.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.101" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "core-pe1.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.102" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "core-pe2.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.103" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "core-p1.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.104" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "core-p2.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.105" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "edge-pe1.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.106" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "edge-pe2.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.107" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "edge-p1.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.108" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "edge-p2.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.109" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "stub-br1.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.110" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "stub-br2.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.111" 2>/dev/null

ssh-keygen -f "$KNOWN_HOSTS" -R "stub-br3.lab" 2>/dev/null
ssh-keygen -f "$KNOWN_HOSTS" -R "192.168.1.112" 2>/dev/null

echo "Module 07 router entries cleared from known_hosts."
echo "Run init_ssh.py next to populate new host keys."
