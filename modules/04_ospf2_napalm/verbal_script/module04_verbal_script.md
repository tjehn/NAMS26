# Module 04 — OSPF Advanced / NAPALM
## Verbal Script — `module04_verbal_script.md`
### NAMS26 | Network Automation Management Station 2026

---

> **Production Notes**
> - Screen follows the script section by section — code is visible on screen,
>   instructor reads from this script
> - References describe what's on screen; instructor does not read code verbatim
> - Tone: conversational, technically precise, CCNP-level audience assumed
> - `[SCREEN]` cues indicate what should be visible on screen at that moment
> - Pre-flight and lab reset procedures are documented in `module04_preflight.md`
>   — reference that document for operational steps, do not repeat them here

---

## SECTION 1 — Module Objectives

`[SCREEN: README.md — Module Objectives section]`

Welcome to Module 4. The tool doesn't change — we're still using NAPALM and the same
three-file workflow from Module 3. What changes is the complexity of what we're
automating.

Module 3 was OSPF Classic Mode — two areas, one ABR, mixed authentication. Module 4
is OSPF Advanced — three areas, two ABRs, two ASBRs, redistribution between OSPF and
two independent EIGRP domains, LSA Type 3 filtering on both ABRs, and an NSSA area.
The scripts have to model all of that. The YAML has to capture all of that. And the
verify script has to validate all of it against a live topology.

By the time we're done, you'll have configured multi-area OSPF with redistribution
from a YAML source of truth via NAPALM. You'll have a verification script that
validates neighbor state, external route presence, LSA filtering behavior, and
bidirectional redistribution across all ten routers. And you'll have a troubleshooting
script with targeted LSA-type checks and failure demonstration scenarios specific to
redistribution and NSSA misconfiguration.

The other thing Module 4 does is reinforce the lesson from Module 3 about the
difference between a troubleshooter and a verifier — but in a redistribution context,
where that distinction becomes even more consequential. We'll come back to that at the
end.

---

## SECTION 2 — Lab Topology

`[SCREEN: README.md — Lab Topology section]`

Ten routers this time — R1 through R10. Three OSPF areas and two EIGRP domains.

**Area 0 — the backbone.** R1, R2, and R3. R1 connects to R2 on `192.1.12.0/24`
and to R3 on `192.1.13.0/24`. These are point-to-point links — no DR/BDR election,
no multi-access complexity. Area 0 in this topology is lean: three routers, two
links, two loopbacks each.

**Area 10 — the left side.** R2 is the ABR. R2 connects to R4 on `192.1.24.0/24`.
R4 connects to R10 on `192.1.40.0/24`. R4 and R10 both carry simulated prefix pools
on numbered loopback interfaces — we'll talk about those in detail when we get to the
YAML.

**Area 20 — the right side — NSSA.** R3 is the ABR. R3 connects to R5 on
`192.1.35.0/24`. R5 connects to R6 on `192.1.56.0/24`. Area 20 is configured as
NSSA on all three routers in that area — R3, R5, and R6.

**EIGRP 100 — the left external domain.** R1, R7, and R8. R1 connects to R7 on
`192.1.17.0/24` and to R8 on `192.1.18.0/24`. R7 and R8 are EIGRP-only — they have
no OSPF configuration at all. R7 and R8 each carry loopbacks simulating prefixes that
will be redistributed into OSPF.

**EIGRP 111 — the right external domain.** R6 and R9. R6 connects to R9 on
`192.1.69.0/24`. R9 is EIGRP-only. R9 carries loopbacks that will enter OSPF through
R6's redistribution.

**The router roles:**

R1 is an ASBR in Area 0. It redistributes bidirectionally between OSPF and EIGRP 100,
and injects a default route into the OSPF domain with `default-information originate
always`.

R2 is an ABR — Area 0 to Area 10. It also filters LSAs leaving Area 10.

R3 is both an ABR and an ASBR. ABR between Area 0 and Area 20. ASBR because it
converts Type 7 LSAs from R6 into Type 5 LSAs for Area 0 — that conversion is
automatic when you're the NSSA ABR. R3 also injects a Type 7 default route into
Area 20 and filters LSAs entering Area 20.

