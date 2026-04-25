# Module 03 — OSPF Classic Mode
## Verbal Script — `module03_verbal_script_final.md`
### NAMS26 | Network Automation Management Station 2026

---

> **Production Notes**
> - Screen follows the script section by section — code is visible on screen,
>   instructor reads from this script
> - References describe what's on screen; instructor does not read code verbatim
> - Tone: conversational, technically precise, CCNP-level audience assumed
> - `[SCREEN]` cues indicate what should be visible on screen at that moment
> - Pre-flight and lab reset procedures are documented in full in
>   `eve-ng_lab_reset_sop.md` — reference that document for operational steps,
>   do not repeat them here

---

## SECTION 1 — Module Objectives

`[SCREEN: README.md — Module Objectives section]`

Welcome to Module 3. We're moving up a level — same three-file workflow from
Module 2, same Jinja2 template and YAML source of truth, but the automation tool
changes. We're replacing Netmiko with NAPALM, and that change brings with it a
fundamentally different model for how configuration gets deployed to devices.

The protocol for this module is OSPF Classic Mode — and this topology is
significantly more complex than the EIGRP lab. Eleven routers, two areas, an ABR,
mixed authentication methods across different segments, DR/BDR priority manipulation,
point-to-point network type overrides on Ethernet interfaces, and inter-area
summarization. There's a lot of OSPF mechanics in this lab, and all of it is driven
from Python.

By the time we're done you'll have configured OSPF across a multi-area topology using
NAPALM's candidate configuration model — meaning you'll see a diff of exactly what's
changing on each device before anything is committed. You'll have a verification
script that validates neighbor adjacency state, interface configuration, the Link
State Database, and the routing table. And you'll have a troubleshooting script that
can catch authentication misconfigurations — including the specific case where an
authentication type is configured but no key is defined — with targeted checks per
interface.

The other thing this module does is establish the NAPALM pattern for Modules 3 and 4.
If you're coming from Module 2, the key shift is this: Netmiko is a command sender.
NAPALM is a configuration manager. That distinction will become very concrete when we
get into the scripts.

---

## SECTION 2 — Lab Topology

`[SCREEN: README.md — Lab Topology section]`

![OSPF Classic Mode Topology](diagrams/topology_ospf_classic.drawio.svg)

Let's orient to the topology. Eleven routers — R1 through R11 — running OSPF process
ID 1 across two areas.

Area 0 is the backbone and carries the majority of the topology. R1, R2, R3, R11 share
the `192.1.100.0/24` multi-access segment. That's the primary broadcast domain for
this lab — four routers on a single Ethernet segment, which gives us an interesting
DR/BDR election to work with. R2 has been configured with OSPF priority 10 on that
segment, making it the likely DR candidate.

R2 and R5 are connected via serial — `192.1.101.0/24`. R4 and R5 are connected via
a second serial link — `192.1.102.0/24` — with PPP encapsulation on both sides.

R3, R4, and R6 share the `192.1.103.0/24` multi-access segment. R4 and R6 both have
priority 10, R3 has priority 5 — so the DR election on that segment has a specific
expected outcome.

Moving right, R6 connects to R7 on `192.1.67.0/24`. R7 connects to R8 on
`192.1.78.0/24` — but this link has `ip ospf network point-to-point` configured on
both ends, which eliminates the DR/BDR election entirely. That's an intentional
design choice we'll come back to.

R8 is the ABR. Its Ethernet0/0 faces Area 0 via R7, and its Ethernet0/1 faces
Area 10 via R9. Area 10 is a simple chain — R8 to R9 on `192.1.89.0/24`, R9 to R10
on `192.1.90.0/24`.

R8 is also configured with `area 0 range 192.1.100.0 255.255.252.0`. That summarizes
the Area 0 subnets — the 100, 101, 102, and 103 segments — into a single Type 3
Summary LSA that Area 10 routers see as one prefix.

Every router has `Ethernet1/3` as the out-of-band management interface on the
`192.168.1.0/24` OOB network. That's the SSH path from the NAMS to the lab. Just
like Module 2, `dns_name` is the connection target — not `oob_ip`.

