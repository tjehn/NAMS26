# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NAMS26** (Network Automation Management Station 2026) is an 11-module network automation curriculum using Python and Cisco IOS (IOL) routers in an EVE-NG lab. Each module introduces a new automation tool: Netmiko → NAPALM → Nornir → pyATS/Genie → Ansible.

## Running Scripts

There is no build system. Scripts are invoked directly from each module directory. Each module follows the same CLI contract:

```bash
# Pre-flight: run after every EVE-NG lab reboot to populate ~/.ssh/known_hosts
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

**Base config demarc:** `Ethernet1/3` (OOB), hostname, credentials, domain, VTY/console, and NTP are managed by the lab admin as a pre-loaded base configuration. The automation scripts do not render or modify these. The OOB interface entry in each YAML is reference data only — the template explicitly excludes it from rendering.

All shutdown Serial interfaces (e.g., `Serial2/1`, `Serial2/2`, `Serial2/3`) must be present in the YAML with `description: UNUSED`. Do not omit unused interfaces.

## Architecture

### Module Layout

All 11 modules share an identical structure:

```
modules/NN_name_tool/
├── data/           # YAML device inventory + routing config
├── templates/      # Jinja2 .j2 templates (one per protocol variant)
├── scripts/        # configure_*.py, verify_*.py, troubleshoot_*.py
├── utils/          # check_ssh.py, ping_hosts.py, push_config.py, module-specific tools
├── configs/        # Rendered device configs (git-ignored, written by --dry-run)
└── logs/           # Session logs (git-ignored)
```

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

| Modules | Tool | Connection Method |
|---------|------|-------------------|
| 02 | Netmiko | SSH, direct `send_config_set` |
| 03–04 | NAPALM | `merge_candidate` + `commit_config`; requires `inline_transfer: True` for Cisco IOL |
| 05–06 | Nornir | Task-based, parallel |
| 07–08 | pyATS/Genie | Structured output parsing |
| 09–11 | Ansible | Roles in `ansible/roles/` |

### NAPALM / Cisco IOL Compatibility — REQUIRED STANDARD (Modules 03+)

Cisco IOL routers have no `flash:` filesystem and do not support SCP. Every NAPALM
configure script targeting IOL **must** use these `optional_args` exactly — no exceptions:

```python
optional_args = {
    "ssh_config_file": None,
    "session_log": session_log_path,
    "dest_file_system": "nvram:",
    "inline_transfer": True,
}
```

Omitting `dest_file_system` or `inline_transfer` will cause NAPALM to fail silently
or raise a file transfer error on every IOL router.

### Ansible

`ansible/ansible.cfg` sets `roles_path = roles/` and `host_key_checking = False`. Device credentials are in `ansible/vault/` (requires vault password). Inventories and group/host vars are populated per module, not centrally.

## Lab Environment

- **Management network:** `192.168.1.x/24` — OOB interface `Ethernet1/3` on each router
- **Lab DNS:** `192.168.1.12` — resolves `r1.lab` through `r11.lab`
- **Default SSH credentials:** `netadmin` / `admin` (set in each module's YAML)
- **Git remotes:** `origin` → Gitea at `192.168.1.12:8418` (dev), `github` → GitHub (production)
- **Python venv:** `.venv/` at project root (git-ignored)

## EVE-NG Lab Reset — CRITICAL

After every EVE-NG reboot the sequence is: **Stop → Wipe → Start → RSA keys → pre-flight → deploy**.
Skipping the Wipe step leaves stale NVRAM config (passive interfaces, test faults) that causes
false FAILs in verify and troubleshoot scripts. See `modules/03_ospf1_napalm/docs/eve-ng_lab_reset_sop.md`.

## Adding a New Module

Follow the existing module structure exactly. Copy `check_ssh.py`, `ping_hosts.py`, and
`push_config.py` from an existing module's `utils/`. The `configure_*.py` script must:
- Resolve all paths using the four-level chain from `__file__` (see Path Resolution above)
- Support `--dry-run` and `--router` flags
- Write rendered configs to `configs/` during dry-run
- Log session output to `modules/NN_name_tool/logs/`
- For NAPALM modules: always include IOL optional_args (see NAPALM section above)