R6 is an ASBR inside Area 20. It redistributes EIGRP 111 routes into OSPF as
Type 7 LSAs — NSSA external — because it's sitting inside an NSSA area.

R7, R8, and R9 are EIGRP-only. No OSPF process. The scripts skip OSPF-specific
checks on these three routers automatically.

Every router has `Ethernet1/3` as the out-of-band management interface on
`192.168.1.0/24`. Same pattern as all previous modules.

---

## SECTION 3 — Tool Overview: NAPALM (continued)

`[SCREEN: README.md — Tool Overview section]`

NAPALM is unchanged from Module 3 — same candidate configuration model, same
`load_merge_candidate` / `compare_config` / `commit_config` sequence, same IOL
`optional_args` block.

There is one IOL behavior worth noting that surfaces in this module. When NAPALM
commits a configuration, it attempts to save a rollback file to `nvram:` before
applying the candidate. IOL doesn't support arbitrary file writes to `nvram:` via
`copy` — only `startup-config` is a valid destination. NAPALM raises an exception
after a successful commit when it can't save the rollback file. The configure script
catches that specific exception and silently continues — the commit itself succeeded,
the rollback mechanism simply isn't available on this platform.

There's also a character encoding issue specific to IOL's TCL interpreter. NAPALM
pushes the configuration file to the router using TCL's `puts` command. IOL's TCL
implementation doesn't handle non-ASCII characters — specifically Unicode em dashes
or special punctuation in interface descriptions. If a description contains anything
outside the ASCII character set, TCL throws a `missing close-brace` error and the
file write fails before a single line of config is applied. The YAML in this module
uses plain ASCII hyphens throughout. On physical hardware this isn't a concern.

---

## SECTION 4 — Configuration

### 4a — The Three-File Workflow

`[SCREEN: module directory tree — data/, templates/, scripts/]`

Same three-file workflow:

```
ospf_advanced.yaml  →  ospf_advanced.j2  →  configure_ospf_advanced.py  →  Router
   (variables)            (template)               (NAPALM SSH push)
```

The delivery mechanism is identical to Module 3. The complexity lives entirely in
the YAML and the template — what they have to model is significantly richer.

---

### 4b — File 1: `ospf_advanced.yaml`

`[SCREEN: ospf_advanced.yaml]`

The YAML structure follows the exact same conventions as Module 3. Credential anchor
at the top, per-device blocks with `dns_name`, `oob_ip`, `oob_interface`, `interfaces`,
and the routing protocol blocks below. Five things in this file are specific to
Module 4.

---

**EIGRP-only routers use `ospf: ~`.**

R7, R8, and R9 have no OSPF configuration. Their device block includes an `eigrp`
block and `ospf: ~` — a YAML null sentinel. The Jinja2 template checks `{% if ospf %}`
before rendering any OSPF block, so these routers produce a clean config with an
EIGRP process and no `router ospf` section at all. The verify and troubleshoot scripts
check for EIGRP-only routers by name and skip OSPF-specific checks on them.

---

**The `eigrp` block.**

Routers that participate in EIGRP — R1, R6, R7, R8, R9 — have an `eigrp` block:

```yaml
eigrp:
  as_number: 100
  networks:
    - 192.1.17.0
    - 192.1.18.0
  redistribute_ospf:
    process: 1
    metric: "10000 100 255 1 1500"
```

On R1 and R6 — the ASBRs — the `redistribute_ospf` sub-block is present. On R7, R8,
and R9 — the EIGRP-only routers — it's absent. The template checks for it and renders
the redistribute statement only when it's defined.

---

**The `area_types` block.**

NSSA area declarations live in the `ospf` block under `area_types`:

```yaml
ospf:
  area_types:
    - area: 20
      type: nssa
      default_information_originate: true
```

R3 — the NSSA ABR — has `default_information_originate: true`. R5 and R6 — internal
Area 20 routers — have the same `area_types` entry but with `default_information_originate:
false`. That `false` suppresses the `default-information-originate` keyword in the
rendered config, giving R5 and R6 simply `area 20 nssa` without the default injection.
One data model, one template condition, two different rendered outputs depending on the
router's role.

