# NAMS26 Session Status — 2026-04-24

## Project Overview

**NAMS26** (Network Automation Management Station 2026) is a 12-module network automation video curriculum using Python + Cisco IOL routers in EVE-NG. Target audience: CCNP-level engineers learning Python-driven network automation.

**Tool progression:** Netmiko (02) → NAPALM (03–04) → Nornir (05–07) → pyATS/Genie (08–09) → Ansible (10–12)

**Project root:** `J:\CCIE EI Lab - Q1 2020\NAMS26_V03`
(also: `\\nas01\SynologySync1\CCIE EI Lab - Q1 2020\NAMS26_V03`)

**Python venv:** `venv/` at project root (Python 3.13)

**Git remotes:** `origin` → Gitea at 192.168.1.12:8418 (dev), `github` → GitHub (production)

---

## Module Status

| Module | Topic | Tool | Status |
|--------|-------|------|--------|
| 02 | EIGRP Classic | Netmiko | COMPLETE |
| 03 | OSPF Classic | NAPALM | COMPLETE |
| 04 | OSPF Advanced | NAPALM | Scripts/data/docs complete; verbal script written, not proof-read; git push pending |
| 05 | IPv6 EIGRP + OSPFv3 | Nornir | See detail below |
| 06–12 | — | Various | NOT STARTED |

---

## Module 05 Detail — `modules/05_ipv6_eigrp_ospf_nornir/`

### Topology
- 9 routers (R1–R9), pure IPv6
- Two EIGRPv6 domains: AS 100 (R1, R7), AS 111 (R6, R8)
- OSPFv3 PID 1: Area 0 (backbone), Area 10 (totally stubby), Area 20 (NSSA)
- Bidirectional redistribution: R1 (EIGRP 100 ↔ OSPF), R6 (EIGRP 111 ↔ OSPF)
- Interface-level OSPF/EIGRP assignment (no network statements)

### File Status

| File | Status |
|------|--------|
| `data/ipv6_eigrp_ospf.yaml` | COMPLETE — all 9 routers |
| `scripts/configure_ipv6_eigrp_ospf.py` | IMPLEMENTED — not yet tested |
| `templates/ipv6_eigrp_ospf.j2` | IMPLEMENTED — not yet tested |
| `scripts/verify_ipv6_eigrp_ospf.py` | STUB only |
| `scripts/troubleshoot_ipv6_eigrp_ospf.py` | STUB only |
| `utils/` (all 5 standard scripts) | COMPLETE |
| `docs/` (all 3 standard docs) | COMPLETE |
| `diagrams/` | NOT STARTED |
| `verbal_script/` | NOT STARTED |

### configure_ipv6_eigrp_ospf.py — Implementation Notes
- Uses **Nornir** with `SimpleInventory` (writes temp YAML files to `tempfile.mkdtemp()`, cleaned up in `finally`)
- Connection plugin: `nornir_netmiko` (`netmiko_send_config` + `netmiko_send_command`)
- Template rendered per-host via Jinja2; rendered config written to `configs/<HOST>_ipv6_eigrp_ospf.cfg` always (both dry-run and live)
- Live mode: strips blank lines and `!` comments from rendered output, sends as `config_commands` list, follows with `write memory`
- Custom Jinja2 filters: `ipv4_addr(cidr)` and `ipv4_mask(cidr)` using `ipaddress.ip_interface`
- CLI: `--dry-run` (render only, no SSH), `--router` (target subset; accepts R1 / r1 / r1.lab)
- ANSI color output: `[PASS]` / `[FAIL]` / `[WARN]` / `[INFO]`

### ipv6_eigrp_ospf.j2 — Template Notes
- Sections: global IPv6 (`ipv6 unicast-routing`, `ipv6 cef`), key chains, interfaces, EIGRPv6 process, OSPFv3 process
- OOB interface (`device.oob_interface` = Ethernet1/3) skipped entirely
- Critical guard: `ospf_area: 0` is integer 0 (falsy in Python/Jinja2) — uses `intf.ospf_area is not none and intf.ospf_area != ""` throughout
- Routers with no IPv4 (R4, R7, R8) have explicit `router_id` in YAML; template emits `eigrp router-id` / `router-id` only when set
- OSPFv3 `redistribute eigrp X` takes no metric params (IPv6 eliminates subnets concept)
- `area X stub no-summary`, `area X stub`, `area X nssa no-summary`, `area X nssa` driven by `area_types` list in YAML

---

## Immediate Next Steps (in order)

1. **Install Nornir packages into `venv/`:**
   ```
   venv\Scripts\pip install nornir nornir-netmiko nornir-utils netmiko pyyaml jinja2
   ```

2. **Run dry-run and review all 9 rendered configs:**
   ```
   cd "J:\CCIE EI Lab - Q1 2020\NAMS26_V03\modules\05_ipv6_eigrp_ospf_nornir\scripts"
   python configure_ipv6_eigrp_ospf.py --dry-run
   ```
   Review output in `configs/` — verify all interfaces, EIGRP/OSPF blocks, key chains.

3. **Close Module 04:** proof-read verbal script → finalize → push to Gitea and GitHub.

4. **Verify SSH reachability** Work PC → r1.lab–r9.lab (after EVE-NG lab is running).

5. **Run live deploy** and validate:
   ```
   python configure_ipv6_eigrp_ospf.py
   python verify_ipv6_eigrp_ospf.py   # (once implemented)
   ```

6. **Implement `verify_ipv6_eigrp_ospf.py`** — Nornir-based; `--check` choices: `neighbors`, `routes`, `redistribution`, `areas`.

7. **Implement `troubleshoot_ipv6_eigrp_ospf.py`** — Nornir-based; `--check` choices: `neighbors`, `process`, `routes`.

---

## Key Standards (apply to all modules)

- **Path resolution:** 4-level `__file__` chain: `SCRIPT_DIR → MODULE_DIR → MODULES_DIR → PROJECT_ROOT`
- **NAPALM on IOL:** always `dest_file_system: "nvram:"` and `inline_transfer: True`
- **Nornir inventory:** built dynamically from module YAML via temp files (not a static Nornir inventory)
- **OOB interface:** Ethernet1/3 — reference only in YAML, never rendered by templates
- **`write memory`** after every config push (IOL does not auto-save)
- **Lab pre-flight** after every EVE-NG Wipe+Start: `clear_known_hosts.sh` → `init_ssh.py` → `ping_hosts.py`

---

## Environment

- Management network: 192.168.1.0/24, OOB on Ethernet1/3 per router
- Lab DNS: 192.168.1.12 resolves r1.lab–r9.lab (M05 routers)
- SSH credentials: netadmin / admin
- Obsidian vault: `C:/Users/tjehn/SynologyDrive/ObsidianVaults/PersonalOS/`
- CLAUDE.md and NAMS26_context.md live in the repo root
