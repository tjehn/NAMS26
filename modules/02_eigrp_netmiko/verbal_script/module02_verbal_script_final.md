# Module 02 — EIGRP Classic Mode
## Verbal Script — `module02_verbal_script_final.md`
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

Alright, welcome to Module 2. This is where we actually start automating things.
Module 1 was all setup and orientation — here we get into the first real lab, and
the tool we're using to do it is Netmiko.

The objective for this module is EIGRP Classic Mode — full configuration,
verification, and troubleshooting, all driven by Python scripts talking to live
Cisco IOS routers over SSH.

By the time we're done here you'll have configured EIGRP Classic Mode across a
six-router topology, including authentication, passive interfaces, static neighbors,
manual summarization, and the variance knob for unequal-cost load balancing. You'll
verify the full adjacency table and routing table using automation, and you'll have
a troubleshooting script that can go out and diagnose a broken EIGRP deployment
without you typing a single CLI command manually.

The other thing this module does — and this is important — is establish the baseline
pattern for every module that follows. YAML feeds data into a Jinja2 template, which
generates configuration, which Netmiko pushes to the devices. That three-file workflow
is the foundation of this entire project. We're going to walk through it carefully here
because it's referenced in detail back in Module 1 and it applies in some form to every
subsequent module.

---

## SECTION 2 — Lab Topology

`[SCREEN: README.md — Lab Topology section]`

![EIGRP Classic Mode Topology](diagrams/topology_eigrp_classic.drawio.svg)

Let's look at the topology. Six routers — R1 through R6 — all running in EVE-NG on
Cisco IOL images. The physical layout is a chain from R1 through to R4, with R4
branching out to both R5 and R6, forming a triangle on the right side of the diagram.

R1 connects to R2 on the `10.12.12.0/24` segment. R2 connects to R3 on
`192.1.23.0/24`. R3 to R4 on `192.1.34.0/24`. Then R4 has two paths out — one to
R5 on `192.1.45.0/24`, and one to R6 on `192.1.46.0/24`. R5 and R6 also connect
directly to each other on `192.1.56.0/24`.

That triangle — R4, R5, R6 — is there specifically to demonstrate unequal-cost load
balancing using the EIGRP `variance` command. The bandwidth values on those links are
intentionally asymmetric. R4 to R5 is configured at 25 Mbps, R4 to R6 at 50 Mbps,
and R5 to R6 at 5 Mbps. That asymmetry is what drives the EIGRP feasibility condition
and gives variance something to work with.

Every router has Ethernet1/3 reserved as the out-of-band management interface,
connected to the `192.168.1.0/24` OOB network. That's how the Network Automation
Management Station communicates with the EVE-NG host routers — that's our SSH path.
I'll come back to that when we get
into the scripts.

R1 also has a significant number of loopbacks — eleven of them — representing
summarizable prefix groups in the `10.1.x.x`, `11.1.x.x`, `101.1.x.x`, and
`150.1.x.x` ranges. Those are there to give us something to filter, redistribute,
and summarize across the topology.

---

## SECTION 3 — Tool Overview: Netmiko

`[SCREEN: README.md — Tool Overview section]`

Netmiko is a Python library built on top of Paramiko — Paramiko is the SSH
implementation, and Netmiko wraps it with device-type-aware logic for network gear.
What that means practically is that Netmiko knows how to handle the quirks of Cisco
IOS prompts, enable mode, config mode transitions, and output parsing in a way that
raw SSH doesn't.

The core value proposition is simple: you write Python, Netmiko handles the SSH
session lifecycle. You don't manage the socket, you don't wait for prompts manually,
you don't worry about whether you're in user EXEC or privileged EXEC. You call
`ConnectHandler`, pass in your device parameters, and get back a connection object
you can interact with programmatically.

The main strength here is visibility. Netmiko sends raw CLI commands and returns raw
CLI output — exactly what you'd see at the terminal. For learning and for
troubleshooting, that transparency is valuable. You always know exactly what's
happening on the device.

The limitation is that it doesn't abstract the CLI. If Cisco changes command syntax,
or you're working with a different vendor, you have to adapt your scripts. There's no
data model underneath — it's CLI automation, not intent-based configuration. As we
move into NAPALM and Nornir in later modules, you'll see how those tools address
that gap.

