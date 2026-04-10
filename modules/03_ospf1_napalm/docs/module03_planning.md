# Module 03 — OSPF Classic Mode / NAPALM
## Planning Document — `module03_planning.md`
### NAMS26 | Network Automation Management Station 2026

---

> **Document Purpose**
> This is the planning document for Module 03. It describes the topology,
> learning objectives, and the design of all scripts.
>
> **Audience:** CCNP-level. Routing protocol mechanics are assumed knowledge.
> The focus is on what the automation scripts need to do, not on explaining OSPF.
>
> **Status:** Complete.

---

## Module Objectives

By the end of Module 03, the following will be in place:

1. **Multi-area OSPF deployed** across 11 routers — Area 0 (backbone) and Area 10 — from a YAML source of truth via NAPALM.
2. **Mixed OSPF authentication demonstrated** — plain-text per-interface, MD5 per-interface, area-level plain-text, and area-level MD5 across different segments.
3. **DR/BDR priority manipulation configured** on two multi-access segments, with expected election outcomes visible in `show ip ospf interface`.
4. **Point-to-point network type override demonstrated** — the R7–R8 Ethernet link configured with `ip ospf network point-to-point` on both ends, eliminating DR/BDR election.
5. **Inter-area summarization configured** — R8 (ABR) using `area 0 range 192.1.100.0 255.255.252.0` to aggregate Area 0 subnets into a single Type 3 Summary LSA for Area 10.
6. **NAPALM workflow established** — `load_merge_candidate` / `compare_config` / `commit_config` pattern introduced and used for all deployments.
7. **Verification script operational** — validates neighbor adjacency state, interface configuration, LSDB content, and routing table across all 11 routers.
8. **Troubleshooting script operational** — live checks for adjacency issues and authentication failures, plus five failure demonstration scenarios.

---

## Lab Topology

### Routers and Roles

| Router | Role | Areas |
|--------|------|-------|
| R1 | Internal | Area 0 |
| R2 | Internal | Area 0 |
| R3 | Internal | Area 0 |
| R4 | Internal | Area 0 |
| R5 | Internal | Area 0 |
| R6 | Internal | Area 0 |
| R7 | Internal | Area 0 |
| R8 | ABR | Area 0 + Area 10 |
| R9 | Internal | Area 10 |
| R10 | Internal | Area 10 |
| R11 | Internal | Area 0 |

### Links

| Segment | Subnet | Routers | Notes |
|---------|--------|---------|-------|
| 192.1.100.0/24 | R1, R2, R3, R11 | Area 0 | Multi-access, DR/BDR election |
| 192.1.101.0/24 | R2, R5 | Area 0 | Serial, MD5 auth |
| 192.1.102.0/24 | R4, R5 | Area 0 | Serial, PPP, MD5 auth |
| 192.1.103.0/24 | R3, R4, R6 | Area 0 | Multi-access, no auth |
| 192.1.67.0/24 | R6, R7 | Area 0 | Ethernet, no auth |
| 192.1.78.0/24 | R7, R8 | Area 0 | Ethernet, point-to-point override |
| 192.1.89.0/24 | R8, R9 | Area 10 | Ethernet, no auth |
| 192.1.90.0/24 | R9, R10 | Area 10 | Ethernet, no auth |

### Loopbacks (all `ip ospf network point-to-point`)

| Router | Loopback | IP | Area |
|--------|----------|----|------|
| R1 | Lo0 | 1.1.1.1/8 | Area 0 |
| R2 | Lo0 | 2.2.2.2/8 | Area 0 |
| R3 | Lo0 | 3.3.3.3/8 | Area 0 |
| R4 | Lo0 | 4.4.4.4/8 | Area 0 |
| R5 | Lo0 | 5.5.5.5/8 | Area 0 |
| R6 | Lo0 | 6.6.6.6/8 | Area 0 |
| R7 | Lo0 | 7.7.7.7/8 | Area 0 |
| R8 | Lo0 | 8.8.8.8/8 | Area 10 |
| R9 | Lo0 | 9.9.9.9/8 | Area 10 |
| R10 | Lo0 | 10.10.10.10/8 | Area 10 |
| R11 | Lo0 | 11.11.11.11/8 | Area 0 |

