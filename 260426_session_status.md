# NAMS26 Session Status — 2026-04-26

## Project Overview

**NAMS26** (Network Automation Management Station 2026) is a 12-module (+Module 13 planned)
network automation video curriculum using Python + Cisco IOL routers in EVE-NG.
Target audience: CCNP-level engineers learning Python-driven network automation.

**Tool progression:** Netmiko (02) → NAPALM (03–04) → Nornir (05–07) → pyATS/Genie (08–09)
→ Ansible (10–12) → Module 13: Advanced Techniques & Practitioner Notes (draft/ideas capture)

**Project root:** `J:\CCIE EI Lab - Q1 2020\NAMS26_V03`
(also: `\\nas01\SynologySync1\CCIE EI Lab - Q1 2020\NAMS26_V03`)

**Git remotes:** `origin` → Gitea at 192.168.1.12:8418 (dev), `github` → GitHub (production)

---

## Session Type

Mixed session — bug fix, standards documentation, content creation. Primary output
is the fully refactored Module 05 verbal script. All changes are uncommitted.

---

## Work Completed This Session

### 1. `ping_hosts.py` — Windows Compatibility Fix (Modules 03, 04, 05)

**Problem:** `ping_hosts.py` used Linux-only ping flags (`-c count`, `-W timeout`).
On Windows, `ping.exe` uses `-n`/`-w` and produces different output — no `"packet loss"`
substring — so all hosts returned FAIL with loss `"unknown"` regardless of reachability.

**Fix applied to:**
- `modules/03_ospf1_napalm/utils/ping_hosts.py`
- `modules/04_ospf2_napalm/utils/ping_hosts.py`
- `modules/05_ipv6_eigrp_ospf_nornir/utils/ping_hosts.py`

**Changes per file:**
- Added `import platform` and `import re`
- Added `platform.system() == "Windows"` branch in `ping()`:
  - Windows: `ping -n <count> -w 2000 <host>`
  - Linux/macOS: `ping -c <count> -W 2 <host>`
- Added Windows packet-loss parsing: look for line containing `"Loss"`,
  extract `(N% loss)` group via regex `r'\((\d+% loss)\)'`

---

### 2. CLAUDE.md Standards Additions

Four new sections added to `CLAUDE.md`:

**Project-Level Documents table** (after Project Root section):

| File | Audience | Purpose |
|------|----------|---------|
| `CLAUDE.md` | Claude Code | Coding standards, architecture, operational guidance |
| `APPENDIX.md` | Students | Reference technology notes and code snippets |

**`ping_hosts.py` entry in `utils/` Standard Scripts table** — updated to:
> "Must use `platform.system()` branching — Windows `ping.exe` uses `-n`/`-w` flags
> and different output format. See Addendum."

**Step 2 (Adding a New Module)** — added two-line warning:
> "`ping_hosts.py` must use `platform.system() == 'Windows'` branching.
> Do not copy raw `-c`/`-W` Linux flags into a new module without this guard."

**Module 13 section** — "Advanced Techniques & Practitioner Notes":
- Status: Draft / Ideas Capture
- Holding area for techniques that emerged during Modules 02–12 but didn't fit any single module
- May crystallize into one or more full lab modules, or remain as a standalone reference chapter
- Draft Topics:
  - `[ ] Router Descriptions Script` — noted during Module 05 verbal script review (2026-04-26)

**Addendum section** — "Discovered Quirks and Fixes":
- `ping_hosts.py` — Windows ping compatibility (discovered Module 05, 2026-04-25)
- Full reproduction steps, root cause, and fix documented

**Module 13 row** added to Tool-per-Module table:
```
| 13 | TBD | Advanced Techniques & Practitioner Notes — draft/ideas capture |
```

---

### 3. APPENDIX.md Created

`APPENDIX.md` created at project root — student-facing reference document.

Ten skeleton sections, each currently `*(Draft notes and snippets go here.)*`:
1. Python & General Patterns
2. Netmiko
3. NAPALM
4. Nornir
5. pyATS / Genie
6. Ansible
7. Jinja2 Templates
8. YAML Device Inventory
9. IOS Command Reference
10. Troubleshooting Reference

Intended to be filled in progressively as modules are completed. Cross-referenced in
`CLAUDE.md` Project-Level Documents table.

---

### 4. DNS Suffix Search List (Partial Fix)

**Problem:** `ping r1` (short name) failed DNS resolution. Only `ping r1.lab` (FQDN) worked.
Scripts already use FQDN (`r1.lab`) so this was not blocking anything.