For this module — EIGRP Classic Mode on Cisco IOS in a lab environment — Netmiko is
exactly the right tool. Simple, direct, transparent.

---

## SECTION 4 — Configuration

### 4a — The Three-File Workflow

`[SCREEN: module directory tree — data/, templates/, scripts/]`

Before we look at any individual file, let's orient to the workflow. Every
configuration push in this module — and in this project — follows the same pattern:
YAML provides the data, Jinja2 renders the configuration from that data, and the
Python script ties everything together and handles the SSH delivery via Netmiko.

```
eigrp_classic.yaml  →  eigrp_classic.j2  →  configure_eigrp_classic.py  →  Router
   (variables)           (template)              (Netmiko SSH push)
```

The reason we separate these three things is flexibility. When you need to change an
IP address, a key string, or an AS number — you only touch the YAML. The template
and the script don't change. When you need to support a new IOS feature in the
rendered config, you update the template. The data and the deployment logic stay
exactly the same. That separation is what makes this pattern scale across every
module that follows.

The three files that implement this are `eigrp_classic.yaml` in the `data/`
directory, `eigrp_classic.j2` in the `templates/` directory, and
`configure_eigrp_classic.py` in the `scripts/` directory. These three files are
tightly coupled — let's walk through each one.

---

### 4b — File 1: `eigrp_classic.yaml`

`[SCREEN: eigrp_classic.yaml]`

The YAML file is the single source of truth. Everything the script needs to know
about the lab lives here — hostnames, IP addresses, interface parameters, EIGRP
settings, key chains, authentication, and credentials.

There are five things in this file worth calling your attention to specifically.

---

**Credentials are defined once.**

At the very top of the file you'll see the `default_credentials` block with a YAML
anchor — that `&creds` tag. Every device then references that anchor with `*creds`.
You define the username and password one time, and every router picks it up
automatically.

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

When Python's `yaml.safe_load()` reads this file, it resolves the anchor
transparently — by the time the data reaches the script, every device dictionary
has its credentials fully populated. You don't have to do anything special on the
Python side to handle it. Any device that defines its own `credentials` block
overrides the default; the Python script handles that fallback logic explicitly.

---

**`dns_name` is the SSH target — not `oob_ip`.**

Every script in this module connects to devices using the `dns_name` field. That
name is resolved through the lab DNS server at `192.168.1.12`. The `oob_ip` is kept
in the file for documentation purposes only — it gives you a clear reference to the
management IP, but no script ever uses it as a connection target.

```yaml
    hostname: R1
    dns_name: r1.lab          # ← SSH target — resolved by lab DNS at 192.168.1.12
    oob_ip: 192.168.1.101/24  # ← Reference only — not used by any script
    oob_interface: Ethernet1/3
```

---

**`oob_interface` drives an exclusion in the template.**

The OOB management interface — `Ethernet1/3` on every router — is listed in each
device entry specifically so the Jinja2 template can skip it. It gets excluded from
the physical interface configuration loop and from EIGRP entirely. We'll see exactly
where that happens when we look at the template.

---

**Bandwidth values on the R4–R5 and R4–R6 links are intentional.**

Most interfaces in the file have blank bandwidth and delay fields — the routers use
IOS defaults. But look at R4's Ethernet0/1 facing R5, and Ethernet0/2 facing R6.
Those have explicit bandwidth values set.

```yaml
      Ethernet0/1:
        description: "To R5"
        ip: 192.1.45.4/24
        shutdown: false
        bandwidth: "25000"    # 25 Mbps — slower than R4–R6
        delay: ""
      Ethernet0/2:
        description: "To R6"
        ip: 192.1.46.4/24
        shutdown: false
        bandwidth: "50000"    # 50 Mbps — faster
        delay: ""
```

That asymmetry is what sets up the unequal-cost load balancing demonstration later.
The same values are mirrored on R5 and R6. The template only renders the `bandwidth`
command when the field is non-empty, so routers without these values set don't get
the command at all.

---

**Key chain ordering is intentional.**

On R2 — which has two authenticated interfaces — look at how the `key_chains` block
sits in the YAML relative to the `authentication` block.

