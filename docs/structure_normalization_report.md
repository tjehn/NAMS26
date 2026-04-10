# NAMS26 — Structure Normalization Report

**Date:** 2026-04-06
**Scope:** All 11 modules (`modules/02_eigrp_netmiko` through `modules/11_vpn_gre_ansible`)

---

## Normalized Standard

Derived from the completed state of Modules 02–04. Every module should conform to this layout:

```
modules/NN_name_tool/
├── NN_ios_configs/                    # Raw IOS configs captured from lab
├── configs/                           # Rendered configs (git-ignored)
├── data/                              # YAML device inventory + routing params
├── diagrams/                          # topology_*.drawio + topology_*.drawio.svg
├── docs/
│   ├── eve-ng_lab_reset_sop.md
│   ├── moduleNN_planning.md
│   ├── moduleNN_closing_demo.md
│   └── README.md
├── logs/                              # Session logs (git-ignored)
├── README.md
├── scripts/
│   ├── configure_*.py
│   ├── verify_*.py
│   └── troubleshoot_*.py
├── templates/                         # *.j2 Jinja2 templates
├── utils/
│   ├── check_ssh.py
│   ├── clear_known_hosts.sh
│   ├── ping_hosts.py
│   └── push_config.py
└── verbal_script/
    └── moduleNN_verbal_script_final.md
```

---

## Gap Table by Module

| Item | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `NN_ios_configs/` | MISSING | OK | OK | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |
| `configs/` | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `data/` | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `diagrams/` (with files) | OK | OK | empty | empty | empty | empty | empty | empty | empty | empty |
| `docs/eve-ng_lab_reset_sop.md` | OK | OK | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |
| `docs/moduleNN_planning.md` | MISSING | MISSING | OK | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |
| `docs/moduleNN_closing_demo.md` | OK | OK | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |
| `logs/` | MISSING | OK | OK | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |
| `README.md` | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `scripts/configure_*.py` | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `scripts/verify_*.py` | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `scripts/troubleshoot_*.py` | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `templates/*.j2` | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `utils/` | OK | OK | OK | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |
| `verbal_script/moduleNN_verbal_script_final.md` | OK | misplaced | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |

> **misplaced** — Module 03 verbal script exists at `docs/module03_verbal_script_final.md` instead of `verbal_script/module03_verbal_script_final.md`

---

## Issues by Category

### 1. `verbal_script/` — content misplaced or missing

- **Module 03:** `module03_verbal_script_final.md` lives in `docs/` — should be moved to `verbal_script/`
- **Modules 04–11:** `verbal_script/` directory exists but is empty

### 2. `utils/` — entirely absent from Modules 05–11

Each module needs: `check_ssh.py`, `clear_known_hosts.sh`, `ping_hosts.py`, `push_config.py`.
These are identical (or near-identical) across NAPALM modules and can be copied from Module 04.
Nornir, pyATS, and Ansible modules (05–11) will require tool-specific adaptations after copying.

### 3. `logs/` — missing from Module 02 and Modules 05–11

`logs/` directories are git-ignored. A `.gitkeep` placeholder is required so git tracks the directory and scripts can write logs without a `mkdir` guard.

Affected modules: **02, 05, 06, 07, 08, 09, 10, 11**

### 4. `NN_ios_configs/` — missing from Module 02 and Modules 05–11

Module 02 has no `02_ios_configs/`. This directory holds the raw IOS configs captured from the
EVE-NG lab and serves as the source-of-truth reference for YAML authoring. Modules 05–11 will
need this populated when their labs are built out.

Affected modules: **02** (can be back-filled), **05–11** (pending lab builds)

### 5. `docs/` — inconsistent contents across completed modules

| File | 02 | 03 | 04 |
|------|:--:|:--:|:--:|
| `eve-ng_lab_reset_sop.md` | OK | OK | MISSING |
| `moduleNN_planning.md` | MISSING | MISSING | OK |
| `moduleNN_closing_demo.md` | OK | OK | MISSING |

Notes:
- Module 04 `docs/` contains `config_review_notes.md` (ad hoc working file) but is missing all three standard docs.
- `eve-ng_lab_reset_sop.md` is identical across NAPALM modules — Module 04 can copy from Module 03.
- `moduleNN_planning.md` for Modules 02 and 03 may not be needed retroactively but should be standard for 05–11.

### 6. `diagrams/` — empty in Module 04 and Modules 05–11

Module 04 has the directory but no `.drawio` or `.svg` topology diagram. All other not-started
modules (05–11) also have empty `diagrams/` directories as expected.

---

## Recommended Normalization Actions

### Structural Fixes (no content authoring required)

| # | Action | Affected Modules |
|---|--------|-----------------|
| 1 | Create `logs/` + `.gitkeep` | 02, 05, 06, 07, 08, 09, 10, 11 |
| 2 | Create `utils/` and copy `check_ssh.py`, `clear_known_hosts.sh`, `ping_hosts.py`, `push_config.py` from Module 04 | 05, 06, 07, 08, 09, 10, 11 |
| 3 | Move `docs/module03_verbal_script_final.md` → `verbal_script/module03_verbal_script_final.md` | 03 |
| 4 | Copy `docs/eve-ng_lab_reset_sop.md` from Module 03 → Module 04 `docs/` | 04 |
| 5 | Create `02_ios_configs/` placeholder | 02 |

### Content Gaps (require authoring — lower priority until modules are developed)

| # | File | Affected Modules |
|---|------|-----------------|
| 6 | `docs/moduleNN_closing_demo.md` | 04, 05–11 |
| 7 | `verbal_script/moduleNN_verbal_script_final.md` | 04, 05–11 |
| 8 | `diagrams/topology_*.drawio` + `.svg` | 04, 05–11 |
| 9 | `docs/moduleNN_planning.md` | 05–11 |
| 10 | `docs/eve-ng_lab_reset_sop.md` | 05–11 |

---

## Summary Count

| Category | Count |
|----------|-------|
| Structural fixes (directories / file moves / copies) | 5 |
| Content gaps requiring authoring | 5 item types × multiple modules |
| Modules fully normalized | 3 (02 partial, 03 partial, 04 partial — none fully clean) |
| Modules with correct scaffold (empty) | 0 — all 05–11 missing `utils/` and `logs/` |
