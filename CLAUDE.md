# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NAMS26** (Network Automation Management Station 2026) is a 12-module network automation curriculum using Python and Cisco IOS (IOL) routers in an EVE-NG lab. Each module introduces a new automation tool: Netmiko → NAPALM → Nornir → pyATS/Genie → Ansible.

## Project Root
J:\CCIE EI Lab - Q1 2020\NAMS26_V03
(also accessible as \\nas01\SynologySync1\CCIE EI Lab - Q1 2020\NAMS26_V03)

## Project-Level Documents

| File | Audience | Purpose |
|------|----------|---------|
| `CLAUDE.md` | Claude Code | Coding standards, architecture, and operational guidance for the AI assistant |
| `APPENDIX.md` | Students | Reference technology notes and code snippets — supplementary to the module READMEs |
| `docs/publication_sop.md` | Instructor | Internal pre-production checklist — never published to GitHub |
| `docs/eve-ng_lab_reset_sop.md` | Instructor | Lab reset procedure — applies to all modules |


## Running Scripts

There is no build system. Scripts are invoked directly from each module directory. Each module follows the same CLI contract:

```bash
# Pre-flight (lab reset sequence — run in this order):
bash modules/02_eigrp_netmiko/utils/clear_known_hosts.sh   # 1. purge stale keys
python modules/02_eigrp_netmiko/utils/init_ssh.py           # 2. accept new keys, populate known_hosts
python modules/02_eigrp_netmiko/utils/ping_hosts.py         # 3. confirm ICMP reachability

# Troubleshooting SSH (not part of reset — verifies existing known_hosts entries)
python modules/02_eigrp_netmiko/utils/check_ssh.py

# Render configs locally only — no SSH connection
python modules/02_eigrp_netmiko/scripts/configure_eigrp_classic.py --dry-run

# Deploy to all routers
python modules/02_eigrp_netmiko/scripts/configure_eigrp_classic.py

# Deploy to specific routers
python modules/02_eigrp_netmiko/scripts/configure_eigrp_classic.py --router R1 R2

# Verify operational state
python modules/02_eigrp_netmiko/scripts/verify_eigrp_classic.py --router R1 --check neighbors routes
```

The same flags (`--dry-run`, `--router`, `--check`) are expected on all modules that have these scripts.

## Code Formatting

```bash
black modules/          # Format all module scripts
black modules/03_ospf1_napalm/scripts/configure_ospf_classic.py  # Single file
```

Black is the only configured code tool (no linter, no test runner).

## Code Commenting Standard

Do not comment obvious code. Add a comment only when the WHY is non-obvious: a hidden constraint, a subtle invariant, or a parameter whose effect would surprise a reader.

**Non-obvious variables must document three things:** current setting, purpose, and valid range. Format:

```python
# One-line description of what this controls.
# Current: X   Range: min – max
"variable_name": value,
```

Apply this to all connection timing parameters (`global_delay_factor`, `delay_factor`,
`conn_timeout`, `SSH_TIMEOUT`) and any parameter whose effect is not obvious from its name.
Do not comment path assignments, standard library imports, or self-explanatory flag names.

### Netmiko Timing Parameters

| Parameter | Scope | Behavior |
|-----------|-------|----------|
| `global_delay_factor` | Connection-wide | Multiplies **all** internal Netmiko delay constants: post-login settling, inter-command pause, prompt-detection loops. Set in `ConnectHandler()` or via NAPALM `optional_args`. |
| `delay_factor` | Per-`send_command` | Multiplies that single command's wait time. Stacks **multiplicatively** with `global_delay_factor`: `effective wait = base × global_delay_factor × delay_factor`. |
| `conn_timeout` | TCP only | TCP handshake timeout. Raises `NetmikoTimeoutException` if exceeded. Does not affect application-level prompt timeouts. |

In NAPALM scripts, `global_delay_factor` is passed via `optional_args` and forwarded to the
underlying Netmiko connection — it is a Netmiko parameter, not a NAPALM one.

Typical values used in this project:

| Script type | `global_delay_factor` | `delay_factor` |
|-------------|----------------------|----------------|
| `push_config.py` (Netmiko, `send_config_set`) | 2.0 | — |
| `configure_*.py` (Netmiko, line-by-line `send_command`) | 4.0 | 5.0 |
| `verify_*.py` / `troubleshoot_*.py` | 2.0 | — |
| NAPALM scripts (via `optional_args`) | 2.0 | — |

