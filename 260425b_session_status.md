# NAMS26 Session Status — 2026-04-25b

## Project Overview

**NAMS26** (Network Automation Management Station 2026) is a 12-module (+Module 13 planned) network automation video curriculum using Python + Cisco IOL routers in EVE-NG. Target audience: CCNP-level engineers learning Python-driven network automation.

**Tool progression:** Netmiko (02) → NAPALM (03–04) → Nornir (05–07) → pyATS/Genie (08–09) → Ansible (10–12) → Flask (13)

**Project root:** `J:\CCIE EI Lab - Q1 2020\NAMS26_V03`
(also: `\\nas01\SynologySync1\CCIE EI Lab - Q1 2020\NAMS26_V03`)

**Git remotes:** `origin` → Gitea at 192.168.1.12:8418 (dev), `github` → GitHub (production)

---

## Session Type

Documentation and standards session — no module code written. All changes are to project-level docs, standards files, and YAML source-of-truth data.

---

## Work Completed This Session

### 1. Verbal Script Log Path Fix (Carry-over from 260425a)

`modules/02_eigrp_netmiko/verbal_script/module02_verbal_script_final.md`

Two incorrect log path references corrected:
- `"written to the project-level \`logs/\` directory"` → `"written to \`modules/02_eigrp_netmiko/logs/\`"`
- `"in \`modules/logs/\`"` → `"in \`modules/02_eigrp_netmiko/logs/\`"`

---

### 2. CLAUDE.md Standards Additions

Four new standards blocks added to `CLAUDE.md`:

**Code Commenting Standard** (after Code Formatting section):
```
Non-obvious variables must document three things: current setting, purpose, and valid range.
Format:
# Short description.
# Current: X   Range: min – max
"variable_name": value,
```

**Netmiko Timing Parameters** table (global_delay_factor, delay_factor, conn_timeout):
- `global_delay_factor`: multiplies ALL internal Netmiko delays (connection-wide). Typical: 2 for lab, 4+ for slow devices.
- `delay_factor`: per-`send_command`, stacks multiplicatively with `global_delay_factor`. Typical: 2.
- `conn_timeout`: TCP handshake only. Does not affect command timing. Typical: 10–30 s.

**LOG_DIR wrong-pattern warnings** (under Path Resolution):
```python
# WRONG — logs go to project root, not the module
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# WRONG — os.path.dirname(MODULE_DIR) is MODULES_DIR, one level too high
LOG_DIR = os.path.join(os.path.dirname(MODULE_DIR), "logs")

# CORRECT
LOG_DIR = os.path.join(MODULE_DIR, "logs")
```

**NAPALM `enable_scp: False`** (under NAPALM / Cisco IOL Compatibility):
```python
optional_args = {
    "ssh_config_file":  None,
    "session_log":      session_log_path,
    "dest_file_system": "nvram:",
    "inline_transfer":  True,
    "enable_scp":       False,   # Module 04+ only — belt-and-suspenders
}
```

**Verbal Script Log Path Standard** (under File Naming Conventions):
```
WRONG:  "A timestamped session log is written to the project-level logs/ directory"
WRONG:  "All output is mirrored to a timestamped log file in modules/logs/"
CORRECT: "A timestamped session log is written to modules/02_eigrp_netmiko/logs/"
         (substitute the correct module path for each module)
```

Interface Standards table: added note that `speed: 100` must be unquoted YAML integer (not `"100"`).

---

### 3. YAML Speed/Duplex Normalization

Updated active Ethernet interface entries to project standard (`speed: 100`, `duplex: full`).

| File | Change |
|------|--------|
| `modules/02_eigrp_netmiko/data/eigrp_classic.yaml` | 12 active Ethernet interfaces: `speed: ""` → `speed: 100`, `duplex: ""` → `duplex: full` |
| `modules/03_ospf1_napalm/data/ospf_classic.yaml` | Already correct — no changes needed |
| `modules/04_ospf2_napalm/data/ospf_advanced.yaml` | `replace_all`: `speed: "100"` → `speed: 100` (normalized quoted string to unquoted integer) |
| `modules/05_ipv6_eigrp_ospf_nornir/data/ipv6_eigrp_ospf.yaml` | Same `replace_all` normalization as Module 04 |

Unused Ethernet, Serial, Loopback, and OOB interfaces with `speed: ""` / `duplex: ""` were left unchanged.

---

### 4. Module Count Update (11 → 12)

Module count updated across 9 files to reflect the current 12-module scope:

| File | Change |
|------|--------|
| `CLAUDE.md` | "11-module" → "12-module"; "All 11 modules" → "All 12 modules"; tool table ranges updated |
| `README.md` | "eleven-module" → "twelve-module"; module table updated with Module 12 row; Ansible ref updated |
| `NAMS26_context.md` | "11-module" → "12-module"; "Modules 05–11" → "Modules 05–12"; tool table updated |
| `modules/02_eigrp_netmiko/verbal_script/module02_verbal_script_final.md` | Tool progression table rows updated |
| `modules/02_eigrp_netmiko/docs/module02_closing_demo.md` | Tool progression table rows updated |
| `modules/03_ospf1_napalm/verbal_script/module03_verbal_script_final.md` | Tool progression table rows updated |
| `modules/03_ospf1_napalm/docs/module03_closing_demo.md` | Tool progression table rows updated |
| `modules/04_ospf2_napalm/verbal_script/module04_verbal_script.md` | Tool progression table rows updated |

