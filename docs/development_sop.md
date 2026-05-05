# NAMS26 — Module Development SOP
## Sequential Steps — Owner Reference
### `docs/development_sop.md` — Project Root Level

---

> **Document Purpose**
> This SOP defines the ordered steps for developing each NAMS26 module
> from initial topology design through development phase close. Follow
> these steps in sequence for every module.
>
> **This document is an internal production reference — it is NOT published
> to the Final Product GitHub Repository.**

---

## Owner Key

| Label | Role |
|-------|------|
| **Tom** | Lab work, instructor decisions, script execution |
| **CoS** | Claude Code — file generation and execution only |
| **Claude.ai** | Planning, review, and CoS instruction authoring |

---

## Phase 1 — Lab and Topology Design

| # | Step | Owner |
|---|------|-------|
| 1.1 | Design logical topology for the module. Decide which routers participate, protocol configuration, and areas/AS numbers. | Tom |
| 1.2 | Build topology in EVE-NG. Apply base configs to all routers via console. Generate RSA keys. | Tom |
| 1.3 | Run pre-flight sequence: `clear_known_hosts.sh` → `init_ssh.py` → `ping_hosts.py`. Confirm all routers reachable. | Tom |
| 1.4 | Capture running configs from all routers into `modules/NN_name_tool/NN_ios_configs/`. | Tom |
| 1.5 | Planning session with Claude.ai — review topology, confirm module scope, tool, protocol coverage, and any special design decisions. Claude.ai produces serialized CoS instruction file for scaffold and initial files. | Claude.ai + Tom |

---

## Phase 2 — Scaffold and Data Files

| # | Step | Owner |
|---|------|-------|
| 2.1 | CoS executes scaffold instruction — creates module directory structure with `.gitkeep` placeholders. Copies `utils/` from previous module and adapts for new module. | CoS |
| 2.2 | CoS reads `NN_ios_configs/` and generates `data/moduleNN.yaml` — full device inventory including interfaces, loopbacks, and protocol configuration. | CoS |
| 2.3 | Claude.ai reviews YAML. Issues correction instructions if needed. Iterate until YAML matches topology exactly. | Claude.ai + Tom |

---

## Phase 3 — Template and Scripts

| # | Step | Owner |
|---|------|-------|
| 3.1 | CoS generates Jinja2 template (`templates/moduleNN.j2`) from YAML. | CoS |
| 3.2 | CoS generates configure script (`scripts/configure_moduleNN.py`) — dry-run and live modes, CLI contract, path resolution standard. | CoS |
| 3.3 | CoS generates verify script (`scripts/verify_moduleNN.py`) — per-device PASS/WARN/FAIL output, Verification Detail and Summary sections, timestamped logs. | CoS |
| 3.4 | CoS generates troubleshoot script (`scripts/troubleshoot_moduleNN.py`) — Troubleshooting Detail and Summary sections, timestamped logs. | CoS |
| 3.5 | Claude.ai reviews all three scripts. Issues correction instructions if needed. Iterate until scripts match project standards. | Claude.ai + Tom |

---

## Phase 4 — Live Lab Validation

| # | Step | Owner |
|---|------|-------|
| 4.1 | Run configure script in dry-run mode. Review rendered configs. Report output to Claude.ai if corrections needed. | Tom |
| 4.2 | Run configure script live against all routers. Report output to Claude.ai if errors occur. | Tom |
| 4.3 | Run verify script against all routers. All checks must PASS or INFO — no FAILs on clean topology. Report full output to Claude.ai. | Tom |
| 4.4 | Run troubleshoot script against all routers. Confirm clean PASS on all checks. Report full output to Claude.ai. | Tom |
| 4.5 | Claude.ai reviews all script output. Issues CoS correction instructions if needed. Iterate until clean. | Claude.ai + Tom |

---

## Phase 5 — Verbal Script and Topology Map

| # | Step | Owner |
|---|------|-------|
| 5.1 | Claude.ai produces CoS instructions to generate verbal script draft. Based on Module 04 verbal script as template; technology-specific content from planning session notes. | Claude.ai |
| 5.2 | CoS generates `verbal_script/moduleNN_verbal_script.md` per instructions. Note: file is NOT renamed to `_final` until Step 6.3. | CoS |
| 5.3 | CoS generates topology map draft in `.drawio` XML format. | CoS |
| 5.4 | Tom refines `.drawio` in draw.io application. Exports `.drawio.svg` for documentation. Exports `.png` for Claude.ai review. | Tom |

---

## Phase 6 — Closing Demo and Review

| # | Step | Owner |
|---|------|-------|
| 6.1 | Tom walks through verbal script against live lab. Tests fault injection sequence end-to-end: inject → troubleshoot → verify → restore. Reports output to Claude.ai. | Tom |
| 6.2 | Claude.ai reviews closing demo output. Issues CoS correction instructions for verbal script and `docs/moduleNN_closing_demo.md` as needed. Iterate until closing demo sequence is validated. | Claude.ai + Tom |
| 6.3 | CoS renames verbal script to `_final`: `moduleNN_verbal_script_final.md`. | CoS |

---

## Phase 7 — Documentation Review

| # | Step | Owner |
|---|------|-------|
| 7.1 | Claude.ai reviews `docs/moduleNN_planning.md` — confirm it accurately reflects the completed module. Issue CoS corrections as needed. | Claude.ai |
| 7.2 | CoS sweeps verbal script and closing demo for: backslash continuations, `python3` references, bash operators. Fixes any violations found. | CoS |
| 7.3 | CoS checks all curriculum progression tables in module docs against authoritative table in `README.md`. Fixes any outdated references. | CoS |

---

## Phase 8 — Development Phase Close

| # | Step | Owner |
|---|------|-------|
| 8.1 | CoS produces `session_status.md` documenting all work completed, commits, and any outstanding items. | CoS |
| 8.2 | Claude.ai reviews session status. Confirms module development phase complete or flags outstanding items for resolution. | Claude.ai |
| 8.3 | All commits pushed to Gitea (`origin`). Do NOT push to GitHub — GitHub push is a project-completion event, not a module-completion event. | CoS |

---

## Standards Reference

All steps must comply with:
- **Path resolution:** Four-level chain from `__file__` (see `CLAUDE.md`)
- **CLI contract:** `--dry-run`, `--router`, `--check` flags on all scripts
- **Interface standards:** Active/unused/OOB as defined in `CLAUDE.md`
- **YAML anchors:** Credentials defined once with `&creds` anchor
- **Log directory:** `modules/NN_name_tool/logs/` — never project root
- **Commit messages:** Descriptive, module-prefixed
- **Terminal commands:** Single line, no backslash continuation, `python` not `python3`

---

## Quick Reference — Pre-Flight Sequence

Run in this order after every EVE-NG Wipe+Start:

```
bash utils/clear_known_hosts.sh
python utils/init_ssh.py
python utils/ping_hosts.py
```

---

---

## Production Phase

Video recording, student guide authoring, GitHub publication, and YouTube
publishing are governed by `docs/production_sop.md` — to be authored after
Module 12 development is complete. The production phase runs once across all
modules, not per-module.

See `docs/publication_sop.md` for the current pre-production checklist
framework.

---

*NAMS26 — Network Automation Management Station 2026*
*Module Development SOP — `docs/development_sop.md`*
*Internal document — not for publication*