---

**LSA filtering — `area_filters` and `prefix_lists`.**

ABRs that filter Type 3 LSAs carry two additional keys in their `ospf` block:

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
        prefix: 0.0.0.0/0
        le: 32
```

`area_filters` drives the `area X filter-list prefix <name> in/out` command inside
the OSPF process. `prefix_lists` drives the `ip prefix-list` entries that are rendered
after the routing blocks. The prefix-list section only renders when `prefix_lists` is
defined — routers without filtering have `prefix_lists: {}` and the template skips
that entire section cleanly.

---

**The R4 loopback prefix pools and wildcard summarization.**

R4 carries eight simulated loopbacks in two blocks of four. Rather than eight
individual network statements, the YAML models two wildcard-aggregated entries:

```yaml
networks:
  - prefix: 105.1.12.0
    wildcard: 0.0.3.255
    area: 10
  - prefix: 105.1.16.0
    wildcard: 0.0.3.255
    area: 10
```

The wildcard `0.0.3.255` spans four contiguous /24 subnets in the third octet —
`.12` through `.15` for block A, `.16` through `.19` for block B. OSPF uses this
to match all four loopbacks in each block with a single network statement. The key
operational point: by splitting the eight loopbacks into two separately-controlled
blocks, you can include or exclude either group independently by adding or removing
one network statement — without touching the interfaces themselves.

This is not inter-area summarization. `area X range` aggregates Type 3 LSAs that
leave the area — what ABRs advertise to other areas. What we're doing here is
controlling which interfaces OSPF *matches* in the first place. The individual /24
prefixes still appear as separate entries in the LSDB. It's a different tool for a
different purpose.

---

### 4c — File 2: `ospf_advanced.j2`

`[SCREEN: ospf_advanced.j2]`

The template extends Module 3's two-section structure — physical interfaces and
loopbacks — with three new sections: EIGRP block, OSPF block, and prefix lists.

---

**The EIGRP block.**

```jinja
{% if eigrp %}
router eigrp {{ eigrp.as_number }}
{% for net in eigrp.networks | default([]) %} network {{ net }}
{% endfor %}
{% if eigrp.redistribute_ospf %} redistribute ospf {{ eigrp.redistribute_ospf.process }} metric {{ eigrp.redistribute_ospf.metric }}
{% endif %}
!
{% endif %}
```

The outer `{% if eigrp %}` guard means this entire block is absent on OSPF-only
routers. On EIGRP-only routers, it's the only routing block in the rendered config.
On ASBRs like R1 and R6, it renders alongside the OSPF block.

---

**The OSPF block — area type and filter-list rendering.**

```jinja
{% for area_type in ospf.area_types | default([]) %}
{% if area_type.type == 'nssa' and area_type.default_information_originate %}
 area {{ area_type.area }} nssa default-information-originate
{% elif area_type.type == 'nssa' %}
 area {{ area_type.area }} nssa
{% endif %}
{% endfor %}
{% for af in ospf.area_filters | default([]) %}
 area {{ af.area }} filter-list prefix {{ af.prefix_list }} {{ af.direction }}
{% endfor %}
```

The area type loop renders the NSSA declaration with or without
`default-information-originate` based on the YAML flag. The filter-list loop renders
the `area X filter-list` command only on routers that have `area_filters` defined.
Routers with empty lists produce no output from these loops.

---

**Prefix lists render after the routing blocks.**

```jinja
{% if ospf.prefix_lists %}
{% for pl_name, pl_entries in ospf.prefix_lists.items() %}
{% for entry in pl_entries %}
{% if entry.le and entry.le != "" %}
ip prefix-list {{ pl_name }} seq {{ entry.seq }} {{ entry.action }} {{ entry.prefix }} le {{ entry.le }}
{% else %}
ip prefix-list {{ pl_name }} seq {{ entry.seq }} {{ entry.action }} {{ entry.prefix }}
{% endif %}
{% endfor %}
{% endfor %}
{% endif %}
```

Prefix lists are rendered at the end — after `router ospf` and `router eigrp` blocks
— because IOS accepts the `area filter-list` reference before the prefix-list is
defined. The `le` field handles the `le 32` qualifier that appears on permit-any
entries and on the A20-IN deny entry.

---

### 4d — File 3: `configure_ospf_advanced.py`

`[SCREEN: configure_ospf_advanced.py]`

The configure script is structurally identical to Module 3's. Path resolution,
YAML load, credential injection, Jinja2 environment with `cidr_to_netmask`
registered, `--dry-run` and `--router` flags. The NAPALM deployment loop is the same.

The only meaningful addition is the rollback exception handling in the commit step:

```python
try:
    device.commit_config()
    passed(f"Configuration committed on {device_name}.")