## Interface Standards

These standards apply to all modules and must be reflected in every YAML data file:

| Interface type | `speed` | `duplex` | `description` | `shutdown` |
|----------------|---------|----------|---------------|------------|
| Active Ethernet (UP/UP) | `100` | `full` | descriptive | `false` |
| Unused Ethernet | `""` | `""` | `UNUSED` | `true` |
| Active Serial | `""` | `""` | descriptive | `false` |
| Unused Serial | `""` | `""` | `UNUSED` | `true` |
| Loopback | `""` | `""` | descriptive | `false` |
| OOB (`Ethernet1/3`) | `""` | `""` | `OOB Management` | `false` |

**`speed: 100` must be an unquoted YAML integer, not a quoted string (`speed: "100"` is wrong).**
The value `100` renders correctly in Jinja2 either way, but the unquoted form is the project standard.
Serial and Loopback interfaces have no applicable speed or duplex — use empty strings for both.

**Base config demarc:** `Ethernet1/3` (OOB), hostname, credentials, domain, VTY/console, and NTP are managed by the lab admin as a pre-loaded base configuration. The automation scripts do not render or modify these. The OOB interface entry in each YAML is reference data only — the template explicitly excludes it from rendering.

All shutdown Serial interfaces (e.g., `Serial2/1`, `Serial2/2`, `Serial2/3`) must be present in the YAML with `description: UNUSED`. Do not omit unused interfaces.

## Architecture

### Module Layout

All 12 modules share an identical structure:

```
modules/NN_name_tool/
├── NN_ios_configs/                    # Raw IOS configs captured from EVE-NG lab
├── configs/                           # Rendered device configs (git-ignored, written by --dry-run)
├── data/                              # YAML device inventory + routing config
├── diagrams/                          # moduleNN_topology_*.drawio + moduleNN_topology_*.drawio.svg
├── docs/
│   ├── eve-ng_lab_reset_sop.md
│   ├── moduleNN_planning.md
│   └── moduleNN_closing_demo.md
├── logs/                              # Session logs (git-ignored)
├── README.md
├── scripts/                           # configure_*.py, verify_*.py, troubleshoot_*.py
├── templates/                         # *.j2 Jinja2 templates
├── utils/                             # check_ssh.py, clear_known_hosts.sh, ping_hosts.py, push_config.py
└── verbal_script/
    └── moduleNN_verbal_script_final.md
```

**Git-ignored directories require a `.gitkeep` placeholder** so git tracks the directory and scripts
can write to it on a fresh clone without a `mkdir` guard. Required for: `configs/`, `logs/`,
`NN_ios_configs/` (when empty), and `utils/` (when scaffold only).

### File Naming Conventions

- **Diagram files:** `moduleNN_topology_<protocol>.drawio` and `moduleNN_topology_<protocol>.drawio.svg`
  — the `moduleNN_` prefix makes files unambiguous when viewed outside their directory context.
- **Verbal script:** `moduleNN_verbal_script_final.md` — the `_final` suffix signals the script
  is production-ready. Do not rename until the content is finalized.
- **`docs/` standard files:** all three (`eve-ng_lab_reset_sop.md`, `moduleNN_planning.md`,
  `moduleNN_closing_demo.md`) are required for every completed module.

### `configs/` Directory Standard

- Rendered config files are datetime-stamped: format `YYMMDD_HHMMSS_HOSTNAME_module.cfg` (e.g. `260428_143022_R1_eigrp_classic.cfg`)
- Date-stamped files are retained during development as an audit trail
- Pre-publication manual check: confirm only one clean set of configs exists before final GitHub push (human review task — not automated)
- `configs/` is git-ignored — files are written by `--dry-run` and are never committed

### Date Format Standard

All dates in log file names and session-related files use YYMMDD format.
Example: `260426_session_status.md`, `260426_R1_session.log`

### Verbal Script Log Path Standard

Verbal scripts must reference the **module-specific** log path. Never use generic references
like "project-level `logs/`" or "`modules/logs/`":

```
WRONG:  "A timestamped session log is written to the project-level logs/ directory"
WRONG:  "All output is mirrored to a timestamped log file in modules/logs/"
CORRECT: "A timestamped session log is written to modules/02_eigrp_netmiko/logs/"
```