One last thing on the topology worth calling out: the authentication configuration
across this lab is intentionally varied. The `192.1.100.0/24` segment uses plain-text
authentication per-interface. The serial links use MD5 per-interface. R5 uses
area-level MD5 authentication instead of per-interface. R11 uses area-level plain-text.
Several segments have no authentication at all. This is not inconsistency — it's
deliberate. The module demonstrates every form of OSPF authentication configuration
that exists in Cisco IOS, and the scripts handle all of them from the same YAML
structure.

---

## SECTION 3 — Tool Overview: NAPALM

`[SCREEN: README.md — Tool Overview section]`

NAPALM stands for Network Automation and Programmability Abstraction Layer with
Multivendor support. The name is a mouthful, but the idea is straightforward: provide
a unified Python API that works across multiple vendors and operating systems, so the
same code that configures a Cisco IOS router can also configure a Juniper, Arista, or
NX-OS device without rewriting your automation logic.

There are two sides to NAPALM that are relevant to this module.

The first is the **configuration management model**. Instead of pushing commands
directly to a device the way Netmiko does, NAPALM uses a candidate configuration
approach. You load a candidate, NAPALM compares it to the running configuration and
shows you the diff, and then you either commit it or discard it. That diff step is
important — it makes the impact of every deployment visible before a single line is
applied.

The second is the **structured getter methods**. NAPALM provides functions like
`get_interfaces()`, `get_bgp_neighbors()`, and `get_route_to()` that return
normalized Python dictionaries regardless of which vendor the device is. We're not
using the getters for configuration in this module, but the verify and troubleshoot
scripts use NAPALM's `cli()` method extensively for show command collection. That
`cli()` method gives us a clean way to issue IOS show commands and get the output
back without managing the raw SSH session directly.

**What changes compared to Netmiko:**

With Netmiko, you opened a connection, sent commands, and received raw CLI text back.
The connection lifecycle was explicit — you managed it. With NAPALM, the IOS driver
wraps all of that. You instantiate a driver, call `open()`, do your work, and call
`close()`. For configuration pushes, you call `load_merge_candidate()` followed by
`compare_config()` and `commit_config()`. The device handles the rest.

**The limitation that surfaces in this lab:**

NAPALM's IOS driver expects a standard IOS filesystem — specifically, it runs a `dir`
command before loading a candidate configuration to check available disk space. Cisco
IOL doesn't have a `flash:` filesystem. It returns "No space information available"
from `system:/`, which breaks NAPALM's pre-flight check.

The fix is two `optional_args` that redirect that check to `nvram:` and bypass the SCP
file transfer that NAPALM would normally use for config push:

```python
optional_args = {
    "dest_file_system": "nvram:",
    "inline_transfer":  True,
}
```

`nvram:` does report free space in the format NAPALM expects. `inline_transfer: True`
sends the configuration directly over the SSH session instead of using SCP, which IOL
also doesn't support. Neither of these overrides is needed against physical hardware.
This is documented in the README and in the script as an IOL-specific construct.

**When to use NAPALM vs. alternatives:**

NAPALM is the right tool when you want the safety of a diff-before-commit workflow,
when you're working in a multi-vendor environment and want normalized data from getter
methods, or when you need configuration rollback capability. In this module, the diff
output on every deployment run is both operationally safe and pedagogically useful —
you see exactly what NAPALM is going to apply before it applies it.

---

## SECTION 4 — Configuration

### 4a — The Three-File Workflow

`[SCREEN: module directory tree — data/, templates/, scripts/]`

Same workflow as Module 2. YAML provides the data, Jinja2 renders the configuration,
and Python delivers it to the devices. The tool that handles delivery changes — Netmiko
is out, NAPALM is in — but the file structure and the relationship between these three
files is identical.

```
ospf_classic.yaml  →  ospf_classic.j2  →  configure_ospf_classic.py  →  Router
   (variables)           (template)              (NAPALM SSH push)
```

---

### 4b — File 1: `ospf_classic.yaml`

`[SCREEN: ospf_classic.yaml]`

The YAML file follows the same structure established in Module 2. Credentials defined
once at the top with a YAML anchor, referenced per device with an alias. `dns_name` as
the connection target, `oob_ip` for documentation only, `oob_interface` driving the
template exclusion logic.

There are four things in this file that are specific to Module 3 and worth walking
through.

---

**The interface block is more complex.**

Module 2's interface entries had six fields: IP, description, shutdown, speed, duplex,
and the EIGRP-specific bandwidth and delay. Module 3's interface entries have all of
those plus five OSPF-specific fields:

```yaml
Ethernet0/0:
  description: "To R2 R3 R11 - Area 0"
  ip: 192.1.100.1/24
  shutdown: false
  ospf_network_type: ""
  ospf_priority: ""
  ospf_authentication:
    type: plaintext
    key: cisco123
    key_id: ""
  encapsulation: ""
```

`ospf_network_type` overrides the default network type on the interface — we use this
on the R7–R8 link and on all Loopback interfaces. `ospf_priority` sets the DR/BDR
election weight. `ospf_authentication` is a sub-block with three fields: `type`,
`key`, and `key_id`. `encapsulation` handles the PPP serial interfaces.

Every interface — even unused ones — has these fields present with empty values.
That's the Module 2 convention: the full interface schema is always present, populated
where applicable and empty where not. It keeps the template logic clean — no
existence checks needed.

---

**Authentication is modeled two ways.**

For most routers, authentication is configured per-interface in the `ospf_authentication`
block under each interface:

```yaml
Serial2/0:
  ospf_authentication:
    type: md5
    key: ccie123
    key_id: 1
```

For R5 and R11, authentication is applied at the area level from the `ospf` block:

```yaml
ospf:
  area_authentication:
    - area: 0
      type: message-digest
```

Both models produce OSPF adjacencies that behave identically. The difference is scope:
per-interface authentication applies only to the interfaces where it's explicitly
configured. Area-level authentication applies to every interface in that area
automatically. The module demonstrates both because both appear in production — and
the verify and troubleshoot scripts handle both.

---

**The `ospf` block contains all process-level configuration.**

Under each device, the `ospf` block carries the process ID, router ID, network
statements with area assignments, area-level authentication, area range summarization,
and passive interfaces. On R8 — the ABR — it looks like this:

```yaml
ospf:
  process_id: 1
  router_id: 0.0.0.8
  networks:
    - prefix: 192.1.78.0
      wildcard: 0.0.0.255
      area: 0
    - prefix: 8.0.0.0
      wildcard: 0.255.255.255
      area: 10
    - prefix: 192.1.89.0
      wildcard: 0.0.0.255
      area: 10
  area_range:
    - area: 0
      prefix: 192.1.100.0
      mask: 255.255.252.0
```

R8's loopback is in area 10, not area 0. That means Area 0 routers will see R8's
loopback as an inter-area route — a Type 3 Summary LSA — rather than an intra-area
route. That's worth noting when you look at the LSDB later.

---

**Loopbacks use the same interface block as physical interfaces.**

In Module 2, loopbacks were in a separate `loopbacks` dictionary. In Module 3, all
interfaces — physical and loopback — are in a single `interfaces` dictionary. The
Jinja2 template separates them by checking for the string `Loopback` in the
interface name. This is the loop guard pattern established in this module:

- Physical loop: `{% if intf_name != oob_interface and 'Loopback' not in intf_name %}`
- Loopback loop: `{% if 'Loopback' in lb_name %}`

---

### 4c — File 2: `ospf_classic.j2`

`[SCREEN: ospf_classic.j2]`

The template follows the same structure as Module 2. Physical interfaces first,
loopbacks second, then the routing protocol block. Three things are worth calling
out here.

---

**The loop guard pattern.**

```jinja
{% for intf_name, intf in interfaces.items() %}
{% if intf_name != oob_interface and 'Loopback' not in intf_name %}
interface {{ intf_name }}
...
{% endif %}
{% endfor %}
```

The physical interface loop excludes both the OOB interface and any Loopback
interface in a single condition. The loopback section uses the complement:

```jinja
{% for lb_name, lb in interfaces.items() %}
{% if 'Loopback' in lb_name %}
interface {{ lb_name }}
...
{% endif %}
{% endfor %}
```

This is clean, explicit, and does exactly one thing: each interface ends up in
exactly one section of the rendered output.

---

**Authentication renders differently depending on type.**

Three auth states are possible for any given interface: none, plain-text, or MD5.
The template handles all three with a pair of independent conditions:

```jinja
{% if intf.ospf_authentication is defined and
     intf.ospf_authentication.type | default('none') == 'plaintext' %}
 ip ospf authentication
 ip ospf authentication-key {{ intf.ospf_authentication.key }}
{% endif %}

{% if intf.ospf_authentication is defined and
     intf.ospf_authentication.type | default('none') == 'md5' %}
 ip ospf authentication message-digest
 ip ospf message-digest-key {{ intf.ospf_authentication.key_id }} md5 {{ intf.ospf_authentication.key }}
{% endif %}
```

Interfaces where `type` is `none` render no authentication commands at all. Plain-text
and MD5 each render their distinct IOS command sets. Area-level authentication is
handled separately inside the `router ospf` block:

```jinja
{% for auth in ospf.area_authentication | default([]) %}
{% if auth.type == 'plaintext' %} area {{ auth.area }} authentication
{% elif auth.type == 'message-digest' %} area {{ auth.area }} authentication message-digest
{% endif %}
{% endfor %}
```

---

**`encapsulation ppp` renders before `ip address`.**

IOS requires `encapsulation ppp` on a serial interface before you can assign an IP
address. The template respects that dependency:

```jinja
{% if intf.encapsulation and intf.encapsulation != "" %} encapsulation {{ intf.encapsulation }}
{% endif %}
{% if intf.ip and intf.ip != "" and '/' in intf.ip %} ip address ...
{% endif %}
```

If `encapsulation` is empty, that line simply doesn't render. If it's `ppp`, it
appears before the IP address line — in the correct IOS configuration order.

---

### 4d — File 3: `configure_ospf_classic.py`

`[SCREEN: configure_ospf_classic.py]`

The configure script follows the same pattern as Module 2 for everything up to the
deployment step: path resolution, YAML load, credential injection, Jinja2
environment setup with the `cidr_to_netmask` filter registered, `--dry-run` and
`--router` flags.

What changes is how the configuration reaches the device.

---

**The NAPALM deployment sequence.**

```python
with driver(
    hostname=dns_name,
    username=username,
    password=password,
    optional_args=optional_args,
) as device:

    device.load_merge_candidate(config=config)

    diff = device.compare_config()
    if diff:
        print(diff)

    device.commit_config()
    device.cli(["write memory"])
```

`load_merge_candidate()` stages the rendered configuration as a candidate. Nothing
has been applied to the router yet. `compare_config()` produces a diff between the
candidate and the running configuration — this is what you see on screen before the
commit. If there's no diff, NAPALM reports that too — it means the configuration is
already present on the device. `commit_config()` applies the candidate, and `cli(["write memory"])`
saves it to NVRAM.

The merge candidate model is additive — it layers the new configuration on top of
what's already there rather than replacing it. For this lab that's the correct
behavior: we're building OSPF on top of base interface configuration that already
exists on the routers.

---

**The IOL optional_args block.**

```python
optional_args = {
    "ssh_config_file":  None,
    "session_log":      session_log_path,
    "dest_file_system": "nvram:",
    "inline_transfer":  True,
}
```

As described in the tool overview: `dest_file_system: "nvram:"` redirects NAPALM's
pre-flight disk check to the one IOL filesystem that reports free space. `inline_transfer:
True` sends the configuration over SSH instead of SCP. Both are IOL-specific — not
needed in production.

---

**Running the script.**

```bash
# 1. Dry-run — render and review configs before pushing
python scripts/configure_ospf_classic.py --dry-run

# 2. Deploy configuration to all routers
python scripts/configure_ospf_classic.py

# 3. Verify OSPF state
python scripts/verify_ospf_classic.py

# 4. Troubleshoot if needed
python scripts/troubleshoot_ospf_classic.py
```

The `--dry-run` step is not optional. With eleven routers and multiple authentication
types, reviewing the rendered configs before a live push is the right discipline.
Open the `.cfg` files in `configs/` and confirm each device's authentication commands,
network statements, and area assignments are exactly what you intended.

---

## SECTION 5 — Verification

`[SCREEN: verify_ospf_classic.py]`

The verification script uses NAPALM's `cli()` method for all show commands. That
method takes a list of command strings and returns a dictionary keyed by command —
clean, no prompt management, no buffer concerns.

Four checks are available: `neighbors`, `interfaces`, `routes`, and `lsdb`. At the
end of every run a summary table prints the worst-case result per device per check —
FAIL beats WARN beats PASS — with a totals row across the bottom.

---

**`check_neighbors`**

Parses `show ip ospf neighbor` line by line, groups neighbor states by interface,
and applies per-interface logic:

- PASS if at least one neighbor is FULL on that interface — covers FULL/DR,
  FULL/BDR, FULL/DROTHER, and FULL/- on point-to-point links
- PASS if all neighbors are 2WAY/DROTHER — this is correct and expected behavior
  between two DROthers on a broadcast segment
- WARN if neighbors are present but none are FULL
- FAIL if no neighbors exist on the interface

The `FULL/  -` state that IOS shows on point-to-point serial links — with embedded
spaces in the role field — is normalized before parsing by collapsing it to `FULL/-`.
Without that normalization, the regex would fail to parse the state correctly.

The 2WAY/DROTHER handling is worth explaining because it trips up students. On the
`192.1.100.0/24` segment, R1 is a DROTHER and R11 is also a DROTHER. DROthers only
form FULL adjacencies with the DR and BDR. Between two DROthers, 2WAY is the correct
and final state — no further adjacency is needed and no further adjacency will form.
The script knows this and reports it as PASS, not FAIL.

---

**`check_interfaces`**

Runs `show ip ospf interface` — the full version, not brief — and parses it into
per-interface blocks. For each active interface it validates:

- Area: live area matches the YAML network statement area — FAIL on mismatch
- Network type: live type matches YAML `ospf_network_type` — FAIL on mismatch.
  IOS uses `POINT_TO_POINT` with an underscore; YAML uses `point-to-point` with
  a hyphen. Both sides are normalized to uppercase underscored form before comparison.
- Priority: validated only when `ospf_priority` is explicitly set in YAML — WARN
  on mismatch
- DR/BDR role: identified by Router ID cross-referenced from the neighbor table.
  Point-to-point interfaces report `P2P (no DR election)`.

---

**`check_routes`**

Two steps. First, the OSPF route table is fetched, parsed, and formatted as a
structured table:

```
  Type   Destination        Via              Interface       Cost   Age
  ───────────────────────────────────────────────────────────────────
  Intra  2.0.0.0/8          192.1.100.2      Ethernet0/0     11     01:14
  Inter  8.0.0.0/8          192.1.100.3      Ethernet0/0     41     00:59
```

Inter-area routes are highlighted in cyan. ECMP paths appear as additional rows
under the same destination.

Second, each YAML network statement is validated against live interface state using
wildcard-aware IP math — the same approach as Module 2 — and reports PASS, WARN, or
FAIL per network based on whether the owning interface is up/up.

---

**`check_lsdb`**

Runs `show ip ospf database` and displays the raw output. Informational only. The
script confirms the Router LSA for this router's ID is present in the database, and
checks for Summary Net LSAs on routers with `area_range` configured. On R8, you'll
see both the Area 0 and Area 10 LSDB sections, and the Summary Net LSAs carrying the
`192.1.100.0/22` aggregate into Area 10.

---

## SECTION 6 — Troubleshooting

`[SCREEN: troubleshoot_ospf_classic.py]`

Same two-mode architecture as Module 2's troubleshoot script: live troubleshooting
mode and failure demonstration mode. The live checks are OSPF-specific and the failure
scenarios are OSPF-specific, but the structure is identical.

**Live checks:** `neighbors`, `authentication`, `database`, `routes`, `process`.

**Failure demonstration scenarios:** `missing-network`, `wrong-router-id`,
`auth-mismatch`, `wrong-area`, `missing-auth-key`.

At the end of every live troubleshooting run, the same summary table as the verify
script prints the worst-case result per device per check.

---

**`check_neighbors`**

Runs `show ip ospf neighbor detail`. Scans for neighbors stuck in EXSTART, EXCHANGE,
INIT, or LOADING state — these indicate MTU mismatch, authentication failure, or
area mismatch. Reports PASS if any FULL adjacency is confirmed, FAIL if none exist.

---

**`check_authentication`**

This check is more sophisticated than the Module 2 equivalent, because this topology
has mixed authentication types on the same routers.

The check runs `show ip ospf interface` and parses it into per-interface text blocks.
For each authentication-configured interface, it searches within that interface's
own block — not the full output — for the auth confirmation string. This is critical
on R2, which has plain-text on Ethernet0/0 and MD5 on Serial2/0. A global search
would find one auth type and incorrectly validate the other.

