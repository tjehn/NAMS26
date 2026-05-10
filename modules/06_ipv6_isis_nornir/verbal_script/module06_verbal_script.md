# Module 06 — IS-IS Named Mode / Nornir
## Verbal Script — `module06_verbal_script.md`
### NAMS26 | Network Automation Management Station 2026

---

> **Production Notes**
> - Screen follows the script section by section — code is visible on screen,
>   instructor reads from this script
> - References describe what's on screen; instructor does not read code verbatim
> - Tone: conversational, technically precise, CCNP-level audience assumed
> - `[SCREEN]` cues indicate what should be visible on screen at that moment
> - Pre-flight and lab reset procedures are documented in `docs/eve-ng_lab_reset_sop.md`
>   — reference that document for operational steps, do not repeat them here

---

## SECTION 1 — Module Objectives

`[SCREEN: README.md — Module Objectives section]`

Welcome to Module 6. The tool doesn't change — we're staying on Nornir from Module 5.
What changes is how we use it, and the protocol gets significantly more interesting.

Module 5 introduced Nornir with EIGRPv6 and OSPFv3 — a dual-stack module that showed
you how Nornir runs tasks against inventory. Module 6 keeps Nornir but deepens two
specific patterns: `nr.run()` with a custom task function, and `nr.filter()` for
role-aware, sequenced deployment. We'll get into both in detail.

The protocol is IS-IS Named Mode. This is the last IGP before BGP in the curriculum.
IS-IS is the preferred IGP in large-scale service provider and carrier networks — it's
what runs the internet's backbone infrastructure. Understanding it is a differentiator
at the CCNP and CCIE level.

Here's what we're covering:

1. IS-IS area design — Level-1, Level-2, and L1/L2 router roles across four areas
2. IS-IS Named Mode configuration including NET address assignment
3. DIS election on a multi-access broadcast segment
4. Route leaking from L2 into L1 and why it's necessary
5. Multi-Topology IS-IS for IPv6 on a bounded subset of the domain
6. OSPF-to-IS-IS redistribution at an ASBR
7. `nr.run()` with a custom task function that pre-renders all configs before any SSH connection opens
8. `nr.filter()` to deploy configuration in the correct operational sequence

The automation story in this module is about order. IS-IS adjacencies form in sequence —
backbone first, area border routers second, leaf routers last. The script enforces that
sequence using `nr.filter()`. In production, you never deploy all IS-IS routers
simultaneously. That's the lesson.

---

## SECTION 2 — Lab Topology

`[SCREEN: diagrams/module06_topology_isis.drawio.svg]`

Twelve routers, four IS-IS areas, and one OSPF stub domain.

The physical routers are connected into a shared Ethernet switch fabric — COSW-01 and
COSW-02. You won't see those switches in any diagram. They're transparent infrastructure.
Logical links between routers are defined by shared IP subnets, exactly as if there were
a direct cable. The topology diagram shows router-to-router logical links only.

---

**L2 Backbone — Area 49.0001**

BB-1 and BB-2 are the backbone core. Both are Level-2-only — they carry no L1 routing
information whatsoever. BB-1 and BB-2 are connected to each other on `10.6.10.0/30`.

Three area border routers attach here: ABR-1, ABR-2, and ABR-3. Each ABR is dual-homed
— it connects to both BB-1 and BB-2, giving the backbone path redundancy and making
`show isis topology` more interesting than a single linear path. ABR-1, ABR-2, and
ABR-3 are Level-1-2 — they participate in both the L2 backbone and their respective L1
areas.

---

**Area 49.0002 — The DIS Demo Area**

ABR-1 is the L1/L2 gateway into this area. BR-1, BR-2, and BR-3 are Level-1-only leaf
routers. ABR-1, BR-1, BR-2, and BR-3 all share a broadcast LAN segment on
`10.6.20.0/24`. This is intentional — multi-access segments are where IS-IS elects a
Designated IS, and that's what we're demonstrating here.

BR-2 wins the DIS election. `isis priority 100` is configured on its LAN interface —
all other routers on that segment use the default priority. When BR-2 is DIS, you'll
see its name in the Circuit Id column of `show isis neighbors` and a pseudonode LSP
in `show isis database`. That pseudonode LSP is BR-2's signature as DIS.

On a broadcast IS-IS segment, L1/L2 routers form separate adjacency
entries per level. `show isis neighbors` on any LAN member will show
more entries than the number of physical neighbors — this is expected
IS-IS behavior.

---

**Area 49.0003 — The IPv6 Zone**

ABR-2 is the L1/L2 gateway. BR-4 and BR-5 are Level-1-only with one addition: they
run Multi-Topology IS-IS for IPv6. Every other router in the domain is IPv4-only.