This mirrors the `LOG_DIR = os.path.join(MODULE_DIR, "logs")` standard in every script.

### `utils/` Standard Scripts

Every module's `utils/` must contain these five files (copy from the previous module and adapt):

| File | Purpose | Referenced in SOP |
|------|---------|-------------------|
| `init_ssh.py` | Lab initialization — drives the interactive SSH first-connection flow using pexpect, accepts host key fingerprints, and populates `~/.ssh/known_hosts`. Run after every EVE-NG lab reset. | Yes |
| `check_ssh.py` | Troubleshooting — verifies SSH connectivity against existing `~/.ssh/known_hosts` entries using Netmiko. Used when diagnosing lab connectivity issues, not as part of the reset sequence. | No |
| `clear_known_hosts.sh` | Removes lab router entries from `~/.ssh/known_hosts` before a wipe/restart | Yes |
| `ping_hosts.py` | ICMP reachability check against all devices in the module YAML. Must use `platform.system()` branching — Windows `ping.exe` uses `-n`/`-w` flags and different output format. See Addendum. | Yes |
| `push_config.py` | Standalone config push utility (bypasses the full configure script) | No |

**`init_ssh.py` vs `check_ssh.py`:** These are distinct tools with different purposes.
`init_ssh.py` is the lab reset script — it must run after every EVE-NG Wipe+Start because IOL
regenerates RSA host keys on each cycle. `check_ssh.py` is a troubleshooting diagnostic that
confirms existing known_hosts entries are still valid.

Module-specific utility scripts (e.g., `module04_ospf_topology_map.py`) also live in `utils/`
and follow the same `moduleNN_` naming prefix.

### Data → Template → Device Flow

1. `data/*.yaml` holds device inventory (hostname, DNS name, interfaces, loopbacks, routing params, credentials)
2. `scripts/configure_*.py` loads YAML, registers custom Jinja2 filters (e.g. `cidr_to_netmask`), renders each device's config from `templates/*.j2`
3. In live mode: connects via SSH (using `dns_name` field, e.g. `r1.lab`) and pushes config
4. In `--dry-run` mode: writes rendered configs to `configs/` with no network calls

All file paths in scripts are resolved relative to the script's own `__file__`, so scripts work correctly regardless of working directory.

### Path Resolution — REQUIRED STANDARD (all modules)

Every script must resolve paths using this exact four-level chain from `__file__`. This is required because scripts may be run from any working directory:

```python
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)
LOG_DIR      = os.path.join(MODULE_DIR, "logs")
```

- Scripts live in `modules/NN_name_tool/scripts/` → SCRIPT_DIR
- Module root is one level up → MODULE_DIR
- All modules directory is one more level up → MODULES_DIR
- Project root is one more level up → PROJECT_ROOT
- Logs go to the **module's own** `logs/` directory, not the project root logs/

**Common LOG_DIR mistakes to avoid:**

```python
# WRONG — points to project root logs/, not the module's logs/
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# WRONG — os.path.dirname(MODULE_DIR) resolves to MODULES_DIR (modules/), not MODULE_DIR
LOG_DIR = os.path.join(os.path.dirname(MODULE_DIR), "logs")

# CORRECT
LOG_DIR = os.path.join(MODULE_DIR, "logs")
```

Both wrong forms write logs to a shared directory outside the module, breaking the
per-module isolation enforced by the directory structure.

### YAML Device Structure

```yaml
devices:
  R1:
    hostname: R1
    dns_name: r1.lab
    oob_ip: 192.168.1.101/24
    credentials: *creds        # anchored from default_credentials
    interfaces:
      Ethernet0/0:
        ip: 10.12.12.1/24
        shutdown: false
    loopbacks:
      Loopback1:
        ip: 10.1.1.1/24
    eigrp:                     # or ospf:, isis:, bgp: depending on module
      ...
```

### Verification Pattern

`verify_*.py` scripts connect to devices, run `show` commands, and compare live state against expected values from YAML. Output is per-device PASS / WARN / FAIL with mirrored timestamped logs under `modules/NN_name_tool/logs/`.

### Tool-per-Module

