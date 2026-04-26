# NAMS26 — Project Status Report

**Date:** 2026-04-26
**Scope:** All modules (01–12) and project-level deliverables
**Basis:** File-system audit + session notes `260426_session_status.md` / `260426b_session_status.md`

---

## Module Completion Summary

| Module | Topic | Tool | Status |
|--------|-------|------|--------|
| 01 | Introduction | — | Stub (README only — intentional placeholder) |
| 02 | EIGRP Classic | Netmiko | **Complete** — minor gaps flagged below |
| 03 | OSPF Classic | NAPALM | **Complete** — minor gaps flagged below |
| 04 | OSPF Advanced | NAPALM | **Complete** — verbal script awaiting `_final` rename |
| 05 | IPv6 EIGRP + OSPFv3 | Nornir | **In Progress** — configure + YAML + docs done; verify/troubleshoot stubs; untested against live lab |
| 06 | IPv6 IS-IS | Nornir | **Not Started** — ios_configs only; no scaffold |
| 07 | IS-IS | Nornir | **Not Started** — README + empty utils only; ios_configs dir misnamed |
| 08 | BGP (Part 1) | pyATS/Genie | **Not Started** — README + empty utils only; ios_configs dir misnamed |
| 09 | BGP (Part 2) | pyATS/Genie | **Not Started** — README + empty utils only; ios_configs dir misnamed |
| 10 | BGP + MPLS | Ansible | **Not Started** — README + empty utils only; ios_configs dir misnamed |
| 11 | MPLS VPN | Ansible | **Not Started** — README + empty utils only; ios_configs dir misnamed |
| 12 | VPN / GRE | Ansible | **Not Started** — README + empty utils only; ios_configs dir misnamed |
| 13 | Advanced Techniques | TBD | **Planned** — ideas captured in CLAUDE.md; no directory |

---

## Deliverables Gap Table (Modules 02–07)

> Modules 08–12 are identical to Module 07's profile — all rows MISSING except README and utils/.gitkeep.

| Item | 02 | 03 | 04 | 05 | 06 | 07 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| `NN_ios_configs/` (populated) | empty | OK | OK | OK | partial | empty |
| `configs/.gitkeep` | OK | missing | OK | OK | missing | missing |
| `data/*.yaml` | OK | OK | OK | OK | missing | missing |
| `diagrams/` (drawio + svg) | OK | OK | OK | OK | missing | missing |
| `docs/eve-ng_lab_reset_sop.md` | ref | ref | ref | ref | missing | missing |
| `docs/moduleNN_planning.md` | OK | OK | OK | OK | missing | missing |
| `docs/moduleNN_closing_demo.md` | OK | OK | OK | OK | missing | missing |
| `logs/.gitkeep` | **MISSING** | **MISSING** | **MISSING** | OK | missing | missing |
| `README.md` | OK | OK | OK | OK | stub | stub |
| `scripts/configure_*.py` | OK | OK | OK | OK | missing | missing |
| `scripts/verify_*.py` | OK | OK | OK | **stub** | missing | missing |
| `scripts/troubleshoot_*.py` | OK | OK | OK | **stub** | missing | missing |
| `templates/*.j2` | OK | OK | OK | OK | missing | missing |
| `utils/` (all 4 scripts) | OK | OK | OK | OK | empty | empty |
| `verbal_script/moduleNN_verbal_script_final.md` | OK | OK | **draft** | **draft** | missing | missing |

> **ref** — file replaced with single-line reference to `docs/eve-ng_lab_reset_sop.md`
> **stub** — file exists but contains placeholder/skeleton code only
> **draft** — file exists with `_final` suffix missing; pending live lab validation
> **partial** — directory exists with some raw configs but not a complete capture
> **empty** — directory or .gitkeep placeholder exists; no content

---

## Deliverables Complete

### Project Level
- `README.md` — rewritten to standard (module progression table, prerequisites, how-to-use, AI acknowledgment)
- `APPENDIX.md` — populated: Sections 2 (Netmiko), 3 (NAPALM), 4 (Nornir), 7 (Jinja2), 8 (YAML), 11 (Credential Security), 12 (OSPF Reference)
- `CLAUDE.md` — comprehensive standards including: path resolution, timing params, NAPALM IOL args, interface standards, `configs/` date-stamp, Named Mode transition, EIGRP redistribution metric, Module 04 as reference standard, README standard, EVE-NG instructor note
- `docs/publication_sop.md` — placed at correct location
- `docs/eve-ng_lab_reset_sop.md` — consolidated SOP covering all modules
- `docs/structure_normalization_report.md` — historical audit (2026-04-06)
- `docs/style_guide.md`, `docs/git_reference_nams26.md` — reference documents

### Module 02 — EIGRP / Netmiko
- Full script set (configure, verify, troubleshoot) + template + YAML
- All `docs/` standard files (planning, closing_demo, sop reference)
- `verbal_script/module02_verbal_script_final.md`
- `diagrams/module02_topology_eigrp_classic.drawio` + `.svg`
- `utils/ping_hosts.py` — Windows platform branching applied
- README written to Module 04 standard

### Module 03 — OSPF Classic / NAPALM
- Full script set + template + YAML + ios_configs (11 routers)
- All `docs/` standard files
- `verbal_script/module03_verbal_script_final.md`
- `diagrams/module03_topology_ospf_classic.drawio` + `.svg`
- README written to Module 04 standard
- `configure_ospf_classic.py` — `global_delay_factor: 2.0` added to `optional_args`