The IPv6 prefix is `2001:db8:6::/48`. BR-4 and BR-5 carry dual-stack addresses on
their links and loopbacks. IS-IS maintains a separate SPF calculation for IPv4 and
IPv6 topologies — that's what multi-topology means. The rest of the domain doesn't
know or care. The zone is self-contained.

---

**Area 49.0004 — The OSPF Redistribution Boundary**

ABR-3 is the L1/L2 gateway. ASBR-1 is Level-1-only but it runs two routing protocols:
IS-IS NAMS26 toward ABR-3, and OSPF process 1 toward OSPF-1.

OSPF-1 is completely outside the IS-IS domain. It's an OSPF stub router. ASBR-1
redistributes OSPF routes into IS-IS. Those redistributed prefixes travel up through
ABR-3 into the L2 backbone and become visible across the entire IS-IS domain.

---

**Router role summary:**

| Router | Physical | IS-IS Role | Area |
|--------|----------|-----------|------|
| BB-1 | R1 | L2-only | 49.0001 |
| BB-2 | R2 | L2-only | 49.0001 |
| ABR-1 | R3 | L1/L2 | 49.0001 ↔ 49.0002 |
| ABR-2 | R4 | L1/L2 | 49.0001 ↔ 49.0003 |
| ABR-3 | R5 | L1/L2 | 49.0001 ↔ 49.0004 |
| BR-1 | R6 | L1-only | 49.0002 |
| BR-2 | R7 | L1-only, DIS | 49.0002 |
| BR-3 | R8 | L1-only | 49.0002 |
| BR-4 | R9 | L1-only + IPv6 | 49.0003 |
| BR-5 | R10 | L1-only + IPv6 | 49.0003 |
| ASBR-1 | R11 | L1-only + OSPF | 49.0004 |
| OSPF-1 | R12 | OSPF only | — |

---

## SECTION 3 — Tool Overview: Nornir (deepening)

`[SCREEN: configure_06_ipv6_isis_nornir.py — _build_nornir() function]`

Module 5 introduced `nr.run()` and the basic Nornir task pattern. Module 6 deepens two
specific things: how you build the inventory, and how you use filters to control
deployment sequence.

---

**Programmatic inventory — no hosts.yaml**

Module 5 used `InitNornir` with the `SimpleInventory` plugin — it wrote temporary
`hosts.yaml` files to disk to satisfy Nornir's file-based inventory requirement, then
read them back. Module 06 eliminates that step entirely by building the inventory
programmatically from the same YAML that drives the templates. No temp files, no
duplication, one source of truth.

Look at `_build_nornir()`. It iterates the devices dict, constructs a `Host` object for
each router, and wraps them in an `Inventory`. The key line:

```python
data=dict(dev),
```

The full device dict goes into `host.data`. That means every field from the YAML —
including `isis_role` — is accessible in a running task via `task.host.data`. It also
means `nr.filter(F(isis_role="backbone"))` works, because Nornir's `F()` filter can
match against host data fields.

The YAML is the single source of truth for both the configuration content and the
Nornir inventory. No duplication, no separate inventory files to keep in sync.

---

**`nr.run()` with a custom task function**

`[SCREEN: configure_06_ipv6_isis_nornir.py — configure_isis_task() and render_all_configs()]`

Module 5 used `nr.run()` with a library task directly — something like
`netmiko_send_config`. Module 6 wraps that in a custom task function:
`configure_isis_task`. This lets us do something important before any SSH connection
opens.

Look at `render_all_configs()`. It runs before `_build_nornir()`. It renders every
device's config from Jinja2 before touching a single router. If a template variable is
missing, if a device block is malformed, if the YAML has a typo in a key name — the
render fails here, cleanly, before anything is pushed to the network.

That matters. In Module 2, Netmiko pushed lines one at a time. If a template rendered
garbage on device 7 of 12, devices 1 through 6 were already configured. Here, all
twelve configs are validated in memory first. If any of them fail to render, nothing
goes out. The script exits before it touches the lab.

---

**`nr.filter()` for role-aware deployment**

`[SCREEN: configure_06_ipv6_isis_nornir.py — main() deployment phases]`

This is the core Nornir lesson for Module 6.

IS-IS convergence depends on deployment order. If you configure a leaf router before
its ABR is up, the leaf forms no adjacency — there's nothing to form one with. If you
configure an ABR before the backbone is up, the ABR's L2 adjacencies don't form. The
order is: backbone first, ABRs second, leaves last.

The script enforces this using `nr.filter()`:

```python
# Phase 1 — backbone (BB-1, BB-2) must be up before ABRs can reach L2 routes
backbone = nr.filter(F(isis_role="backbone"))
backbone.run(task=configure_isis_task, rendered=rendered_configs)

# Phase 2 — ABRs (ABR-1, ABR-2, ABR-3) become gateways for their L1 areas
abrs = nr.filter(F(isis_role="abr"))
abrs.run(task=configure_isis_task, rendered=rendered_configs)

# Phase 3 — leaf routers and ASBR-1 form L1 adjacencies to their ABRs
leaves = nr.filter(F(isis_role__in=["leaf", "asbr"]))
leaves.run(task=configure_isis_task, rendered=rendered_configs)

# Phase 4 — OSPF stub router, independent of IS-IS convergence
ospf_only = nr.filter(F(isis_role="ospf_only"))
ospf_only.run(task=configure_ospf_task, rendered=rendered_configs)
```

Each `nr.filter()` returns a new Nornir object scoped to only the matching hosts.
`F(isis_role="backbone")` matches BB-1 and BB-2. `F(isis_role__in=["leaf","asbr"])`
matches seven routers in one call.

> **Instructor talking point:** This is what production IS-IS automation looks like.
> You don't push configs to twelve routers simultaneously. You push to the backbone,
> wait for L2 adjacencies, push to ABRs, wait for L1 adjacencies, push to leaves.
> `nr.filter()` is the tool that lets you express that sequence without writing
> separate scripts for each phase. One script, one YAML, four controlled phases.

---

## SECTION 4 — Configuration

### 4a — The Three-File Workflow

`[SCREEN: module directory tree — data/, templates/, scripts/]`

Same three-file workflow, new tool and new protocol:

```
06_ipv6_isis_nornir.yaml  →  06_ipv6_isis_nornir_named.j2
     (variables)                      (template)
                          →  configure_06_ipv6_isis_nornir.py  →  Router (Nornir + Netmiko)
                                    (Nornir SSH push)
```

Two templates this module. The reason: ASBR-1 and OSPF-1 require OSPF configuration
that doesn't belong in the IS-IS template.

- `06_ipv6_isis_nornir_named.j2` — renders IS-IS config for all eleven IS-IS-capable routers
- `06_ipv6_isis_nornir_ospf_stub.j2` — renders the OSPF process block for ASBR-1, and the full config for OSPF-1

ASBR-1 gets both templates concatenated — the IS-IS config from the named template
followed immediately by the OSPF process block from the stub template. The configure
script handles the concatenation in `render_all_configs()`.

---

### 4b — File 1: `06_ipv6_isis_nornir.yaml`

`[SCREEN: 06_ipv6_isis_nornir.yaml]`

Five things in this YAML are specific to Module 6.

---

**`isis_role` and `isis_area` at the device level**

Every device block opens with two fields:

```yaml
BB-1:
  hostname: BB-1
  dns_name: bb-1.lab
  isis_role: backbone
  isis_area: "49.0001"
```

`isis_role` drives both the Nornir `F()` filter and the template rendering logic.
`isis_area` is reference data — used in output headers and the verify script.
These are not IS-IS configuration parameters; they describe the router's function
in the automation model.

Valid `isis_role` values: `backbone`, `abr`, `leaf`, `asbr`, `ospf_only`.

---

**NET address design**

Every IS-IS router has a Network Entity Title — its IS-IS address. The format in this
lab:

```
49.AABB.SSSS.SSSS.SSSS.00
 │  │    └──────────── System ID (12 hex digits, padded)
 │  └──────────────── Area ID (4 hex digits)
 └─────────────────── AFI (always 49 for private IS-IS)
```

BB-1's NET: `49.0001.0000.0000.0001.00`

Area 49.0001, system ID `0000.0000.0001`, NSEL `00`. The NSEL is always `00` for
a router — it distinguishes router addresses from end-system addresses in the
original OSI model.

System IDs are sequential across the lab: BB-1 is `0001`, BB-2 is `0002`, through
ASBR-1 at `0011`. Routers in different areas carry different area IDs in their NETs —
a BR-1 in Area 49.0002 has NET `49.0002.0000.0000.0006.00`.

---

**The `isis.interfaces` block**

IS-IS configuration is per-interface. The YAML models it explicitly:

```yaml
isis:
  process_name: NAMS26
  net: "49.0001.0000.0000.0001.00"
  is_type: level-2-only
  metric_style: wide
  interfaces:
    Ethernet0/0:
      isis_enable: true
      isis_network: point-to-point
      isis_metric: 10
      isis_circuit_type: level-2-only
    Loopback0:
      isis_enable: true
      isis_passive: true
```

