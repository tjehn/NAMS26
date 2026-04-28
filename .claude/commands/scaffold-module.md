# scaffold-module

Scaffold a new NAMS26 module directory from scratch, following the standards in CLAUDE.md.

## Usage

```
/project:scaffold-module <NN> <short_name> <tool>
```

**Arguments** (space-separated in `$ARGUMENTS`):
- `NN` — two-digit module number, e.g. `06`
- `short_name` — snake_case protocol/topic name, e.g. `isis` or `bgp1`
- `tool` — automation tool, e.g. `nornir`, `ansible`, `ansible_pyats`

The directory will be named `modules/NN_shortname_tool/`.

**Example:**
```
/project:scaffold-module 06 isis nornir
```

---

## Steps

When this skill is invoked with `$ARGUMENTS`, parse the three positional arguments and then execute every step below in order.

### 1 — Resolve names

Derive the following from the arguments:

| Variable | Example value |
|----------|--------------|
| `NN` | `06` |
| `short_name` | `isis` |
| `tool` | `nornir` |
| `module_dir` | `modules/06_isis_nornir` |
| `module_prefix` | `module06` |
| `source_utils` | `modules/04_ospf2_napalm/utils` |

### 2 — Create directory scaffold

Run these Bash commands (adapt `module_dir` to the resolved value):

```bash
mkdir -p modules/NN_name_tool/{NN_ios_configs,data,diagrams,docs,scripts,templates,verbal_script}
mkdir -p modules/NN_name_tool/configs && touch modules/NN_name_tool/configs/.gitkeep
mkdir -p modules/NN_name_tool/logs    && touch modules/NN_name_tool/logs/.gitkeep
```

Also create a `.gitkeep` in `NN_ios_configs/` if no raw configs exist yet:

```bash
touch modules/NN_name_tool/NN_ios_configs/.gitkeep
```

### 3 — Copy `utils/` from Module 04

```bash
cp -r modules/04_ospf2_napalm/utils/ modules/NN_name_tool/utils/
```

Then make the following targeted edits inside the copied files:

| File | What to change |
|------|---------------|
| `utils/init_ssh.py` | Update the module number in the header comment, script description string, and the "Ready to run" message at the bottom. Update the YAML filename reference to match `data/moduleNN_<short_name>.yaml` (or the expected YAML name). |
| `utils/ping_hosts.py` | Update the YAML filename reference. Confirm `platform.system() == "Windows"` branching is present — do not remove it. |
| `utils/clear_known_hosts.sh` | Update the module number in the header comment if one exists. |
| `utils/module04_ospf_topology_map.py` | Delete this file — it is Module 04-specific. |

All other `utils/` files (`check_ssh.py`, `push_config.py`) can be used as-is; update header comments only.

### 4 — Create placeholder `docs/` files

Create three empty stub files (with a one-line heading only — do not write content):

- `docs/eve-ng_lab_reset_sop.md` — create with single line only:
  `See project-level docs/eve-ng_lab_reset_sop.md for lab reset procedure.`
  Do not copy the full SOP — the consolidated SOP lives at the project level.
- `docs/moduleNN_planning.md` — create with heading `# Module NN Planning` only
- `docs/moduleNN_closing_demo.md` — create with heading `# Module NN Closing Demo` only

### 5 — Create placeholder `README.md`

Create `modules/NN_name_tool/README.md` with the following stub (fill in the resolved values):

```markdown
# Module NN — <Protocol/Topic> (<Tool>)

> Status: NOT STARTED

## What this module covers

_TODO_

## Prerequisites

_TODO_

## Directory structure

_TODO_

## How to run the scripts

_TODO_

## What to expect

_TODO_
```

### 6 — Create placeholder verbal script

Create `verbal_script/moduleNN_verbal_script.md` (no `_final` suffix until content is complete):

```markdown
# Module NN Verbal Script

> Status: DRAFT
```

### 7 — Verify `.gitignore` coverage

Check that `configs/` and `logs/` are covered by `.gitignore`. The project root `.gitignore` should already contain entries for `modules/*/configs/` and `modules/*/logs/`. If either is missing, add it.

### 8 — Report

After completing all steps, print a summary:

```
Module NN scaffold complete
  Created: modules/NN_name_tool/
  Directories: configs/ logs/ data/ scripts/ templates/ diagrams/ docs/ verbal_script/ NN_ios_configs/
  utils/ copied from Module 04 — review init_ssh.py and ping_hosts.py for YAML filename references
  module04_ospf_topology_map.py deleted

  Still required before module is COMPLETE:
    [ ] data/moduleNN_<short_name>.yaml — device inventory
    [ ] scripts/configure_<short_name>.py
    [ ] scripts/verify_<short_name>.py
    [ ] templates/<short_name>.j2
    [ ] diagrams/moduleNN_topology_<protocol>.drawio + .svg
    [ ] docs/moduleNN_planning.md — fill in content
    [ ] docs/moduleNN_closing_demo.md — fill in content
    [ ] verbal_script/moduleNN_verbal_script_final.md — rename from _draft when complete
    [ ] README.md — fill in all sections
    [ ] Update project README.md module table (status → IN PROGRESS)
    [ ] Update CLAUDE.md Tool-per-Module table (status → IN PROGRESS)
```

---

## Standards reminders (do not skip)

- **Named Mode:** Modules 06+ must use Named Mode (EIGRP Named, OSPF Named, IS-IS Named). Never mix classic and named mode.
- **Path resolution:** Every script must use the four-level `__file__` chain (`SCRIPT_DIR → MODULE_DIR → MODULES_DIR → PROJECT_ROOT`) and set `LOG_DIR = os.path.join(MODULE_DIR, "logs")`.
- **NAPALM modules:** Always include `dest_file_system`, `inline_transfer`, and (Module 04+) `enable_scp: False` in `optional_args`.
- **Two-act structure:** Modules 10–12 require a two-act verbal script (Act 1 — Ansible deploys; Act 2 — pyATS verifies).
- **Interface standards:** Active Ethernet uses `speed: 100` (unquoted integer), `duplex: full`. All unused interfaces must be present in YAML with `description: UNUSED`.