except Exception as exc:
    if "rollback" in str(exc).lower():
        # Suppressed — IOL does not support nvram: rollback files
        pass
    else:
        raise
```

The commit succeeds. The rollback file failure is silently swallowed. On physical
hardware this exception never fires — the rollback mechanism works as designed.

---

**Running the script.**

```bash
# 1. Dry-run — render and review all ten configs
python scripts/configure_ospf_advanced.py --dry-run

# 2. Deploy to all routers
python scripts/configure_ospf_advanced.py

# 3. Verify OSPF state
python scripts/verify_ospf_advanced.py

# 4. Troubleshoot if needed
python scripts/troubleshoot_ospf_advanced.py
```

The dry-run step matters more in Module 4 than it did in Module 3. With redistribution
and NSSA in play, there are more ways for the rendered config to be subtly wrong
before it hits a router. Open the `.cfg` files in `configs/` and confirm the EIGRP
blocks, the NSSA declarations, the filter-list references, and the prefix-list
entries on R2 and R3 specifically.

---

## SECTION 5 — Verification

`[SCREEN: verify_ospf_advanced.py]`

The verify script has five checks: `neighbors`, `interfaces`, `routes`, `lsdb`, and
`redistribution`. The first two are carried over from Module 3 with one addition —
EIGRP-only routers are skipped automatically and return INFO rather than FAIL.

---

**`check_neighbors`**

Same logic as Module 3. Parses `show ip ospf neighbor`, validates FULL adjacency
state per interface. Skipped on R7, R8, and R9. On Area 20 routers, a failed
adjacency after NSSA misconfiguration — like removing `area 20 nssa` from one side —
will surface here as FAIL.

---

**`check_interfaces`**

Same logic as Module 3. Validates area assignment and network type per interface.
No authentication validation in this module — authentication is not a focus of
Module 4. Skipped on R7, R8, and R9.

---

**`check_routes` — enhanced for external routes and filtering.**

The route parser now handles six OSPF route types: Intra (`O`), Inter (`O IA`),
E1 (`O E1`), E2 (`O E2`), N1 (`O N1`), and N2 (`O N2`). The route table display
color-codes them — inter-area routes in cyan, external E1/E2 routes in yellow,
NSSA N1/N2 routes in green.

After the route table, the check validates filtering behavior. For Area 20 routers
— R5 and R6 — it checks that `O N2 0.0.0.0/0` is present (the NSSA default route
from R3), and that `100.0.0.0/8` is absent (blocked by R3's A20-IN filter). For
all other OSPF routers, it checks that `102.0.0.0/8` and `103.0.0.0/8` are absent
(blocked by R2's A10-OUT filter). These are definitive pass/fail checks — not
informational. If the filtering isn't working, this check fails.

---

**`check_lsdb` — targeted per-type commands.**

Module 3's `check_lsdb` ran `show ip ospf database` — one command, the full combined
output. Module 4 runs five separate commands, one per LSA type:

```bash
show ip ospf database router          # Type 1 — Router LSAs
show ip ospf database summary         # Type 3 — Summary LSAs
show ip ospf database asbr-summary    # Type 4 — ASBR Summary LSAs
show ip ospf database external        # Type 5 — AS External LSAs
show ip ospf database nssa-external   # Type 7 — NSSA External LSAs
```

This makes each LSA type explicitly visible rather than buried in a combined dump.
On Area 10 routers you'll see Type 4 ASBR Summary LSAs advertising R1's reachability.
On Area 20 routers you'll see Type 7 NSSA External LSAs from R6's redistribution.
On Area 0 routers you'll see Type 5 AS External LSAs from both R1 and the Type 7 →
Type 5 conversion R3 performs on R6's routes. This check is always informational —
it's the visual confirmation that the LSA mechanics are working as expected.

---

**`check_redistribution` — new in Module 4.**

This check has three different behaviors depending on the router's role.

On R1 and R6 — the ASBRs — it checks both directions. It runs `show ip route eigrp`
and looks for `D EX` entries — OSPF routes redistributed into EIGRP. It also runs
`show ip route ospf` and looks for `O E1`, `O E2`, `O N1`, or `O N2` entries — EIGRP
routes redistributed into OSPF. Both directions must be working for the check to pass.

On R7, R8, and R9 — EIGRP-only — it checks `show ip route eigrp` for `D EX` entries.
These are the redistributed OSPF routes arriving from R1 or R6. If redistribution
from OSPF into EIGRP is working, these routers see OSPF prefixes as `D EX`.

On internal OSPF routers — R2, R3, R4, R5, R10 — it checks `show ip route ospf` for
external route types. If redistribution is working end-to-end, every OSPF router in
the domain should see external routes regardless of area.

---

## SECTION 6 — Troubleshooting

`[SCREEN: troubleshoot_ospf_advanced.py]`

Same two-mode architecture as Module 3: live troubleshooting and failure demonstration.
The live checks are `neighbors`, `database`, `routes`, `redistribution`, and `process`.

Authentication is gone from the check list — it's not a Module 4 focus. `redistribution`
takes its place. The failure scenarios are specific to redistribution and NSSA
behavior rather than authentication misconfigurations.

---

**`check_neighbors`**

Same as Module 3 — `show ip ospf neighbor detail`, scans for problem states, confirms
FULL adjacencies. Skipped on EIGRP-only routers. An NSSA area type mismatch — one
router with `area 20 nssa` and one without — will surface here as a stuck adjacency
in EXSTART or INIT.

---

**`check_database` — LSA health by type.**

This is the most targeted check in the troubleshoot script. It runs separate commands
per LSA type and applies specific logic to each.

Type 1 — Router LSAs: confirms this router's own router ID appears in the database.
If it doesn't, OSPF isn't running or the router ID is wrong.

Type 4 — ASBR Summary LSAs: checked on Area 10 routers (R4, R10). If Type 4 LSAs
are absent on an Area 10 router, R2 cannot reach or is not advertising R1's ASBR
reachability into Area 10. R4 and R10 would lose the ability to reach external
prefixes.

Type 5 — AS External LSAs: checked on all OSPF routers. If Type 5 LSAs are absent,
redistribution from R1 has failed, or R3's Type 7 → Type 5 conversion is broken.

Type 7 — NSSA External LSAs: checked only on Area 20 routers (R5, R6). If Type 7
LSAs are absent on R5, R6 is not redistributing EIGRP 111 into OSPF, or the NSSA
configuration on R6 is broken.

---

**`check_redistribution`**

Same role-based logic as the verify script, but presented as a live troubleshooting
output. On ASBRs, it shows both the EIGRP routing table and the OSPF routing table
so you can see both directions in one check. On internal routers, it shows the OSPF
routing table and counts the external route entries.

---

**`check_routes`**

Runs `show ip route ospf` and `show ip ospf border-routers`. On Area 20 routers,
checks for the NSSA default route — `O N1` or `O N2 0.0.0.0/0`. If it's absent,
R3's `default-information-originate` is either not configured or not working.
Border router entries in `show ip ospf border-routers` confirm ABR and ASBR
reachability from any router's perspective.

---

**`check_process`**

Runs `show ip protocols`. For OSPF routers, validates the process ID and router ID.
For EIGRP routers, validates the AS number. On dual-protocol routers like R1 and R6,
it validates both OSPF and EIGRP process state from the same command output.

---

**Failure demonstration scenarios.**

Five scenarios, all in-memory — no router is touched.

`missing-network` and `wrong-router-id` carry forward from Module 3. The three new
scenarios are specific to Module 4.

`missing-redistribute` removes the `redistribute_eigrp` statement from an ASBR's
OSPF block. The config diff shows exactly one line removed — the redistribute
statement. The symptom: `O E1` and `O E2` routes disappear from the entire OSPF
domain. All adjacencies remain FULL. The troubleshooter passes every neighbor and
process check. The verifier catches it on `--check redistribution`. This is the
closing demonstration scenario.

`wrong-area-type` removes the `area 20 nssa` declaration from an Area 20 router.
The diff shows the NSSA line removed. The symptom: the adjacency between that router
and its Area 20 neighbor drops — area type mismatch in the Hello packet. Unlike
missing redistribution, this one breaks neighbors. The troubleshooter catches it
immediately on `--check neighbors`.

`missing-nssa` removes `default-information-originate` from R3's NSSA declaration —
`area 20 nssa` stays, only the default injection flag is removed. The diff shows
`area 20 nssa default-information-originate` replaced by `area 20 nssa`. The symptom:
R5 and R6 lose their `O N2 0.0.0.0/0` default route. All adjacencies remain FULL.
All Type 7 LSAs from R6's redistribution remain present. The only thing missing is
the default path to Area 0. This is the subtlest failure in the module — everything
looks healthy except reachability from Area 20 to the rest of the network.

---

## SECTION 7 — Closing Demonstration: Configuration Drift

`[SCREEN: terminal — scripts/ and utils/ directories]`

Same structure as Module 3's closing demonstration. Inject a drift, show the
troubleshooter passes, show the verifier catches it, restore from the source of truth.

The fault is redistribution — specifically, removing the `redistribute eigrp 100`
statement from R1's OSPF process. This is the most realistic drift scenario in this
module. It's the kind of change that happens in production — someone removes a
redistribution statement during maintenance, OSPF adjacencies stay up, protocol
looks healthy, but the routing domain quietly loses external reachability.

---

### Part 1 — Inject the Drift

```bash
python utils/push_config.py --router R1 \
  --cmd "router ospf 1" "no redistribute eigrp 100 metric-type 1 subnets"
