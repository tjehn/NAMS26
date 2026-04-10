# Module 04 — OSPF Advanced / NAPALM
## Planning Document — `module04_planning.md`
### NAMS26 | Network Automation Management Station 2026

---

> **Document Purpose**
> This is the pre-development planning document for Module 04. It describes the
> topology, learning objectives, and the intended design of all scripts before
> any code is written. It is the reference for Claude.ai planning sessions.
>
> **Audience:** CCNP-level. Routing protocol mechanics are assumed knowledge.
> The focus is on what the automation scripts need to do, not on explaining OSPF.
>
> **Status:** Lab configs verified (R1–R10). Scripts not yet written.
> Lab not yet rebooted. SSH not yet tested for this module.

---

## Module Objectives

By the end of Module 04, the following will be in place:

1. **Multi-area OSPF deployed** across 10 routers — Area 0 (backbone), Area 10, and Area 20 (NSSA) — from a YAML source of truth via NAPALM.
2. **Redistribution configured** between OSPF and two independent EIGRP domains (EIGRP 100 on the left, EIGRP 111 on the right), with R1 and R6 as ASBRs.
3. **LSA Type 3 filtering demonstrated** on both ABRs — R2 blocks specific prefixes from leaving Area 10; R3 blocks specific prefixes from entering Area 20.
4. **NSSA area behavior demonstrated** — Area 20 configured as NSSA, R3 injecting a Type 7 default route into Area 20, R6 redistributing EIGRP 111 routes as Type 7 LSAs.
5. **Type 4 / Type 5 LSA mechanics observable** — external routes from both EIGRP domains propagate through the OSPF domain as Type 5 LSAs, with Type 4 LSAs tracking ASBR reachability.
6. **NAPALM workflow reinforced** — same `load_merge_candidate` / `compare_config` / `commit_config` pattern from Module 03, applied to a more complex configuration.
7. **Verification script operational** — validates neighbor state, OSPF process config, external route presence, and filtering behavior across all 10 routers.
8. **Troubleshooting script operational** — live checks for redistribution failures, missing Type 4/5 LSAs, and NSSA misconfiguration.

---

## Lab Topology

### Routers and Roles

| Router | Role | Areas / Domains |
|--------|------|-----------------|
| R1 | ASBR | Area 0 + EIGRP 100 |
| R2 | ABR | Area 0 ↔ Area 10 |
| R3 | ABR + ASBR | Area 0 ↔ Area 20 (NSSA) |
| R4 | Internal | Area 10 |
| R5 | Internal | Area 20 |
| R6 | ASBR | Area 20 + EIGRP 111 |
| R7 | EIGRP only | EIGRP 100 |
| R8 | EIGRP only | EIGRP 100 |
| R9 | EIGRP only | EIGRP 111 |
| R10 | Internal | Area 10 |

### Links

| Segment | Subnet | Routers | Area |
|---------|--------|---------|------|
| 192.1.12.0/24 | R1 – R2 | Area 0 |
| 192.1.13.0/24 | R1 – R3 | Area 0 |
| 192.1.17.0/24 | R1 – R7 | EIGRP 100 |
| 192.1.18.0/24 | R1 – R8 | EIGRP 100 |
| 192.1.24.0/24 | R2 – R4 | Area 10 |
| 192.1.35.0/24 | R3 – R5 | Area 20 |
| 192.1.40.0/24 | R4 – R10 | Area 10 |
| 192.1.56.0/24 | R5 – R6 | Area 20 |
| 192.1.69.0/24 | R6 – R9 | EIGRP 111 |

### Loopbacks (all `ip ospf network point-to-point`)