For MD5, IOS uses two different strings depending on interface type:
- Ethernet: `Message digest authentication enabled`
- Serial: `Cryptographic authentication enabled`

Both are recognized as valid MD5 confirmation strings.

For the specific case of MD5 configured but no key defined, IOS outputs:
```
  Cryptographic authentication enabled
      No key configured, using default key id 0
```

The string `Youngest key id is 1` is the indicator of a valid key. If that string is
absent, the check reports WARN: `MD5 authentication enabled but no key configured
(missing ip ospf message-digest-key)`. This is a real failure mode — the router will
send hellos with authentication enabled but no valid key, which the neighbor
immediately rejects.

---

**`check_database`**

Runs `show ip ospf database`. Confirms the Router LSA for this device's router ID is
present in the LSDB. On R8, checks for Summary Net LSAs to confirm inter-area
summarization is active. If the Router Link States section is absent entirely, it
reports FAIL — the LSDB may be empty, indicating the OSPF process is not running or
not exchanging LSAs.

---

**`check_routes`**

Runs `show ip route ospf` and `show ip ospf border-routers`. On Area 10 routers
(R9, R10), validates that inter-area routes (`O IA`) are present — their absence
indicates a problem with R8's ABR function or the area range configuration. Border
router entries in `show ip ospf border-routers` confirm ABR reachability.

---

**`check_process`**

Runs `show ip protocols` and validates the OSPF process ID and router ID against the
YAML. If the process isn't running, or the router ID doesn't match, this is the
check that surfaces it.

---

**Failure demonstration scenarios.**

The five injectors work the same way as Module 2 — deep copy, targeted mutation,
original data untouched. `inject_missing_network` removes the first non-loopback
network statement. `inject_wrong_router_id` changes the router ID to `0.0.0.99`.
`inject_auth_mismatch` appends `_WRONG` to the key on the first authenticated
interface. `inject_wrong_area` moves the first non-loopback network to area 99.
`inject_missing_auth_key` enables auth type but clears the key value.

Each demo renders both configs, diffs them, and walks through the CLI symptoms and
the fix — no router is touched.

---

## SECTION 7 — Closing Demonstration: Configuration Drift

`[SCREEN: terminal — scripts/ and utils/ directories]`

Before we wrap Module 3, the same closing demonstration we ran in Module 2 — inject
a configuration drift, show that the troubleshooter passes and the verifier catches
it, restore from the source of truth.

The point is the same but the tools are different. In Module 2, the troubleshooter
answered "is EIGRP working?" and said yes while the verifier found a stray network
statement. Here, the troubleshooter answers "is OSPF working?" — it checks adjacency
state, the LSDB, the route table. The verifier checks whether the device matches
the YAML. Both questions matter.

---

### Part 1 — Inject the Drift

```bash
python utils/push_config.py --router R1 --cmd "router ospf 1" "no network 1.0.0.0 0.255.255.255 area 0"
```

R1's loopback network statement is now removed. R1's loopback `1.1.1.1/8` is no
longer being advertised into OSPF. The router remains fully functional — all
adjacencies are up, the rest of the routing table is intact.

---

### Part 2 — Troubleshooter Shows a Healthy Router

```bash
python scripts/troubleshoot_ospf_classic.py --router R1
```

All five checks pass. Neighbors FULL, database populated with R1's Router LSA,
routes present and correct from R1's perspective, process running with the correct
router ID.

> **Instructor talking point:** R1 is passing every operational check. From a
> protocol standpoint, OSPF is working perfectly on this router. The troubleshooter
> is answering its question correctly — "is OSPF working?" — and the answer is yes.
>
> Now ask: did the troubleshooter tell us whether R1 is advertising everything it
> should be? It did not. That is not its job.

---

### Part 3 — Verifier Reveals the Drift

```bash
python scripts/verify_ospf_classic.py --router R1 --check routes
```

The network statement validation section reports:

```
  [FAIL] Network 1.0.0.0 0.255.255.255 area 0 — no interface found
         with a matching IP on R1
```

> **Instructor talking point:** The YAML says R1 should be advertising `1.0.0.0/8`
> into OSPF area 0. The live router is not. That discrepancy is configuration drift —
> the router no longer matches its source of truth.
>
> The troubleshooter passed. The verifier failed. Both answers are correct. They are
> answering different questions.
>
> In production, you need both. The troubleshooter tells you whether the protocol is
> functional right now. The verifier tells you whether the configuration matches what
> was intended. A router can be operationally healthy and still be wrong.

