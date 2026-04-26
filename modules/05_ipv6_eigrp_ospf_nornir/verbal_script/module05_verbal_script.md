# Module 05 — IPv6 EIGRP / OSPFv3 / Nornir
## Verbal Script — `module05_verbal_script.md`
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

Welcome to Module 5. Two things change from everything we've done so far. First, the
protocol stack — we move from IPv4 OSPF to a pure-IPv6 topology: EIGRPv6 and OSPFv3.
Second, the automation tool changes. We leave NAPALM and move to Nornir.

Those are two shifts at the same time, so let's be clear about where the weight is.
The IPv6 protocols are the networking content — EIGRPv6, OSPFv3, redistribution
between two EIGRP domains and a multi-area OSPF domain, stub areas, NSSA. If you've
worked through Module 4, the routing concepts are familiar. The IPv6-specific mechanics
— interface-level process assignment, explicit router IDs on IPv6-only routers — are
the new protocol layer.

Nornir is the automation content, and that's where we spend most of our time today.

By the time we're done here you'll have configured IPv6 EIGRP and OSPFv3 across a
nine-router topology using a Python script that deploys to all nine devices
simultaneously. You'll verify adjacency state, routing table entries, and
redistribution in parallel. You'll troubleshoot a redistribution failure using targeted
automation, and you'll restore the correct configuration from the YAML source of truth
in a single command.

You'll also have a clear picture of what Nornir adds over NAPALM and Netmiko, and
specifically why parallel execution matters for real-world automation at scale — and
where Nornir's own boundaries are.

The three-file pattern from Module 2 continues: YAML provides the data, Jinja2 renders
the configuration, Python deploys it. The delivery mechanism is what changes. That
difference will be concrete by the end of this section.

---

## SECTION 2 — Lab Topology

`[SCREEN: diagrams/module05_topology_ipv6_eigrp_ospf.drawio.svg]`

Nine routers. Two EIGRPv6 domains anchoring a three-area OSPFv3 core.

**Area 0 — the backbone.** R1, R2, and R3 share a single Ethernet LAN segment on
`FC00:192:168:123::/64`. These three routers form the OSPFv3 backbone. R1 is the left
ASBR — it redistributes bidirectionally between OSPFv3 and EIGRPv6 AS 100. R3 is the
right ASBR and also an ABR for Area 20.

**Area 10 — Totally Stubby.** R2 is the ABR. R2 connects to R5 via a serial link on
`FC00:192:168:25::/64`. R5 connects to R9 on `FC00:192:168:59::/64`. Area 10 is
configured as totally stubby — `area 10 stub no-summary` on R2. R5 and R9 receive
only a default route from R2. No external LSAs and no inter-area LSAs enter this area.
All traffic leaving Area 10 uses the single default route toward R2.

**Area 20 — NSSA.** R3 and R4 are the ABRs. R3 connects to R4 on
`FC00:192:168:34::/64`. R4 connects to R6 on `FC00:192:168:46::/64`. R6 is the right
ASBR — it redistributes bidirectionally between OSPFv3 and EIGRPv6 AS 111. Area 20 is
NSSA with `no-summary` on R3 — R6's redistributed routes enter as Type 7 LSAs, which
R3 translates to Type 5 for Area 0.

**EIGRPv6 AS 100.** R1 and R7. R7 connects to R1 on `FC00:192:168:17::/64`. R7 is
EIGRP-only — it has no OSPF process. R1 redistributes between EIGRP 100 and OSPFv3
in both directions.

**EIGRPv6 AS 111.** R6 and R8. R8 connects to R6 on `FC00:192:168:68::/64`. R8 is
EIGRP-only. R6 redistributes between EIGRP 111 and OSPFv3 in both directions.

One IPv6-specific detail worth calling out before we get into the scripts: routers that
have no IPv4 addresses — R7, R8, and R9 in this topology — cannot derive an OSPF or
EIGRP router ID automatically. IOS derives the router ID from the highest IPv4 address
on a loopback or physical interface. If there are no IPv4 addresses at all, there's
nothing to derive from, and the routing process won't start cleanly.

