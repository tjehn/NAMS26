# Module 03 — OSPF Classic / NAPALM

This module deploys classic multi-area OSPF with mixed authentication across eleven
Cisco IOL routers. Configuration is managed from a YAML source of truth via NAPALM
using the `load_merge_candidate` / `compare_config` / `commit_config` workflow.
The key advance over Module 02 is the diff-before-commit model — the operator sees
exactly what will change before it is applied to any router. The closing demonstration
uses a deliberate config drift to show how the troubleshooter and verifier answer
different questions about the same router.

## Prerequisites

- Module 02 complete — YAML → Jinja2 → Python three-file workflow understood
- CCNP-level OSPF knowledge: multi-area, ABR, authentication, network types, DR/BDR
- Python 3.10+, `napalm`, `pyyaml`, `jinja2` installed
- EVE-NG lab running with R1–R11 reachable via OOB management (`192.168.1.0/24`)

## Directory Structure

```
03_ospf1_napalm/
├── 03_ios_configs/        # Raw IOS configs captured from EVE-NG lab
├── configs/               # Rendered device configs (git-ignored, written by --dry-run)
├── data/
│   └── ospf_classic.yaml  # Device inventory, interfaces, OSPF parameters
├── diagrams/
│   ├── module03_topology_ospf_classic.drawio
│   └── module03_topology_ospf_classic.drawio.svg
├── docs/
│   ├── eve-ng_lab_reset_sop.md   # See project-level docs/eve-ng_lab_reset_sop.md
│   ├── module03_planning.md      # Pre-development topology and script design notes
│   └── module03_closing_demo.md  # Live demonstration — config drift scenario
├── logs/                  # Session logs (git-ignored)
├── scripts/
│   ├── configure_ospf_classic.py    # Deploy OSPF config via NAPALM
│   ├── verify_ospf_classic.py       # Validate live state against YAML
│   └── troubleshoot_ospf_classic.py
├── templates/
│   └── ospf_classic.j2    # Jinja2 template — interfaces, OSPF process, authentication
├── utils/
│   ├── clear_known_hosts.sh
│   ├── init_ssh.py
│   ├── check_ssh.py
│   ├── ping_hosts.py
│   └── push_config.py
└── verbal_script/
    └── module03_verbal_script_final.md
```

## How to Run the Scripts

```bash
# Pre-flight (run after every EVE-NG Wipe+Start, in this order)
bash utils/clear_known_hosts.sh
python utils/init_ssh.py
python utils/ping_hosts.py

# Dry-run — render configs locally, no SSH connection
python scripts/configure_ospf_classic.py --dry-run

# Deploy to all routers
python scripts/configure_ospf_classic.py

# Deploy to specific routers
python scripts/configure_ospf_classic.py --router R1 R2

# Verify all routers — all checks
python scripts/verify_ospf_classic.py

# Verify specific router and checks
python scripts/verify_ospf_classic.py --router R1 --check neighbors routes
```

## What to Expect

After a successful `configure_ospf_classic.py` run:

- All eleven routers have OSPF adjacencies in FULL state
- Area 0 (backbone) and Area 10 are formed with the correct ABR (R1)
- OSPF authentication is active on interfaces where configured in the YAML
- Interface descriptions, speed, and duplex settings match the YAML

`verify_ospf_classic.py` with all checks passing confirms the topology matches the
YAML source of truth. Session logs are written to `modules/03_ospf1_napalm/logs/` on every run.
