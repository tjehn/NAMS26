# Module 06 — IPv6 IS-IS Named Mode / Nornir

This module deploys IS-IS Named Mode across four areas and twelve Cisco IOL routers using
Nornir with a custom task function and `nr.filter()` for role-aware phased deployment.
The IS-IS domain spans a Level-2 backbone (Area 49.0001: BB-1, BB-2) with three dual-homed
Area Border Routers (ABR-1, ABR-2, ABR-3) connecting three Level-1 areas: Area 49.0002
(BR-1, BR-2, BR-3 on a shared broadcast LAN with DIS election), Area 49.0003 (BR-4 and BR-5
with MT-IS-IS for IPv6), and Area 49.0004 (ASBR-1 redistributing OSPF routes into IS-IS from
an OSPF stub domain). Nornir deploys configuration in four phases — backbone first, ABRs
second, leaf routers and ASBR third, OSPF-only router last — enforcing the operational
sequencing that IS-IS adjacency formation requires. The closing demonstration injects DIS
priority drift on BR-2: the troubleshooter returns PASS (adjacencies are healthy), the
verifier returns WARN (live DIS role does not match the YAML source of truth), and the
configure script restores the intended state idempotently.

## Prerequisites

- Module 05 complete — Nornir `nr.run()` and inventory model understood
- CCNP-level IS-IS knowledge: area design, NET addresses, DIS election, route leaking,
  L1/L2 router roles
- Python 3.10+, `nornir`, `nornir-netmiko`, `nornir-utils`, `pyyaml`, `jinja2` installed
- EVE-NG lab running with BB-1 through OSPF-1 reachable via OOB management (`192.168.1.0/24`)

## Directory Structure

```
06_ipv6_isis_nornir/
├── 06_ios_configs/        # Raw IOS configs captured from EVE-NG lab
├── configs/               # Rendered device configs (git-ignored, written by --dry-run)
├── data/
│   └── 06_ipv6_isis_nornir.yaml  # Device inventory, interfaces, IS-IS + OSPF parameters
├── diagrams/
│   ├── module06_topology_isis.drawio
│   └── module06_topology_isis.drawio.svg
├── docs/
│   ├── eve-ng_lab_reset_sop.md       # Lab reset procedure — run after every Wipe+Start
│   ├── module06_planning.md          # Pre-development topology and script design notes
│   └── module06_closing_demo.md      # Live demonstration — DIS priority drift scenario
├── logs/                  # Session logs (git-ignored)
├── scripts/
│   ├── configure_06_ipv6_isis_nornir.py    # Deploy IS-IS + OSPF config via Nornir
│   ├── verify_06_ipv6_isis_nornir.py       # Validate live state against YAML
│   └── troubleshoot_06_ipv6_isis_nornir.py
├── templates/
│   ├── 06_ipv6_isis_nornir_named.j2        # IS-IS Named Mode Jinja2 template
│   └── 06_ipv6_isis_nornir_ospf_stub.j2   # OSPF stub config for ASBR-1 and OSPF-1
├── utils/
│   ├── clear_known_hosts.sh
│   ├── init_ssh.py
│   ├── check_ssh.py
│   ├── ping_hosts.py
│   └── push_config.py
└── verbal_script/
    └── module06_verbal_script_final.md
```

## How to Run the Scripts

```bash
# Pre-flight (run after every EVE-NG Wipe+Start, in this order)
bash utils/clear_known_hosts.sh
python utils/init_ssh.py
python utils/ping_hosts.py

# Dry-run — render configs locally, no SSH connection
python scripts/configure_06_ipv6_isis_nornir.py --dry-run

# Deploy to all routers (four-phase: backbone → ABRs → leaves → OSPF)
python scripts/configure_06_ipv6_isis_nornir.py

# Deploy to specific routers
python scripts/configure_06_ipv6_isis_nornir.py --router BB-1 BB-2

# Verify all routers — all checks
python scripts/verify_06_ipv6_isis_nornir.py

# Verify specific router and checks
python scripts/verify_06_ipv6_isis_nornir.py --router BR-2 --check neighbors

# Troubleshoot specific router
python scripts/troubleshoot_06_ipv6_isis_nornir.py --router ASBR-1 --check adjacency ospf
```

## What to Expect

After a successful `configure_06_ipv6_isis_nornir.py` run:

- All IS-IS routers have adjacencies Up in `show isis neighbors`
- L2 backbone (BB-1, BB-2) has three dual-homed ABRs (ABR-1, ABR-2, ABR-3) — each ABR
  connects to both backbone routers, providing redundant paths across the L2 domain
- Area 49.0002 broadcast LAN: BR-2 is DIS (`isis priority 100`), pseudonode LSP visible
  in `show isis database`
- Area 49.0003 IPv6 zone: BR-4 and BR-5 running MT-IS-IS, IPv6 loopbacks
  `2001:db8:6:1::9/128` and `2001:db8:6:1::10/128` visible in IS-IS LSDB
- Area 49.0004: OSPF-1 loopback `10.6.31.1` redistributed into IS-IS via ASBR-1,
  visible in ASBR-1's LSP at metric 20 and propagated to all backbone routers
- Route leaking active on all three ABRs — L1 leaf routers have full routing
  visibility beyond their local area

`verify_06_ipv6_isis_nornir.py` with all checks PASS confirms all 12 routers match
the YAML source of truth. Session logs are written to `modules/06_ipv6_isis_nornir/logs/`
on every run.