```yaml
    eigrp:
      as: 100
      authentication:
        - interface: Ethernet0/0
          mode: md5
          key_chain: BBB
        - interface: Ethernet0/1
          mode: md5
          key_chain: BC
      key_chains:         # ← Rendered before authentication in the template
        - name: BBB
          keys:
            - id: 1
              string: Cisco123
        - name: BC
          keys:
            - id: 1
              string: Ccie123
```

In Cisco IOS, a key chain has to exist on the router before you can reference it in
an authentication statement — if you apply auth first and the key chain isn't there
yet, the command fails. The YAML structure mirrors this dependency, and the template
renders key chains first, then the authentication block. We'll see that ordering
explicitly when we look at the template.

---

### 4c — File 2: `eigrp_classic.j2`

`[SCREEN: eigrp_classic.j2]`

The Jinja2 template takes the YAML data and renders a complete Cisco IOS
configuration for each device. The Python script passes the entire device dictionary
in as the rendering context — every key in the YAML device block becomes a variable
the template can use directly.

Three things worth highlighting here.

---

**The OOB interface is excluded right at the top of the interface loop.**

The physical interface loop iterates over every interface in the `interfaces`
dictionary, but the very first thing it does is check whether the current interface
is the OOB interface. If it is, the entire block is skipped.

```jinja
{% for intf_name, intf in interfaces.items() %}
{% if intf_name != oob_interface %}
interface {{ intf_name }}
{% if intf.description and intf.description.strip() %} description {{ intf.description.strip() }}
{% endif %}
{% if intf.ip and intf.ip != "" and '/' in intf.ip %} ip address {{ intf.ip.split('/')[0] }} {{ intf.ip.split('/')[1] | cidr_to_netmask }}
{% endif %}
...
{% if intf.shutdown | default(true) %} shutdown
{% else %} no shutdown
{% endif %}
!
{% endif %}
{% endfor %}
```

That `{% if intf_name != oob_interface %}` condition is exactly why we put
`oob_interface: Ethernet1/3` in the YAML. The template uses it to make a clean
decision — include or skip — for every interface it encounters. For interfaces that
aren't in use, `shutdown: true` in the YAML keeps them administratively down. The
template only renders `no shutdown` if `shutdown` is explicitly false.

---

**`cidr_to_netmask` is a custom filter registered in Python.**

You'll notice the IP address line calls `| cidr_to_netmask` on the prefix length.
Jinja2 doesn't natively convert CIDR notation to dotted-decimal subnet masks. That
conversion is a Python function defined in `configure_eigrp_classic.py` and
registered with the Jinja2 environment before the template is loaded.

```jinja
 ip address {{ intf.ip.split('/')[0] }} {{ intf.ip.split('/')[1] | cidr_to_netmask }}
```

The template splits the IP field on the `/` — the left side is the host address,
the right side is the prefix length — and passes the prefix length through the
filter. The result is a line like `ip address 10.12.12.1 255.255.255.0`. We'll see
the filter registration on the Python side in a moment.

Optional interface attributes use guards so that missing fields produce nothing
rather than an error:

```jinja
{% if intf.bandwidth and intf.bandwidth != "" %} bandwidth {{ intf.bandwidth }}
{% endif %}
{% if intf.delay and intf.delay != "" %} delay {{ intf.delay }}
{% endif %}
```

---

**Key chains render before the EIGRP process block.**

Just like in IOS, the template renders key chains first. They appear in a dedicated
section between the loopback interfaces and the `router eigrp` stanza.

```jinja
{% if eigrp.key_chains | default([]) | length > 0 %}
! =========================================
! Key Chains
! =========================================
{% for chain in eigrp.key_chains %}
key chain {{ chain.name }}
{% for key in chain['keys'] | default([]) %} key {{ key.id }}
  key-string {{ key.string }}
{% endfor %}
!
{% endfor %}
{% endif %}
```

The EIGRP process block comes after, and authentication is rendered last — after
the EIGRP process itself. The template handles both a single authenticated interface
and a list of them, using an `is mapping` / `is iterable` check:

```jinja
{% if eigrp.authentication %}
{% if eigrp.authentication is mapping %}
interface {{ eigrp.authentication.interface }}
 ip authentication mode eigrp {{ eigrp.as }} {{ eigrp.authentication.mode }}
 ip authentication key-chain eigrp {{ eigrp.as }} {{ eigrp.authentication.key_chain }}
!
{% elif eigrp.authentication is iterable %}
{% for auth in eigrp.authentication %}
interface {{ auth.interface }}
 ip authentication mode eigrp {{ eigrp.as }} {{ auth.mode }}
 ip authentication key-chain eigrp {{ eigrp.as }} {{ auth.key_chain }}
!
{% endfor %}
{% endif %}
{% endif %}
```

A single mapping covers routers with one authenticated interface. A list covers
routers with two. The template handles both without any changes to the script. The
`variance` line only renders if the value is greater than 1 — so for routers where
variance is set to 1 (the default), that line simply doesn't appear.

---

### 4d — File 3: `configure_eigrp_classic.py`

`[SCREEN: configure_eigrp_classic.py]`

Now let's look at the Python script that drives the whole thing.

---

**Argument parsing — your primary lab controls.**

The script supports two flags that you'll use constantly:

```python
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Render and save configs locally only — no SSH connection.",
)
parser.add_argument(
    "--router",
    nargs="*",
    metavar="HOSTNAME",
    help="Target one or more routers by hostname (e.g. --router R1 R2). "
         "Defaults to all devices in YAML.",
)
```

`--dry-run` renders and saves the configs to the `configs/` directory but never
opens an SSH session. `--router` lets you target one or more specific routers instead
of running against all six. You can combine them — `--dry-run --router R1` is a clean
way to sanity-check a single device's rendered output before committing to a full
deployment.

The `--router` flag accepts the device name in any of these forms — all resolve to
the same target: `R1` (exact YAML key), `r1` (lowercase), `r1.lab` (FQDN), or
`R1.lab` (uppercase FQDN). Resolution is case-insensitive at every step.

---

**Path resolution.**

The path resolution block at the top captures the absolute path of the script itself
using `__file__`. From there, `MODULE_DIR` steps up one level to the module root, and
`PROJECT_ROOT` steps up one more to the NAMS26 project root. All subsequent paths —
to the YAML file, the templates directory, the configs output directory, and the logs
directory — are built from those resolved roots. This means the script runs correctly
regardless of which directory you call it from.

---

**Loading the YAML.**

```python
with open(YAML_FILE, "r") as fh:
    data = yaml.safe_load(fh)

devices       = data.get("devices", {})
default_creds = data.get("default_credentials", {})
```

`yaml.safe_load()` reads the file and resolves all anchors — the `*creds` references
become fully populated credential dictionaries in the Python data structure. The
script then pulls out the `devices` dictionary and the `default_credentials` block
separately.

---

**Credential injection.**

```python
for device_data in devices.values():
    if not device_data.get("credentials"):
        device_data["credentials"] = default_creds
```

This short loop runs before any template or SSH logic. Any device that didn't define
its own credentials gets the top-level defaults injected here. In this lab all six
routers use `*creds`, but this fallback makes the pattern robust for future modules
where individual devices might use different credentials.

---

**Setting up the Jinja2 environment — and registering the custom filter.**

```python
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    trim_blocks=True,
    lstrip_blocks=True
)
env.filters["cidr_to_netmask"] = cidr_to_netmask
```

`FileSystemLoader` points Jinja2 at the `templates/` directory. `trim_blocks` and
`lstrip_blocks` are set so that Jinja2 control tags — the `{% %}` blocks — don't
leave extra blank lines in the rendered output. The result is clean IOS configuration
with no stray whitespace.

The last line registers the `cidr_to_netmask` Python function as a named Jinja2
filter — the bridge between the script and the template. Without it, the
`| cidr_to_netmask` call in the template would throw an error.

---

**Rendering and saving each config.**

```python
for device_name in target_routers:
    device_data = devices[device_name]

    config = generate_config(template, device_data)

    config_path = os.path.join(CONFIG_DIR, f"{run_date}_{device_name}_eigrp_classic.cfg")
    with open(config_path, "w") as fh:
        fh.write(config)
    print(f"  Config written : {config_path}")

    if args.dry_run:
        print(f"  DRY-RUN        : SSH push skipped.")
    else:
        apply_config(device_name, device_data, config)
```

