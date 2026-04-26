# Module 05 — IPv6 EIGRP + OSPFv3 / Nornir
## Planning Document — `module05_planning.md`
### NAMS26 | Network Automation Management Station 2026

---

> **Document Purpose**
> This is the pre-development planning document for Module 05. It describes the
> topology, learning objectives, and the intended design of all scripts before
> any code is written. It is the reference for Claude.ai planning sessions.
>
> **Audience:** CCNP-level. IPv6 addressing and routing protocol mechanics are
> assumed knowledge. The focus is on what the automation scripts need to do,
> not on explaining EIGRPv6 or OSPFv3.
>
> **Status:** YAML complete. Jinja2 template and configure script scaffolded
> but not fully tested. Verify and troubleshoot scripts are stubs. Lab not
> yet fully validated.

---

## Module Objectives

By the end of Module 05, the following will be in place:

1. **Pure-IPv6 topology deployed** — nine routers, no IPv4 routing beyond OOB management.
2. **Two independent EIGRPv6 domains** — AS 100 on the left (R1, R7), AS 111 on the right (R6, R8) — each redistributed bidirectionally into a central OSPFv3 domain.
3. **Multi-area OSPFv3 deployed** — Area 0 (backbone), Area 10 (totally stubby), Area 20 (NSSA) — using per-interface area assignment (`ipv6 ospf <pid> area <area>`), not `network` statements.
4. **Nornir-based parallel deployment** — all nine routers configured simultaneously using `netmiko_send_config` tasks dispatched by Nornir's `RunnerPlugin`.
5. **Explicit router-IDs required** — routers with no IPv4 addresses (Area 10/20 internal routers) must have `router-id` explicitly configured in the OSPFv3 and EIGRPv6 process — otherwise the process fails to start.
6. **Verification script operational** — validates neighbor state, routing table entries, redistribution presence, and area membership across all nine routers.
7. **Troubleshooting script operational** — live checks for neighbor state, process configuration, and routing table entries.
8. **Closing demo shows Nornir merge limitation** — removing R1's EIGRP→OSPF redistribution and demonstrating that `netmiko_send_config` does not restore it (additive only), while the verify script catches the drift.

---

## Lab Topology

### Routers and Roles

| Router | Role | OSPFv3 Area | EIGRPv6 AS |
|--------|------|-------------|------------|
| R1 | ASBR | Area 0 | AS 100 (ASBR) |
| R2 | ABR | Area 0 ↔ Area 10 | — |
| R3 | ABR | Area 0 ↔ Area 20 | — |
| R4 | ABR | Area 10 ↔ Area 20 | — |
| R5 | Internal | Area 10 | — |
| R6 | ASBR | Area 20 | AS 111 (ASBR) |
| R7 | EIGRP only | — | AS 100 |
| R8 | EIGRP only | — | AS 111 |
| R9 | Internal | Area 10 | — |

### OSPFv3 Areas

| Area | Type | Routers | ABR | Notes |
|------|------|---------|-----|-------|
| 0 | Backbone | R1, R2, R3 | — | R1/R2/R3 LAN segment |
| 10 | Totally Stubby | R2 (ABR), R4 (ABR), R5, R9 | R2, R4 | `stub no-summary` on R2 |
| 20 | NSSA | R3 (ABR), R4 (ABR), R6 (ASBR) | R3, R4 | `nssa no-summary` on R3 |

> R4 is a dual-ABR: it sits at the boundary of Area 10 and Area 20. This is a
> deliberate design choice — it demonstrates that an ABR does not need to connect
> to Area 0 directly as long as there is a path through Area 0 ABRs.

### EIGRPv6 Domains

| AS | Routers | Redistribution Point |
|----|---------|----------------------|
| 100 | R1, R7 | R1 (bidirectional into/from OSPFv3) |
| 111 | R6, R8 | R6 (bidirectional into/from OSPFv3) |

### Links

| Segment | IPv6 Prefix | Routers | Area / Domain |
|---------|-------------|---------|---------------|
| `FC00:192:168:123::/64` | R1–R2–R3 LAN | Eth0/0 | OSPFv3 Area 0 |
| `FC00:192:168:17::/64` | R1–R7 | Eth0/1 / Eth0/0 | EIGRPv6 AS 100 |
| R2–R4 link | TBD from YAML | Area 10 |
| R3–R6 or R3–R4 link | TBD from YAML | Area 20 |

> Confirm all link prefixes against the YAML before finalizing the verbal script.
> The YAML is the authoritative source — this table is a planning summary.

---

## Key Configuration Elements

### Per-Interface Area Assignment

OSPFv3 does not use `network` statements. Area assignment is per-interface:

```
interface Ethernet0/0
 ipv6 ospf 1 area 0
```