| Module | Name | Technology | Tool | Structure |
|--------|------|-----------|------|-----------|
| 02 | EIGRP Classic | EIGRP | Netmiko | Single act — COMPLETE |
| 03 | OSPF Classic | OSPF | NAPALM | Single act — COMPLETE |
| 04 | OSPF Advanced | OSPF Advanced | NAPALM | Single act — COMPLETE |
| 05 | IPv6 EIGRP + OSPFv3 | IPv6 EIGRP + OSPFv3 | Nornir | Single act — IN PROGRESS |
| 06 | IS-IS | IS-IS (IPv4 + IPv6 zone) | Nornir | Single act — NOT STARTED |
| 07 | BGP Part 1 | BGP | Ansible | Single act — NOT STARTED |
| 08 | BGP Part 2 | BGP Advanced | Ansible | Single act — NOT STARTED |
| 09 | Route Policy | Route Maps, Prefix Lists, AD, Redistribution | Ansible | Single act — NOT STARTED |
| 10 | BGP + MPLS | BGP + MPLS | Ansible + pyATS/Genie | Two acts — NOT STARTED |
| 11 | MPLS VPN | MPLS VPN | Ansible + pyATS/Genie | Two acts — NOT STARTED |
| 12 | VPN / GRE | VPN / GRE | Ansible + pyATS/Genie | Two acts — NOT STARTED |
| 13 | Capstone | Multi-site Enterprise | Flask + Mixed | Capstone — PLANNED |

### Protocol Configuration Mode Standard

- **Modules 02–05:** Classic configuration mode
- **Module 06 onward:** Named Mode exclusively (IS-IS Named Mode, EIGRP Named Mode, OSPF Named Mode where applicable)
- All new modules from 06 forward must use Named Mode
- Do not mix classic and named mode within a single module

### EIGRP Redistribution Metric Standard

All EIGRP redistribution statements must use the following metric:

```
metric: "10000 100 255 1 1500"
```

This applies to all modules containing EIGRP redistribution. Verify this value is consistent
in all YAML files for Modules 02–05.

### Module 04 Standard

Module 04 (`04_ospf2_napalm`) is the reference standard for all project documentation,
demonstration plans, diagrams, config files, and templates. Exceptions are permitted only
for technology-specific requirements (e.g. IPv6 syntax, Nornir inventory structure).

When adding a new module or normalizing an existing one, compare against Module 04
deliverables first.

### Two-Act Module Structure (Modules 10–12)

Each module follows a two-act structure:
  Act 1 — Ansible deploys the Cisco technology
  Act 2 — pyATS/Genie verifies what Ansible built

The verbal script must clearly delineate the two acts.
The Cisco technology is the foundation — it must not be lost in the tool lesson.
The planning doc must address both acts with equal depth.

### Module 09 — Route Policy Standard

Module 09 is a dedicated route policy and filtering module.
Topology must include OSPF, BGP, and EIGRP redistribution boundaries.
Topics must include: route maps, prefix lists, distribute lists,
administrative distance manipulation, conditional redistribution.
This is a curriculum differentiator — depth over breadth.

### README.md Standard

**Project-level `README.md`** must contain:
- What NAMS26 is (one paragraph)
- Target audience (CCNP-level, Python automation focus)
- Module progression table (tool per module, status)
- How to use the repository
- Prerequisites (Python version, EVE-NG, Cisco IOL)
- AI acknowledgment line (see below)

**Module-level `README.md`** must contain:
- What this module covers (one paragraph)
- Prerequisites — what the student should know coming in
- Directory structure — what each folder contains
- How to run the scripts — the three CLI commands
- What to expect — what success looks like

> Module 04 README is the template. All subsequent modules follow it exactly.

### NAPALM / Cisco IOL Compatibility — REQUIRED STANDARD (Modules 03+)

Cisco IOL routers have no `flash:` filesystem and do not support SCP. Every NAPALM
configure script targeting IOL **must** use these `optional_args` exactly — no exceptions:

```python
optional_args = {
    "ssh_config_file": None,
    "session_log":      session_log_path,
    # IOL has no flash: filesystem — point NAPALM's space check at nvram: instead.
    "dest_file_system": "nvram:",
    # IOL does not support SCP — send config inline over the SSH session.
    "inline_transfer":  True,
}
```