`generate_config()` is intentionally minimal — it just calls
`template.render(device_data)`. The template does the work. The rendered output is
written to `configs/` as `260428_143022_R1_eigrp_classic.cfg`, `260428_143022_R2_eigrp_classic.cfg`, and so on.
These files persist after the run — they're your record of exactly what was pushed
to each device, and they're what you review during a dry-run.

---

**Inside `apply_config()` — the Netmiko session.**

If we're not in dry-run mode, `apply_config()` handles the SSH session for each
device. The connection target comes from `dns_name`. A timestamped session log is
written to `modules/02_eigrp_netmiko/logs/` — every SSH session gets its own
file, and those logs are your audit trail.

```python
connection_params = {
    "device_type":         "cisco_ios",
    "host":                dns_name,
    "username":            username,
    "password":            password,
    "global_delay_factor": 4.0,
    "session_log":         session_log_path,
}
```

The `global_delay_factor` of 4.0 gives each IOL node extra time to process each
command before the next one arrives.

---

**Config delivery — IOL line-by-line send.**

In production against real hardware, Netmiko's `send_config_set()` is the right
call — it handles entering and exiting configuration mode automatically and sends
the entire block efficiently:

```python
# PRODUCTION VERSION
conn.send_config_set(config.splitlines())
save_output = conn.send_command("write memory")
```

In this lab we send lines individually. That's an IOL limitation — the input buffer
on IOL instances is small enough that bulk sends can get truncated mid-config.
Line-by-line with prompt confirmation is reliable. After the last line is sent,
the script exits config mode with `end` and saves the running config with
`write memory`.

```python
# LAB VERSION — line-by-line send (IOL buffer limitation)
conn.send_command("configure terminal", expect_string=r"#")

for line in config.splitlines():
    if line.strip():
        conn.send_command(line, expect_string=r"#", delay_factor=5.0)

conn.send_command("end", expect_string=r"#")
save_output = conn.send_command("write memory")
```

---

**Running the script.**

With all three files understood, here's the deployment sequence you'll follow:

```bash
# 1. Dry-run — render and review configs before pushing
python scripts/configure_eigrp_classic.py --dry-run

# 2. Deploy configuration to all routers
python scripts/configure_eigrp_classic.py

# 3. Verify EIGRP state
python scripts/verify_eigrp_classic.py

# 4. Troubleshoot if needed
python scripts/troubleshoot_eigrp_classic.py
```

Step 1 is not optional in practice. Before you push config to six routers, open the
rendered `.cfg` files in `configs/` and confirm the YAML and template are producing
exactly what you expect for every device. That review is where you catch mistakes
before they hit the lab.

---

## SECTION 5 — Verification

`[SCREEN: verify_eigrp_classic.py]`

The verification script follows the same structural pattern as the configure script
— path resolution, YAML load, credential injection, DNS-based SSH targets — so we
won't re-walk all of that. What's different here is everything the script does once
it's connected.

The first thing worth calling out is the `AVAILABLE_CHECKS` list defined near the
top of the file. This is the single source of truth for what checks the script can
run — `neighbors`, `interfaces`, and `routes`. Both the `--list-checks` argument and
the `--check` argument validation reference this same list, so if a check is added
or renamed, it only needs to change in one place.

The script also defines a set of terminal color helper functions — `passed`,
`failed`, `warned`, and `info` — each wrapping a message with the appropriate ANSI
color code. Green for PASS, red for FAIL, yellow for WARN, cyan for INFO. These are
used consistently across the output so that when you're scanning a full six-router
verification run, the pass/fail status is immediately visible without reading every
line.

The `connect` function here uses a `global_delay_factor` of 2.0 instead of 4.0,
because we're only sending show commands, not pushing configuration line-by-line.

**`check_neighbors`** runs `show ip eigrp neighbors` and prints the raw output to
the terminal. Then it pulls the `static_neighbors` list from the YAML `eigrp` block
for that device and checks whether each expected neighbor IP appears in the live
output. Each one either gets a PASS or a FAIL. For devices that don't have
`static_neighbors` defined in the YAML — R4, R5, and R6 — it prints an INFO message
and skips the validation step. The raw output is still displayed so you can visually
confirm those neighbors manually.