| Router | Loopback | IP | Domain |
|--------|----------|----|--------|
| R1 | Lo0 | 1.0.0.1/8 | Area 0 |
| R1 | Lo1 | 11.0.0.1/8 | Area 0 |
| R2 | Lo0 | 2.0.0.2/8 | Area 0 |
| R2 | Lo1 | 22.0.0.2/8 | Area 0 |
| R3 | Lo0 | 3.0.0.3/8 | Area 0 |
| R3 | Lo1 | 33.0.0.3/8 | Area 0 |
| R4 | Lo0 | 4.0.0.4/8 | Area 10 |
| R4 | Lo1 | 44.0.0.4/8 | Area 10 |
| R4 | Lo12–Lo15 | 105.1.12.4 – 105.1.15.4 /24 | Area 10 (simulated prefix pool — block A, matched by `network 105.1.12.0 0.0.3.255`) |
| R4 | Lo16–Lo19 | 105.1.16.4 – 105.1.19.4 /24 | Area 10 (simulated prefix pool — block B, matched by `network 105.1.16.0 0.0.3.255`) |
| R5 | Lo0 | 5.0.0.5/8 | Area 20 |
| R5 | Lo1 | 55.0.0.5/8 | Area 20 |
| R6 | Lo0 | 6.0.0.6/8 | EIGRP 111 |
| R6 | Lo1 | 66.0.0.6/8 | EIGRP 111 |
| R7 | Lo0 | 7.0.0.7/8 | EIGRP 100 |
| R7 | Lo1 | 77.0.0.7/8 | EIGRP 100 |
| R7 | Lo2 | 107.7.7.7/24 | EIGRP 100 |
| R8 | Lo0 | 8.0.0.8/8 | EIGRP 100 |
| R8 | Lo1 | 88.0.0.8/8 | EIGRP 100 |
| R8 | Lo2 | 108.8.8.8/24 | EIGRP 100 |
| R9 | Lo0 | 9.0.0.9/8 | EIGRP 111 |
| R9 | Lo1 | 99.0.0.9/8 | EIGRP 111 |
| R10 | Lo0 | 10.0.0.10/8 | Area 10 |
| R10 | Lo1 | 110.0.0.10/8 | Area 10 |
| R10 | Lo11–Lo14 | 100–103.0.0.10 /8 | Area 10 (simulated prefix pool) |

> R5 Loopback0 (5.0.0.5) and R6 Loopback0 (6.0.0.6) are active. Both Lo0 and Lo1
> are advertised on R5 (into OSPF Area 20) and R6 (into EIGRP 111).
>
> R10 Loopback1 (110.0.0.10) is advertised in OSPF Area 10 via
> `network 110.0.0.0 0.255.255.255 area 10`.

---

## Key Configuration Elements

### Redistribution

**R1 — OSPF ↔ EIGRP 100 (bidirectional)**
```
router eigrp 100
 redistribute ospf 1 metric 10000 100 255 1 1500
!
router ospf 1
 redistribute eigrp 100 metric-type 1 subnets
 default-information originate always
```
R1 is both an ABR (Area 0) and an ASBR. It injects EIGRP 100 prefixes (R7 and R8 loopbacks, 192.1.17.0, 192.1.18.0) into OSPF as Type 5 LSAs. It injects OSPF routes back into EIGRP 100. `default-information originate always` injects a default route into OSPF domain-wide.