Omitting `dest_file_system` or `inline_transfer` will cause NAPALM to fail silently
or raise a file transfer error on every IOL router.

**Module 04 adds one additional key** — `enable_scp: False` — as a belt-and-suspenders
guard against IOL MD5 checksum errors when SCP is attempted against `nvram:` on some
image versions. `inline_transfer` already prevents SCP; `enable_scp: False` makes the
intent explicit and disables SCP at the NAPALM layer as well:

```python
optional_args = {
    "ssh_config_file":  None,
    "session_log":      session_log_path,
    "dest_file_system": "nvram:",
    "inline_transfer":  True,
    "enable_scp":       False,   # Module 04+ only
}
```

### Ansible

`ansible/ansible.cfg` sets `roles_path = roles/` and `host_key_checking = False`. Device credentials are in `ansible/vault/` (requires vault password). Inventories and group/host vars are populated per module, not centrally.

## Lab Environment

- **Management network:** `192.168.1.x/24` — OOB interface `Ethernet1/3` on each router
- **Lab DNS:** `192.168.1.12` — resolves `r1.lab` through `r11.lab`
- **Default SSH credentials:** `netadmin` / `admin` (set in each module's YAML)
- **Git remotes:** `origin` → Gitea at `192.168.1.12:8418` (dev), `github` → GitHub (production)
- **Python venv:** `venv/` at project root (git-ignored). PyCharm cannot resolve the interpreter path when the project is opened from a UNC or mapped-drive path (`J:\` / `\\nas01\...`) — use the system Python (`C:\Users\tjehn\AppData\Local\Programs\Python\Python313\python.exe`) as the PyCharm interpreter in that case. All required packages are installed there.

## EVE-NG Lab Reset — CRITICAL

After every EVE-NG reboot the sequence is: **Stop → Wipe → Start → RSA keys → pre-flight → deploy**.
Skipping the Wipe step leaves stale NVRAM config (passive interfaces, test faults) that causes
false FAILs in verify and troubleshoot scripts. See `docs/eve-ng_lab_reset_sop.md`.

**Instructor Procedure Note:**
The EVE-NG lab reset sequence is an instructor preparation procedure. It is not referenced
in any student-facing module instructions or docs. It belongs in the instructor SOP only.

## Adding a New Module

### Step 1 — Create the scaffold

Create all directories with `.gitkeep` placeholders for the git-ignored ones:

```bash
mkdir -p modules/NN_name_tool/{NN_ios_configs,data,diagrams,docs,scripts,templates,verbal_script}
mkdir -p modules/NN_name_tool/configs && touch modules/NN_name_tool/configs/.gitkeep
mkdir -p modules/NN_name_tool/logs    && touch modules/NN_name_tool/logs/.gitkeep
```

### Step 2 — Copy `utils/` from the previous module

```bash
cp -r modules/04_ospf2_napalm/utils/ modules/NN_name_tool/utils/
```

Adapt `init_ssh.py` and `ping_hosts.py` for the new module's YAML filename and tool name.
Update the module number in headers and the "Ready to run" message at the bottom of `init_ssh.py`.
Remove or replace `module04_ospf_topology_map.py` as appropriate.

`ping_hosts.py` must use `platform.system() == "Windows"` branching in the `ping()` function.
Do not copy the raw `-c`/`-W` Linux flags into a new module without this guard — see Addendum for the full pattern.

### Step 3 — Create `docs/` standard files

All three are required before the module is considered complete:
- `docs/eve-ng_lab_reset_sop.md` — copy from Module 04, update if lab topology changed
- `docs/moduleNN_planning.md` — module design and topology planning notes
- `docs/moduleNN_closing_demo.md` — closing demo script / fault injection procedure

### Step 4 — Write the `configure_*.py` script

The script must:
- Resolve all paths using the four-level chain from `__file__` (see Path Resolution above)
- Support `--dry-run` and `--router` flags
- Write rendered configs to `configs/` during dry-run
- Log session output to `modules/NN_name_tool/logs/`
- For NAPALM modules: always include IOL optional_args (see NAPALM section above)

### Step 5 — Name diagram and verbal script files correctly

- Diagrams: `diagrams/moduleNN_topology_<protocol>.drawio` + `.svg`
- Verbal script: `verbal_script/moduleNN_verbal_script_final.md` (only rename to `_final` when complete)

## Module 13 — Advanced Techniques & Practitioner Notes

**Status: Draft / Ideas Capture.** Module 13 is a holding area for techniques, patterns, and
lab ideas that emerged during Modules 02–12 but did not belong in any single module. It may
crystallize into one or more full lab modules, or remain as a standalone reference chapter.

There is no fixed tool or topology for Module 13 yet. Topics are queued here as they are
identified — each entry should note where it came up and why it was deferred rather than
absorbed into an earlier module.

### Draft Topics

- [ ] **Router Descriptions Script** — noted during Module 05 verbal script review (2026-04-26)

- [ ] **[ELECTIVE] Change Control Form — Merge vs Replace Execution Model** — noted during Module 05 verbal script development (2026-04-27)
  - GUI change control form with an Execution Model selector (radio button or dropdown): **Merge** and **Replace**
  - Merge maps to `load_merge_candidate` (NAPALM) or `netmiko_send_config` (Nornir) — additive, safe for incremental changes
  - Replace maps to `load_replace_candidate` (NAPALM) — enforces complete intended state, removes stale config
  - Makes the merge vs replace distinction tangible and interactive rather than purely conceptual; operator consciously chooses the execution model before pushing — consistent with how mature network automation platforms work
  - Elective — include if time and scope permit during Module 13 design

- [ ] **[ELECTIVE] Dynamic EIGRP Redistribution Metric Derivation** — noted during Module 05 verify/troubleshoot implementation (2026-04-27)
  - When an EIGRP redistribution statement is required, the script should parse `show interface <intf>` output on the ASBR and derive the five metric components dynamically rather than using the hardcoded standard value `"10000 100 255 1 1500"`
  - Metric components and how to derive them from `show interface` output:
    - **Bandwidth:**   `BW XXXXX Kbit/sec` — use value as-is in Kbps
    - **Delay:**       `DLY XXXXX usec` — divide by 10 (`show interface` reports in microseconds; EIGRP metric requires tens of microseconds). Example: DLY 1000 usec → 100
    - **Reliability:** `reliability 255/255` — extract numerator (255)
    - **Load:**        `txload 1/255` — extract numerator (1)
    - **MTU:**         `MTU 1500 bytes` — extract value (1500)
  - Example `show interface` output and derived metric:
    ```
    Ethernet0/1 is up, line protocol is up
      MTU 1500 bytes, BW 10000 Kbit/sec, DLY 1000 usec,
         reliability 255/255, txload 1/255, rxload 1/255
    → redistribute ospf 1 metric 10000 100 255 1 1500
    ```
  - Implementation notes:
    - Use Netmiko, NAPALM, or Nornir (whichever is the module tool) to run `show interface <intf>` on the ASBR
    - Parse the BW/DLY/reliability/load/MTU fields via regex or ntc-templates
    - Divide DLY by 10 before inserting into the metric statement
    - Applies to both IPv4 EIGRP and EIGRPv6 redistribution
    - The interface to query is the one facing the EIGRP domain (e.g. link toward R7/R8 on R1, toward R8 on R6)
    - Prerequisite: student must be familiar with `show interface` parsing via pyATS/Genie or ntc-templates (Modules 08–09)
  - Elective — include if time and scope permit during Module 13 design

---

## Addendum — Discovered Quirks and Fixes

Issues found during development that are not obvious from the code or the module design.
Add new entries here as they are encountered.

### `ping_hosts.py` — Windows ping compatibility (discovered Module 05, 2026-04-25)

The original `ping_hosts.py` used Linux ping flags (`-c count`, `-W timeout_seconds`).
On Windows, `ping.exe` uses different flags (`-n count`, `-w timeout_milliseconds`) and
produces different output — no "packet loss" substring, so loss always parsed as "unknown"
and return code was non-zero for all hosts regardless of actual reachability.

**Fix applied to modules 03, 04, 05:** use `platform.system() == "Windows"` to branch between
`ping -n 3 -w 2000` (Windows) and `ping -c 3 -W 2` (Linux/macOS). Packet loss parsing also
branches: Windows looks for `"Loss"` in the line and extracts the `(N% loss)` group via regex;
Linux/macOS parses the third comma-separated field of the "packet loss" line.

Apply this same platform-aware pattern to `ping_hosts.py` in every new module.