> R8's loopback is in Area 10, not Area 0. Area 0 routers will see R8's loopback
> as an inter-area route (Type 3 Summary LSA) rather than an intra-area route.

---

## Key Configuration Elements

### Authentication

Authentication across this topology is intentionally varied — every IOS OSPF
authentication method is demonstrated:

| Segment | Method | Routers |
|---------|--------|---------|
| 192.1.100.0/24 | Plain-text per-interface (`cisco123`) | R1, R2, R3, R11 |
| 192.1.101.0/24 | MD5 per-interface (`ccie123`) | R2, R5 |
| 192.1.102.0/24 | MD5 per-interface + PPP (`ccie123`) | R4, R5 |
| 192.1.103.0/24 | None | R3, R4, R6 |
| 192.1.67.0/24 | None | R6, R7 |
| 192.1.78.0/24 | None | R7, R8 |

R5 uses **area-level MD5** (`area 0 authentication message-digest`) instead of
per-interface commands. R11 uses **area-level plain-text** (`area 0 authentication`).
Both produce identical adjacency results — the module demonstrates that per-interface
and area-level authentication are equivalent in outcome but different in configuration
scope.

### DR/BDR Priority Manipulation

| Segment | Router | Priority | Expected Role |
|---------|--------|----------|---------------|
| 192.1.100.0/24 | R2 | 10 | DR |
| 192.1.100.0/24 | R3 | 1 (default) | BDR |
| 192.1.100.0/24 | R1, R11 | 1 (default) | DROTHER |
| 192.1.103.0/24 | R4, R6 | 10 | DR (tie — highest RID wins) |
| 192.1.103.0/24 | R3 | 5 | BDR |

### Point-to-Point Network Type Override

The R7–R8 Ethernet link uses `ip ospf network point-to-point` on both ends.
This eliminates DR/BDR election on what would otherwise be a broadcast segment.
The verify script correctly identifies P2P links and reports them as
`P2P (no DR election)` rather than looking for a DR/BDR that will never exist.

### Inter-Area Summarization

R8 (ABR) is configured with:
```
router ospf 1
 area 0 range 192.1.100.0 255.255.252.0
```

This summarizes the four Area 0 segments (192.1.100.0, 192.1.101.0, 192.1.102.0,
192.1.103.0) into a single /22 Type 3 Summary LSA that Area 10 routers see as one
inter-area prefix. Area 10 routers (R9, R10) see `192.1.100.0/22` as `O IA`.

---

## Tool: NAPALM

NAPALM (Network Automation and Programmability Abstraction Layer with Multivendor
support) is introduced in Module 03 as the replacement for Netmiko. The core
difference from an automation standpoint:

- **Netmiko** — command sender. Pushes CLI lines directly to the device.
- **NAPALM** — configuration manager. Loads a candidate, diffs it against running
  config, commits only after operator review.

The deployment workflow established in Module 03:

```python
with driver(hostname, username, password, optional_args=optional_args) as device:
    device.load_merge_candidate(config=rendered_config)
    diff = device.compare_config()
    if diff:
        print(diff)
    device.commit_config()
    device.cli(["write memory"])
```

**IOL `optional_args` required:**
```python
optional_args = {
    "ssh_config_file": None,
    "session_log":     session_log_path,
    "dest_file_system": "nvram:",
    "inline_transfer":  True,
    "enable_scp":       False,
}
```

`nvram:` reports free space in the format NAPALM expects. `inline_transfer: True`
pushes configuration over SSH instead of SCP. `enable_scp: False` prevents the
MD5 verification error that occurs on some IOL image versions. None of these
overrides are needed on physical hardware.

---