The YAML assigns an explicit `router-id` to every router as a result. Even routers
that do have IPv4 loopbacks get an explicit router ID so the topology is deterministic
regardless of interface state at boot time. The template renders this unconditionally
— it's not a conditional field in the YAML. Every router gets an explicit `eigrp
router-id` or OSPF `router-id` statement.

---

## SECTION 3 — Tool Overview: Nornir

`[SCREEN: README.md — Tool Overview section]`

Nornir is a Python automation framework. It is not a library you call to connect to
a router. It is an orchestration layer that sits above the connection libraries you
already know — Netmiko, NAPALM — and runs tasks against your inventory in parallel.

### What Nornir Actually Does

Nornir has three jobs.

**First: inventory management.** Nornir reads a structured inventory — in this module,
a `hosts.yaml` file written from the module YAML at runtime — and gives every task
access to each host's connection parameters and host data. The inventory abstraction
means your task code never hard-codes a hostname, IP address, or credential. It
operates generically against whatever the inventory provides.

**Second: parallel task dispatch.** This is Nornir's primary value. When you call
`nr.run()`, Nornir dispatches your task to every host in the inventory simultaneously
using a `ThreadPoolExecutor`. For this module, all nine routers receive configuration
in parallel. What would take nine times as long sequentially — waiting for each router
to finish before starting the next — runs in roughly the time of the slowest single
router.

At nine routers the difference is noticeable. At ninety routers it is the difference
between a ten-minute maintenance window and a ninety-minute one. That's the real
motivation for Nornir in production.

**Third: result aggregation.** Nornir collects every task's return value into an
`AggregatedResult` object and reports pass/fail per host. Failed hosts are immediately
visible without parsing log files. The `print_result()` function from `nornir_utils`
walks that result tree and prints each host's outcome with color coding.

### What Nornir Does Not Do

Nornir does not define how configuration is pushed. That is determined entirely by
the task plugin you use inside `nr.run()`.

This module uses `netmiko_send_config` as its task plugin. `netmiko_send_config` sends
commands via Netmiko's `send_config_set` — it enters `configure terminal` on the router
and issues each command in sequence. This is a **merge** operation. IOS adds or
modifies what it receives and leaves everything else untouched. The script has no
awareness of what is already on the router and sends no `no` commands.

If the task plugin were changed to use NAPALM's `replace_candidate` instead, the
behavior would be the opposite — the entire running configuration would be replaced
with what the template produces. Nornir itself is neutral on this question. The
merge-versus-replace behavior belongs entirely to the task plugin, not to Nornir.

The practical consequence: running `configure_ipv6_eigrp_ospf.py` a second time on a
router that has accumulated stale or manually added configuration will not clean it up.
The script pushes what the template produces and leaves everything else in place.

> **Instructor talking point:** Demonstrate this concretely. After running the
> configure script against R1, add a manual EIGRP process to R1 from the CLI:
>
> ```
> R1# conf t
> R1(config)# ipv6 router eigrp 999
> R1(config-rtr)# eigrp router-id 9.9.9.9
> R1(config-rtr)# end
> R1# write memory
> ```
>
> Now run the configure script again:
>
> ```bash
> python scripts/configure_ipv6_eigrp_ospf.py --router R1
> ```
>
> Then check R1:
>
> ```
> R1# show ipv6 protocols
> ```
>
> EIGRP 999 is still there. The script configured exactly what the YAML says — AS 100
> with its interfaces and redistribution. AS 999 was not in the YAML, so the script
> did not touch it. The router's running configuration is now the YAML content plus
> the manually added process.
>
> This is the most important behavioral distinction between a merge-based tool and a
> replace-based one. The configure script assumes a clean baseline; it does not create
> one. The closing demo will show exactly when this matters.

### The Three-File Workflow Continues

`[SCREEN: module directory tree — data/, templates/, scripts/]`

The workflow is identical to Modules 2 through 4:

```
ipv6_eigrp_ospf.yaml  →  ipv6_eigrp_ospf.j2  →  configure_ipv6_eigrp_ospf.py  →  Routers
      (variables)             (template)            (Nornir / Netmiko parallel push)
```

The data model and the template are unchanged in concept from every prior module. The
delivery mechanism is what changes — instead of a sequential loop calling Netmiko or
NAPALM per device, Nornir dispatches all nine simultaneously.

---

## SECTION 4 — Configuration

### 4a — The Three-File Workflow

`[SCREEN: module directory tree — data/, templates/, scripts/]`

Before looking at any individual file, let's orient to the workflow. YAML provides the
data, Jinja2 renders the configuration from that data, and the Python script ties
everything together. The difference in this module is the last step: instead of a for
loop over devices, the Python script hands the work off to Nornir, which dispatches
all nine devices at once.

```
ipv6_eigrp_ospf.yaml  →  ipv6_eigrp_ospf.j2  →  configure_ipv6_eigrp_ospf.py  →  Routers
      (variables)             (template)            (Nornir / Netmiko parallel push)
```

When you need to change an IP address, a router ID, or a redistribution metric — you
only touch the YAML. The template and the script don't change. That separation is
what makes this pattern scale.

---

### 4b — File 1: `ipv6_eigrp_ospf.yaml`

`[SCREEN: data/ipv6_eigrp_ospf.yaml]`

The YAML file is the single source of truth. Everything the script needs to know
about the lab lives here — hostnames, IP addresses, interface parameters, OSPF area
assignments, EIGRP process numbers, redistribution metrics, and credentials.

Five things worth calling your attention to specifically.

---

**Credentials are defined once.**

At the very top of the file you'll see the `default_credentials` block with a YAML
anchor — the `&creds` tag. Every device references that anchor with `*creds`.

```yaml
default_credentials: &creds
  username: netadmin
  password: admin

devices:
  R1:
    hostname: R1
    dns_name: r1.lab
    oob_ip: 192.168.1.101/24
    oob_interface: Ethernet1/3
    credentials: *creds
```

When `yaml.safe_load()` reads this file, it resolves the anchor transparently. By
the time the data reaches the script, every device dictionary has its credentials
fully populated. You define the username and password exactly once.

---

**`dns_name` is the SSH target — not `oob_ip`.**

Every script in this module connects to devices using the `dns_name` field. That
name is resolved through the lab DNS server at `192.168.1.12`. The `oob_ip` is kept
in the file for documentation purposes only.

```yaml
    hostname: R1
    dns_name: r1.lab          # ← SSH target — resolved by lab DNS at 192.168.1.12
    oob_ip: 192.168.1.101/24  # ← Reference only — no script uses this as a target