This is a fundamental difference from OSPFv2. The Jinja2 template must render
`ipv6 ospf <pid> area <area>` on every interface that has an `ospf_area` value
in the YAML.

### Explicit Router-IDs

Routers with no IPv4 addresses cannot auto-select a router-id from an IPv4 interface.
EIGRPv6 and OSPFv3 will fail to start without an explicit router-id on these routers.
The YAML includes a `router_id` field for every device — the template renders it
unconditionally.

```
ipv6 router ospf 1
 router-id 4.4.4.4
```

### Redistribution at R1 and R6

Bidirectional redistribution between EIGRPv6 and OSPFv3. The metric for
EIGRP redistribution follows the project standard:

```
ipv6 router eigrp 100
 redistribute ospf 1 metric 10000 100 255 1 1500
!
ipv6 router ospf 1
 redistribute eigrp 100 metric-type 1
```

### Area Types

**Area 10 — Totally Stubby** (R2 ABR):
```
ipv6 router ospf 1
 area 10 stub no-summary
```

**Area 20 — NSSA** (R3 ABR):
```
ipv6 router ospf 1
 area 20 nssa no-summary
```

All other Area 20 and Area 10 participants use the matching area type command
without `no-summary`.

---

## Tool: Nornir

Module 05 introduces Nornir as the automation framework. Key differences from NAPALM:

| Dimension | NAPALM (Modules 03–04) | Nornir (Module 05) |
|-----------|----------------------|---------------------|
| Execution | Sequential, one device at a time | Parallel by default |
| Config push | `merge_candidate` / `commit_config` | `netmiko_send_config` (merge) |
| Diff before commit | Yes — explicit NAPALM diff | No — changes applied directly |
| Inventory | Manual YAML loading | `SimpleInventory` plugin |
| Connection | Direct NAPALM driver | `netmiko` connection plugin |

**Nornir's three jobs:**
1. **Inventory** — load and filter devices (`SimpleInventory` from YAML)
2. **Parallel dispatch** — run tasks across all devices simultaneously (`RunnerPlugin`)
3. **Result aggregation** — collect and display per-device results (`print_result`)

**Key limitation:** `netmiko_send_config` is additive. It adds what is in the
rendered config. It does not remove lines that are absent from the candidate.
This is the central point of the Module 05 closing demonstration.

---

## Data Model — YAML Design

The YAML follows the established project structure with these Module 05 additions:

### Per-interface keys

Each interface entry includes:
```yaml
Ethernet0/0:
  ipv6_address: FC00:192:168:123::1/64
  ipv6_link_local: FE80:192:168:123::1
  ospf_area: 0
  ospf_network_type: ""
  eigrp_as: ""
  shutdown: false
  speed: 100
  duplex: full
```

- `ipv6_address` / `ipv6_link_local` replace the IPv4 `ip` field
- `ospf_area` drives per-interface `ipv6 ospf <pid> area <area>` rendering
- `eigrp_as` drives per-interface `ipv6 eigrp <as>` rendering
- Interfaces with `ospf_area: ""` and `eigrp_as: ""` are not rendered in any routing block

### Per-device routing block

```yaml
ospf:
  process_id: 1
  router_id: "1.1.1.1"
  area_types:
    - area: 20
      type: nssa
      no_summary: true
  redistribute_eigrp:
    as_number: 100
    metric_type: 1

eigrp:
  as_number: 100
  router_id: "1.1.1.1"
  redistribute_ospf:
    process: 1
    metric: "10000 100 255 1 1500"
```

EIGRP-only routers (R7, R8) have `ospf: ~` (null sentinel). The template skips
the OSPFv3 block entirely when `ospf` is null.

---

## Template Design — Jinja2

`ipv6_eigrp_ospf.j2` renders sections in this order:

1. **Global IPv6 commands** — `ipv6 unicast-routing`, `ipv6 cef`
2. **Physical interfaces** (excluding OOB) — IPv6 addresses, link-local, `ipv6 ospf <pid> area <area>`, `ipv6 eigrp <as>`
3. **Loopback interfaces** — IPv6 addresses, `ipv6 ospf <pid> area <area>`
4. **EIGRPv6 block** (if `eigrp` is defined) — `ipv6 router eigrp <as>`, `router-id`, `redistribute ospf`
5. **OSPFv3 block** (if `ospf` is defined) — `ipv6 router ospf <pid>`, `router-id`, area types, `redistribute eigrp`

**Critical Jinja2 guard:** `ospf_area: 0` is falsy in Jinja2. Do not use
`{% if intf.ospf_area %}` to check whether OSPF area assignment should be rendered
— Area 0 will always be skipped. Use:

```jinja
{% if intf.ospf_area is not none and intf.ospf_area != "" %}
 ipv6 ospf {{ ospf.process_id }} area {{ intf.ospf_area }}
{% endif %}
```

---