### Module 04 — OSPF Advanced / NAPALM (Reference Standard)
- Full script set + template + YAML + ios_configs (10 routers)
- All `docs/` standard files (planning, closing_demo, sop reference) — closing demo enhanced with drift detection block + instructor notes
- `diagrams/module04_topology_ospf_advanced.drawio` + `.svg`
- `verify_ospf_advanced.py` — `emit_drift()` helper + structured FAIL logging on all redistribution paths
- `utils/module04_ospf_topology_map.py`
- README written to standard (becomes Module 04 template)

### Module 05 — IPv6 EIGRP + OSPFv3 / Nornir
- `configure_ipv6_eigrp_ospf.py` — fully implemented
- `data/ipv6_eigrp_ospf.yaml` — complete device inventory
- `templates/ipv6_eigrp_ospf.j2` — Jinja2 template with IPv6 syntax
- `diagrams/module05_topology_ipv6_eigrp_ospf.drawio` + `.svg`
- All `docs/` standard files (planning full rewrite to Module 04 structure, closing_demo, sop reference)
- Full `utils/` set (init_ssh, check_ssh, clear_known_hosts, ping_hosts, push_config)
- `verbal_script/module05_verbal_script.md` — draft complete
- README rewritten to standard

---

## Deliverables Outstanding

### Immediate — Active Work (Module 05)

| # | Item | Notes |
|---|------|-------|
| 1 | `scripts/verify_ipv6_eigrp_ospf.py` — implement | Currently a stub; must match Module 04 verify pattern |
| 2 | `scripts/troubleshoot_ipv6_eigrp_ospf.py` — implement | Currently a stub |
| 3 | `docs/module05_closing_demo.md` — complete | Current content is placeholder; needs fault injection output from live lab |
| 4 | Live lab test — configure script end-to-end | EVE-NG reset required; untested |
| 5 | Confirm R4 dual-ABR role (Area 10 ↔ 20) | Based on YAML header comment only; verify against running lab |
| 6 | Rename to `module05_verbal_script_final.md` | After live lab validation |

### Near-Term — Structural Fixes (no content authoring)

| # | Item | Affected |
|---|------|---------|
| 7 | Create `logs/.gitkeep` | Modules 02, 03, 04 |
| 8 | Rename `module04_verbal_script.md` → `module04_verbal_script_final.md` | Module 04 — after live lab validation of closing demo |
| 9 | Delete root `publication_sop.md` | Project root — duplicate artifact; committed copy is at `docs/publication_sop.md` |
| 10 | Rename `NN_ios_configs/` directories in Modules 07–12 | All are off-by-one: `06_ios_configs` in Module 07, `07_ios_configs` in Module 08, etc. |
| 11 | Add `configs/.gitkeep` to Module 03 (and 06) | Ensures clean-clone creates the directory |
| 12 | Refactor Module 02 `ping_hosts.py` HOSTS dict to load from YAML | Low priority — functional as-is; inconsistent with Modules 03–05 |

### Content Authoring — Future Modules

| # | Item | Scope |
|---|------|-------|
| 13 | Full scaffold (data, diagrams, docs, scripts, templates, verbal_script, logs) | Module 06 |
| 14 | Full scaffold from scratch | Modules 07–12 |
| 15 | APPENDIX.md — Sections 1, 5, 6, 9, 10 | Fill progressively as modules are completed |
| 16 | Module 13 directory + draft planning doc | After Module 12 complete |

---

## On The Radar

Issues that don't block current work but warrant attention:

| Issue | Detail | Priority |
|-------|--------|----------|
| Module 02 `ping_hosts.py` HOSTS dict hard-coded | Lists R1–R6 only; other modules load from YAML. Functional as-is. | Low |
| Module 02 Jinja2 template speed/duplex guard | Not verified during normalization session — confirm `eigrp_classic.j2` has the guard | Low |
| Module 03 `configs/` may contain committed rendered configs | Pre-dates gitignore convention; if so, should be removed before GitHub push | Medium — pre-publication |
| Module 04 `docs/config_review_notes.md` | Ad-hoc working file; not part of the standard three docs; consider removing or archiving | Low |
| Root session status files (260424–260426) | Internal artifacts at project root — not committed but creating noise | Housekeeping |
| `nams26_workflow_migration.md` at project root | Appears committed; purpose unclear relative to docs/ | Clarify / move |
| Named Mode requirement from Module 06 | All Modules 06+ must use EIGRP Named Mode / OSPFv3 Named Mode — no classic mode | Standards enforcement |
| Module 13 has no directory yet | CLAUDE.md documents it; no scaffold created | Deferred until Module 12 complete |

---

## Git State

**Branch:** `main` — 3 commits ahead of start-of-session baseline; up to date with `origin` (Gitea).

**Uncommitted (internal artifacts — do not commit):**
- `260426_cos_instructions.md`, `260426b_session_status.md`, `260426_session_status.md`
- `260426 - project restructuring and refinement.txt`
- `publication_sop.md` (root duplicate)
- `_pdf_reference/`
- `modules/05_ipv6_eigrp_ospf_nornir/05_ios_configs/SCRATCH.txt`

**Not pushed to GitHub** — all commits are Gitea (`origin`) only per standing protocol.