`isis_network: point-to-point` suppresses DIS election on P2P links — the `isis
network point-to-point` command. Without it, IS-IS would attempt to elect a DIS
on every Ethernet interface, even point-to-point ones, which wastes adjacency time
and generates a pseudonode LSP nobody needs.

`isis_passive: true` marks the loopback as passive — IS-IS advertises the prefix
but never sends Hellos on it. This maps to `passive-interface Loopback0` under the
IS-IS Named Mode process block, not on the interface itself.

`isis_priority: 100` appears on exactly one router: BR-2's Ethernet0/0. That's the
DIS priority configuration. No other router in the lab has it.

---

**`ipv6_multitopology: true` — BR-4 and BR-5 only**

```yaml
BR-4:
  isis:
    ipv6_multitopology: true
    interfaces:
      Ethernet0/0:
        isis_enable: true
        isis_network: point-to-point
        isis_metric: 10
        isis_circuit_type: level-1-only
        ipv6_isis_enable: true
```

`ipv6_multitopology: true` at the process level enables `address-family ipv6 /
multi-topology` in the rendered IS-IS Named Mode config. `ipv6_isis_enable: true`
at the interface level adds `ipv6 router isis NAMS26` to that interface.

These two keys appear only on BR-4 and BR-5. The template checks for them and renders
the IPv6 blocks conditionally. All other routers produce no IPv6 IS-IS configuration.

---

**The `ospf` block — ASBR-1 and OSPF-1**

ASBR-1 carries both an `isis` block and an `ospf` block. OSPF-1 carries only an
`ospf` block — it has no `isis` block at all, and `isis_role: ospf_only` tells the
configure script which template to use.

```yaml
ASBR-1:
  isis_role: asbr
  isis:
    process_name: NAMS26
    net: "49.0004.0000.0000.0011.00"
    ...
  ospf:
    process_id: 1
    router_id: 10.6.3.1
    interfaces:
      Ethernet0/1:
        area: 0
        ospf_network: point-to-point
      Loopback0:
        area: 0
        ospf_passive: true
```

ASBR-1 is the dual-domain router. Both protocols share the same loopback. The IS-IS
template handles all interface and IS-IS process config; the OSPF stub template appends
only the `router ospf` block for ASBR-1.

---

### 4c — File 2: Templates

`[SCREEN: 06_ipv6_isis_nornir_named.j2]`

Three highlights from the IS-IS Named Mode template.

---

**The IS-IS process block — Named Mode structure**

```jinja2
router isis {{ isis.process_name }}
 net {{ isis.net }}
 is-type {{ isis.is_type }}
 metric-style {{ isis.metric_style }}
{% for intf_name, iisis in isis.interfaces.items() %}
{% if iisis.isis_passive | default(false) %}
 passive-interface {{ intf_name }}
{% endif %}
{% endfor %}
```

Named Mode is the project standard from Module 6 forward. The process has a name —
`NAMS26` — rather than just a process number. All IS-IS Named Mode configuration,
including `passive-interface`, lives under the named process block. Classic Mode puts
`isis passive` on the interface. Named Mode puts `passive-interface` under the process.
That distinction matters — Classic Mode syntax produces `% Invalid input detected` in
Named Mode.

Wide metrics are configured globally: `metric-style wide`. Narrow IS-IS metrics max
out at 63. Wide metrics support values up to 16,777,215. All interfaces in this lab
use metric 10, but the wide format is required for any realistic cost differentiation
at scale.

---

**Route leaking — L2 into L1 on ABR routers**

```jinja2
{% if isis.is_type == 'level-1-2' %}
 !
 address-family ipv4 unicast
  redistribute isis ip level-2 into level-1 distribute-list prefix LEAK-L2-TO-L1
 exit-address-family
{% endif %}
...
{% if isis.is_type == 'level-1-2' %}
ip prefix-list LEAK-L2-TO-L1 seq 5 permit 0.0.0.0/0 le 32
{% endif %}
```

This block renders only on ABR-1, ABR-2, and ABR-3 — the L1/L2 routers.

By default, L1 routers know only routes within their own area, plus a default route
pointing toward the nearest L1/L2 ABR. Route leaking injects selected L2 prefixes
into L1, giving leaf routers full visibility of specific destinations without needing
to become L2 routers themselves. The prefix-list `LEAK-L2-TO-L1` permits everything
— students can tighten that scope as an exercise.

> **Instructor talking point:** This is a fundamental IS-IS design question. Do you
> let L1 routers use a default route to reach everything outside their area? Or do
> you inject specific L2 prefixes into L1 so they have explicit routes? Default route
> is simpler. Route leaking is more precise. In a service provider network, you
> typically leak specific prefixes rather than relying on a default — it gives
> operators visibility into which paths the L1 routers are actually using.