## Data Model — YAML Design

The YAML follows the established project structure:

- YAML anchor for credentials at the top (`&creds`), aliased per device (`*creds`)
- `dns_name` as the SSH connection target — never `oob_ip`
- `oob_interface` drives template exclusion of the OOB interface from rendering
- All interfaces present in a single `interfaces` dict — physical and loopback
- Every interface carries the full field set, populated or empty

### Per-interface OSPF fields

```yaml
Ethernet0/0:
  ospf_network_type: ""        # overrides default (e.g. point-to-point)
  ospf_priority: ""            # DR/BDR election weight
  ospf_authentication:
    type: plaintext            # plaintext | md5 | none
    key: cisco123
    key_id: ""                 # used only for MD5
  encapsulation: ""            # ppp — for serial interfaces
```

### Per-device OSPF block

```yaml
ospf:
  process_id: 1
  router_id: 0.0.0.1
  networks:
    - prefix: 192.1.100.0
      wildcard: 0.0.0.255
      area: 0
  area_authentication:         # area-level auth — R5 and R11 only
    - area: 0
      type: message-digest     # plaintext | message-digest
  area_range:                  # inter-area summarization — R8 only
    - area: 0
      prefix: 192.1.100.0
      mask: 255.255.252.0
  passive_interfaces: []
```

---

## Template Design — Jinja2

The `ospf_classic.j2` template renders sections in this order:

1. **Physical interfaces** (excluding OOB and Loopbacks) — ip address,
   encapsulation, OSPF network type, OSPF priority, authentication, speed/duplex
2. **Loopback interfaces** — ip address, `ip ospf network point-to-point`
3. **OSPF process block** — router-id, area authentication, network statements,
   area range, passive interfaces

Key template behaviors:
- Physical loop guard: `{% if intf_name != oob_interface and 'Loopback' not in intf_name %}`
- Loopback loop guard: `{% if 'Loopback' in lb_name %}`
- `encapsulation ppp` renders before `ip address` to satisfy IOS dependency order
- Plain-text and MD5 authentication render from independent conditions — interfaces
  with `type: none` produce no authentication commands

---

## Script Design

### `configure_ospf_classic.py`

- 4-level path resolution from `__file__`
- `--dry-run` and `--router` flags
- Jinja2 environment with `cidr_to_netmask` filter registered
- NAPALM IOS driver with IOL `optional_args`
- Per-device session logs to `logs/`
- Rendered configs written to `configs/` on every run

### `verify_ospf_classic.py`

Checks available via `--check` flag: `neighbors`, `interfaces`, `routes`, `lsdb`

**`check_neighbors`** — parses `show ip ospf neighbor`, validates FULL adjacency
state per interface. `2WAY/DROTHER` between two DROthers on a broadcast segment
is correctly identified as PASS — not a failure.

IOS quirk: point-to-point interfaces show the state as `FULL/  -` with embedded
spaces. Normalized to `FULL/-` before parsing.

**`check_interfaces`** — runs `show ip ospf interface` (full) and `show ip ospf
neighbor`. Validates area, network type, and priority per interface. DR/BDR role
identified by Router ID cross-referenced from the neighbor table. Point-to-point
interfaces report `P2P (no DR election)`.

**`check_routes`** — two steps:
1. Fetches `show ip route ospf`, parses into structured table
   (Type / Destination / Via / Interface / Cost / Age), renders with ECMP support
2. Validates each YAML network statement against live interface state using
   wildcard-aware IP math — PASS/WARN/FAIL per network

**`check_lsdb`** — runs `show ip ospf database`, informational only. Confirms
Router LSA for this router's ID is present. Checks for Summary Net LSAs on R8.

### `troubleshoot_ospf_classic.py`

**Live checks:** `neighbors`, `authentication`, `database`, `routes`, `process`

**`check_neighbors`** — `show ip ospf neighbor detail`. Scans for EXSTART,
EXCHANGE, INIT, LOADING states. Reports PASS if any FULL adjacency confirmed.