Tool progression table rows updated in all files: `05–06` → `05–07` (Nornir), `07–08` → `08–09` (pyATS), `09–11` → `10–12` (Ansible).

Historical audit docs (`docs/structure_normalization_report.md`, `docs/structure_normalization_review_2026-04-07.md`) were intentionally left unchanged — they are point-in-time records.

---

### 5. Module 13 Placeholder Added to NAMS26_context.md

- `| 13 | Flask | Change Control Web Interface + Utilities |` row added to tool progression table
- Module 13 detail section added (Status: PLANNED — not yet designed):
  - Flask-based change control web interface candidate features
  - Design rule: must not influence Modules 02–12; design begins after Module 12 is complete

---

### 6. Git Commit

All changes bundled into a single commit:

```
commit 20affd5
"Standards session — CLAUDE.md additions, YAML normalization, module count 11→12, Module 13 placeholder"
```

**97 files changed.**

---

## Current State

| Area | State |
|------|-------|
| CLAUDE.md | Up to date — all session standards incorporated |
| NAMS26_context.md | Up to date — 12 modules + Module 13 placeholder |
| Module 02 YAML | Normalized — speed/duplex correct |
| Module 03 YAML | Already correct |
| Module 04 YAML | Normalized — speed values unquoted integers |
| Module 05 YAML | Normalized — speed values unquoted integers |
| Commit 20affd5 | Local only |
| Gitea push | FAILED — authentication not cached |
| GitHub push | NOT YET — requires Claude.ai review before any push |

---

## Module Status

| Module | Topic | Tool | Status |
|--------|-------|------|--------|
| 02 | EIGRP Classic | Netmiko | COMPLETE |
| 03 | OSPF Classic | NAPALM | COMPLETE |
| 04 | OSPF Advanced | NAPALM | COMPLETE |
| 05 | IPv6 EIGRP + OSPFv3 | Nornir | Partial — configure script + YAML done; verify/troubleshoot stubs; untested |
| 06–12 | — | Various | NOT STARTED |
| 13 | Flask / Change Control | Flask | PLANNED |

---

## Outstanding / Next Steps

### Immediate (before next development session)

1. **Push to Gitea** — run manually from the NMS workstation:
   ```bash
   git config credential.helper store   # optional — caches credentials going forward
   git push origin main
   ```
   Commit `20affd5` is sitting local-only. All of this session's work is uncommitted to Gitea.

2. **GitHub push** — pending Claude.ai review and approval per standing protocol.

### Module 05 — Resume Development

3. **Install Nornir packages** into the project Python environment:
   ```
   pip install nornir nornir-netmiko nornir-utils netmiko pyyaml jinja2
   ```

4. **Run dry-run** and review all 9 rendered configs:
   ```bash
   python modules/05_ipv6_eigrp_ospf_nornir/scripts/configure_ipv6_eigrp_ospf.py --dry-run
   ```

5. **Live deploy and verify** (requires EVE-NG lab running, pre-flight complete):
   ```bash
   bash modules/05_ipv6_eigrp_ospf_nornir/utils/clear_known_hosts.sh
   python modules/05_ipv6_eigrp_ospf_nornir/utils/init_ssh.py
   python modules/05_ipv6_eigrp_ospf_nornir/utils/ping_hosts.py
   python modules/05_ipv6_eigrp_ospf_nornir/scripts/configure_ipv6_eigrp_ospf.py
   ```

6. **Implement `verify_ipv6_eigrp_ospf.py`** — Nornir-based; `--check` choices: `neighbors`, `routes`, `redistribution`, `areas`.

7. **Implement `troubleshoot_ipv6_eigrp_ospf.py`** — Nornir-based; `--check` choices: `neighbors`, `process`, `routes`.

8. **Module 04 verbal script** — proof-read `module04_verbal_script.md`, rename to `module04_verbal_script_final.md` when approved.

---

## Key Standards (apply to all modules)

- **Path resolution:** 4-level `__file__` chain: `SCRIPT_DIR → MODULE_DIR → MODULES_DIR → PROJECT_ROOT`
- **LOG_DIR:** always `os.path.join(MODULE_DIR, "logs")` — not PROJECT_ROOT or MODULES_DIR
- **NAPALM on IOL:** `dest_file_system: "nvram:"` + `inline_transfer: True`; Module 04+: also `enable_scp: False`
- **YAML speed/duplex:** active Ethernet → `speed: 100` (unquoted int), `duplex: full`; everything else `speed: ""` / `duplex: ""`
- **Code comments:** non-obvious variables — `# Description. / # Current: X   Range: min – max`
- **OOB interface:** Ethernet1/3 — reference only in YAML, never rendered by templates
- **`write memory`** after every config push (IOL does not auto-save)
- **Lab pre-flight** after every EVE-NG Wipe+Start: `clear_known_hosts.sh` → `init_ssh.py` → `ping_hosts.py`
- **Verbal script log paths:** always `modules/NN_name_tool/logs/` — never "project-level logs/" or "modules/logs/"

---

*Session 260425b — documentation/standards only — NAMS26_V03*
