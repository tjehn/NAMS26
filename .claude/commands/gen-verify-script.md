# gen-verify-script

Generate a verify script for a NAMS26 module following the Module 04 standard.

## Usage

```
/project:gen-verify-script <NN> <yaml_basename> <tool>
```

**Arguments:**
- `NN` — two-digit module number, e.g. `05`
- `yaml_basename` — base name of the module YAML file without extension, e.g. `ipv6_eigrp_ospf`
- `tool` — automation tool: `netmiko`, `napalm`, or `nornir`

**Example:**
```
/project:gen-verify-script 05 ipv6_eigrp_ospf nornir
```

---

## Steps

### 1 — Resolve names

| Variable | Example value |
|----------|--------------|
| `NN` | `05` |
| `yaml_basename` | `ipv6_eigrp_ospf` |
| `tool` | `nornir` |
| `module_dir` | `modules/05_ipv6_eigrp_ospf_nornir` |
| `script_name` | `verify_ipv6_eigrp_ospf.py` |
| `output_path` | `modules/05_ipv6_eigrp_ospf_nornir/scripts/verify_ipv6_eigrp_ospf.py` |

### 2 — Read the module YAML

Read `modules/NN_*/data/<yaml_basename>.yaml` to understand:
- Device list and hostnames
- Routing protocols configured (eigrp, ospf, isis, bgp)
- Interface structure
- Loopback addresses
- Any redistribution defined

This drives what `--check` categories are generated.

### 3 — Determine check categories

Based on protocols found in the YAML:

| Protocol found | Check categories to generate |
|---------------|------------------------------|
| `eigrp` | `neighbors`, `routes` |
| `ospf` | `neighbors`, `routes`, `areas` |
| `isis` | `neighbors`, `routes` |
| `bgp` | `neighbors`, `routes`, `policy` |
| Any redistribution | add `redistribution` |
| IPv6 addressing | add `ipv6` prefix to relevant checks |

### 4 — Generate the verify script

Generate a complete, production-ready verify script. Do not generate a stub.

**Required structure:**

```python
#!/usr/bin/env python3
"""
verify_<yaml_basename>.py — Verify <protocol> state on all devices.

Usage:
    python verify_<yaml_basename>.py
    python verify_<yaml_basename>.py --router R1 R2
    python verify_<yaml_basename>.py --check neighbors routes

Checks:
    neighbors     — verify adjacency state and neighbor count
    routes        — verify expected prefixes in routing table
    redistribution — verify redistributed routes present (if applicable)
    areas         — verify area assignments (OSPF/IS-IS only)
"""

import os
import sys
import argparse
import yaml
import logging
from datetime import datetime

# ── Path resolution ────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)
LOG_DIR      = os.path.join(MODULE_DIR, "logs")
```

**Tool-specific connection pattern:**

For `nornir`:
- Use `SimpleInventory` built dynamically from YAML (same pattern as configure script)
- Use `netmiko_send_command` for show commands
- Use `nr.filter()` for `--router` argument
- Run checks via `nr.run(task=check_<category>)`

For `napalm`:
- Use `get_facts()`, `get_bgp_neighbors()`, `get_interfaces()` etc.
- Loop over devices from YAML
- Use `napalm.get_network_driver("ios")`

For `netmiko`:
- Use `ConnectHandler` with `global_delay_factor: 2.0`
- Loop over devices from YAML
- Use `send_command()` for show commands

**Required output pattern (all tools):**

```python
# Per-device result
print(f"  {'[PASS]':8} {check_name}: {detail}")   # green
print(f"  {'[WARN]':8} {check_name}: {detail}")   # yellow
print(f"  {'[FAIL]':8} {check_name}: {detail}")   # red

# Summary table at end
# Worst-case result per device
# Overall PASS / WARN / FAIL
```

**Required CLI:**
```python
parser.add_argument("--router", nargs="+", help="Target specific routers")
parser.add_argument("--check", nargs="+",
    choices=["neighbors", "routes", "redistribution", "areas"],
    default=["neighbors", "routes", ...])  # all checks by default
```

**Required logging:**
```python
os.makedirs(LOG_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
log_path = os.path.join(LOG_DIR, f"{timestamp}_verify_{yaml_basename}.log")
# Mirror all output to log file
```

**Drift detection logging** (apply to all FAIL paths):
```python
def emit_drift(device_name: str, check_name: str, detail: str, lf=None) -> None:
    timestamp = datetime.now().strftime("%Y%m%d %H:%M:%S")
    header = f"=== DRIFT DETECTED — {device_name} — {timestamp} ==="
    separator = "=" * len(header)
    lines = [header, f"Check:  {check_name}", f"Detail: {detail}", separator]
    for line in lines:
        print(line)
        if lf:
            lf.write(line + "\n")
```

### 5 — Write the file

Write the generated script to `output_path`.
Do not overwrite an existing non-stub verify script without confirmation.
A stub is defined as fewer than 50 lines or containing only `pass` statements.

### 6 — Report

```
verify script generated: modules/NN_name_tool/scripts/verify_<yaml_basename>.py

  Tool:    nornir
  Checks:  neighbors, routes, redistribution, areas
  Devices: R1 R2 R3 R4 R5 R6 R7 R8 R9  (read from YAML)
  Log dir: modules/NN_name_tool/logs/

  Next steps:
    [ ] Review generated script against YAML — confirm check logic is correct
    [ ] Run dry-check (--router R1 --check neighbors) against live lab
    [ ] Confirm all checks produce PASS on a clean lab
    [ ] Add to git after validation
```

---

## Standards reminders

- **Path resolution:** Always four-level `__file__` chain. `LOG_DIR` must be
  `os.path.join(MODULE_DIR, "logs")` — never PROJECT_ROOT.
- **ANSI colors:** `[PASS]` green, `[WARN]` yellow, `[FAIL]` red.
- **Summary table:** worst-case result per device; overall result at bottom.
- **Drift logging:** all FAIL paths must call `emit_drift()`.
- **Timing params:** `global_delay_factor: 2.0` for verify scripts (see CLAUDE.md).
- **Comments:** non-obvious variables must document current value, purpose,
  and valid range per CLAUDE.md commenting standard.