---

### Part 4 — Restore from Source of Truth

```bash
python scripts/configure_ospf_classic.py --router R1
python scripts/verify_ospf_classic.py --router R1
```

NAPALM loads the candidate, shows the diff — the missing network statement appears
as an addition — commits, saves. Verify confirms all checks clean.

---

### Part 5 — NAPALM in Context

This demonstration also highlights something specific to NAPALM's merge candidate
model. When we ran `configure_ospf_classic.py` to restore R1, NAPALM showed us
exactly what was going to be applied — one network statement — before committing.
That diff is the safety net. In Module 2, Netmiko pushed lines without that preview.
Here, you see the change before it lands.

That said, the merge model has a limit. It's additive. NAPALM merged the missing
network statement back in, but it did not remove anything that shouldn't be there.
If R1 had an extra network statement — something in the config that isn't in the YAML
— the merge would leave it in place. A replace candidate would remove it. That's the
next level of configuration management, and it's one of the things Ansible's
declarative model addresses in Modules 9 through 11.

| Module | Protocol   | Tool          | What It Adds                                  |
|--------|------------|---------------|-----------------------------------------------|
| 02     | EIGRP      | Netmiko       | Direct SSH, explicit command control           |
| 03–04  | OSPF       | NAPALM        | Candidate config, diff before commit, rollback |
| 05–07  | IPv6/IS-IS | Nornir        | Concurrent execution, inventory model          |
| 08–09  | BGP        | pyATS/Genie   | Structured parsing, stateful testing           |
| 10–12  | MPLS/VPN   | Ansible       | Declarative intent, idempotency at scale       |

---

## SECTION 8 — Objectives Review and Wrap-Up

`[SCREEN: README.md — Module Objectives section]`

Let's go back to the objectives we set at the start and confirm each one.

**OSPF Classic Mode configured across eleven routers.** Done. The configure script
deployed the full OSPF configuration from YAML and Jinja2 to all eleven devices —
process ID 1, router IDs, network statements with correct area assignments,
authentication, and summarization.

**NAPALM candidate configuration model demonstrated.** Done. Every deployment run
showed a diff before committing. The merge candidate, compare, commit sequence is
now established and will carry forward to Module 4.

**Mixed authentication methods implemented.** Done. Plain-text per-interface, MD5
per-interface, area-level plain-text, and area-level MD5 are all configured and
verified. The scripts handle every variant from the same YAML structure.

**DR/BDR priority manipulation configured.** Done. R2 has priority 10 on the
`192.1.100.0/24` segment. R4 and R6 compete at priority 10 on `192.1.103.0/24`.
R3 sits at priority 5 on the same segment. The expected election outcomes are
visible in `show ip ospf interface`.

**Point-to-point network type override demonstrated.** Done. The R7–R8 link uses
`ip ospf network point-to-point` on both ends. The verify script correctly identifies
P2P links and reports them as `P2P (no DR election)` rather than looking for a DR/BDR
that will never exist on that segment.

**Inter-area summarization configured and verified.** Done. R8's `area 0 range`
statement aggregates the Area 0 subnets into a single Type 3 LSA. Area 10 routers
see `192.1.100.0/22` as an inter-area route. The verify script's LSDB check confirms
the Summary Net LSAs are present.

**Verification script operational across all four checks.** Done. `verify_ospf_classic.py`
running neighbors, interfaces, routes, and lsdb cleanly across all eleven routers,
with the per-device summary table confirming PASS across the board.

**Troubleshooting script operational.** Done. `troubleshoot_ospf_classic.py` running
all five live checks, authentication check correctly detecting missing MD5 keys and
mixed auth types per-interface, and all five failure demonstration scenarios working.

The full lab reset procedure — including EVE-NG node wipe and RSA key generation —
is documented in `eve-ng_lab_reset_sop.md`. The lab does not need to be in a clean
state to proceed to Module 4.

Module 4 continues with OSPF using NAPALM — multi-area OSPF, redistribution, area
types, and virtual links. The tool stays the same; the topology and the protocol
complexity go up. See you there.

---

*End of Module 03 Verbal Script*
*NAMS26 — Network Automation Management Station 2026*