```

R1 stops redistributing EIGRP 100 into OSPF. R7 and R8's loopbacks — the EIGRP 100
prefixes — disappear from the OSPF domain. The `192.1.17.0/24` and `192.1.18.0/24`
segments also disappear. All OSPF adjacencies remain FULL. R1 is a healthy OSPF
router. EIGRP 100 is running normally on R1. Nothing is broken from a protocol
standpoint. The routing domain simply no longer knows about the EIGRP 100 side of
the network.

---

### Part 2 — Troubleshooter Shows a Healthy Router

```bash
python scripts/troubleshoot_ospf_advanced.py --router R1 --check neighbors process
```

Both checks pass. R1 has FULL adjacencies with R2 and R3. OSPF process 1 is running
with router ID `0.0.0.1`. EIGRP AS 100 is confirmed running. From the troubleshooter's
perspective, R1 is completely healthy.

> **Instructor talking point:** Everything the troubleshooter checks is true. The
> neighbors are FULL. The process is running. The router IDs are correct. The
> troubleshooter answered its question — "is OSPF working on R1?" — and the answer
> is yes.
>
> But the troubleshooter has no visibility into whether redistribution is configured.
> It checks operational state. Redistribution is a configuration policy. Those are
> different questions.

---

### Part 3 — Verifier Reveals the Drift

```bash
python scripts/verify_ospf_advanced.py --router R1 --check redistribution
```

The check reports FAIL on R1:

```
  [FAIL] OSPF: no external routes (E1/E2/N1/N2) found
         — EIGRP -> OSPF redistribution may have failed