```

---

**Every router has an explicit router ID.**

This is the IPv6-specific requirement mentioned during the topology walkthrough. For
routers with no IPv4 addresses — R7, R8, and R9 — IOS cannot automatically derive an
OSPF or EIGRP router ID. The template renders `eigrp router-id` and OSPF `router-id`
unconditionally from the YAML. Here's how R7's EIGRP block looks in the YAML:

```yaml
    eigrp:
      as_number: 100
      router_id: 7.7.7.7
      redistribute_ospf: null
```

And here's R9's OSPF block — R9 is Area 10 and has no EIGRP:

```yaml
    ospf:
      process_id: 1
      router_id: 9.9.9.9
      area_types: []
      redistribute_eigrp: null
```

Even R1, which has a `1.1.1.1/32` IPv4 loopback, gets an explicit `router-id: 1.1.1.1`
in both its EIGRP and OSPF blocks. Explicit router IDs everywhere make the topology
deterministic regardless of which interfaces are up when routing processes initialize.

---

**Area assignment is per-interface — there are no OSPF network statements.**

This is the fundamental difference between OSPFv3 on IOS and OSPFv2. In OSPFv2 you
use `network` statements under `router ospf` to map interfaces into areas. In OSPFv3
the area assignment happens on the interface itself with `ipv6 ospf <pid> area <area>`.

Look at R1's interface definitions in the YAML:

```yaml
      Ethernet0/0:
        description: "R1/R2/R3 LAN - OSPF Area 0"
        ipv6_address: FC00:192:168:123::1/64
        ospf_area: 0
        ospf_network_type: ""
        eigrp_as: ""
      Loopback0:
        description: "Router ID / OSPF Loopback"
        ipv4_address: 1.1.1.1/32
        ipv6_address: FC00:10:1:1::1/64
        ospf_area: 0
        ospf_network_type: point-to-point
        eigrp_as: ""
      Ethernet0/1:
        description: "R1 to R7 - EIGRPv6 100"
        ipv6_address: FC00:192:168:17::1/64
        ospf_area: ""
        eigrp_as: 100
```

`ospf_area` and `eigrp_as` are per-interface fields. The template uses these fields
to render the `ipv6 ospf 1 area 0` or `ipv6 eigrp 100` command directly under each
interface. An interface that participates in neither protocol has both fields empty,
and the template renders neither command.

There's one subtle point about `ospf_area: 0`. The value zero is falsy in Python and
in Jinja2. If the template guarded with `{% if intf.ospf_area %}`, Area 0 would
silently be skipped — and R1's backbone interfaces would never join the OSPFv3 process.
The template guards with `is not none and != ""` instead:

```jinja
{% if device.ospf and intf.ospf_area is not none and intf.ospf_area != "" %}
 ipv6 ospf {{ device.ospf.process_id }} area {{ intf.ospf_area }}
{% endif %}
```

That guard passes for `ospf_area: 0`, passes for `ospf_area: 10`, and skips when the
field is an empty string or absent. This is the kind of subtle bug that will not show
up in a dry-run — it only becomes visible when you check the live router and find the
Area 0 neighbor adjacency that never formed.

---

**Area types are declared at the process level — per router.**

Stub and NSSA area configuration goes on the ABR, not on every router in the area.
The YAML captures this in an `area_types` list under each device's `ospf` block.

Here's R2's OSPF block — R2 is the ABR for Area 10:

```yaml
    ospf:
      process_id: 1
      router_id: 2.2.2.2
      area_types:
        - area: 10
          type: stub
          no_summary: true
      redistribute_eigrp: null
```

And R3, the ABR for Area 20:

```yaml
    ospf:
      process_id: 1
      router_id: 3.3.3.3
      area_types:
        - area: 20
          type: nssa
          no_summary: true
      redistribute_eigrp: null
