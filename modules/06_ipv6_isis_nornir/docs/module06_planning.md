# Module 06 — IS-IS / Nornir
## Planning Document
### `docs/module06_planning.md`
### NAMS26 — Network Automation Management Station 2026

---

## Module at a Glance

| Item | Value |
|------|-------|
| Module | 06 |
| Technology | IS-IS Named Mode (IPv4 primary + IPv6 zone) |
| Tool | Nornir |
| Config Mode | Named Mode exclusively |
| Lab Fabric | Shared fabric — COSW-01 / COSW-02 |
| Router Count | 12 (R1–R12) |
| Status | COMPLETE — Phase 6 complete |

---

## Learning Objectives

By the end of this module, students will be able to:

1. Explain IS-IS area design — Level-1, Level-2, and L1/L2 router roles
2. Configure IS-IS Named Mode on Cisco IOL routers including NET address assignment
3. Understand and demonstrate DIS election on a multi-access (broadcast) segment
4. Explain route leaking from L2 to L1 and why it is needed
5. Configure Multi-Topology IS-IS (MT-IS-IS) for IPv6 on a subset of routers
6. Redistribute an external routing domain (OSPF) into IS-IS at an ASBR
7. Use `nr.run()` with a custom task function for role-aware IS-IS deployment
8. Use `nr.filter()` to deploy configuration in the correct operational sequence

---

## Technology Scope

### What This Module Covers

- IS-IS Named Mode configuration (`router isis NAMS26`)
- NET address design and assignment
- Level-1, Level-2, and L1/L2 router roles
- IS-IS area design — three L1 areas + one L2 backbone
- DIS election on a broadcast segment — priority manipulation, pseudonode LSP
- Route leaking (L2 → L1) — `redistribute isis ip level-2 into level-1`
- MT-IS-IS for IPv6 — `address-family ipv6 / multi-topology` on two leaf routers
- OSPF-to-IS-IS redistribution at ASBR-1
- Wide metrics — `metric-style wide` under IS-IS Named Mode
- Interface cost assignment

### What This Module Does Not Cover

- IS-IS authentication (deferred — not required for automation demonstration)
- Route summarization (deferred to Module 09)
- IS-IS over serial links (all Ethernet for simplicity on shared fabric)
- Classic IS-IS mode (Named Mode only per project standard)
- Full dual-stack IS-IS throughout — IPv6 is a bounded zone only

### Nornir Deepening

Module 05 introduced `nr.run()` and the basic Nornir task pattern.
Module 06 deepens both:

| Pattern | Module 05 | Module 06 |
|---------|-----------|-----------|
| `nr.run()` | Basic task, single protocol | Custom task function, IS-IS Named Mode config |
| `nr.filter()` | Not used | Role-aware deployment: ABRs first, then leaf routers |
| Result handling | Basic AggregatedResult | Per-role result inspection |

The `nr.filter()` story: in production you never deploy all IS-IS routers simultaneously.
ABRs must be configured before leaf routers can form adjacencies. The script enforces
this sequence using `nr.filter(F(isis_role="abr"))` followed by
`nr.filter(F(isis_role="leaf"))`. This is the real-world automation story for Module 06.

---

## Topology Design

### Router Roster — 12 Devices

| Router | Hostname | IS-IS Role | IS-IS Area | Notes |
|--------|----------|-----------|-----------|-------|
| R1 | BB-1 | L2-only | 49.0001 | Backbone core |
| R2 | BB-2 | L2-only | 49.0001 | Backbone core |
| R3 | ABR-1 | L1/L2 | 49.0001 ↔ 49.0002 | Dual-homed to BB-1 and BB-2 |
| R4 | ABR-2 | L1/L2 | 49.0001 ↔ 49.0003 | Dual-homed to BB-1 and BB-2 |
| R5 | ABR-3 | L1/L2 | 49.0001 ↔ 49.0004 | Dual-homed to BB-1 and BB-2 |
| R6 | BR-1 | L1-only | 49.0002 | DIS LAN member |
| R7 | BR-2 | L1-only | 49.0002 | DIS LAN member — wins DIS by priority |
| R8 | BR-3 | L1-only | 49.0002 | DIS LAN member |
| R9 | BR-4 | L1-only | 49.0003 | MT-IS-IS IPv6 zone |
| R10 | BR-5 | L1-only | 49.0003 | MT-IS-IS IPv6 zone |
| R11 | ASBR-1 | L1-only + OSPF | 49.0004 | IS-IS + OSPF, redistribution boundary |
| R12 | OSPF-1 | OSPF only | — | OSPF stub domain — not in IS-IS |


### IS-IS Area Summary