**Attempted fix:** Set Windows DNS search list via registry:
```powershell
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" `
  -Name "SearchList" -Value "lab"
```

Registry write succeeded. `ipconfig /all` confirmed `lab` in `DNS Suffix Search List`.

**Deferred:** `Restart-Service Dnscache` fails — Dnscache is a protected Windows 10
service. Change will take effect on next system reboot. Short-name resolution (`ping r1`)
is not used in any project scripts; this fix is quality-of-life only.

**Not blocking any module work.**

---

### 5. Module 05 Topology Diagram

`modules/05_ipv6_eigrp_ospf_nornir/diagrams/module05_topology_ipv6_eigrp_ospf.drawio`
created. Nine-router topology, blue background, Cisco router icons, consistent with
Module 04 diagram style.

User has since modified the diagram in draw.io. Current diagram on disk reflects
user edits.

---

### 6. Module 05 Verbal Script — Full Refactor

**File:** `modules/05_ipv6_eigrp_ospf_nornir/verbal_script/module05_verbal_script.md`

Refactored from a partially stubbed draft to fully written prose matching Module 02 style.
All 8 sections complete — no placeholder stubs remain.

**Section summaries:**

| Section | Content |
|---------|---------|
| 1 — Objectives | Conversational intro; two changes (IPv6 + Nornir); module deliverables |
| 2 — Topology | Nine routers; Area 0/10/20 with addresses; EIGRP AS 100/111; explicit router-ID requirement for IPv6-only nodes |
| 3 — Nornir Overview | Three jobs (inventory, parallel dispatch, result aggregation); merge vs replace; `netmiko_send_config` = merge; Instructor demo: manual EIGRP process survives re-run |
| 4 — Configuration | Full walkthrough of YAML (5 callouts), template (4 callouts), configure script (7 callouts incl. Nornir inventory construction, `nr.run()`, temp dir cleanup) |
| 5 — Verification | Four check categories: `neighbors`, `routes`, `redistribution`, `areas`; what each check examines and what it catches |
| 6 — Troubleshooting | Three check categories: `neighbors`, `process`, `routes`; key distinction: troubleshoot = "is the protocol working?", verify = "does it match the YAML?" |
| 7 — Closing Demo | Scenario A (R1 EIGRP→OSPF redistribution removed); Parts 1–5; "The Bigger Conversation" — what Nornir adds/doesn't add vs NAPALM; module progression table |
| 8 — Objectives Review | Each objective individually confirmed; module progression table; tease of Module 8 (pyATS/Genie) |

**Key talking points documented:**
- `ospf_area: 0` is falsy in Jinja2 — guard must use `is not none and != ""` not `{% if intf.ospf_area %}`
- `netmiko_send_config` is a merge operation — additive, no `no` commands, does not enforce complete intended state
- Nornir adds parallel execution and inventory abstraction; does not add config enforcement or structured parsing
- Troubleshoot vs verify: different questions, different tools — closing demo makes this concrete

**File retains draft name** (`module05_verbal_script.md` not `_final`) per CLAUDE.md
convention — rename to `_final` when content is validated against live lab.

---

## Git State

**Branch:** `main` — up to date with `origin/main` (Gitea)

**Uncommitted changes (modified):**
- `.claude/settings.local.json`
- `CLAUDE.md`
- `modules/03_ospf1_napalm/utils/ping_hosts.py`
- `modules/04_ospf2_napalm/utils/ping_hosts.py`
- `modules/05_ipv6_eigrp_ospf_nornir/utils/ping_hosts.py`

**Untracked (new this session or prior, not yet staged):**
- `260425b_session_status.md` (prior session — not yet committed)
- `260426_session_status.md` (this file)
- `APPENDIX.md`
- `_pdf_reference/`
- `modules/05_ipv6_eigrp_ospf_nornir/05_ios_configs/SCRATCH.txt`
- `modules/05_ipv6_eigrp_ospf_nornir/diagrams/` (topology diagram)
- `modules/05_ipv6_eigrp_ospf_nornir/verbal_script/` (verbal script)

**Last commit:** `20affd5` — "docs: add Module 13 placeholder — change control web interface capstone"
(from session 260425b — sitting local on Gitea `origin/main`)

**No commit made this session.**

---

## Module Status

| Module | Topic | Tool | Status |
|--------|-------|------|--------|
| 02 | EIGRP Classic | Netmiko | COMPLETE |
| 03 | OSPF Classic | NAPALM | COMPLETE |
| 04 | OSPF Advanced | NAPALM | COMPLETE — verbal script draft pending `_final` rename |
| 05 | IPv6 EIGRP + OSPFv3 | Nornir | Partial — configure script + YAML + diagram + verbal script draft done; verify/troubleshoot stubs; untested against live lab |
| 06–12 | — | Various | NOT STARTED |
| 13 | Advanced Techniques | TBD | PLANNED — draft/ideas capture only |

---

## Outstanding / Next Steps

### Immediate

1. **Git commit** — stage and commit this session's work:
   ```bash
   git add CLAUDE.md APPENDIX.md
   git add modules/03_ospf1_napalm/utils/ping_hosts.py
   git add modules/04_ospf2_napalm/utils/ping_hosts.py
   git add modules/05_ipv6_eigrp_ospf_nornir/utils/ping_hosts.py
   git add modules/05_ipv6_eigrp_ospf_nornir/diagrams/
   git add modules/05_ipv6_eigrp_ospf_nornir/verbal_script/
   git add 260425b_session_status.md 260426_session_status.md
   git commit -m "Module 05 — verbal script, topology diagram, ping fix; CLAUDE.md Addendum + Module 13"
   ```

2. **Push to Gitea** (`origin`):
   ```bash
   git push origin main
   ```

3. **DNS suffix** — short-name resolution (`ping r1`) will activate after next system reboot.
   Not blocking.

### Module 05 — Complete Implementation

4. **Install Nornir packages** (if not already on system Python):
   ```bash
   pip install nornir nornir-netmiko nornir-utils netmiko pyyaml jinja2
   ```

5. **Dry-run** — render and review all 9 device configs:
   ```bash
   python modules/05_ipv6_eigrp_ospf_nornir/scripts/configure_ipv6_eigrp_ospf.py --dry-run
   ```

6. **Live deploy** (requires EVE-NG lab running, pre-flight complete):
   ```bash
   bash modules/05_ipv6_eigrp_ospf_nornir/utils/clear_known_hosts.sh
   python modules/05_ipv6_eigrp_ospf_nornir/utils/init_ssh.py
   python modules/05_ipv6_eigrp_ospf_nornir/utils/ping_hosts.py
   python modules/05_ipv6_eigrp_ospf_nornir/scripts/configure_ipv6_eigrp_ospf.py
   ```

7. **Implement `verify_ipv6_eigrp_ospf.py`** — Nornir-based, `--check` choices:
   `neighbors`, `routes`, `redistribution`, `areas`

8. **Implement `troubleshoot_ipv6_eigrp_ospf.py`** — Nornir-based, `--check` choices:
   `neighbors`, `process`, `routes`

9. **Complete `docs/module05_closing_demo.md`** — validate fault injection scenarios A and B
   against live lab; replace PLACEHOLDER content

10. **Rename verbal script** to `module05_verbal_script_final.md` after scripts are
    validated and closing demo is confirmed working

### Carry-Forward

11. **Module 04 verbal script** — `module04_verbal_script.md` still draft. Review and rename
    to `module04_verbal_script_final.md` when approved.

12. **APPENDIX.md** — fill in sections progressively as modules are completed. Start with
    Nornir (Section 4) after Module 05 is done.

13. **Module 13 — Router Descriptions Script** — deferred idea noted in CLAUDE.md Draft Topics.
    Return to this after Module 12 is complete.

---

## Key Standards (apply to all modules)

- **Path resolution:** 4-level `__file__` chain: `SCRIPT_DIR → MODULE_DIR → MODULES_DIR → PROJECT_ROOT`
- **LOG_DIR:** always `os.path.join(MODULE_DIR, "logs")` — never PROJECT_ROOT or MODULES_DIR
- **NAPALM on IOL:** `dest_file_system: "nvram:"` + `inline_transfer: True`; Module 04+: also `enable_scp: False`
- **YAML speed/duplex:** active Ethernet → `speed: 100` (unquoted int), `duplex: full`; all others `""`
- **Code comments:** non-obvious variables — `# Description. / # Current: X   Range: min – max`
- **OOB interface:** `Ethernet1/3` — reference only in YAML, never rendered by templates
- **`write memory`** after every config push (IOL does not auto-save)
- **Lab pre-flight** after every EVE-NG Wipe+Start: `clear_known_hosts.sh` → `init_ssh.py` → `ping_hosts.py`
- **Verbal script log paths:** always `modules/NN_name_tool/logs/` — never "project-level logs/" or "modules/logs/"
- **`ping_hosts.py`:** must use `platform.system() == "Windows"` branching in every module — apply at copy time

---

*Session 260426 — bug fix, documentation, Module 05 verbal script refactor — NAMS26_V03*