```

R5 and R9, which are inside Area 10, have `area_types: []` — they're stub members,
not ABRs, and the stub configuration only goes on the ABR. R6, inside Area 20, has
`area_types: []` for the same reason.

---

### 4c — File 2: `ipv6_eigrp_ospf.j2`

`[SCREEN: templates/ipv6_eigrp_ospf.j2]`

The Jinja2 template takes the YAML data and renders a complete IOS configuration for
each device. The Python script passes the entire device dictionary in as `device`, so
every key in the YAML becomes directly accessible in the template.

Four things worth calling out here.

---

**The OOB interface is excluded in the interface loop.**

The interface loop iterates over every interface in the device dictionary, and the
very first thing it checks is whether the current interface is the OOB management
interface. If it matches `device.oob_interface`, the entire block is skipped.

```jinja
{% for intf_name, intf in device.interfaces.items() %}
{% if intf_name != device.oob_interface %}
interface {{ intf_name }}
{% if intf.description and intf.description != "" %} description {{ intf.description }}
{% endif %}
{% if intf.ipv4_address and intf.ipv4_address != "" %} ip address {{ intf.ipv4_address | ipv4_addr }} {{ intf.ipv4_address | ipv4_mask }}
{% else %} no ip address
{% endif %}
{% if intf.ipv6_link_local and intf.ipv6_link_local != "" %} ipv6 address {{ intf.ipv6_link_local }} link-local
{% endif %}
{% if intf.ipv6_address and intf.ipv6_address != "" %} ipv6 address {{ intf.ipv6_address }}
{% endif %}
...
{% if intf.shutdown %} shutdown
{% else %} no shutdown
{% endif %}
!
{% endif %}
{% endfor %}
```

The `Ethernet1/3` OOB interface is in the YAML as reference data — the template
skips it explicitly. Every other interface goes through the full rendering block.

---

**OSPF and EIGRP are assigned per-interface within the loop.**

Inside the interface block, the template renders the routing protocol assignment if
the corresponding field is populated:

```jinja
{% if device.ospf and intf.ospf_area is not none and intf.ospf_area != "" %}
 ipv6 ospf {{ device.ospf.process_id }} area {{ intf.ospf_area }}
{% endif %}
{% if intf.ospf_network_type and intf.ospf_network_type != "" %}
 ipv6 ospf network {{ intf.ospf_network_type }}
{% endif %}
{% if device.eigrp and intf.eigrp_as is not none and intf.eigrp_as != "" %}
 ipv6 eigrp {{ intf.eigrp_as }}
{% endif %}
```

The `ospf_network_type` field renders `ipv6 ospf network point-to-point` for loopback
interfaces — without it, IOS treats loopbacks as host routes with a /128 mask in the
OSPF database, which prevents summarization and causes subtle prefix visibility issues.
Loopbacks in this lab all have `ospf_network_type: point-to-point` in the YAML.

---

**The EIGRPv6 process block renders after the interfaces.**

```jinja
{% if device.eigrp %}
! =========================================
! EIGRPv6 Process
! =========================================
ipv6 router eigrp {{ device.eigrp.as_number }}
 eigrp router-id {{ device.eigrp.router_id }}
{% if device.eigrp.redistribute_ospf %}
 redistribute ospf {{ device.eigrp.redistribute_ospf.process }} metric {{ device.eigrp.redistribute_ospf.metric }}
{% endif %}
!
{% endif %}
```

For R7 and R8, `redistribute_ospf` is null and the redistribution line is skipped.
For R1, it renders with the metric seed values from the YAML:
`redistribute ospf 1 metric 10000 100 255 1 1500`. For routers with no EIGRP block at
all — R2, R3, R4, R5, R9 — the entire section is skipped.

---

**The OSPFv3 process block handles area types with a loop.**

```jinja
{% if device.ospf %}
! =========================================
! OSPFv3 Process
! =========================================
ipv6 router ospf {{ device.ospf.process_id }}
{% if device.ospf.router_id and device.ospf.router_id != "" %}
 router-id {{ device.ospf.router_id }}
{% endif %}
{% for area_type in device.ospf.area_types | default([]) %}
{% if area_type.type == 'stub' and area_type.no_summary %}
 area {{ area_type.area }} stub no-summary
{% elif area_type.type == 'stub' %}
 area {{ area_type.area }} stub
{% elif area_type.type == 'nssa' and area_type.no_summary %}
 area {{ area_type.area }} nssa no-summary
{% elif area_type.type == 'nssa' %}
 area {{ area_type.area }} nssa
{% endif %}
{% endfor %}
{% if device.ospf.redistribute_eigrp %}
 redistribute eigrp {{ device.ospf.redistribute_eigrp.as_number }}
{% endif %}
!
{% endif %}
```

R2 renders `area 10 stub no-summary`. R3 renders `area 20 nssa no-summary`. All other
routers have `area_types: []` and the loop produces nothing. The template handles zero,
one, or multiple area type declarations with the same loop — if a future module adds an
ABR that touches three areas, the YAML grows and the template doesn't change.

---

### 4d — File 3: `configure_ipv6_eigrp_ospf.py`

`[SCREEN: configure_ipv6_eigrp_ospf.py]`

Now let's look at the Python script that drives the whole thing. The YAML loading,
credential injection, and argument parsing should look familiar — those patterns are
identical to every prior module. What's new is everything from the Nornir inventory
construction through the `nr.run()` call.

---

**Argument parsing — same flags, same behavior.**

```python
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Render configs to configs/ without connecting to routers.",
)
parser.add_argument(
    "--router",
    nargs="*",
    metavar="HOSTNAME",
    help="Target one or more routers (e.g. --router R1 R6). Accepts R1, r1, r1.lab.",
)
```

`--dry-run` renders and saves configs to the `configs/` directory and returns
immediately — no SSH, no Nornir inventory construction, no `nr.run()`. `--router`
limits the target set, and the resolution logic accepts `R1`, `r1`, `r1.lab`, or
`R1.lab` interchangeably. Same flags, same behavior, different backend.

---

**Path resolution — the same four-level chain.**

```python
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)
LOG_DIR      = os.path.join(MODULE_DIR, "logs")
```

All paths resolve from `__file__` — the script runs correctly regardless of which
directory it's called from. Logs go to `modules/05_ipv6_eigrp_ospf_nornir/logs/`,
not to the project root.

---

**Building the Nornir inventory on the fly.**

Nornir's SimpleInventory plugin reads from three YAML files on disk: `hosts.yaml`,
`groups.yaml`, and `defaults.yaml`. This module generates those files at runtime from
the module's own `ipv6_eigrp_ospf.yaml`, writes them to a temporary directory, and
deletes them when the run completes.

```python
tmp_dir = tempfile.mkdtemp(prefix="nornir_m05_")
try:
    hosts_file, groups_file, defaults_file = _write_nornir_inventory(
        target_devices, tmp_dir
    )
    # ... run Nornir ...
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)
```

The `finally` block runs whether the Nornir run succeeds or fails. The temporary
inventory directory is always cleaned up — it never accumulates between runs.

Inside `_write_nornir_inventory()`, each device becomes a Nornir host entry:

```python
hosts[name] = {
    "hostname": dev["dns_name"],
    "platform": "cisco_ios",
    "username": creds.get("username", ""),
    "password": creds.get("password", ""),
    "data": dev,
}
```

The `data` key passes the complete device dictionary into Nornir's host data store.
Inside any task, `task.host.data` gives you the full YAML device block — interfaces,
routing parameters, credentials — everything. The task code is generic; it accesses
`task.host.data` and never references a specific device name.

---

**Initializing Nornir.**

```python
nr = InitNornir(
    inventory={
        "plugin": "SimpleInventory",
        "options": {
            "host_file": hosts_file,
            "group_file": groups_file,
            "defaults_file": defaults_file,
        },
    },
    logging={"enabled": False},
)
```

`InitNornir` builds the Nornir runner from the three inventory files. SimpleInventory
is Nornir's built-in file-based plugin — no database, no external service, just YAML
files on disk. `logging={"enabled": False}` suppresses Nornir's default `nornir.log`
output to the working directory. Session output is already printed to the terminal by
`print_result()` — the extra log file adds nothing here.

---

**Dispatching tasks in parallel.**

```python
result = nr.run(
    task=configure_task,
    template_env=template_env,
    config_dir=CONFIG_DIR,
    dry_run=args.dry_run,
)
```

`nr.run()` dispatches `configure_task` to every host in the inventory simultaneously.
Nornir uses a `ThreadPoolExecutor` internally — the default `num_workers` is 100,
which is effectively one thread per host for a nine-router lab. Extra keyword
arguments (`template_env`, `config_dir`, `dry_run`) are forwarded to `configure_task`
as `**kwargs` on every thread. Each host gets the same shared objects. The returned
`AggregatedResult` maps host names to `MultiResult` objects.

---

**Inside `configure_task()` — what each thread actually does.**

```python
def configure_task(task: Task, template_env: Environment, config_dir: str, dry_run: bool) -> Result:
    dev = dict(task.host.data)
    template = template_env.get_template(TEMPLATE_FILE)
    rendered = template.render(device=dev)

    config_path = os.path.join(config_dir, f"{task.host.name}_ipv6_eigrp_ospf.cfg")
    with open(config_path, "w") as fh:
        fh.write(rendered)

    if dry_run:
        return Result(host=task.host, result=f"[DRY-RUN] Config written to {config_path}", changed=True)

    commands = [
        line.rstrip()
        for line in rendered.splitlines()
        if line.strip() and not line.strip().startswith("!")
    ]

    task.run(task=netmiko_send_config, config_commands=commands)
    task.run(task=netmiko_send_command, command_string="write memory")

    return Result(host=task.host, result=f"Configured {task.host.name}", changed=True)