---

**MT-IS-IS — IPv6 on BR-4 and BR-5**

```jinja2
{% if isis.ipv6_multitopology | default(false) %}
 !
 address-family ipv6
  multi-topology
 exit-address-family
{% endif %}
```

And on the interface, when `ipv6_isis_enable` is true:

```jinja2
 ipv6 router isis {{ isis.process_name }}
```

Multi-Topology IS-IS maintains two independent SPF trees — one for IPv4 reachability,
one for IPv6. Without multi-topology, IS-IS runs a single SPF and assumes the IPv4
and IPv6 topologies are congruent. If you add IPv6 to some interfaces but not others,
the single-topology assumption breaks. MT-IS-IS solves this by decoupling the two
calculations.

BR-4 and BR-5 are the only routers with `ipv6_multitopology: true`. The template
renders the MT block only on them. The rest of the domain never sees an IPv6 topology
TLV. The zone is bounded.

`[SCREEN: 06_ipv6_isis_nornir_ospf_stub.j2]`

The OSPF stub template is straightforward. For OSPF-1, it renders interfaces, loopbacks,
and the full OSPF process block. For ASBR-1, it skips the interface section entirely —
those are already rendered by the IS-IS template — and appends only `router ospf 1`.
The `{% if isis_role == 'ospf_only' %}` guard handles the distinction.

---

### 4d — File 3: `configure_06_ipv6_isis_nornir.py`

`[SCREEN: configure_06_ipv6_isis_nornir.py — main() function]`

The entry point runs in four phases. Before any of them, all twelve configs are
pre-rendered and validated. Then Nornir deploys in sequence.

---

**Phase 1 — Backbone**

```bash
[Phase 1] Backbone routers (BB-1, BB-2)
```

BB-1 and BB-2 get their IS-IS Named Mode config first. The L2 adjacency forms between
them on `10.6.10.0/30`. No L1 information is generated — these are L2-only routers.
When Phase 1 completes, the backbone exists.

---

**Phase 2 — ABRs**

```bash
[Phase 2] ABRs (ABR-1, ABR-2, ABR-3) — backbone must be up first
```

ABR-1, ABR-2, and ABR-3 each form L2 adjacencies to BB-1 and BB-2. Being dual-homed,
each ABR has two L2 links into the backbone. They become the reachable gateways for
their respective L1 areas. When Phase 2 completes, the L2 domain is converged and
three area gateways are operational.

---

**Phase 3 — Leaves and ASBR**

```bash
[Phase 3] Leaf routers and ASBR (BR-1..5, ASBR-1)
```

Seven routers in one filter. BR-1, BR-2, BR-3 form L1 adjacencies to ABR-1 on the
10.6.20.0/24 LAN. BR-4 and BR-5 form L1 adjacencies to ABR-2 on their point-to-point
links. ASBR-1 forms its L1 adjacency to ABR-3. IS-IS converges across the full domain.

---

**Phase 4 — OSPF**

```bash
[Phase 4] OSPF-only stub router (OSPF-1)
```

OSPF-1 is independent of IS-IS convergence. Its config goes last for narrative clarity.
When it comes up, the OSPF adjacency with ASBR-1 forms, ASBR-1 redistributes OSPF
routes into IS-IS, and those external prefixes propagate through the L1/L2 hierarchy
to every router in the domain.

---

**Running the script:**

```bash
# Render all twelve configs locally — no SSH
python scripts/configure_06_ipv6_isis_nornir.py --dry-run

# Deploy in four phases
python scripts/configure_06_ipv6_isis_nornir.py

# Verify IS-IS state
python scripts/verify_06_ipv6_isis_nornir.py

# Troubleshoot if needed
python scripts/troubleshoot_06_ipv6_isis_nornir.py
```

The dry-run step matters. Twelve configs, two templates, six IS-IS areas and roles.
Open the `.cfg` files in `configs/` and check: are the IS-IS Named Mode process blocks
correct? Are `passive-interface` statements under the process, not on the interface?
Do the ABR configs have the route-leaking `address-family` block? Do BR-4 and BR-5
have the MT-IS-IS `address-family ipv6` block? Do ASBR-1's config and OSPF-1's
config both look right? Verify before you push.

---

## SECTION 5 — Verification

`[SCREEN: verify_06_ipv6_isis_nornir.py]`

The verify script has four checks: `neighbors`, `lsdb`, `routes`, and `mt`. It runs
against all twelve routers — eleven IS-IS routers and the OSPF-only stub. OSPF-1 gets
adapted checks: OSPF adjacency state and OSPF routes instead of IS-IS checks.

