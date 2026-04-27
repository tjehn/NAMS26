# NAMS26 — Project Context
## Network Automation Management Station 2026

---

## Project Overview

NAMS26 is a 12-module network automation video curriculum taught over a Cisco IOL lab running in EVE-NG. Each module introduces a real-world automation tool against a progressively more complex network topology. The tool progression is:

| Modules | Tool               | Protocol(s)                              |
|---------|--------------------|------------------------------------------|
| 02      | Netmiko            | EIGRP                                    |
| 03–04   | NAPALM             | OSPF Classic / Advanced                  |
| 05–06   | Nornir             | IPv6 EIGRP + OSPFv3 / IS-IS              |
| 07–09   | Ansible            | BGP / Route Policy                       |
| 10–12   | Ansible + pyATS/Genie | BGP+MPLS / MPLS VPN / VPN+GRE        |
| 13      | Flask + Mixed      | Multi-site Capstone                      |

Module 01 is an introduction (no lab scripts). Module 02 is the EIGRP/Netmiko baseline. The curriculum assumes a CCNP-level audience — routing protocol mechanics are not explained from scratch; the focus is on how Python drives the configuration and what each tool adds over the previous one.

---

## Lab Environment

- **Platform:** EVE-NG on a dedicated server
- **Routers:** Cisco IOL (IOS on Linux) — 15.7 images
- **Management network:** `192.168.1.0/24` — OOB `Ethernet1/3` on each router
- **Lab DNS:** `192.168.1.12` resolves `r1.lab` through `r11.lab`
- **SSH credentials:** `netadmin` / `admin` (set in each module's YAML)
- **NMS workstation:** Kali Linux VM (`192.168.1.x`), hostname `nams26`
- **Python environment:** `.venv/` at project root (Python 3.13)
- **Git remotes:** `origin` → Gitea at `192.168.1.12:8418` (dev), `github` → GitHub (production)
- **IDE:** PyCharm on the NMS workstation

### IOL Constraint (NAPALM modules)

Cisco IOL has no `flash:` filesystem and does not support SCP. Every NAPALM script must include:

```python
optional_args = {
    "ssh_config_file": None,
    "session_log":     session_log_path,
    "dest_file_system": "nvram:",
    "inline_transfer":  True,
}
```

`nvram:` reports free space in the format NAPALM expects. `inline_transfer: True` pushes configuration over SSH instead of SCP. Neither override is needed on physical hardware.

### EVE-NG Lab Reset Sequence

After every lab reboot: **Stop → Wipe → Start → console base config → RSA keys → pre-flight → deploy**.
Skipping Wipe leaves stale NVRAM config that causes false FAILs in verify scripts.

Pre-flight order within a session:
1. `utils/clear_known_hosts.sh` — purge stale host key entries (IOL regenerates RSA keys on every Wipe)
2. `utils/init_ssh.py` — interactive pexpect-driven SSH flow; accepts new host keys and populates `~/.ssh/known_hosts`
3. `utils/ping_hosts.py` — ICMP reachability confirm before deploying

`utils/check_ssh.py` is a separate troubleshooting diagnostic (Netmiko-based); it is **not** part of the reset sequence.

---

## Project Structure

```
NAMS26/
├── CLAUDE.md                  # Claude Code project instructions
├── NAMS26_context.md          # This file — project context for AI planning
├── docs/
│   ├── style_guide.md
│   └── git_reference_nams26.md
└── modules/
    ├── 02_eigrp_netmiko/
    ├── 03_ospf1_napalm/
    ├── 04_ospf2_napalm/       # COMPLETE
    ├── 05_...                 # ← Current module
    └── ...
```

### Module Directory Layout (all modules identical)

```
modules/NN_name_tool/
├── data/           # YAML device inventory + routing config
├── templates/      # Jinja2 .j2 templates
├── scripts/        # configure_*.py, verify_*.py, troubleshoot_*.py
├── utils/          # check_ssh.py, ping_hosts.py, clear_known_hosts.sh, push_config.py
├── configs/        # Rendered device configs (git-ignored)
├── logs/           # Session logs (git-ignored)
└── docs/           # Verbal scripts, SOPs, planning docs
```

---

## Established Patterns and Standards

These patterns are consistent across all modules and must not change:

### Path Resolution (4-level chain from `__file__`)
```python
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)
LOG_DIR      = os.path.join(MODULE_DIR, "logs")
```

### CLI Contract (all configure scripts)
```bash
python scripts/configure_*.py --dry-run           # Render only, no SSH
python scripts/configure_*.py                     # Deploy all routers
python scripts/configure_*.py --router R1 R2      # Deploy specific routers
python scripts/verify_*.py --router R1 --check neighbors routes
```

### Interface Standards (YAML)
| Type | speed | duplex | shutdown |
|------|-------|--------|----------|
| Active Ethernet | `100` | `full` | `false` |
| Unused Ethernet | `""` | `""` | `true` |
| Active Serial | `""` | `""` | `false` |
| Loopback | `""` | `""` | `false` |
| OOB (Ethernet1/3) | `""` | `""` | `false` — reference only, not rendered |

### `utils/` Standard Scripts (all modules)

| File | Tool | Purpose | In SOP |
|------|------|---------|--------|
| `init_ssh.py` | pexpect | Lab reset — accepts new host key fingerprints, populates `~/.ssh/known_hosts` | Yes |
| `check_ssh.py` | Netmiko | Troubleshooting — verifies connectivity against existing known_hosts | No |
| `clear_known_hosts.sh` | bash | Purges stale lab router keys from `~/.ssh/known_hosts` | Yes |
| `ping_hosts.py` | icmplib/subprocess | ICMP reachability check against all devices in module YAML | Yes |
| `push_config.py` | varies | Standalone config push (bypasses full configure script) | No |

### Verification Output Pattern
All verify scripts produce per-device PASS / WARN / FAIL output with a worst-case summary table and mirrored timestamped logs under `modules/NN_name_tool/logs/`.

---

## Module Status

### Module 02 — EIGRP / Netmiko
**Status: COMPLETE**

- 11-router EIGRP topology (R1–R11)
- Netmiko `send_config_set` for deployment
- `configure_eigrp_classic.py`, `verify_eigrp_classic.py`, `troubleshoot_eigrp_classic.py`
- Established the three-file workflow (YAML → Jinja2 → Python) and the CLI contract used by all subsequent modules

---

### Module 03 — OSPF Classic / NAPALM
**Status: COMPLETE**

- 11-router, 2-area OSPF topology (R1–R11)
- Area 0 backbone with multi-access segment `192.1.100.0/24` (R1, R2, R3, R11) — DR/BDR election
- Area 10 stub chain (R8 ABR → R9 → R10)
- R8 configured with `area 0 range 192.1.100.0 255.255.252.0` (inter-area summarization)
- Mixed OSPF authentication: plain-text per-interface, MD5 per-interface, area-level plain-text, area-level MD5
- PPP encapsulation on serial links (R2–R5, R4–R5)
- DR/BDR priority manipulation across two multi-access segments
- Point-to-point network type override on R7–R8 Ethernet link
- NAPALM `load_merge_candidate` / `compare_config` / `commit_config` deployment pattern established
- `configure_ospf_classic.py`, `verify_ospf_classic.py`, `troubleshoot_ospf_classic.py`
- Closing demo: inject config drift → troubleshooter passes, verifier catches it → restore from YAML

**Key lesson established:** The troubleshooter answers "is the protocol working?" The verifier answers "does the device match the source of truth?" Both are needed. A router can be operationally healthy and still be wrong.

---

### Module 04 — OSPF Advanced / NAPALM
**Status: COMPLETE**

- 10-router topology (R1–R10, no R11)
- Multi-area OSPF: Area 0 (backbone), Area 10, Area 20 (NSSA)
- Dual EIGRP redistribution: EIGRP 100 (R1, R7, R8) and EIGRP 111 (R6, R9)
- LSA Type 3 filtering on both ABRs (R2, R3)
- NSSA with `default-information-originate` on R3 (ABR for Area 20)
- OSPF network statement wildcard summarization on R4 (two four-subnet blocks)
- Type 4 / Type 5 / Type 7 LSA propagation mechanics demonstrated
- NAPALM workflow: `load_merge_candidate` / `compare_config` / `commit_config`
- `configure_ospf_advanced.py` — deployed and validated
- `verify_ospf_advanced.py` — deployed and validated
- `troubleshoot_ospf_advanced.py` — deployed and validated
- `utils/push_config.py` — deployed and validated
- `utils/init_ssh.py` — deployed and validated
- `data/ospf_advanced.yaml` — source of truth complete
- `templates/ospf_advanced.j2` — template complete
- `docs/module04_planning.md` — complete
- `docs/module04_preflight.md` — complete
- `docs/module04_verbal_script.md` — complete
- `docs/module04_closing_demo.md` — complete

---

### Module 05 — IPv6 EIGRP + OSPFv3 / Nornir
**Status: IN PROGRESS**

- EIGRPv6 and OSPFv3 Named Mode on 11-router topology
- Nornir task-based parallel deployment
- Tool: Nornir

---

### Module 06 — IS-IS / Nornir
**Status: NOT STARTED**

- IS-IS Named Mode (IPv4 primary topology)
- One IPv6 zone included to reinforce IPv6 concepts from Module 05
- Nornir deployment (same pattern as Module 05)
- Tool: Nornir

---

### Module 07 — BGP Part 1 / Ansible
**Status: NOT STARTED**

- BGP fundamentals — eBGP, iBGP, peering, path selection
- Ansible introduction — playbooks, inventory, idempotent configuration
- NOTE: Module 07 carries both the BGP lesson AND the Ansible introduction.
  The verbal script and planning doc must allocate appropriate time to both.
  The Ansible introduction section may require more time than the BGP content
  in the early part of the lesson.
- Tool: Ansible

---

### Module 08 — BGP Part 2 / Ansible
**Status: NOT STARTED**

- BGP advanced — route reflection, confederations, communities, policy
- Ansible deepening — roles, templates, vault
- Tool: Ansible

---

### Module 09 — Route Policy / Ansible
**Status: NOT STARTED**

- Dedicated route policy and filtering module
- Topics: route maps (match and set clauses), prefix lists, distribute lists,
  administrative distance manipulation, conditional redistribution
- Topology: OSPF core with BGP and EIGRP connections — redistribution boundaries
  at every seam force students to think about policy at each protocol transition
- Detailed topology TBD during module planning
- NOTE: This module addresses a known weak point for engineers.
  It is a curriculum differentiator — give it the depth it deserves.
- Tool: Ansible

---

### Modules 10–12 — Ansible + pyATS/Genie (Two-Act Structure)
**Status: NOT STARTED**

Each module follows a two-act structure:
  Act 1 — Ansible: Teach and deploy a Cisco enterprise technology via Ansible playbooks
  Act 2 — pyATS/Genie: Verify the network that Ansible just built using structured
          parsing and test cases

Module 10 — BGP + MPLS: pyATS/Genie introduction
Module 11 — MPLS VPN: pyATS/Genie deepening
Module 12 — VPN / GRE: pyATS/Genie advanced

The pyATS/Genie progression across three modules gives students:
- Module 10: testbed, basic parsers, first test cases
- Module 11: structured assertions, feature objects, test reporting
- Module 12: advanced patterns, multi-device test suites

The Cisco technology is not subordinate to the tool — it is the foundation
that makes the verification meaningful. Students must understand correct
MPLS VPN / GRE state in order to write meaningful pyATS test cases.

Detailed pyATS/Genie design to be crafted with Claude.ai when Modules 10–12
planning begins.

---

### Module 13 — Multi-site Enterprise Capstone
**Status: PLANNED — not yet designed**

Confirmed components:
- Flask-based change control web interface
- pyATS/Genie verification task (callback to Modules 10–12)
- Multi-site enterprise topology — all tools, all technologies
- Ansible for configuration deployment
- Nornir for targeted operational tasks (TBD)

**Design rule:** This module must not influence the design of Modules 02–12.
Design begins after Module 12 is complete.
Detailed design to be crafted with Claude.ai.

---

## Key Design Decisions and Conventions

- **YAML anchors for credentials:** Default credentials defined once at top of each YAML file with an anchor (`&creds`), referenced per device with an alias (`*creds`). Single point of change.
- **`dns_name` as connection target:** Scripts always connect via DNS name (e.g., `r1.lab`), never OOB IP. Consistent with how the lab DNS server resolves hostnames.
- **OOB interface excluded from rendering:** `Ethernet1/3` is present in the YAML as reference data but the Jinja2 template explicitly skips it. The OOB config is managed by the lab admin, not automation.
- **All unused interfaces present in YAML:** Every Ethernet and Serial interface slot is accounted for, even if unused (description: `UNUSED`, shutdown: `true`). No implied defaults.
- **Merge candidate model:** NAPALM's `load_merge_candidate` is additive — it layers config on top of existing. Does not remove stale config. This is intentional for this curriculum: the automation scripts deploy routing config on top of a pre-loaded base configuration.
- **`write memory` after every commit:** Explicit `cli(["write memory"])` call after `commit_config()` in all NAPALM scripts. IOL does not auto-save.