```

Each thread renders the Jinja2 template for its specific host and writes the rendered
config to `configs/`. If it's a dry-run, it returns immediately. In live mode, it
strips blank lines and IOS comment lines (lines starting with `!`), then calls
`netmiko_send_config` with the resulting command list. That's the merge push —
`configure terminal`, send each line, exit. Then `write memory` to save.

`task.run()` is called twice inside `configure_task` — once for the config push and
once for `write memory`. Nornir records both as subtasks under the host's
`MultiResult`, and `print_result()` shows both.

---

**Reading the output.**

```python
print_result(result)
```

`print_result()` from `nornir_utils` walks the `AggregatedResult` tree and prints
each host's outcome. Because `configure_task` sets `changed=True` on both return
paths, `print_result()` always prints the result text — not just when something
failed. A clean nine-router run shows nine hosts, each with two subtask entries,
all green.

If any host fails, `failed_hosts` is non-empty and the script exits with a non-zero
status code:

```python
failed_hosts = [h for h, r in result.items() if r.failed]
if failed_hosts:
    failed(f"Failed hosts: {', '.join(failed_hosts)}")
    sys.exit(1)
```

---

**Running the script.**

With all three files understood, the deployment sequence is the same as every prior
module:

```bash
# 1. Dry-run — render and review all nine configs before pushing
python scripts/configure_ipv6_eigrp_ospf.py --dry-run

# 2. Deploy to all nine routers in parallel
python scripts/configure_ipv6_eigrp_ospf.py

# 3. Deploy to a single router if needed
python scripts/configure_ipv6_eigrp_ospf.py --router R1

# 4. Verify state
python scripts/verify_ipv6_eigrp_ospf.py