**R6 — OSPF ↔ EIGRP 111 (bidirectional)**
```
router eigrp 111
 redistribute ospf 1 metric 10000 100 255 1 1500
!
router ospf 1
 redistribute eigrp 111 metric-type 1 subnets
```
R6 is an ASBR within Area 20 (NSSA). It injects EIGRP 111 prefixes (R9 loopbacks, 192.1.69.0) into OSPF as Type 7 LSAs (because it's in an NSSA). R3 (the NSSA ABR) converts those Type 7 LSAs into Type 5 LSAs before flooding them into Area 0.

### Network Statement Summarization (R4)

R4 carries eight simulated loopback prefixes in Area 10, organized into two contiguous blocks:

- **Block A:** Lo12–Lo15 — `105.1.12.4` through `105.1.15.4` /24
- **Block B:** Lo16–Lo19 — `105.1.16.4` through `105.1.19.4` /24

Rather than eight individual network statements, R4 uses two wildcard-aggregated statements:

```
router ospf 1
 network 105.1.12.0 0.0.3.255 area 10
 network 105.1.16.0 0.0.3.255 area 10
```

The wildcard `0.0.3.255` spans four /24 subnets within the third octet (e.g., `.12` through `.15`), matching exactly the four loopbacks in each block. Students will have covered wildcard mask math in prior material — the point here is the operational consequence: by splitting eight loopbacks into two separately-controlled blocks, an operator can include or exclude either block independently simply by adding or removing one network statement. This is a lightweight illustration of how OSPF network statement scope affects what gets advertised without touching the interfaces themselves.

> Note: The individual /24 prefixes still appear as separate Type 1 LSA entries in the
> LSDB — the wildcard controls which interfaces OSPF *matches*, not how the prefixes
> are advertised. Inter-area summarization (Type 3 LSA aggregation) is a separate
> mechanism using `area X range`.

### LSA Filtering

**R2 — Block 102.0.0.0/8 and 103.0.0.0/8 from leaving Area 10**
```
ip prefix-list A10-OUT deny 102.0.0.0/8
ip prefix-list A10-OUT deny 103.0.0.0/8
ip prefix-list A10-OUT permit 0.0.0.0/0 le 32
!
router ospf 1
 area 10 filter-list prefix A10-OUT out
```
These are R10's Loopback13 (102.0.0.10) and Loopback14 (103.0.0.10) prefixes. After filtering, Area 0 and Area 20 routers will not see these two /8 prefixes in their routing tables.

**R3 — Block 100.0.0.0/8 from entering Area 20**
```
ip prefix-list A20-IN deny 100.0.0.0/8 le 32
ip prefix-list A20-IN permit 0.0.0.0/0 le 32
!
router ospf 1
 area 20 filter-list prefix A20-IN in
```
R10's Loopback11 (100.0.0.10) is in the 100.0.0.0/8 range. Area 20 routers (R5, R6) will not receive this prefix. All other inter-area routes pass through normally. R10 Lo1 (110.0.0.10) is advertised in OSPF Area 10 but falls outside the 100.0.0.0/8 deny range and is therefore not affected by this filter.

> Note: R1 also has `ip prefix-list A20-IN` defined in its running config. It is
> not referenced by any `filter-list` on R1 and has no operational effect. This is
> a stale artifact from lab exercise work and can be cleaned up but does not affect
> behavior.

### NSSA (Area 20)

Area 20 is configured as NSSA on all three Area 20 routers (R3, R5, R6):
```
router ospf 1
 area 20 nssa
```
R3 (the ABR) additionally injects a Type 7 default route into Area 20:
```
router ospf 1
 area 20 nssa default-information-originate
```
This provides Area 20 routers with a default path toward Area 0 and the external domains. The `default-information-originate` is on the ABR only — R5 and R6 simply have `area 20 nssa`.

---

## Tool: NAPALM (same as Module 03)

No new tool is introduced in Module 04. The NAPALM workflow is identical to Module 03:

```python
with driver(hostname, username, password, optional_args=optional_args) as device:
    device.load_merge_candidate(config=rendered_config)
    diff = device.compare_config()
    if diff:
        print(diff)
    device.commit_config()
    device.cli(["write memory"])
```

The IOL `optional_args` remain required:
```python
optional_args = {
    "ssh_config_file": None,
    "session_log":     session_log_path,
    "dest_file_system": "nvram:",
    "inline_transfer":  True,
}
```

**What Module 04 adds over Module 03 (from an automation standpoint):**
- The YAML must model redistribution parameters, prefix-list filters, and NSSA configuration — not just OSPF interfaces and network statements
- The Jinja2 template must render EIGRP blocks alongside OSPF blocks (some routers are EIGRP-only)
- The verify script must understand external routes (Type 5 / Type 7), not just intra- and inter-area routes
- The troubleshoot script must check ASBR reachability (Type 4 LSAs) and NSSA conversion behavior

---

## Data Model — YAML Design

The YAML will follow the established Module 03 structure with these additions:

### Per-device additions

**Redistribution** — on R1 and R6 (routers that redistribute between protocols):
```yaml
redistribution:
  ospf_into_eigrp:
    eigrp_as: 100
    metric: "10000 100 255 1 1500"
  eigrp_into_ospf:
    eigrp_as: 100
    metric_type: 1
    subnets: true
```

**EIGRP block** — on R1, R6, R7, R8, R9 (EIGRP participants):
```yaml
eigrp:
  as_number: 100
  networks:
    - 192.1.17.0
    - 192.1.18.0
```

**OSPF area types** — on ABRs (R2 NSSA type not needed; R3 is NSSA ABR):
```yaml
ospf:
  area_types:
    - area: 20
      type: nssa
      default_information_originate: true   # ABR only
```

**LSA filtering** — on ABRs (R2, R3):
```yaml
ospf:
  area_filters:
    - area: 10
      direction: out
      prefix_list: A10-OUT
  prefix_lists:
    A10-OUT:
      - seq: 5
        action: deny
        prefix: 102.0.0.0/8
      - seq: 10
        action: deny
        prefix: 103.0.0.0/8
      - seq: 15
        action: permit
        prefix: 0.0.0.0/0 le 32
```

### Routers without OSPF (R7, R8, R9)

These routers only need an `eigrp` block. The YAML device structure will include an
`ospf: ~` (null) sentinel so the template can cleanly skip the OSPF block. This is the
same pattern as Module 03 handled loopback vs. physical interface separation.

---

## Template Design — Jinja2

The `ospf_advanced.j2` template will render sections in this order:

1. **Physical interfaces** (excluding OOB and Loopbacks) — ip address, shutdown, description, speed/duplex
2. **Loopback interfaces** — ip address, `ip ospf network point-to-point`
3. **EIGRP block** (if `eigrp` key is defined and not null) — AS number, network statements, redistribution
4. **OSPF block** (if `ospf` key is defined and not null):
   - `router ospf <process_id>`
   - `router-id`
   - Area type declarations (`area X nssa`, `area X stub`, etc.)
   - Area filter-list statements
   - Network statements
   - Redistribution into OSPF
   - `default-information originate always` (if configured)
5. **Prefix-lists** (if `prefix_lists` is defined) — rendered after routing blocks

The EIGRP-only routers (R7, R8, R9) will only render sections 1–3. The template must handle
this cleanly without leaving blank `router ospf` blocks.

---

## Script Design

### `configure_ospf_advanced.py`

Follows the exact same structure as `configure_ospf_classic.py` from Module 03:
- 4-level path resolution from `__file__`
- `--dry-run` and `--router` flags
- Jinja2 environment with `cidr_to_netmask` filter registered
- NAPALM IOS driver with IOL `optional_args`
- Per-device session logs to `logs/`
- Rendered configs written to `configs/` during dry-run

### `verify_ospf_advanced.py`

Checks available via `--check` flag: `neighbors`, `interfaces`, `routes`, `lsdb`, `redistribution`

**`check_neighbors`** — same logic as Module 03. Parses `show ip ospf neighbor`, validates FULL adjacency state. On EIGRP-only routers (R7, R8, R9), this check is skipped.

**`check_interfaces`** — same logic as Module 03. Validates area assignment and network type per OSPF interface. Skipped on EIGRP-only routers.

**`check_routes`** — enhanced for Module 04:
- Parses `show ip route ospf` including Type E1 (`O E1`) and Type N1/N2 (`O N1`, `O N2`) external routes, not just intra/inter-area
- Validates that Area 20 routers (R5, R6) have a default route (`O N2 0.0.0.0/0`) from NSSA
- Validates that filtering is working: Area 20 routers should NOT have `100.0.0.0/8` (blocked by R3's A20-IN filter); Area 0 routers should NOT have `102.0.0.0/8` or `103.0.0.0/8` (blocked by R2's A10-OUT filter)
- R4 prefix pool expected routes: `105.1.12.0/24` through `105.1.15.0/24` (block A) and `105.1.16.0/24` through `105.1.19.0/24` (block B) — all eight should appear as `O IA` on Area 0 routers; absence of either block indicates a network statement or summarization issue on R4
- R5 Lo0 (`5.0.0.5`) and Lo1 (`55.0.0.5`) should both appear as `O IA` on Area 0 routers
- R6 Lo0 (`6.0.0.6`) and Lo1 (`66.0.0.6`) enter OSPF via redistribution (Type 7 → Type 5) — should appear as `O E1` on Area 0 routers, not `O IA`

**`check_lsdb`** — enhanced for Module 04:
- Parses `show ip ospf database` for all LSA types
- Confirms Type 5 LSAs (external routes from R1 and R6/R3 conversion) are present in Area 0 routers
- Confirms Type 4 LSAs (ASBR summary) are present — R1's ASBR reachability should be advertised into Area 10 and Area 20
- On Area 20 routers, confirms Type 7 LSAs (NSSA external) are present for R6's redistributed routes
- Flags if Type 7 LSAs are missing on R5/R6 (redistribution not working)

**`check_redistribution`** (new in Module 04):
- On R1: confirms `show ip route eigrp` has OSPF-sourced routes redistributed into EIGRP 100
- On R6: confirms `show ip route eigrp` has OSPF-sourced routes redistributed into EIGRP 111
- On R7/R8: confirms EIGRP routes include D EX (external) entries from OSPF redistribution
- On R9: confirms EIGRP routes include D EX entries from OSPF redistribution

### `troubleshoot_ospf_advanced.py`

**Live checks:** `neighbors`, `database`, `routes`, `redistribution`, `process`

**`check_database`** — checks for presence of Type 4, Type 5, and Type 7 LSAs:
- Missing Type 4 on R4/R10: indicates the ABR (R2) cannot reach or is not advertising the ASBR (R1)
- Missing Type 5 from R1's router-id on Area 0 routers: redistribution from EIGRP 100 has failed
- Missing Type 7 on R5: R6 is not redistributing EIGRP 111 into OSPF or the NSSA conversion is broken
- Checks `show ip ospf database external` and `show ip ospf database nssa-external`

**`check_redistribution`** — targeted per-router:
- Uses `show ip route` to detect missing redistributed prefixes
- Compares expected EIGRP loopback count (R7: 3 loopbacks, R8: 3 loopbacks) against actual routes in OSPF table on a backbone router (R1)

**Failure demonstration scenarios:**
- `inject_missing_redistribute` — remove redistribution on R1 or R6; show missing Type 5/7 LSAs
- `inject_wrong_area_type` — remove `area 20 nssa` from R5; show adjacency failure or wrong LSA types
- `inject_filter_all` — replace prefix-list with `deny any`; show all inter-area routes blocked
- `inject_missing_network` — remove a network statement (same as Module 03)
- `inject_wrong_router_id` — change router ID to `0.0.0.99` (same as Module 03)

---

## Closing Demonstration

Same structure as Module 03's config-drift demonstration, adapted for redistribution:

**Inject the drift:**
```bash
python utils/push_config.py --router R1 --cmd "router ospf 1" "no redistribute eigrp 100 metric-type 1 subnets"
```
R1 stops redistributing EIGRP 100 into OSPF. R7 and R8 loopbacks vanish from the OSPF domain. All adjacencies remain up.

**Troubleshooter passes:**
```bash
python scripts/troubleshoot_ospf_advanced.py --router R1
```
All neighbor and process checks pass. R1 is a healthy OSPF router. The troubleshooter does not check whether redistribution is configured.

**Verifier catches it:**
```bash
python scripts/verify_ospf_advanced.py --router R1 --check redistribution
```
Reports FAIL: expected redistributed EIGRP prefixes are absent from the OSPF domain.

**Restore:**
```bash
python scripts/configure_ospf_advanced.py --router R1
python scripts/verify_ospf_advanced.py --router R1
```

**Instructor talking point:** Same lesson as Module 03, reinforced in a redistribution context. The troubleshooter confirms OSPF is running. The verifier confirms OSPF is doing what the source of truth says it should be doing. Redistribution misconfiguration — one of the most common production issues — is invisible to the troubleshooter and immediately visible to the verifier.

---

## Comparison to Module 03

| Dimension | Module 03 | Module 04 |
|-----------|-----------|-----------|
| Routers | 11 (R1–R11) | 10 (R1–R10) |
| OSPF areas | 2 (Area 0, Area 10) | 3 (Area 0, Area 10, Area 20) |
| Area types | Standard only | Standard + NSSA |
| Authentication | Mixed (plaintext, MD5, area-level) | None (not a focus of this module) |
| Redistribution | None | Bidirectional, two EIGRP domains |
| Filtering | None | LSA Type 3 filtering on both ABRs |
| External routes | None | Type 5 (from R1), Type 7→5 (from R6 via R3) |
| Tool | NAPALM | NAPALM (same) |
| Workflow | Identical | Identical |

---

## Lab Reset Sequence (Module 04)

```
# EVE-NG Web UI
Stop all nodes → Wipe all nodes → Start all nodes
Open consoles in SecureCRT (R1–R10)

# Each Router via console (R1–R10)
[Apply base configuration: hostname, credentials, Ethernet1/3 OOB, VTY SSH, NTP]
write memory
crypto key generate rsa modulus 1024
write memory

# NAMS26 Workstation — modules/04_ospf2_napalm/utils/
python ping_hosts.py
bash clear_known_hosts.sh
python check_ssh.py

# NAMS26 Workstation — modules/04_ospf2_napalm/scripts/
python configure_ospf_advanced.py --dry-run
python configure_ospf_advanced.py
python verify_ospf_advanced.py
```

---

*End of Module 04 Planning Document*
*NAMS26 — Network Automation Management Station 2026*