**`check_interfaces`** runs `show ip eigrp interfaces` and is intentionally
informational — no PASS/FAIL logic. After printing the raw output it reads the
passive interface configuration from the YAML and prints it as INFO lines, so you
can compare what the YAML says should be active against what the router is actually
reporting.

**`check_routes`** runs `show ip route eigrp` and cross-references every network
statement from the YAML against live interface state. For each advertised network it
finds the owning interface using wildcard-aware IP math and reports:

- `PASS` — the interface owning that network is up/up
- `WARN` — the interface exists but is not up/up
- `FAIL` — no interface found with a matching IP on this device

**The `main()` function** adds two useful command-line capabilities. First, `--check`
lets you run a subset of the available checks. Second, `--route` adds an on-the-fly
`show ip route | include <target>` lookup — useful during live demonstration to
spot-check reachability to a specific prefix without running the full verification
suite.

All output is mirrored to a timestamped log file in `modules/02_eigrp_netmiko/logs/` so every
verification run is fully auditable.

---

## SECTION 6 — Troubleshooting

`[SCREEN: troubleshoot_eigrp_classic.py]`

The troubleshooting script is the most architecturally interesting file in this
module. It has two completely distinct operating modes, and understanding why it's
built that way is as important as understanding what it does.

**Mode 1 is live troubleshooting.** Connect to the routers, run targeted diagnostic
show commands, evaluate the output against the YAML, and report findings with PASS,
FAIL, and WARN annotations. Five checks are available: `neighbors`, `authentication`,
`passive`, `routes`, and `process`.

**Mode 2 is failure demonstration**, triggered by the `--demo-failure` flag. This
mode never touches a router. It takes an in-memory copy of the YAML data, injects a
specific fault, renders both the correct and broken configurations from the Jinja2
template, diffs them, and walks through exactly what symptoms you'd see on a live
device. This is a teaching tool built directly into the script.

The five failure scenarios — `missing-keychain`, `keychain-mismatch`, `wrong-as`,
`passive-active`, and `missing-network` — are defined in the `FAILURE_SCENARIOS`
dictionary near the top of the file. Each entry contains a title, a prose description
of what the failure is and why it happens, a list of CLI symptoms, the CLI commands
you'd use to diagnose it, and the fix. The `FAULT_INJECTORS` dictionary maps each
scenario key to its corresponding injector function.

Let's walk the injector functions briefly, because the pattern is clean and worth
understanding. Each injector receives a deep copy of a single device's data
dictionary — `copy.deepcopy` ensures the original YAML data is never mutated. The
function makes a targeted change to that copy and returns it. `inject_wrong_as`
changes `eigrp.as` to 999. `inject_missing_keychain` clears the `key_chains` list.
`inject_keychain_mismatch` appends `_WRONG` to each key chain name referenced in
the authentication block, so the reference points to a chain that doesn't exist.
`inject_passive_active` takes the first interface from `no_passive_interfaces` and
moves it to the `passive_interfaces` list. `inject_missing_network` removes the
first network statement from the `networks` list. In every case the original data is
untouched — only the in-memory copy changes.

The `run_demo_failure` function orchestrates the full demonstration cycle. For each
target router it renders the correct config from clean data, renders the broken
config from the injected copy, calls `diff_configs` to produce a line-level diff,
then walks through the symptoms, troubleshooting commands, and fix. The
`diff_configs` function uses set operations on the rendered config lines — green for
lines present in the correct config but missing from the broken one, red for lines in
the broken config that aren't in the correct one, dimmed for unchanged lines.

Now for the live troubleshooting checks.

**`check_neighbors`** runs `show ip eigrp neighbors detail`. The detail version is
important — it exposes authentication counters and hold timer state that the basic
neighbor table doesn't show. The function scans the output for the string `INIT`,
which indicates a neighbor stuck in the initialization state, and flags it as a
warning for possible authentication mismatch.

**`check_authentication`** runs `show ip eigrp interfaces detail`, which exposes
per-interface authentication send and receive counters. Non-zero auth failure counters
in that output are the definitive indicator of a key chain or MD5 configuration
problem. After the interfaces check, it immediately follows up with `show key chain`
— you see both in sequence. The function then cross-references each key chain name
defined in the YAML against the `show key chain` output and reports PASS or FAIL
for each one. If the key chain name is in the output, the chain exists on the router.
If it's not, that's your fault.