---

**`check_neighbors`**

Runs `show isis neighbors`. Parses UP neighbors and compares the count against an
expected value table hardcoded in the script:

```python
EXPECTED_NEIGHBORS = {
    "BB-1":   4,   # BB-2, ABR-1, ABR-2, ABR-3
    "BB-2":   4,   # BB-1, ABR-1, ABR-2, ABR-3
    "ABR-1":  5,   # BB-1, BB-2, BR-1, BR-2, BR-3
    "ABR-2":  4,   # BB-1, BB-2, BR-4, BR-5
    "ABR-3":  3,   # BB-1, BB-2, ASBR-1
    ...
    "ASBR-1": 1,   # ABR-3
}
```

> **Instructor talking point:** ABR-1 shows five neighbors — not four
> physical devices. On a broadcast IS-IS segment, an L1/L2 router forms
> separate L1 and L2 adjacency entries with each neighbor it has
> dual-level adjacency with. BR-2 and BR-3 are both L1/L2 routers — so
> ABR-1 forms two adjacency entries per router: one at Level-1 and one at
> Level-2. That's two entries each for BR-2 and BR-3, plus one for BR-1
> (L1-only, single entry), totaling five entries visible in
> `show isis neighbors`. This is correct IS-IS behavior on a broadcast
> segment.

If the count matches expected, PASS. If it's short, WARN. If zero, FAIL.

Two role-specific sub-checks run inside `check_neighbors`:

BR-2's DIS role is verified by looking for `BR-2.` in the Circuit Id column of
`show isis neighbors`. When BR-2 is DIS, its system ID appears as the DIS pseudonode
ID in that column. If BR-2 won the DIS election, the check passes.

ASBR-1's OSPF adjacency is verified by running `show ip ospf neighbor` and checking
for `FULL` state. Both checks run inside the same connection to that router.

---

**`check_lsdb`**

Three sub-checks. First, `show isis database` — is the router's own LSP present and
marked with `*`? The `*` means self-originated. If it's absent, IS-IS isn't running
or the router hasn't generated its own LSP yet.

Second, `show isis database <device>.00-00 detail` — is the router's Loopback0 IP
address visible in its own LSP? Loopbacks are passive interfaces. If IS-IS isn't
advertising the loopback, `ip router isis NAMS26` or `isis passive` is missing from
that interface's config.

Third, on ASBR-1 specifically: is `10.6.31.1` visible in ASBR-1's detailed LSP?
That's OSPF-1's loopback — the address that ASBR-1 redistributes from OSPF into IS-IS.
If it's missing, redistribution isn't working.

---

**`check_routes`**

Runs `show ip route isis` and counts lines beginning with `i` at column 0. IS-IS route
codes in Cisco IOS are `i L1` and `i L2` — at the leftmost column, not indented. That
column-0 distinction matters if you're writing the regex — `O` routes are indented,
`i` IS-IS routes are not.

For BR-4 and BR-5 only, the script also runs `show ipv6 route isis` and looks for
lines starting with `I1`, `I2`, `IA`, or `IS` at column 0. Those are IS-IS IPv6 route
codes. If MT-IS-IS is working, both routers should have IPv6 reachability to each
other's loopbacks via IS-IS.

---

**`check_mt`**

Applies only to BR-4 and BR-5. Runs `show isis neighbors detail` and looks for MT
capability indicators: `Remote TID: 0, 2` in IOL output, or `IPv6 Unicast` or
`Multi-Topology` in other IOS versions. Also verifies that the IPv6 loopback address
appears in the router's own detailed LSP.

A few IOL-specific behaviors worth noting:

- `show clns protocol` shows the IS type as `level-2` instead of `level-2-only` — the
  `-only` suffix is dropped. The verify and troubleshoot scripts account for this.
- The NET doesn't appear as a combined string in `show clns protocol` output. The area
  ID and system ID are printed in separate fields. Both scripts check them independently.
- IS-IS route codes at column 0 — `i L1`, `i L2` — rather than indented as OSPF routes
  are. The route parser explicitly matches on the leading `i` with a following space.
- MT capability in `show isis neighbors detail` appears as `Remote TID: 0, 2` on IOL.

---

## SECTION 6 — Troubleshooting

`[SCREEN: troubleshoot_06_ipv6_isis_nornir.py]`

The troubleshoot script has seven checks. Two of them are IS-IS-specific and differ
from anything we've seen in earlier modules.

---

**`process` — `show clns protocol`**

IS-IS is not IP-based. It runs over CLNS — the Connectionless Network Service —
which is the OSI network layer protocol. That's why the command is `show clns protocol`
and not `show ip protocols`. IS-IS predates IP and can run without IP at all.

