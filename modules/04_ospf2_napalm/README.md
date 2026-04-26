# Module 04 — OSPF Advanced / NAPALM

This module deploys multi-area OSPF with redistribution between OSPF and two independent
EIGRP domains across ten Cisco IOL routers. Configuration is managed from a YAML source
of truth via NAPALM using the same `load_merge_candidate` / `compare_config` / `commit_config`
workflow introduced in Module 03. The closing demonstration shows how redistribution drift
is invisible to a protocol troubleshooter but immediately visible to a verifier comparing
against the source of truth.

## Prerequisites

- Module 03 complete — NAPALM workflow and IOL `optional_args` understood
- CCNP-level OSPF knowledge: multi-area, LSA types 1–7, NSSA, redistribution, LSA filtering
- Python 3.10+, `napalm`, `pyyaml`, `jinja2` installed
- EVE-NG lab running with R1–R10 reachable via OOB management (`192.168.1.0/24`)

## Directory Structure

```
04_ospf2_napalm/
├── 04_ios_configs/        # Raw IOS configs captured from EVE-NG lab
├── configs/               # Rendered device configs (git-ignored, written by --dry-run)
├── data/
│   └── ospf_advanced.yaml # Device inventory, interfaces, OSPF + EIGRP parameters
├── diagrams/
│   ├── module04_topology_ospf_advanced.drawio
│   └── module04_topology_ospf_advanced.drawio.svg
├── docs/
│   ├── eve-ng_lab_reset_sop.md   # See project-level docs/eve-ng_lab_reset_sop.md
│   ├── module04_planning.md      # Pre-development topology and script design notes
│   └── module04_closing_demo.md  # Live demonstration — redistribution drift scenario
├── logs/                  # Session logs (git-ignored)
├── scripts/
│   ├── configure_ospf_advanced.py    # Deploy OSPF + EIGRP config via NAPALM
│   ├── verify_ospf_advanced.py       # Validate live state against YAML
│   └── troubleshoot_ospf_advanced.py
├── templates/
│   └── ospf_advanced.j2   # Jinja2 template — interfaces, EIGRP, OSPF, prefix-lists
├── utils/
│   ├── clear_known_hosts.sh
│   ├── init_ssh.py
│   ├── check_ssh.py
│   ├── ping_hosts.py
│   └── push_config.py
└── verbal_script/
    └── module04_verbal_script.md
```

## How to Run the Scripts

```bash
# Pre-flight (run after every EVE-NG Wipe+Start, in this order)
bash utils/clear_known_hosts.sh
python utils/init_ssh.py
python utils/ping_hosts.py

# Dry-run — render configs locally, no SSH connection
python scripts/configure_ospf_advanced.py --dry-run

# Deploy to all routers
python scripts/configure_ospf_advanced.py

# Deploy to specific routers
python scripts/configure_ospf_advanced.py --router R1 R6

# Verify all routers — all checks
python scripts/verify_ospf_advanced.py

# Verify specific router and checks
python scripts/verify_ospf_advanced.py --router R1 --check neighbors redistribution

# Troubleshoot specific router
python scripts/troubleshoot_ospf_advanced.py --router R1 --check neighbors process
```

## What to Expect

After a successful `configure_ospf_advanced.py` run:

- All ten routers have OSPF adjacencies in FULL state
- Area 0 (R1, R2, R3), Area 10 (R2, R4, R10), Area 20 NSSA (R3, R5, R6) are formed
- R1 redistributes bidirectionally between OSPF and EIGRP 100 (R7, R8 loopbacks visible as `O E1`)
- R6 redistributes EIGRP 111 routes as Type 7 LSAs; R3 converts them to Type 5 for Area 0
- R2 filters `102.0.0.0/8` and `103.0.0.0/8` from leaving Area 10 (R2 A10-OUT filter)
- R3 filters `100.0.0.0/8` from entering Area 20 (R3 A20-IN filter)
- Area 20 routers (R5, R6) have an NSSA default route (`O N2 0.0.0.0/0`) from R3

`verify_ospf_advanced.py` with all checks passing confirms the topology matches the
YAML source of truth. Session logs are written to `modules/04_ospf2_napalm/logs/` on every run.