**`check_passive`** runs `show ip protocols` and cross-references the passive
interface configuration from the YAML. This check catches the most common and most
silent EIGRP failure: an interface that should be sending hellos is accidentally
passive, the neighbor times out, and there's no error message anywhere.

**`check_routes`** runs both `show ip route eigrp` and `show ip eigrp topology`.
The topology table check looks at the state codes — `P` means passive, which is
stable and converged; `A` means active, which means EIGRP is currently reconverging
and something is wrong. If you see active routes in the topology table after a
deployment, EIGRP hasn't settled. Wait for convergence or investigate why it's
stuck active.

**`check_process`** runs `show ip protocols` and validates the AS number from the
YAML against what's actually running on the router. If the AS in the output doesn't
match the YAML, either the configuration didn't apply correctly or there's a stale
EIGRP process from a previous configuration.

The `main()` function handles both modes cleanly. If `--demo-failure` is present,
it loads the Jinja2 template, calls `run_demo_failure`, and exits — no SSH
connections are made. If not, it proceeds into live troubleshooting mode with the
standard connect-and-check loop. The `--list-checks` and `--list-failures` flags
let you inspect what's available without running anything.

---

## SECTION 7 — Closing Demonstration: Configuration Drift

`[SCREEN: terminal — scripts/ and utils/ directories]`

Before we wrap Module 2, there's one more demonstration that ties everything
together — and it makes a point that's just as important as anything in the scripts
themselves.

We're going to deliberately introduce a configuration drift on R4, then use the two
scripts we just walked through to show exactly what each one can and cannot tell you.

---

### Part 1 — Inject the Drift

From the `utils/` directory, push a network statement to R4 that doesn't exist in
`eigrp_classic.yaml`. This simulates the kind of manual CLI change that gets made
during an incident and never gets cleaned up or documented.

```bash
python utils/push_config.py --router R4 --cmd "router eigrp 100" "network 192.1.99.0"
```

The configuration is now live on R4 and saved to NVRAM. The router is advertising
`192.1.99.0` into EIGRP AS 100 — a network that has no corresponding interface on
R4 and no entry in the YAML source of truth.

---

### Part 2 — Troubleshooting Shows a Healthy Router

```bash
python scripts/troubleshoot_eigrp_classic.py --router R4
```

All five checks pass. Neighbors are up on all three interfaces. The topology is fully
converged. The process is running AS 100. From a pure operational standpoint, R4
looks completely healthy.

> **Instructor talking point:** Ask the class what the troubleshooter told us.
> The answer is: *R4 is working*. Every check passed.
>
> Now ask: *Did the troubleshooter tell us whether R4 matches our intended
> configuration?* It did not. That is not its job. The troubleshooter answers
> the question "is EIGRP working?" — it does not answer the question "is this
> router configured the way it's supposed to be?"

---

### Part 3 — Verification Reveals the Drift

```bash
python scripts/verify_eigrp_classic.py --router R4
```

Fifteen network statements return `[PASS]`. Then:

```
  [FAIL] Network 192.1.99.0 0.0.0.255 (classful inferred) — no interface found
         with a matching IP on R4
```

> **Instructor talking point:** This is configuration drift. The router has a
> network statement that does not correspond to any interface on the device, and
> that does not exist anywhere in our YAML source of truth.
>
> The router passed troubleshooting. It failed verification. Both of those
> statements are true at the same time. That distinction matters.
>
> The verification script is not asking "is EIGRP working?" — it is asking "does
> this router match what our YAML says it should look like?" Those are fundamentally
> different questions, and in production you need both answers.

---

### Part 4 — Restore from Source of Truth

```bash
python scripts/configure_eigrp_classic.py --router R4
python scripts/verify_eigrp_classic.py --router R4
```

All checks pass. The YAML is the authoritative baseline — and re-running the
configure script from it is the correct way to restore a drifted device.

---

### Part 5 — The Bigger Conversation: Netmiko in Context

This demonstration leads directly into a question worth sitting with: if this is
what it takes to catch one stray network statement on one router in a six-device lab
— what does that look like in a network with five hundred devices?