# 5. Troubleshoot if needed
python scripts/troubleshoot_ipv6_eigrp_ospf.py
```

Step 1 is not optional. Before pushing config to nine routers, open the rendered
`.cfg` files in `configs/` and confirm each device's output is correct. With nine
files to check, a review-before-push discipline prevents a template bug from hitting
the entire lab simultaneously.

---

## SECTION 5 — Verification

`[SCREEN: scripts/verify_ipv6_eigrp_ospf.py]`

The verification script follows the same structural pattern as the configure script —
path resolution, YAML load, Nornir inventory construction, parallel dispatch. What's
different is what each task does once connected.

Four check categories are available, selectable via `--check`:

```bash
python scripts/verify_ipv6_eigrp_ospf.py --check neighbors routes redistribution areas
```

---

**`neighbors`** — runs `show ipv6 eigrp neighbors` on EIGRP routers and `show ipv6
ospf neighbor` on OSPF routers. For EIGRP routers, the check cross-references the
neighbor output against the expected adjacencies derivable from the YAML — each
router's EIGRP-participating interfaces tell you which neighbors should be present.
For OSPF routers, expected neighbors are derived from the shared subnet structure. A
neighbor table that's missing an expected adjacency gets a FAIL; all expected
neighbors present gets a PASS.

---

**`routes`** — runs `show ipv6 route` and cross-references expected prefixes against
the live routing table. The expected prefix set is derived from the YAML — every
interface address, every loopback, and every redistributed prefix should appear
somewhere in the network. Prefixes that are missing from the routing table on a router
that should be receiving them get a FAIL. This check catches the symptom of a
redistribution fault before it's visible to a user.

---

**`redistribution`** — focused check on the ASBRs: R1 and R6. Runs `show ipv6 route`
on OSPF routers and verifies that EIGRP-learned prefixes are visible, and on EIGRP
routers and verifies that OSPF prefixes are visible. A redistribution failure on R1
would cause all EIGRP AS 100 prefixes to disappear from the OSPF domain — this check
catches that specific failure mode.

---

**`areas`** — verifies that stub and NSSA area types are correctly applied on the ABRs.
Runs `show ipv6 ospf` on R2 and R3 and checks for the `Stub, no summary LSA` and
`NSSA, no summary LSA` flags in the output. If the area type command didn't render
correctly — for example, because of the `ospf_area: 0` guard issue in the template —
this check will catch it.

---

**Running a targeted check.**

During the closing demo you'll run the `redistribution` check specifically to surface
a fault that the troubleshooter missed. You can also run a single-router check during
initial deployment validation:

```bash
# Verify all checks on R1 only
python scripts/verify_ipv6_eigrp_ospf.py --router R1

# Verify redistribution across the full topology
python scripts/verify_ipv6_eigrp_ospf.py --check redistribution
```

All output is mirrored to a timestamped log file in
`modules/05_ipv6_eigrp_ospf_nornir/logs/` so every verification run is fully
auditable.

---

## SECTION 6 — Troubleshooting

`[SCREEN: scripts/troubleshoot_ipv6_eigrp_ospf.py]`

The troubleshooting script connects to routers, runs targeted diagnostic commands, and
reports findings with PASS, FAIL, and WARN annotations. Three check categories are
available:

```bash
python scripts/troubleshoot_ipv6_eigrp_ospf.py --check neighbors process routes
```

---

**`neighbors`** — runs `show ipv6 eigrp neighbors` and `show ipv6 ospf neighbor` and
reports adjacency state. This check answers the question: "Is this router's neighbor
table populated?" It catches adjacency-level failures — misconfigured interface
participation, neighbor drops, Hello timer mismatches. It does not catch
process-level failures where neighbors are up but redistribution is broken. That
distinction is the key teaching point in the closing demo.

---

**`process`** — runs `show ipv6 protocols` and validates the process configuration:
AS numbers, process IDs, redistribution statements. This check catches the class of
fault where the routing process is running but configured incorrectly — a missing
`redistribute` statement, a wrong metric, or a `no redistribute` command issued
manually that left the redistribution configuration intact on the interface but removed
the process-level statement. `show ipv6 protocols` exposes the redistribution
configuration in a way that `show ipv6 eigrp neighbors` does not.

---

**`routes`** — runs `show ipv6 route` and looks for missing or unexpected routing table
entries relative to what the topology should contain. The route check is the broadest
of the three — it looks at the symptom (missing routes) rather than the cause. Use it
to confirm whether a fault is route-loss, then use `neighbors` and `process` to
diagnose why.

---

**Usage in the closing demo.**

The troubleshoot script and the verify script answer fundamentally different questions.

The troubleshoot script asks: *Is the routing protocol working?*
The verify script asks: *Does this router match what the YAML says it should look like?*

Those questions are not the same, and a router can pass one while failing the other.
The closing demo shows exactly that scenario.

---

## SECTION 7 — Closing Demonstration: Redistribution Fault

`[SCREEN: terminal — scripts/ and utils/ directories]`

Before we close Module 5, there's one more demonstration that makes the most important
point of the module concrete. We're going to inject a redistribution fault, observe
what the troubleshooter can and cannot see, use the verifier to surface the symptom,
and restore the correct configuration from the YAML in a single command.

---

### Part 1 — Inject the Fault

We'll remove the EIGRP-to-OSPF redistribution statement from R1. This is a
process-level fault — the EIGRP neighbors on R1 stay up, the OSPF neighbors stay up,
but EIGRP-learned routes stop entering the OSPF domain.

```bash
python utils/push_config.py --router R1 \
  --cmd "ipv6 router eigrp 100" "no redistribute ospf 1 metric 10000 100 255 1 1500"