```

> **Instructor talking point:** The YAML says R1 should be redistributing EIGRP 100
> into OSPF. The live router is not. The external routes that should be in the OSPF
> domain are absent. That's configuration drift — the router no longer matches its
> source of truth.
>
> The troubleshooter passed. The verifier failed. Both answers are correct. They are
> answering different questions.
>
> This is the same lesson as Module 3, but in a redistribution context. And
> redistribution is where this distinction matters most in production. A broken
> neighbor is visible immediately — adjacencies drop, routes disappear, alarms fire.
> A broken redistribution statement is invisible to the protocol. OSPF is fully
> operational. EIGRP is fully operational. The policy that connects them is simply
> gone, and nothing tells you unless you're comparing against a source of truth.

---

### Part 4 — Restore from Source of Truth

```bash
python scripts/configure_ospf_advanced.py --router R1
python scripts/verify_ospf_advanced.py --router R1
```

NAPALM loads the candidate, compares it to running config, shows the diff — one line,
the missing redistribute statement. Commits. Saves. Verify confirms all checks clean
across all five checks on R1.

---

### Part 5 — What NAPALM's Diff Showed You

The diff output before the commit showed exactly one line as an addition:

```
+  redistribute eigrp 100 metric-type 1 subnets
```

Nothing else changed. The entire rest of R1's configuration was already present. The
merge candidate model applied precisely the one thing that was missing and nothing
more. That's the safety of diff-before-commit — you saw the change before it landed,
and you saw that it was exactly what you expected.

Compare that to what a `no redistribute` command looks like in production without
automation: someone removes the statement, traffic drops, you spend time figuring out
what changed. With a source of truth and a verify script, the gap between "something
is wrong" and "here is exactly what diverged" collapses.

---

## SECTION 8 — Objectives Review and Wrap-Up

`[SCREEN: README.md — Module Objectives section]`

Let's confirm each objective.

**Multi-area OSPF deployed across ten routers.** Done. Area 0, Area 10, and Area 20
NSSA configured from YAML via NAPALM. All adjacencies FULL, all areas operational.

**Redistribution configured between OSPF and two EIGRP domains.** Done. R1
redistributing bidirectionally with EIGRP 100. R6 redistributing bidirectionally
with EIGRP 111. External routes visible across the OSPF domain.

**LSA Type 3 filtering demonstrated on both ABRs.** Done. R2 blocking
`102.0.0.0/8` and `103.0.0.0/8` from leaving Area 10. R3 blocking `100.0.0.0/8`
from entering Area 20. The verify script confirms filter behavior from the routing
table on each affected router.

**NSSA area behavior demonstrated.** Done. Area 20 NSSA on R3, R5, and R6. R3
injecting a Type 7 default route into Area 20. R6 redistributing EIGRP 111 as Type 7
LSAs. R3 converting those Type 7 LSAs into Type 5 for Area 0.

**Type 4 / Type 5 LSA mechanics observable.** Done. Type 4 ASBR Summary LSAs visible
on Area 10 routers. Type 5 AS External LSAs from R1 and from R3's conversion of R6's
Type 7 routes visible in Area 0.

**NAPALM workflow reinforced.** Done. Same `load_merge_candidate` / `compare_config`
/ `commit_config` pattern as Module 3, applied to a topology that includes EIGRP
blocks, NSSA declarations, area type conditions, and prefix-list filtering — all
from the same three-file workflow.

**Verification script operational.** Done. Five checks across ten routers — including
external route type validation, filtering behavior confirmation, and bidirectional
redistribution validation — with a summary table at the end.

**Troubleshooting script operational.** Done. Five live checks with targeted LSA-type
database analysis, and three new failure demonstration scenarios specific to
redistribution and NSSA misconfiguration.

---

Module 5 moves to Nornir. The protocol and topology will change — Nornir brings a
concurrent execution model and an inventory abstraction that changes how we think
about targeting devices at scale. The three-file workflow continues. See you there.

---

| Module | Protocol   | Tool          | What It Adds                                   |
|--------|------------|---------------|------------------------------------------------|
| 02     | EIGRP      | Netmiko       | Direct SSH, explicit command control            |
| 03–04  | OSPF       | NAPALM        | Candidate config, diff before commit            |
| 05–07  | TBD        | Nornir        | Concurrent execution, inventory model           |
| 08–09  | TBD        | pyATS/Genie   | Structured parsing, stateful testing            |
| 10–12  | TBD        | Ansible       | Declarative intent, idempotency at scale        |

---

*End of Module 04 Verbal Script*
*NAMS26 — Network Automation Management Station 2026*