The check validates three things: the IS-IS process name `NAMS26` is present, the area
ID matches the YAML, and the system ID matches the YAML. Because IOL prints the area ID
and system ID separately rather than as a combined NET, the script parses the NET from
YAML and checks the two components independently.

The IS type check uses `is_type.replace("-only", "")` before matching — IOL outputs
`level-2` where the YAML stores `level-2-only`.

---

**`adjacency` — `show isis neighbors`**

Parses the neighbor table for Up, Down, and Init state counts. Any neighbor in Down or
Init state generates a WARN. Zero total neighbors generates a FAIL.

On routers with `isis_priority` configured, the script runs the DIS check — looking
for the router's own name in the Circuit Id column. If it's configured with priority
100 but isn't appearing as DIS, something changed: another router won the election,
or the priority isn't applied.

---

**`interfaces` — `show clns interface`**

Note: `show isis interface brief` and `show isis interface` are both unsupported on
Cisco IOL 15.7. `show clns interface` replaces them. It shows each interface's CLNS
status — IS-IS-enabled interfaces display `Routing Protocol: IS-IS` with circuit
type, metric, and adjacency count. Non-IS-IS interfaces show `CLNS protocol processing
disabled`.

The check verifies that all interfaces with `isis_enable: true` in the YAML appear
in the command output.

---

**`lsdb` — `show isis database`**

Checks that the router's own LSP is present and self-originated. Checks that the LSDB
has at least three entries — a single-entry LSDB means IS-IS has converged only with
itself. With twelve routers, a healthy LSDB has twelve or more LSPs.

---

**`reachability` — ping neighbor IPs from YAML**

No hardcoded neighbor tables. The script derives neighbor IPs by matching interface
subnets across all devices in the YAML. If two routers share a subnet on their data
plane interfaces, they're neighbors. The script pings each derived neighbor IP.

This means reachability checking works correctly on any subset of routers without
modification — it reads the topology from the YAML rather than a static table.

---

**`mt` — `show isis neighbors detail`**

Applies to BR-4 and BR-5 only. Checks for MT-IS-IS IPv6 capability in the neighbor
detail output, then verifies the IPv6 loopback appears in the IS-IS LSDB detail.
Both sub-checks must pass for the MT check to return PASS.

---

**`ospf` — `show ip ospf neighbor` + `show ip route ospf`**

Applies only to ASBR-1 and OSPF-1. All other routers return INFO immediately.

On ASBR-1: verifies OSPF adjacency is FULL, then checks that OSPF routes are present
for redistribution. If ASBR-1 has no OSPF routes, there's nothing to redistribute into
IS-IS — the redistribution statement is correct but the OSPF domain isn't providing
any input.

On OSPF-1: verifies OSPF adjacency with ASBR-1 is FULL.

---

## SECTION 7 — Closing Demonstration: Configuration Drift

`[SCREEN: terminal — scripts/ and utils/ directories]`

Same three-beat structure as Module 4. Inject a fault, run the troubleshooter, run
the verifier, restore from the source of truth. The protocol is IS-IS, the fault is
DIS priority manipulation.

---

### Part 1 — Inject the Drift

```bash
python utils/push_config.py --router BR-2 --cmd "interface Ethernet0/0" "isis priority 0"
```

BR-2's DIS priority drops from 100 to 0 on the LAN interface. IS-IS triggers a new
DIS election on the Area 49.0002 broadcast segment. BR-2 yields — it's now the lowest
priority router on that segment. BR-1 or BR-3 wins. A new pseudonode LSP appears in
the LSDB. BR-2's pseudonode LSP is withdrawn.

All adjacencies remain UP. IS-IS is fully operational. The DIS role has simply moved.

---

### Part 2 — Troubleshooter Shows Healthy Adjacencies

```bash
python scripts/troubleshoot_06_ipv6_isis_nornir.py --router BR-2 --check adjacency
```

> **Instructor talking point:** Watch the output. BR-2 reports adjacencies UP — ABR-1
> and all its LAN neighbors are present and healthy. The troubleshooter's question is
> "are IS-IS adjacencies working?" The answer is yes. The protocol is healthy.
>
> The troubleshooter has no visibility into whether the DIS role matches what the
> source of truth says it should be. That's not its job. It checks operational state.
> Operational state is fine.

---

### Part 3 — Verifier Catches the Drift

```bash
python scripts/verify_06_ipv6_isis_nornir.py --router BR-2 --check neighbors
```

