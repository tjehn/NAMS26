# gen-troubleshoot-script

Generate a troubleshoot script for a NAMS26 module following the Module 04 standard.

## Usage

```
/project:gen-troubleshoot-script <NN> <yaml_basename> <tool>
```

**Arguments:**
- `NN` — two-digit module number, e.g. `05`
- `yaml_basename` — base name of the module YAML file without extension, e.g. `ipv6_eigrp_ospf`
- `tool` — automation tool: `netmiko`, `napalm`, or `nornir`

**Example:**
```
/project:gen-troubleshoot-script 05 ipv6_eigrp_ospf nornir
```

---

## Key Distinction — Troubleshoot vs Verify

This is critical and must be reflected in the generated script:

| Script | Question it answers | Data source |
|--------|--------------------|----|
| `verify_*.py` | Does the device match the YAML source of truth? | YAML + live device |
| `troubleshoot_*.py` | Is the protocol operationally healthy right now? | Live device only |

The troubleshoot script does NOT compare against YAML.
It checks operational state — adjacencies, process state, route presence —
and reports whether the protocol appears to be functioning correctly.
A device can PASS troubleshoot and FAIL verify simultaneously.
This distinction must appear as a docstring comment in the generated script.

---

## Steps

### 1 — Resolve names

| Variable | Example value |
|----------|--------------|
| `NN` | `05` |
| `yaml_basename` | `ipv6_eigrp_ospf` |
| `tool` | `nornir` |
| `module_dir` | `modules/05_ipv6_eigrp_ospf_nornir` |
| `script_name` | `troubleshoot_ipv6_eigrp_ospf.py` |
| `output_path` | `modules/05_ipv6_eigrp_ospf_nornir/scripts/troubleshoot_ipv6_eigrp_ospf.py` |

### 2 — Read the module YAML

Read `modules/NN_*/data/<yaml_basename>.yaml` to understand:
- Device list and hostnames
- Routing protocols configured
- Expected neighbor relationships
- Redistribution points (ASBRs)

### 3 — Determine check categories

| Protocol found | Check categories to generate |
|---------------|------------------------------|
| `eigrp` | `neighbors`, `process`, `routes` |
| `ospf` | `neighbors`, `process`, `routes` |
| `isis` | `neighbors`, `process`, `routes` |
| `bgp` | `neighbors`, `process`, `routes` |
| Any redistribution | add `redistribution` |

### 4 — Generate the troubleshoot script

Generate a complete, production-ready troubleshoot script. Do not generate a stub.

**Required structure:**

```python
#!/usr/bin/env python3
"""
troubleshoot_<yaml_basename>.py — Troubleshoot <protocol> operational state.

PURPOSE:
    This script checks whether the protocol is operationally healthy.
    It does NOT compare against the YAML source of truth.
    Use verify_<yaml_basename>.py to check source-of-truth compliance.

    A device can PASS this script and still FAIL the verify script.
    Both scripts are needed — they answer different questions.

Usage:
    python troubleshoot_<yaml_basename>.py
    python troubleshoot_<yaml_basename>.py --router R1 R2
    python troubleshoot_<yaml_basename>.py --check neighbors process

Checks:
    neighbors     — are adjacencies up?
    process       — is the routing process running and healthy?
    routes        — are routes being learned and installed?
    redistribution — are redistributed routes appearing? (if applicable)
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

**Check content by protocol:**

For EIGRP / EIGRPv6:
- `neighbors`: `show ip eigrp neighbors` / `show ipv6 eigrp neighbors` — confirm state is UP
- `process`: `show ip eigrp` / `show ipv6 eigrp` — confirm process is running, AS number correct
- `routes`: `show ip route eigrp` / `show ipv6 route eigrp` — confirm D routes present

For OSPF / OSPFv3:
- `neighbors`: `show ip ospf neighbor` / `show ipv6 ospf neighbor` — confirm FULL state
- `process`: `show ip ospf` / `show ipv6 ospf` — confirm process running, router-id set
- `routes`: `show ip route ospf` / `show ipv6 route ospf` — confirm O routes present

For IS-IS:
- `neighbors`: `show isis neighbors` — confirm UP state
- `process`: `show isis` — confirm process running, NET address configured
- `routes`: `show ip route isis` — confirm i routes present

For BGP:
- `neighbors`: `show bgp summary` — confirm Established state
- `process`: `show bgp` — confirm process running, router-id set
- `routes`: `show bgp` — confirm prefixes being learned

**Tool-specific connection pattern:**
Same as gen-verify-script — use the tool-appropriate connection method.
`global_delay_factor: 2.0` for all troubleshoot scripts.

**Required output pattern:**
Same PASS / WARN / FAIL pattern as verify scripts.
Same summary table format.
Same logging to `LOG_DIR`.

**Required CLI:**
```python
parser.add_argument("--router", nargs="+")
parser.add_argument("--check", nargs="+",
    choices=["neighbors", "process", "routes", "redistribution"],
    default=["neighbors", "process", "routes"])
```

### 5 — Write the file

Write the generated script to `output_path`.
Do not overwrite an existing non-stub troubleshoot script without confirmation.

### 6 — Report

```
troubleshoot script generated: modules/NN_name_tool/scripts/troubleshoot_<yaml_basename>.py

  Tool:    nornir
  Checks:  neighbors, process, routes
  Devices: R1 R2 R3 R4 R5 R6 R7 R8 R9  (read from YAML)
  Log dir: modules/NN_name_tool/logs/

  Reminder:
    This script checks operational health only.
    It does NOT compare against YAML source of truth.
    Use verify_<yaml_basename>.py for source-of-truth compliance.

  Next steps:
    [ ] Review generated script — confirm show commands match IOS version
    [ ] Run against live lab: --router R1 --check neighbors
    [ ] Confirm PASS on a clean lab before using for fault injection demo
    [ ] Add to git after validation
```

---

## Standards reminders

- **Troubleshoot vs verify distinction:** Must appear in the script docstring.
  This is a teaching point — do not omit it.
- **Path resolution:** Four-level `__file__` chain. `LOG_DIR` must be
  `os.path.join(MODULE_DIR, "logs")`.
- **ANSI colors:** `[PASS]` green, `[WARN]` yellow, `[FAIL]` red.
- **Summary table:** worst-case result per device.
- **Timing params:** `global_delay_factor: 2.0` (see CLAUDE.md).
- **No YAML comparison:** The troubleshoot script reads YAML only for the
  device list and credentials — never for expected state comparison.
- **Comments:** non-obvious variables documented per CLAUDE.md standard.