| Area | Type | Routers | Key Feature |
|------|------|---------|-------------|
| 49.0001 | L2 backbone | BB-1, BB-2, ABR-1, ABR-2, ABR-3 | Point-to-point links, dual-homed ABRs |
| 49.0002 | L1 stub | ABR-1, BR-1, BR-2, BR-3 | Broadcast LAN segment, DIS election |
| 49.0003 | L1 stub | ABR-2, BR-4, BR-5 | MT-IS-IS for IPv6 on BR-4 and BR-5 |
| 49.0004 | L1 stub | ABR-3, ASBR-1 | OSPF redistribution into IS-IS |

### NET Address Design

NET format: `49.AABB.RRRR.RRRR.RRRR.00`

| Area | Area ID | Router | System ID | NET |
|------|---------|--------|-----------|-----|
| 49.0001 | 49.0001 | BB-1 | 0000.0000.0001 | `49.0001.0000.0000.0001.00` |
| 49.0001 | 49.0001 | BB-2 | 0000.0000.0002 | `49.0001.0000.0000.0002.00` |
| 49.0001 | 49.0001 | ABR-1 | 0000.0000.0003 | `49.0001.0000.0000.0003.00` |
| 49.0001 | 49.0001 | ABR-2 | 0000.0000.0004 | `49.0001.0000.0000.0004.00` |
| 49.0001 | 49.0001 | ABR-3 | 0000.0000.0005 | `49.0001.0000.0000.0005.00` |
| 49.0002 | 49.0002 | BR-1 | 0000.0000.0006 | `49.0002.0000.0000.0006.00` |
| 49.0002 | 49.0002 | BR-2 | 0000.0000.0007 | `49.0002.0000.0000.0007.00` |
| 49.0002 | 49.0002 | BR-3 | 0000.0000.0008 | `49.0002.0000.0000.0008.00` |
| 49.0003 | 49.0003 | BR-4 | 0000.0000.0009 | `49.0003.0000.0000.0009.00` |
| 49.0003 | 49.0003 | BR-5 | 0000.0000.0010 | `49.0003.0000.0000.0010.00` |
| 49.0004 | 49.0004 | ASBR-1 | 0000.0000.0011 | `49.0004.0000.0000.0011.00` |

> L1/L2 routers (ABR-1, ABR-2, ABR-3) carry a single NET. IS-IS Named Mode
> allows one NET per router. The router participates in both L1 and L2 based
> on the `is-type` setting under the IS-IS process.

### IPv4 Addressing Plan

#### Loopbacks (all IS-IS routers)

| Router | Loopback0 |
|--------|-----------|
| BB-1 | 10.6.0.1/32 |
| BB-2 | 10.6.0.2/32 |
| ABR-1 | 10.6.0.3/32 |
| ABR-2 | 10.6.0.4/32 |
| ABR-3 | 10.6.0.5/32 |
| BR-1 | 10.6.1.1/32 |
| BR-2 | 10.6.1.2/32 |
| BR-3 | 10.6.1.3/32 |
| BR-4 | 10.6.2.1/32 |
| BR-5 | 10.6.2.2/32 |
| ASBR-1 | 10.6.3.1/32 |

#### Point-to-Point Links — L2 Backbone

| Link | Subnet | BB-1 | BB-2 |
|------|--------|------|------|
| BB-1 ↔ BB-2 | 10.6.10.0/30 | .1 | .2 |

#### Point-to-Point Links — ABR to Backbone (dual-homed)

| Link | Subnet | ABR | Backbone |
|------|--------|-----|----------|
| ABR-1 ↔ BB-1 | 10.6.11.0/30 | .2 | .1 |
| ABR-1 ↔ BB-2 | 10.6.11.4/30 | .6 | .5 |
| ABR-2 ↔ BB-1 | 10.6.11.8/30 | .10 | .9 |
| ABR-2 ↔ BB-2 | 10.6.11.12/30 | .14 | .13 |
| ABR-3 ↔ BB-1 | 10.6.11.16/30 | .18 | .17 |
| ABR-3 ↔ BB-2 | 10.6.11.20/30 | .22 | .21 |

#### Area 49.0002 — LAN Segment (broadcast)

| Segment | Subnet | BR-1 | BR-2 (DIS) | BR-3 | ABR-1 |
|---------|--------|------|-----------|------|-------|
| DIS LAN | 10.6.20.0/24 | .1 | .2 | .3 | .4 |

#### Area 49.0003 — Point-to-Point Links

| Link | Subnet | Left | Right |
|------|--------|------|-------|
| ABR-2 ↔ BR-4 | 10.6.21.0/30 | .1 | .2 |
| ABR-2 ↔ BR-5 | 10.6.21.4/30 | .5 | .6 |
| BR-4 ↔ BR-5 | 10.6.21.8/30 | .9 | .10 |