## Script Design

### `configure_ipv6_eigrp_ospf.py`

- 4-level path resolution from `__file__` (`SCRIPT_DIR → MODULE_DIR → MODULES_DIR → PROJECT_ROOT`)
- `--dry-run` and `--router` flags
- Builds Nornir `SimpleInventory` from YAML (hosts.yaml / groups.yaml constructed dynamically from module YAML, or inline dict)
- Renders Jinja2 template per device
- Dispatches `netmiko_send_config` in parallel via `nr.run()`
- Session logs to `modules/05_ipv6_eigrp_ospf_nornir/logs/`
- Rendered configs to `configs/` during dry-run

### `verify_ipv6_eigrp_ospf.py`

Checks via `--check` flag: `neighbors`, `routes`, `redistribution`, `areas`

- **`check_neighbors`** — `show ipv6 ospf neighbor` (OSPF) and `show ipv6 eigrp neighbors` (EIGRP); validate adjacency state per expected interface
- **`check_routes`** — `show ipv6 route ospf` and `show ipv6 route eigrp`; validate route types and expected prefixes
- **`check_redistribution`** — on R1/R6: confirm redistribution statements are configured; on EIGRP-only: confirm `D EX` entries present
- **`check_areas`** — `show ipv6 ospf` per router; validate process-id, router-id, area type

### `troubleshoot_ipv6_eigrp_ospf.py`

Checks via `--check` flag: `neighbors`, `process`, `routes`

- **`check_neighbors`** — live adjacency state only; does not compare against YAML
- **`check_process`** — confirms OSPFv3 and EIGRPv6 processes are running with correct router-ids
- **`check_routes`** — displays routing table; flags if no routes found

---

## Closing Demonstration

Same structure as Module 04's redistribution drift demonstration, adapted for Nornir
and the merge model limitation.

**Inject the drift:**
```bash
python utils/push_config.py --router R1 \
  --cmd "ipv6 router ospf 1" "no redistribute eigrp 100"
```
R1 stops redistributing EIGRP 100 into OSPFv3. R7's prefixes vanish from the OSPFv3 domain.
OSPFv3 adjacencies remain FULL.

**Troubleshooter passes:**
```bash
python scripts/troubleshoot_ipv6_eigrp_ospf.py --router R1
```
Neighbor and process checks pass — R1 is healthy.

**Verifier catches it:**
```bash
python scripts/verify_ipv6_eigrp_ospf.py --router R1 --check redistribution
```
Reports FAIL: redistribution statement absent.

**Attempt to restore with Nornir (demonstrates limitation):**
```bash
python scripts/configure_ipv6_eigrp_ospf.py --router R1
```
The `netmiko_send_config` task adds lines from the rendered template. But the missing
`redistribute eigrp 100` line IS in the template — it will be re-added. Wait: actually
`netmiko_send_config` adds what the config contains — so it would add the redistribute
line back since that line is in the rendered template. The limitation demo requires
injecting a *stray* line that is NOT in the template — then showing that re-running
the configure script produces no diff and leaves the stray line in place.

**Stray line demonstration:**
```bash
python utils/push_config.py --router R1 \
  --cmd "ipv6 router ospf 1" "redistribute connected"
python scripts/configure_ipv6_eigrp_ospf.py --router R1
# No change — stray line remains; Nornir/netmiko_send_config is additive
python scripts/verify_ipv6_eigrp_ospf.py --router R1 --check redistribution
# Verify catches unexpected behavior in the route table
```

**Instructor talking point:** Nornir adds parallel execution and inventory abstraction.
It does not add config enforcement. The stray line persists because `netmiko_send_config`
does not enforce complete intended state — it only applies what is in the rendered template.
This is the boundary between Nornir (push-based) and Ansible (desired state). That
transition begins in Module 10.

---

## Comparison to Module 04

| Dimension | Module 04 | Module 05 |
|-----------|-----------|-----------|
| Routers | 10 (R1–R10) | 9 (R1–R9) |
| IP version | IPv4 | IPv6 only |
| Tool | NAPALM | Nornir |
| Config push | Sequential, diff-before-commit | Parallel, additive (no diff preview) |
| OSPF areas | 3 (Area 0, 10, 20 NSSA) | 3 (Area 0, 10 Stub, 20 NSSA) |
| Area assignment | `network` statements | Per-interface (`ipv6 ospf <pid> area`) |
| EIGRP domains | 2 (AS 100, AS 111) | 2 (AS 100, AS 111) |
| Redistribution | OSPF ↔ EIGRP 100/111 | OSPFv3 ↔ EIGRPv6 100/111 |
| Router-ID requirement | Auto from IPv4 | Must be explicit (IPv6-only routers) |

---

*End of Module 05 Planning Document*
*NAMS26 — Network Automation Management Station 2026*
