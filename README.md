# NAMS26 — Network Automation Management Station 2026

A professional-grade network automation lab and curriculum for CCNP-level engineers.
Twelve modules progress from Netmiko through NAPALM, Nornir, pyATS/Genie, and Ansible,
with each module deploying live Cisco IOL routers in EVE-NG using Python automation scripts.

> *This curriculum was developed with the assistance of Claude (Anthropic) as an AI development partner.*

## Module Progression

| Module | Protocol / Topic                          | Tool                  | Status      |
|--------|-------------------------------------------|-----------------------|-------------|
| 01     | Introduction                              | N/A                   | In Progress |
| 02     | EIGRP Classic                             | Netmiko               | Complete    |
| 03     | OSPF Classic                              | NAPALM                | Complete    |
| 04     | OSPF Advanced                             | NAPALM                | Complete    |
| 05     | IPv6 EIGRP + OSPFv3                       | Nornir                | In Progress |
| 06     | IPv6 IS-IS                                | Nornir                | Planned     |
| 07     | BGP Part 1                                | Ansible               | Planned     |
| 08     | BGP Part 2                                | Ansible               | Planned     |
| 09     | Route Policy                              | Ansible               | Planned     |
| 10     | BGP + MPLS                                | Ansible + pyATS/Genie | Planned     |
| 11     | MPLS VPN                                  | Ansible + pyATS/Genie | Planned     |
| 12     | VPN / GRE                                 | Ansible + pyATS/Genie | Planned     |
| 13     | Capstone — Multi-site Enterprise          | Flask + Mixed         | Planned     |

## Prerequisites

- **Python:** 3.10+
- **Lab:** EVE-NG Professional with Cisco IOL L3 images
- **Packages:** `netmiko`, `napalm`, `nornir`, `nornir-netmiko`, `nornir-utils`, `pyats[full]`, `ansible`
- **Knowledge:** CCNP-level routing and switching; basic Python scripting

## How to Use This Repository

Each module is self-contained under `modules/NN_name_tool/`. The workflow for every module is:

```bash
# 1. Lab reset (after every EVE-NG Wipe+Start)
bash modules/NN_name_tool/utils/clear_known_hosts.sh
python modules/NN_name_tool/utils/init_ssh.py
python modules/NN_name_tool/utils/ping_hosts.py

# 2. Dry-run — render configs locally, no SSH connection
python modules/NN_name_tool/scripts/configure_*.py --dry-run

# 3. Deploy to all routers
python modules/NN_name_tool/scripts/configure_*.py

# 4. Verify operational state
python modules/NN_name_tool/scripts/verify_*.py
```

See each module's `README.md` for module-specific instructions and expected output.

## Repository Structure

```
NAMS26/
├── docs/                 # Project-level documentation
├── modules/              # One directory per module
│   ├── 02_eigrp_netmiko/
│   ├── 03_ospf1_napalm/
│   ├── 04_ospf2_napalm/
│   ├── 05_ipv6_eigrp_ospf_nornir/
│   └── ...
├── ansible/              # Ansible roles and playbooks (Modules 10-12)
├── APPENDIX.md           # Student reference — technology notes and snippets
└── requirements.txt
```

## Lab Environment

- **NAMS Workstation:** Dell T7610 (64 GB RAM) — VMware Workstation → Kali Linux
- **Emulation Host:** Dell T7610 (128 GB RAM) — VMware ESXi → EVE-NG Professional
- **Devices:** Cisco IOL L3 images
- **Storage / Git:** Synology NAS → Gitea (dev) → GitHub (production)