#### Area 49.0004 — IS-IS Links

| Link | Subnet | Left | Right |
|------|--------|------|-------|
| ABR-3 ↔ ASBR-1 | 10.6.22.0/30 | .1 | .2 |

#### OSPF Stub Domain

| Link | Subnet | Left | Right |
|------|--------|------|-------|
| ASBR-1 ↔ OSPF-1 | 10.6.30.0/30 | .1 | .2 |

| Router | Loopback0 |
|--------|-----------|
| OSPF-1 | 10.6.31.1/32 |

### IPv6 Addressing Plan — Area 49.0003 Only

Prefix: `2001:db8:6::/48` (module 06, documentation range)

| Link | Subnet | Left | Right |
|------|--------|------|-------|
| BR-4 ↔ BR-5 | 2001:db8:6:21::/127 | ::0 (BR-4) | ::1 (BR-5) |

| Router | Loopback0 IPv6 |
|--------|---------------|
| BR-4 | 2001:db8:6:1::9/128 |
| BR-5 | 2001:db8:6:1::10/128 |

> ABR-2 is IPv4-only. The IPv6 zone is confined to BR-4 and BR-5.
> IPv6 routing enabled only on these two routers (`ipv6 unicast-routing`).
> MT-IS-IS enabled under the IS-IS process and on the BR-4 ↔ BR-5 interface only.

---

## Key Design Decisions

### Named Mode Only
Per project standard, Module 06 and all subsequent modules use IS-IS Named Mode
exclusively. Configuration under `router isis NAMS26` with address-family blocks.
No classic mode syntax.

### Dual-Homed ABRs
All three ABRs connect to both BB-1 and BB-2. This provides path redundancy,
makes `show isis topology` more interesting (multiple equal-cost paths to
backbone destinations), and reflects real SP/enterprise IS-IS design.

### DIS Election in Area 49.0002
BR-1, BR-2, and BR-3 share a broadcast LAN segment. BR-2 wins DIS by default
(highest priority configured explicitly: `isis priority 100` on the LAN interface).
Students can verify with `show isis neighbors` (pseudonode appears as a virtual
neighbor) and `show isis database` (pseudonode LSP visible in LSDB).

Demo point: lower BR-2's priority to 0 during closing demo → watch re-election.

### Route Leaking (L2 → L1)
By default, L1 routers only know routes within their own area plus a default
route pointing to the nearest L1/L2 ABR. Route leaking injects specific L2
prefixes into L1, giving leaf routers full visibility of selected destinations.

Configured on each ABR:
```
router isis NAMS26
 address-family ipv4 unicast
  redistribute isis ip level-2 into level-1 distribute-list prefix LEAK-L2-TO-L1
```

Demo point: show L1 router routing table before and after leaking is configured.

### MT-IS-IS for IPv6 (Area 49.0003)
BR-4 and BR-5 run MT-IS-IS. All other routers are IPv4-only.
Configuration on BR-4 and BR-5:
```
router isis NAMS26
 address-family ipv6
  multi-topology
!
interface Ethernet0/0
 ipv6 router isis NAMS26
```

IS-IS advertises IPv6 prefixes in separate TLVs (Type 236 for IPv6 reachability).
Verify with `show isis database detail` — IPv6 TLVs visible only on BR-4 and BR-5 LSPs.

### OSPF Redistribution (Area 49.0004)
ASBR-1 runs OSPF process 1 toward OSPF-1, and IS-IS NAMS26 toward
ABR-3. Redistribution is one-way: OSPF → IS-IS only.

```
router isis NAMS26
 redistribute ospf 1 metric 20 metric-type external route-map OSPF-TO-ISIS
```

In IS-IS Named Mode, redistributed OSPF routes appear as regular IP
prefix entries in ASBR-1's LSP at metric 20 — not as explicit External
TLVs. Verify by checking that OSPF-1's loopback prefix (10.6.31.1)
appears in ASBR-1's detailed LSP entry in `show isis database detail`.

### Wide Metrics
All routers use `metric-style wide` under IS-IS Named Mode. Narrow metrics
(max 63) are insufficient for real-world cost differentiation. Wide metrics
support values up to 16,777,215. Default interface cost: 10.

---

## Nornir Implementation Plan

### Inventory Structure

Each device in the Nornir inventory carries an `isis_role` field in host data:

```python
# Programmatic inventory — built directly from YAML devices block
# No hosts.yaml / groups.yaml files written to disk.
# isis_role field exposed as host data for nr.filter(F(isis_role=...))

host_dict["BB-1"] = Host(
    name="BB-1",
    hostname="bb-1.lab",
    platform="ios",
    data={
        "isis_role": "backbone",
        "isis_area": "49.0001",
    },
    ...
)
```