Netmiko is an excellent tool for getting started with network automation. It is
approachable, well-documented, and makes the underlying mechanics of SSH-based
automation visible in a way that higher-abstraction tools do not. For a small network
— a lab, a branch site, a handful of devices — this approach works well.

But the approach demonstrated in this module does not scale to an enterprise network.
Understanding why is as important as understanding how to use it.

**Connection management is serial by default.** Each script connects to one router at
a time, runs its commands, disconnects, and moves to the next. In a six-router lab
this is invisible. In a network with hundreds of devices, it becomes a significant
bottleneck.

**There is no state awareness.** Netmiko sends commands and receives output. It has no
model of the network, no understanding of device state across runs, and no awareness
of what changed between the last execution and this one.

**Configuration management is additive, not declarative.** The configure script pushes
lines to the router — it does not verify what is already there, remove lines that
should no longer exist, or enforce the complete intended state. The `192.1.99.0`
network statement survived a `configure_eigrp_classic.py` run because the script adds
lines; it does not reconcile them.

**Error recovery is manual.** If a push fails midway through, the device may be left
in a partial configuration state. Netmiko surfaces the error, but it does not roll
back the changes.

**There is no inventory or orchestration layer.** The YAML file in this module is a
flat device inventory written for this specific lab. It has no concept of device
groups, roles, regions, or hierarchical data inheritance.

These are not defects to be fixed in the Netmiko scripts — they are the motivation
for everything that comes next.

| Module | Protocol   | Tool          | What It Adds                              |
|--------|------------|---------------|-------------------------------------------|
| 02     | EIGRP      | Netmiko       | Direct SSH, explicit command control      |
| 03–04  | OSPF       | NAPALM        | Structured getters, config diff, rollback |
| 05–06  | IPv6/IS-IS | Nornir        | Concurrent execution, inventory model     |
| 10–12  | BGP        | pyATS/Genie   | Structured parsing, stateful testing      |
| 07–12  | MPLS/VPN   | Ansible       | Declarative intent, idempotency at scale  |

Netmiko is not the wrong tool — it is the right tool for this stage of the learning
progression. It keeps the mechanics visible. Every SSH connection, every command,
every line of output is explicit in the code. That visibility is exactly what a first
automation module should provide. The limitations noted above are the motivation for
every module that follows.

---

## SECTION 8 — Objectives Review and Wrap-Up

`[SCREEN: README.md — Module Objectives section]`

Let's go back to where we started — the objectives we set out at the beginning of
this module — and confirm each one.

**EIGRP Classic Mode configured across six routers.** Done. The configure script
deployed the full EIGRP configuration from YAML and Jinja2 to all six devices —
AS 100, network statements, passive interfaces, and static neighbors where defined.

**MD5 authentication implemented.** Done. R1, R2, and R3 have authentication
configured on their active interfaces using named key chains. The key chain ordering
in the YAML and template ensures IOS receives the key chain definition before the
authentication reference.

**Manual summarization configured.** Done. R1 summarizes the `101.1.4.0/22` block
toward R2. R4 summarizes the `101.1.8.0/22` block toward R3.

**Unequal-cost load balancing demonstrated.** Done. The asymmetric bandwidth values
on the R4–R5–R6 triangle drive the EIGRP feasibility condition, and the `variance`
setting on R4 enables EIGRP to install both paths.

**The three-file workflow understood.** Done. YAML as data source, Jinja2 as
configuration renderer, Python as orchestrator and SSH delivery engine — that pattern
is now established and will carry forward to every module that follows.

**Verification script running and clean.** Done. `verify_eigrp_classic.py` confirmed
all network statements passing against live interface state across all six routers.

**Troubleshooting script operational.** Done. `troubleshoot_eigrp_classic.py` running
all five live checks cleanly, and the five failure demonstration scenarios fully
documented and working.

The full lab reset procedure, including EVE-NG node wipe and RSA key generation, is
documented in `eve-ng_lab_reset_sop.md`.

Module 3 moves to OSPF with NAPALM. The abstraction layer goes up a level — NAPALM
introduces structured getters that return parsed data rather than raw CLI output, and
a configuration diff and replace model that begins to address the declarative gap we
identified here. See you there.

---

*End of Module 02 Verbal Script*
*NAMS26 — Network Automation Management Station 2026*
