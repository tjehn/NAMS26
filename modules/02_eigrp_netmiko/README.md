# Module 02 — EIGRP Classic / Netmiko

This module deploys classic EIGRP across eleven Cisco IOL routers from a YAML source
of truth using Netmiko. Each router's configuration is rendered from a Jinja2 template
and pushed line-by-line over SSH using `send_config_set`. The verification script
validates neighbor adjacencies, routing table entries, and interface state against the
YAML. This is the foundation module — all subsequent modules build on the three-file
workflow (YAML → Jinja2 → Python) established here.

## Prerequisites

- Basic Python scripting: files, loops, functions, argparse
- CCNP-level EIGRP knowledge: neighbor adjacency, wildcard masks, passive interfaces, redistribution
- Python 3.10+, `netmiko`, `pyyaml`, `jinja2` installed
- EVE-NG lab running with R1–R11 reachable via OOB management (`192.168.1.0/24`)

## Directory Structure

```
02_eigrp_netmiko/
├── 02_ios_configs/        # Raw IOS configs captured from EVE-NG lab
├── configs/               # Rendered device configs (git-ignored, written by --dry-run)
├── data/
│   └── eigrp_classic.yaml # Device inventory, interfaces, EIGRP parameters
├── diagrams/
│   ├── module02_topology_eigrp_classic.drawio
│   └── module02_topology_eigrp_classic.drawio.svg
├── docs/
│   ├── eve-ng_lab_reset_sop.md   # See project-level docs/eve-ng_lab_reset_sop.md
│   ├── module02_planning.md      # Pre-development topology and script design notes
│   └── module02_closing_demo.md  # Live demonstration — config drift scenario
├── logs/                  # Session logs (git-ignored)
├── scripts/
│   ├── configure_eigrp_classic.py   # Deploy EIGRP config via Netmiko
│   ├── verify_eigrp_classic.py      # Validate live state against YAML
│   └── troubleshoot_eigrp_classic.py
├── templates/
│   └── eigrp_classic.j2   # Jinja2 template — interfaces, EIGRP process
├── utils/
│   ├── clear_known_hosts.sh
│   ├── init_ssh.py
│   ├── check_ssh.py
│   ├── ping_hosts.py
│   └── push_config.py
└── verbal_script/
    └── module02_verbal_script_final.md
```

## How to Run the Scripts

```bash
# Pre-flight (run after every EVE-NG Wipe+Start, in this order)
bash utils/clear_known_hosts.sh
python utils/init_ssh.py
python utils/ping_hosts.py

# Dry-run — render configs locally, no SSH connection
python scripts/configure_eigrp_classic.py --dry-run

# Deploy to all routers
python scripts/configure_eigrp_classic.py

# Deploy to specific routers
python scripts/configure_eigrp_classic.py --router R1 R2

# Verify all routers — all checks
python scripts/verify_eigrp_classic.py

# Verify specific router and checks
python scripts/verify_eigrp_classic.py --router R1 --check neighbors routes
```

## What to Expect

After a successful `configure_eigrp_classic.py` run:

- All eleven routers have EIGRP AS 100 adjacencies in a FULL state
- EIGRP routes appear in routing tables across the topology
- Passive interfaces are correctly configured and excluded from adjacency formation
- Interface descriptions, speed, and duplex settings match the YAML

`verify_eigrp_classic.py` with all checks passing confirms the topology matches the
YAML source of truth. Session logs are written to `modules/02_eigrp_netmiko/logs/` on every run.