The YAML devices block is the single source of truth for both
configuration content and Nornir inventory. No duplication.

### Deployment Sequence Using `nr.filter()`

```python
# Phase 1 — backbone routers first
backbone = nr.filter(F(isis_role="backbone"))
result = backbone.run(task=configure_isis)

# Phase 2 — ABRs second (backbone must be up)
abrs = nr.filter(F(isis_role="abr"))
result = abrs.run(task=configure_isis)

# Phase 3 — leaf routers last (ABRs must be up)
leaves = nr.filter(F(isis_role__in=["leaf", "asbr"]))
result = leaves.run(task=configure_isis)

# Phase 4 — OSPF-only router (independent of IS-IS convergence)
ospf_only = nr.filter(F(isis_role="ospf_only"))
result = ospf_only.run(task=configure_ospf_task)
```

This enforces correct operational sequencing — not just correctness of config,
but correctness of deployment order. IS-IS adjacencies form in the right sequence.

### Script Files

| Script | Purpose |
|--------|---------|
| `configure_06_ipv6_isis_nornir.py` | Deploy IS-IS Named Mode config — backbone, ABRs, leaf routers in sequence |
| `verify_06_ipv6_isis_nornir.py` | Per-device PASS/WARN/FAIL — neighbors, LSDB, routes, MT-IS-IS |
| `troubleshoot_06_ipv6_isis_nornir.py` | Operational checks — adjacency state, DIS, route leaking, redistribution |

---

## Closing Demo Plan

The closing demo demonstrates the automation story, not IS-IS edge cases.
Three beats:

**Beat 1 — Clean state verify**
Run `verify_06_ipv6_isis_nornir.py` against all routers. All checks PASS. Students see the
Nornir result aggregation across 11 IS-IS devices simultaneously.

**Beat 2 — Fault injection (DIS manipulation)**
Lower BR-2's DIS priority to 0 on the LAN interface:
python utils/push_config.py --router BR-2 --cmd "interface Ethernet0/0" "isis priority 0"
Run troubleshoot script — adjacency check returns PASS. IS-IS adjacencies
are healthy. The troubleshooter cannot detect the DIS policy drift.
Run verify script — neighbors check returns WARN on BR-2. The source of
truth says BR-2 should be DIS (isis_priority: 100). The live state shows
another router won DIS election. The verifier catches what the
troubleshooter cannot.

**Beat 3 — Restore from source of truth**
python scripts/configure_06_ipv6_isis_nornir.py --router BR-2
python scripts/verify_06_ipv6_isis_nornir.py --router BR-2 --check neighbors
Nornir pushes the rendered config. isis priority 100 restored. BR-2
reclaims DIS. Verifier confirms PASS.

---

## Files Required (Phase 2 onward)

| File | Phase | Notes |
|------|-------|-------|
| `data/06_ipv6_isis_nornir.yaml` | 2 | Device inventory, IS-IS config, OSPF config for ASBR-1 |
| `templates/06_ipv6_isis_nornir_named.j2` | 3 | IS-IS Named Mode Jinja2 template |
| `templates/06_ipv6_isis_nornir_ospf_stub.j2` | 3 | OSPF stub config for ASBR-1 and OSPF-1 |
| `scripts/configure_06_ipv6_isis_nornir.py` | 3 | Nornir configure script with `nr.filter()` sequencing |
| `scripts/verify_06_ipv6_isis_nornir.py` | 3 | Verification script |
| `scripts/troubleshoot_06_ipv6_isis_nornir.py` | 3 | Troubleshooting script |
| `verbal_script/module06_verbal_script.md` | 5 | Draft verbal script (renamed to `_final` at Phase 6) |
| `docs/module06_closing_demo.md` | 6 | Closing demo procedure |
| `diagrams/module06_topology_isis.drawio` | 5 | CoS-generated drawio from YAML |
| `diagrams/module06_topology_isis.drawio.svg` | 5 | Exported SVG |

---

## Resolved Items

All items resolved during lab build and script validation:

- [x] Physical router assignments confirmed — R1=BB-1 through R12=OSPF-1
- [x] Interface assignments confirmed from captured IOS configs
- [x] OSPF-2 not implemented — OSPF-1 is the single OSPF stub router
- [x] NET address format validated on Cisco IOL 15.7 — standard
      dotted-decimal format accepted

---

*NAMS26 — Network Automation Management Station 2026*
*Module 06 Planning Document — `docs/module06_planning.md`*
*Updated: 2026-05-10 — Phase 6 complete*
*Internal document — not for publication*