```

The redistribution configuration is now gone from R1. The EIGRP AS 100 domain — R1
and R7 — is isolated. Routes that R7 was advertising into EIGRP and that R1 was
previously redistributing into OSPFv3 have disappeared from the OSPF domain.

---

### Part 2 — Troubleshooting Misses It

```bash
python scripts/troubleshoot_ipv6_eigrp_ospf.py --router R1 --check neighbors
```

R1's EIGRP 100 neighbor — R7 — is still up. R1's OSPFv3 neighbors — R2 and R3 on
the Area 0 LAN — are still up. Every adjacency is intact.

```bash
python scripts/troubleshoot_ipv6_eigrp_ospf.py --router R1 --check process
```

> **Instructor talking point:** Walk through the `show ipv6 protocols` output. The
> EIGRP 100 process is running. The OSPFv3 process 1 is running. But look carefully
> at the redistribution section — `show ipv6 protocols` will show that
> `Redistributing: ospf 1` is no longer listed under the EIGRP 100 process block.
>
> The `process` check catches this. Ask the class to look at the output carefully
> and identify what changed. The absence of a line is the fault.
>
> Now ask: if we had only run `--check neighbors`, would we have found the fault?
> No. The neighbors are healthy. The fault is invisible to neighbor-level checking.

---

### Part 3 — Verifier Surfaces the Impact

Now let's see what the verifier catches that the troubleshooter already told us:

```bash
python scripts/verify_ipv6_eigrp_ospf.py --check redistribution
```

The `redistribution` check runs against the full topology. OSPF routers — R2, R3,
R4, R5, and R9 — are interrogated for the EIGRP-originated prefixes that should be
visible in their routing tables. Those prefixes are missing.

```
  [FAIL] R2  — EIGRP AS 100 prefix FC00:192:168:17::/64 not in routing table
  [FAIL] R3  — EIGRP AS 100 prefix FC00:192:168:17::/64 not in routing table
  [FAIL] R4  — EIGRP AS 100 prefix FC00:192:168:17::/64 not in routing table
  [FAIL] R5  — EIGRP AS 100 prefix FC00:192:168:17::/64 not in routing table
  [FAIL] R9  — EIGRP AS 100 prefix FC00:192:168:17::/64 not in routing table
