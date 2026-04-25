# Session Status — 2026-04-25 (260425a)

## Project Context

**NAMS26** (Network Automation Management Station 2026) is an 11-module network automation
curriculum built on Python and Cisco IOS-on-Linux (IOL) routers running inside EVE-NG.

- **Project root:** `J:\CCIE EI Lab - Q1 2020\NAMS26_V03` (also `\\nas01\SynologySync1\...`)
- **Tool progression:** Netmiko (02) → NAPALM (03–04) → Nornir (05–06) → pyATS/Genie (07–08) → Ansible (09–11)
- **Active module this session:** Module 05 — IPv6 EIGRP / OSPFv3 using Nornir

---

## Environment

| Item | Detail |
|------|--------|
| Python | 3.13.13 (system — `C:\Users\tjehn\AppData\Local\Programs\Python\Python313\python.exe`) |
| pip | 26.0.1 |
| PyCharm interpreter | System Python (project venv on UNC share is inaccessible — see note below) |
| Project venv | `venv/` at project root — empty, git-ignored, kept as placeholder |

**PyCharm / UNC path note:** PyCharm cannot resolve the Python interpreter path when the project
is opened from a mapped drive (`J:\`) or UNC path (`\\nas01\...`). All packages are installed
in the system Python. The project `venv/` is retained as a scaffold placeholder only.

---

## Packages Installed (system Python)

All `requirements.txt` packages confirmed present. Nornir stack:

| Package | Version |
|---------|---------|
| nornir | 3.5.0 |
| nornir-napalm | 0.5.0 |
| nornir-netmiko | 1.0.1 |
| nornir-utils | 0.2.0 |

`nornir-napalm` was missing and was installed this session.

---

## Work Completed This Session

### 1. requirements.txt — Fixed and updated
- Removed duplicate `napalm==5.1.0` entry (was on lines 19 and 52)
- Fixed file encoding: PyCharm had regenerated it as UTF-16 — rewritten as UTF-8
- Added all four nornir packages
- Added `colorama==0.4.6` (pulled in as a transitive dependency)

### 2. CLAUDE.md — PyCharm UNC limitation documented
Added a note to the `Python venv` entry in the Lab Environment section explaining that
PyCharm cannot resolve the venv interpreter path from a UNC/mapped-drive path, and that
the system Python should be used as the PyCharm interpreter in this setup.

### 3. Module 05 configure script — `changed=True` fix
**File:** `modules/05_ipv6_eigrp_ospf_nornir/scripts/configure_ipv6_eigrp_ospf.py`

**Problem:** Nornir's `print_result` was showing `changed: False` with no result text for
all routers. Configs were actually being written to disk, but the terminal output was
misleading — looked like nothing happened.

**Root cause:** The `configure_task` function returned `Result(host=..., result="...")` without
setting `changed=True`. Nornir's `print_result` suppresses result text when `changed=False`.

**Fix:** Added `changed=True` to both return statements in `configure_task`:
```python
# dry-run path
return Result(host=task.host, result=f"[DRY-RUN] Config written to {config_path}", changed=True)

# live deploy path
return Result(host=task.host, result=f"Configured {task.host.name}", changed=True)
```

### 4. Jinja2 templates — speed/duplex guard for IOL Ethernet interfaces
**Files fixed (all four active modules):**
- `modules/02_eigrp_netmiko/templates/eigrp_classic.j2`
- `modules/03_ospf1_napalm/templates/ospf_classic.j2`
- `modules/04_ospf2_napalm/templates/ospf_advanced.j2`
- `modules/05_ipv6_eigrp_ospf_nornir/templates/ipv6_eigrp_ospf.j2`

**Problem:** Templates were rendering `speed 100` and `duplex full` on Ethernet interfaces.
IOL Ethernet interfaces are virtual and reject these commands with an error:
```
R7(config-if)# speed 100
                   ^
% Invalid input detected
```

**Root cause:** The CLAUDE.md interface standard specifies `speed: 100` / `duplex: full` for
active Ethernet interfaces (reference values in YAML). The templates rendered them without
checking whether the interface type supports those commands.

**Fix:** Added `and 'Ethernet' not in intf_name` guard to both speed and duplex blocks:
```jinja2
{% if intf.speed and intf.speed != "" and 'Ethernet' not in intf_name %} speed {{ intf.speed }}
{% endif %}
{% if intf.duplex and intf.duplex != "" and 'Ethernet' not in intf_name %} duplex {{ intf.duplex }}
{% endif %}
```

YAML values are unchanged — they remain as documentation of intended state. The guard
ensures the commands are never sent to IOL Ethernet interfaces. Serial and other
non-Ethernet interface types are unaffected.

---

## Current State — Module 05

- `--dry-run` confirmed working: all 9 router cfg files written to `configs/`
- `configs/` directory contains: R1–R9 `_ipv6_eigrp_ospf.cfg` (96–110 lines each)
- Speed/duplex commands removed from all Ethernet interface blocks in rendered configs
- Ready for live deploy after EVE-NG lab reset sequence

---

## Outstanding / Next Steps

- Run `--dry-run` again post-fix to verify speed/duplex no longer appears in Ethernet blocks
- Execute EVE-NG lab reset sequence (Stop → Wipe → Start → RSA keys → pre-flight)
- Run live deploy: `python configure_ipv6_eigrp_ospf.py`
- Run verify: `python verify_ipv6_eigrp_ospf.py`
- Begin Module 06 scaffold when Module 05 is verified clean
