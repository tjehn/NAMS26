# check-module

Inspect a NAMS26 module directory and report completion status against the Module 04 standard.

## Usage

```
/project:check-module <NN>
```

**Arguments:**
- `NN` — two-digit module number, e.g. `05`

**Example:**
```
/project:check-module 05
```

---

## Steps

When this skill is invoked with `$ARGUMENTS`, parse the module number and execute every step below in order.

### 1 — Resolve module directory

Find the module directory matching `modules/NN_*/` and resolve:

| Variable | Example value |
|----------|--------------|
| `NN` | `05` |
| `module_dir` | `modules/05_ipv6_eigrp_ospf_nornir` |
| `module_prefix` | `module05` |

If no directory matching `modules/NN_*/` exists, report:
```
ERROR: No module directory found matching modules/NN_*/
```
and stop.

### 2 — Check required files and directories

Check for the presence of each item below. Mark each as PRESENT or MISSING:

**Directories:**
- `data/`
- `templates/`
- `scripts/`
- `utils/`
- `configs/` (with `.gitkeep`)
- `logs/` (with `.gitkeep`)
- `docs/`
- `diagrams/`
- `verbal_script/`
- `NN_ios_configs/`

**Standard utils files:**
- `utils/init_ssh.py`
- `utils/check_ssh.py`
- `utils/clear_known_hosts.sh`
- `utils/ping_hosts.py`
- `utils/push_config.py`

**Data and templates:**
- `data/*.yaml` — at least one YAML file present
- `templates/*.j2` — at least one template present

**Scripts:**
- `scripts/configure_*.py`
- `scripts/verify_*.py`
- `scripts/troubleshoot_*.py`

**Docs:**
- `docs/eve-ng_lab_reset_sop.md`
- `docs/moduleNN_planning.md`
- `docs/moduleNN_closing_demo.md`

**Diagrams:**
- `diagrams/moduleNN_topology_*.drawio`
- `diagrams/moduleNN_topology_*.svg`

**Verbal script:**
- `verbal_script/moduleNN_verbal_script.md` OR
- `verbal_script/moduleNN_verbal_script_final.md`
- Note whether `_final` version exists

**README:**
- `README.md` — present and not a stub (more than 10 lines)

### 3 — Check standards compliance

For each file that is PRESENT, perform these checks:

**`utils/ping_hosts.py`:**
- Contains `platform.system()` branching — PASS / FAIL

**`scripts/configure_*.py`:**
- Contains four-level path resolution (`SCRIPT_DIR`, `MODULE_DIR`,
  `MODULES_DIR`, `PROJECT_ROOT`) — PASS / FAIL
- Contains `LOG_DIR = os.path.join(MODULE_DIR, "logs")` — PASS / FAIL
- If NAPALM module: contains `dest_file_system` and `inline_transfer`
  in `optional_args` — PASS / FAIL / N/A

**`data/*.yaml`:**
- Active Ethernet interfaces use `speed: 100` (unquoted integer) — PASS / FAIL
- All interfaces present including unused — PASS / FAIL / UNABLE TO VERIFY

**Verbal script:**
- If `_final` version exists → FINALIZED
- If only draft version exists → DRAFT
- If neither exists → MISSING

### 4 — Report

Print a structured completion report:

```
=== Module NN Completion Report ===
Directory: modules/NN_name_tool/

--- Directory Structure ---
  configs/          PRESENT (with .gitkeep)
  logs/             PRESENT (with .gitkeep)
  data/             PRESENT
  scripts/          PRESENT
  templates/        PRESENT
  utils/            PRESENT
  docs/             PRESENT
  diagrams/         MISSING   ← example
  verbal_script/    PRESENT
  NN_ios_configs/   PRESENT

--- Utils ---
  init_ssh.py           PRESENT
  check_ssh.py          PRESENT
  clear_known_hosts.sh  PRESENT
  ping_hosts.py         PRESENT — platform branching: PASS
  push_config.py        PRESENT

--- Scripts ---
  configure_*.py        PRESENT — path resolution: PASS | LOG_DIR: PASS
  verify_*.py           STUB ONLY
  troubleshoot_*.py     STUB ONLY

--- Data / Templates ---
  data/*.yaml           PRESENT
  templates/*.j2        PRESENT

--- Docs ---
  eve-ng_lab_reset_sop.md     PRESENT
  moduleNN_planning.md        PRESENT
  moduleNN_closing_demo.md    PRESENT

--- Diagrams ---
  *.drawio              MISSING
  *.svg                 MISSING

--- Verbal Script ---
  Status: DRAFT (no _final version)

--- README ---
  Status: PRESENT — content present

--- Standards Compliance ---
  ping_hosts.py Windows branching:    PASS
  configure path resolution:          PASS
  configure LOG_DIR:                  PASS
  NAPALM optional_args:               N/A

=== Summary ===
  COMPLETE:   8 / 14 items
  MISSING:    3 items (diagrams/*, verify script content, troubleshoot script content)
  WARNINGS:   1 (verbal script not finalized)

  Module status: IN PROGRESS
```

---

## Standards reminders

- Module 04 (`04_ospf2_napalm`) is the reference standard for all deliverables
- A module is COMPLETE only when all items are PRESENT and verbal script is `_final`
- Stub scripts (fewer than 50 lines or containing only `pass`) are reported as STUB ONLY