> **Instructor talking point:** Now watch the verifier. It runs `show isis neighbors`
> and checks whether BR-2's own name appears in the Circuit Id column. It doesn't —
> another router won DIS election. The YAML says BR-2 should be DIS. The live state
> disagrees.
>
> WARN — BR-2 not found in Circuit Id column.
>
> The troubleshooter told us the protocol was working. The verifier told us the live
> state no longer matches the source of truth. Both were right. Both were needed.
>
> DIS priority is a policy decision — it's captured in the YAML as `isis_priority: 100`
> on BR-2's Ethernet0/0. That policy says BR-2 wins DIS election on this segment. The
> verify script enforces that policy. When the priority drifts, the verifier catches it.
> The troubleshooter can't, because a DIS re-election doesn't break any adjacency.

---

### Part 4 — Restore from Source of Truth

```bash
python scripts/configure_06_ipv6_isis_nornir.py --router BR-2
```

Nornir reconnects to BR-2, pushes the rendered config. `isis priority 100` is
restored on Ethernet0/0. IS-IS triggers another DIS election — BR-2 wins. The
pseudonode LSP returns to BR-2. Run verify again:

```bash
python scripts/verify_06_ipv6_isis_nornir.py --router BR-2 --check neighbors
```

PASS — BR-2 confirmed as DIS.

> **Instructor talking point:** Notice what restoring from source of truth means here.
> We didn't remember the command. We didn't look up what priority BR-2 should have.
> We ran the configure script — Nornir loaded the YAML, rendered the template, and
> pushed exactly what the source of truth says BR-2 should have. That's idempotent
> restore. The YAML is always the answer.
>
> The session log in `modules/06_ipv6_isis_nornir/logs/` has the full audit trail:
> when the verify WARN fired, which check, what finding, and when the restore was
> applied. One timestamped log per run. If you ran this in a change window, that
> log is your evidence of what happened and when.

---

## SECTION 8 — Objectives Review and Wrap-Up

`[SCREEN: README.md — Module Objectives section]`

Let's confirm each objective.

**IS-IS area design.** Done. Four areas, three router roles, dual-homed ABRs providing
path redundancy to the backbone, L1/L2 boundary demonstrated throughout.

**IS-IS Named Mode configuration.** Done. All eleven IS-IS routers use Named Mode.
NET addresses, `is-type`, `metric-style wide`, `passive-interface` under the process,
`address-family` blocks for route leaking and MT-IS-IS. No Classic Mode syntax.

**DIS election.** Done. BR-2 holds DIS by priority. The closing demo shows re-election
when priority drops. The pseudonode LSP is visible in `show isis database`. The verifier
confirms DIS role against the source of truth.

**Route leaking.** Done. ABR-1, ABR-2, and ABR-3 inject L2 prefixes into their L1
areas via `redistribute isis ip level-2 into level-1`. L1 leaf routers have full
routing visibility beyond a default route.

**MT-IS-IS for IPv6.** Done. BR-4 and BR-5 carry dual-stack. The IPv6 zone is bounded.
`address-family ipv6 / multi-topology` enabled on those two routers. IPv6 loopbacks
visible in the IS-IS LSDB. IPv6 routes confirmed in the routing table.

**OSPF redistribution.** Done. ASBR-1 bridges IS-IS and the OSPF stub domain.
OSPF-1's loopback prefix is redistributed into IS-IS and propagates through the
L1/L2 hierarchy to every router in the domain.

**`nr.run()` with a custom task function.** Done. `configure_isis_task` pre-renders
all configs before opening any SSH connection. Render failures surface before any
router is touched.

**`nr.filter()` for role-aware deployment.** Done. Four-phase deployment — backbone,
ABRs, leaves, OSPF-only. IS-IS convergence order enforced by the script. This is what
production IS-IS automation looks like.

---

Module 7 moves to Ansible and BGP Part 1. Nornir stays in the toolkit — it's not
replaced. Ansible brings a different model: declarative intent and idempotency at
scale. BGP brings a different automation challenge: peer relationships, policy
propagation, and at-scale state management across many neighbors. That's where
Ansible shines.

---

| Module | Protocol | Tool | What It Adds |
|--------|----------|------|--------------|
| 02 | EIGRP | Netmiko | Direct SSH, explicit command control |
| 03–04 | OSPF | NAPALM | Candidate config, diff before commit |
| 05–06 | IPv6 + IS-IS | Nornir | Task-based execution, role-aware inventory |
| 07–09 | BGP / Route Policy | Ansible | Declarative intent, idempotency at scale |
| 10–12 | BGP+MPLS / VPN | Ansible + pyATS | Structured parsing, stateful testing |

---

*End of Module 06 Verbal Script*
*NAMS26 — Network Automation Management Station 2026*
