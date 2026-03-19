cat > README.md << 'EOF'
# NAMS26 — Network Automation Management Station 2026

A professional-grade network automation lab and curriculum showcasing Python
scripting, network protocols, and automation tools across an eleven-module
progression from Netmiko through Ansible.

## Project Goal

Build and demonstrate network automation expertise through hands-on lab work
with live Cisco IOS routers in EVE-NG, producing high-quality instructional
content (code + documentation + video lessons) published on GitHub and YouTube.

## Automation Tool Progression

| Module | Protocol    | Tool          |
|--------|-------------|---------------|
| 01     | Introduction| N/A           |
| 02     | EIGRP       | Netmiko       |
| 03     | OSPF-1      | NAPALM        |
| 04     | OSPF-2      | NAPALM        |
| 05     | IPv6/IS-IS  | Nornir        |
| 06     | IS-IS       | Nornir        |
| 07     | BGP-1       | pyATS/Genie   |
| 08     | BGP-2       | pyATS/Genie   |
| 09     | BGP MPLS    | Ansible       |
| 10     | MPLS-VPN    | Ansible       |
| 11     | VPN/GRE     | Ansible       |

## Lab Environment

- **NAMS:** Dell T7610 (64GB RAM) — VMware Workstation → Kali Linux
- **Emulation:** Dell T7610 (128GB RAM) — VMware ESXi → EVE-NG Professional
- **Devices:** Cisco IOL L3/L2 images
- **Storage:** Synology NAS — Gitea (dev) → GitHub (production)

## Repository Structure
```
NAMS26/
├── ansible/          # Ansible roles and playbooks (Modules 09-11)
├── docs/             # Project-level documentation
├── inventory/        # Project-level inventory
├── modules/          # One directory per module
│   ├── 01_introduction/
│   ├── 02_eigrp_netmiko/
│   └── ...
├── utils/            # Project-level shared utilities
└── requirements.txt
```

## Status

| Module | Topic       | Tool        | Status      |
|--------|-------------|-------------|-------------|
| 01     | Introduction| N/A         | In Progress |
| 02     | EIGRP       | Netmiko     | Complete    |
| 03-11  | See above   | See above   | Planned     |
EOF