**`check_authentication`** — `show ip ospf interface` parsed into per-interface
text blocks. Validates each auth-configured interface individually — critical on
mixed-auth routers like R2. Detects MD5 enabled with no key via absence of
`Youngest key id` string.

**`check_database`** — `show ip ospf database`. Confirms own Router LSA present.
Checks for Summary Net LSAs on R8. Reports FAIL if Router Link States section absent.

**`check_routes`** — `show ip route ospf` and `show ip ospf border-routers`.
On Area 10 routers, validates inter-area routes (`O IA`) are present.

**`check_process`** — `show ip protocols`. Validates OSPF process ID and router ID.

**Failure demonstration scenarios:**

| Scenario | Fault Injected | Key Symptom |
|----------|---------------|-------------|
| `missing-network` | First non-loopback network statement removed | Prefix absent from LSDB and routing table |
| `wrong-router-id` | router-id changed to `0.0.0.99` | LSA conflict, SPF instability |
| `auth-mismatch` | Authentication key appended with `_WRONG` | Adjacency drops silently |
| `wrong-area` | First non-loopback network moved to area 99 | Adjacency stuck in ExStart/Init |
| `missing-auth-key` | Auth type set but key cleared | Hellos rejected immediately |

---

## Closing Demonstration

**Inject the drift:**
```bash
python utils/push_config.py --router R1 --cmd "router ospf 1" "no network 1.0.0.0 0.255.255.255 area 0"
```

R1's loopback network statement is removed. R1 no longer advertises `1.1.1.1/8`
into OSPF. All adjacencies remain FULL.

**Troubleshooter passes:**
```bash
python scripts/troubleshoot_ospf_classic.py --router R1
```

All five checks pass. R1 is operationally healthy.

**Verifier catches it:**
```bash
python scripts/verify_ospf_classic.py --router R1 --check routes
```

Reports FAIL: `Network 1.0.0.0 0.255.255.255 area 0 — no interface found with a
matching IP on R1`.

**Restore:**
```bash
python scripts/configure_ospf_classic.py --router R1
python scripts/verify_ospf_classic.py --router R1
```

**Instructor talking point:** The troubleshooter answers "is OSPF working?" The
verifier answers "does the device match the source of truth?" Both are needed.
A router can be operationally healthy and still be wrong. This lesson is
established in Module 03 and reinforced in Module 04 in a redistribution context.

---

## Comparison to Module 02

| Dimension | Module 02 | Module 03 |
|-----------|-----------|-----------|
| Routers | 11 (R1–R11) | 11 (R1–R11) |
| Protocol | EIGRP | OSPF |
| Tool | Netmiko | NAPALM |
| Config model | Direct push | Candidate + diff + commit |
| Authentication | None | Mixed (plaintext, MD5, area-level) |
| Areas | N/A | Area 0 + Area 10 |
| Summarization | None | `area 0 range` on R8 |
| Serial links | None | R2-R5, R4-R5 (PPP) |

---

## Lab Reset Sequence (Module 03)

See `docs/eve-ng_lab_reset_sop.md` for the full procedure.

```
# EVE-NG Web UI
Stop all nodes -> Wipe all nodes -> Start all nodes
Open consoles in SecureCRT (R1-R11)

# Each Router via console (R1-R11)
[Apply base configuration: hostname, credentials, Ethernet1/3 OOB, VTY SSH, NTP]
write memory
crypto key generate rsa modulus 1024
write memory

# NAMS26 Workstation - modules/03_ospf1_napalm/utils/
python ping_hosts.py
bash clear_known_hosts.sh
python init_ssh.py

# NAMS26 Workstation - modules/03_ospf1_napalm/scripts/
python configure_ospf_classic.py --dry-run
python configure_ospf_classic.py
python verify_ospf_classic.py
```

---

*End of Module 03 Planning Document*
*NAMS26 - Network Automation Management Station 2026*
