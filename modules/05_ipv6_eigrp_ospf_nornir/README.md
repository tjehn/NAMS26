# Module 05 — IPv6 EIGRP + OSPFv3 / Nornir

This module deploys a pure-IPv6 topology across nine Cisco IOL routers: two independent
EIGRPv6 domains flanking a central OSPFv3 multi-area domain, with bidirectional
redistribution at R1 (EIGRP AS 100 ↔ OSPF) and R6 (EIGRP AS 111 ↔ OSPF). The
automation tool changes from NAPALM to Nornir — introducing parallel task execution and
inventory abstraction. The key distinction from NAPALM: Nornir's `netmiko_send_config`
is a merge operation, not a replace. It adds what the YAML defines but does not enforce
complete intended state. The closing demonstration makes this concrete.

## Prerequisites

- Modules 02–04 complete — YAML → Jinja2 → Python workflow and NAPALM diff model understood
- CCNP-level knowledge: EIGRPv6, OSPFv3, IPv6 addressing, redistribution, NSSA
- Python 3.10+, `nornir`, `nornir-netmiko`, `nornir-utils`, `netmiko`, `pyyaml`, `jinja2` installed
- EVE-NG lab running with R1–R9 reachable via OOB management (`192.168.1.0/24`)

## Directory Structure

```
05_ipv6_eigrp_ospf_nornir/
├── 05_ios_configs/        # Raw IOS configs captured from EVE-NG lab
├── configs/               # Rendered device configs (git-ignored, written by --dry-run)
├── data/
│   └── ipv6_eigrp_ospf.yaml   # Device inventory, interfaces, EIGRPv6 + OSPFv3 parameters
├── diagrams/
│   ├── module05_topology_ipv6_eigrp_ospf.drawio
│   └── module05_topology_ipv6_eigrp_ospf.drawio.svg
├── docs/
│   ├── eve-ng_lab_reset_sop.md    # See project-level docs/eve-ng_lab_reset_sop.md
│   ├── module05_planning.md       # Pre-development topology and script design notes
│   └── module05_closing_demo.md   # Live demonstration — Nornir merge model limitation
├── logs/                  # Session logs (git-ignored)
├── scripts/
│   ├── configure_ipv6_eigrp_ospf.py    # Deploy config via Nornir + netmiko_send_config
│   ├── verify_ipv6_eigrp_ospf.py       # Validate live state against YAML
│   └── troubleshoot_ipv6_eigrp_ospf.py
├── templates/
│   └── ipv6_eigrp_ospf.j2   # Jinja2 template — interfaces, EIGRPv6, OSPFv3
├── utils/
│   ├── clear_known_hosts.sh
│   ├── init_ssh.py
│   ├── check_ssh.py
│   ├── ping_hosts.py
│   └── push_config.py
└── verbal_script/
    └── module05_verbal_script.md
```

## How to Run the Scripts

```bash
# Pre-flight (run after every EVE-NG Wipe+Start, in this order)
bash utils/clear_known_hosts.sh
python utils/init_ssh.py
python utils/ping_hosts.py

# Dry-run — render configs locally, no SSH connection
python scripts/configure_ipv6_eigrp_ospf.py --dry-run

# Deploy to all routers
python scripts/configure_ipv6_eigrp_ospf.py

# Deploy to specific routers
python scripts/configure_ipv6_eigrp_ospf.py --router R1 R2

# Verify all routers — all checks
python scripts/verify_ipv6_eigrp_ospf.py

# Verify specific router and checks
python scripts/verify_ipv6_eigrp_ospf.py --router R1 --check neighbors routes
```

## What to Expect

After a successful `configure_ipv6_eigrp_ospf.py` run:

- All nine routers have EIGRPv6 and/or OSPFv3 adjacencies established
- Area 0 (R1, R2, R3), Area 10 Totally Stubby (R2, R4), Area 20 NSSA (R3, R5, R6) formed
- R1 redistributes bidirectionally between EIGRP AS 100 and OSPFv3
- R6 redistributes EIGRP AS 111 routes as Type 7 LSAs into OSPFv3 Area 20 NSSA
- R7, R8 (EIGRP AS 100 only) and R9 (EIGRP AS 111 only) are EIGRP-only routers — OSPFv3
  checks are skipped on these automatically

`verify_ipv6_eigrp_ospf.py` with all checks passing confirms the topology matches the
YAML source of truth. Session logs are written to `modules/05_ipv6_eigrp_ospf_nornir/logs/` on every run.