```

> **Instructor talking point:** The troubleshooter told us the processes are running
> and the neighbors are up. The verifier told us that five routers can't reach the
> EIGRP domain that R1 is supposed to be redistributing.
>
> Both of those statements are true at the same time. Troubleshooting answers
> "is EIGRP working?" — and the answer is yes. The EIGRP process is running, the
> neighbors are up, the topology is converged. Verification answers "does this network
> match what the YAML says it should look like?" — and the answer is no.
>
> These are fundamentally different questions. In production you need both answers,
> and you need to know which tool gives you which one.

---

### Part 4 — Restore from Source of Truth

```bash
python scripts/configure_ipv6_eigrp_ospf.py --router R1
python scripts/verify_ipv6_eigrp_ospf.py --check redistribution
```

The configure script re-renders R1's config from the YAML and merges it back onto
the router. The `redistribute ospf 1 metric 10000 100 255 1 1500` statement reappears
under `ipv6 router eigrp 100`. The OSPF domain repopulates with EIGRP-originated
routes. All `redistribution` checks pass.

> **Instructor talking point:** Note that the configure script is still a merge — it
> did not remove anything from R1 that wasn't in the YAML, it only added what was
> missing. In this case, that was exactly the right behavior. The fault was a missing
> line, and the merge pushed it back.
>
> The case where merge fails you is when the fault is an extra line — an incorrect
> route-map applied to redistribution, a `metric-type` you didn't intend. That extra
> line survives a configure re-run. Catching and removing unwanted configuration
> requires either a replace-based tool (NAPALM replace_candidate) or an explicit
> negation in the template. Nornir with `netmiko_send_config` doesn't give you that
> automatically.

---

### Part 5 — The Bigger Conversation: Nornir in Context

This demonstration leads directly into a question worth sitting with. We saw Nornir
configure nine routers in parallel, verify redistribution state across the topology in
parallel, and restore a faulted router from source of truth in seconds. What does that
actually give us that NAPALM and Netmiko did not? And where are the edges?

**What Nornir adds.**

The most concrete thing Nornir adds is parallel execution. In Modules 2 through 4,
every script iterated over devices one at a time — connect, configure, disconnect,
repeat. In a lab with nine routers the difference between sequential and parallel
is maybe two minutes. In a production network with ninety routers, or nine hundred,
that gap becomes the difference between a maintenance window you can complete in a
scheduled downtime and one you cannot.

Nornir also adds an inventory model. The YAML in this module is still a flat device
file — not a database, not a hierarchy, not role-aware — but it flows through Nornir's
inventory abstraction. As you move toward larger tooling (Ansible in Modules 10 through
12, infrastructure-as-code patterns beyond that), this inventory concept becomes the
organizing principle for everything.

And Nornir adds structured result aggregation. The `AggregatedResult` object tells you,
per host, per subtask, whether the operation succeeded or failed. You don't parse log
output to find out which of nine routers had a problem.

**What Nornir does not add.**

Nornir does not add configuration enforcement. The configure script in this module is
still a merge. It adds and overwrites; it does not remove. A stale EIGRP process, a
misconfigured route-map, a manually added access-list — these survive a `nr.run()` just
as they survive any other Netmiko push. Replace-based enforcement requires a different
task plugin, not a different orchestration framework.

Nornir does not add structured data parsing. The troubleshoot and verify scripts in
this module send show commands and receive raw CLI output — the same strings you'd see
at the terminal. Parsing that output for specific values requires regex, string
matching, or external parsers. In Modules 8 and 9, pyATS and Genie replace that
pattern with structured getters that return Python dictionaries — no regex required.

Nornir does not add declarative intent. The configure script knows what it wants to
push, but it has no model of what the network should look like and no ability to
reconcile live state against that model. Ansible in Modules 10 through 12 addresses
that gap — idempotent plays, role-based configuration management, intent-based
enforcement.

| Module | Protocol        | Tool          | What It Adds                                   |
|--------|-----------------|---------------|------------------------------------------------|
| 02     | EIGRP           | Netmiko       | Direct SSH, explicit command control            |
| 03–04  | OSPF            | NAPALM        | Candidate config, diff before commit            |
| 05–07  | IPv6 / mixed    | Nornir        | Parallel task dispatch, inventory abstraction   |
| 08–09  | TBD             | pyATS/Genie   | Structured parsing, stateful testing            |
| 10–12  | TBD             | Ansible       | Declarative intent, idempotency at scale        |

Nornir is the right tool for this stage of the progression because it keeps the task
structure visible — you write a Python function, you see what it does per host, you
control exactly what happens. The parallel execution is transparent. The tradeoffs
are concrete. That visibility, combined with the scale advantage, is why Nornir belongs
between NAPALM and Ansible in this curriculum.

---

## SECTION 8 — Objectives Review and Wrap-Up

`[SCREEN: README.md — Module Objectives section]`

Let's go back to where we started — the objectives we set at the beginning of this
module — and confirm each one.

---

**IPv6 unicast routing enabled across all nine routers.** Done. The template renders
`ipv6 unicast-routing` and `ipv6 cef` unconditionally at the top of every device's
configuration. Without these two lines, IOS does not forward IPv6 packets, and nothing
else in the module works.

---

**EIGRPv6 AS 100 configured on R1 and R7; AS 111 on R6 and R8.** Done. Interface-level
`ipv6 eigrp <as>` commands are rendered on every EIGRP-participating interface from
the `eigrp_as` field in the YAML. Process-level `ipv6 router eigrp` blocks are
rendered with explicit router IDs. R7 and R8 — IPv6-only routers — have their router
IDs set explicitly in the YAML.

---

**OSPFv3 Area 0 backbone established with R1, R2, R3.** Done. All three routers have
their shared LAN interface (`FC00:192:168:123::/64`, `Ethernet0/0`) assigned to Area 0
via `ipv6 ospf 1 area 0`. Loopbacks are assigned point-to-point network type so they
appear as /64 prefixes in the OSPF database.

---

**Area 10 configured as totally stubby.** Done. R2's OSPF block in the YAML has
`area 10 stub no-summary`, rendered as `area 10 stub no-summary` under `ipv6 router
ospf 1`. R5 and R9 receive only a default route. No external or inter-area LSAs enter
Area 10.

---

**Area 20 configured as NSSA.** Done. R3's OSPF block has `area 20 nssa no-summary`.
R6's redistributed EIGRP routes enter Area 20 as Type 7 LSAs. R3 translates them to
Type 5 for the Area 0 backbone. No summary LSAs from the backbone enter Area 20.

---

**Bidirectional redistribution at both ASBRs.** Done. R1 redistributes between EIGRP
100 and OSPFv3 in both directions. R6 redistributes between EIGRP 111 and OSPFv3 in
both directions. Metric seed values — `10000 100 255 1 1500` for OSPF-to-EIGRP — are
defined in the YAML and rendered from there.

---

**Nornir parallel deployment operational.** Done. `configure_ipv6_eigrp_ospf.py`
deploys to all nine routers simultaneously via `nr.run()`. The Nornir inventory is
constructed at runtime from the module YAML, written to a temporary directory, and
deleted after the run. `print_result()` shows per-host, per-subtask outcomes.

---

**Verification script running and clean.** Done. `verify_ipv6_eigrp_ospf.py` confirms
neighbor adjacencies, routing table contents, redistribution visibility, and area type
configuration across the full topology in parallel.

---

**Troubleshooting script operational, distinction from verifier understood.** Done.
`troubleshoot_ipv6_eigrp_ospf.py` checks neighbor state, process configuration, and
routing table contents. The closing demo made the distinction concrete: the
troubleshooter tells you whether the protocol is working; the verifier tells you
whether the network matches the YAML. Both questions matter, and they require
different tools.

---

The full lab reset procedure is documented in `docs/eve-ng_lab_reset_sop.md`.

Module 6 continues on the Nornir platform with a different protocol stack. Module 8
introduces pyATS and Genie — the abstraction level goes up another step. Show commands
start returning structured Python objects instead of raw CLI strings, and stateful
testing replaces string matching. See you there.

---

| Module | Protocol        | Tool          | What It Adds                                   |
|--------|-----------------|---------------|------------------------------------------------|
| 02     | EIGRP           | Netmiko       | Direct SSH, explicit command control            |
| 03–04  | OSPF            | NAPALM        | Candidate config, diff before commit            |
| 05–07  | IPv6 / mixed    | Nornir        | Parallel task dispatch, inventory abstraction   |
| 08–09  | TBD             | pyATS/Genie   | Structured parsing, stateful testing            |
| 10–12  | TBD             | Ansible       | Declarative intent, idempotency at scale        |

---

*End of Module 05 Verbal Script (draft)*
*NAMS26 — Network Automation Management Station 2026*
