# NAMS26 — Student Reference Appendix

Supplementary technology notes and code snippets for students working through the NAMS26
curriculum. This is a reference document — read it alongside the module READMEs, not instead
of them. Entries are added as topics arise during module development.

Sections marked *(Draft)* are pending final review against the live lab.

---

## Contents

1. [Python & General Patterns](#1-python--general-patterns)
2. [Netmiko](#2-netmiko)
3. [NAPALM](#3-napalm)
4. [Nornir](#4-nornir)
5. [pyATS / Genie](#5-pyats--genie)
6. [Ansible](#6-ansible)
7. [Jinja2 Templates](#7-jinja2-templates)
8. [YAML Device Inventory](#8-yaml-device-inventory)
9. [IOS Command Reference](#9-ios-command-reference)
10. [Troubleshooting Reference](#10-troubleshooting-reference)
11. [Credential Security](#11-credential-security)
12. [OSPF Reference](#12-ospf-reference)

---

## 1. Python & General Patterns

*(Draft notes and snippets go here.)*

---

## 2. Netmiko *(Draft)*

### Timing Parameters

Netmiko uses internal delay constants to manage SSH timing. Three parameters control how
long it waits at various stages of the connection.

| Parameter | Scope | Behavior |
|-----------|-------|----------|
| `global_delay_factor` | Connection-wide | Multiplies **all** internal Netmiko delay constants: post-login settling, inter-command pause, prompt-detection loops. Set in `ConnectHandler()` or via NAPALM `optional_args`. |
| `delay_factor` | Per-`send_command` | Multiplies that single command's wait time. Stacks **multiplicatively** with `global_delay_factor`: `effective wait = base × global_delay_factor × delay_factor`. |
| `conn_timeout` | TCP only | TCP handshake timeout in seconds. Raises `NetmikoTimeoutException` if exceeded. Does not affect application-level prompt timeouts. |

**Values used in this project:**

| Script type | `global_delay_factor` | `delay_factor` |
|-------------|----------------------|----------------|
| `push_config.py` (Netmiko, `send_config_set`) | 2.0 | — |
| `configure_*.py` (Netmiko, line-by-line `send_command`) | 4.0 | 5.0 |
| `verify_*.py` / `troubleshoot_*.py` | 2.0 | — |
| NAPALM scripts (via `optional_args`) | 2.0 | — |

**Why IOL needs higher values than physical hardware:** Cisco IOL runs as a software
process inside a Linux VM. Command processing is slower than on dedicated hardware —
especially in config mode. The `global_delay_factor: 4.0` and `delay_factor: 5.0`
values give IOL enough time to process each line and return the prompt before Netmiko
times out waiting for it.

---

## 3. NAPALM *(Draft)*

### Cisco IOL `optional_args`

Cisco IOL routers have no `flash:` filesystem and do not support SCP. Every NAPALM
configure script targeting IOL must use these `optional_args`:

```python
# Modules 03-04 (adjust session_log_path per module)
optional_args = {
    "ssh_config_file":  None,
    "session_log":      session_log_path,
    # global_delay_factor is a Netmiko parameter forwarded through NAPALM's
    # optional_args to the underlying SSH connection. Doubles all internal
    # Netmiko timing constants — needed because IOL routers respond slowly.
    # Current: 2.0   Range: 1.0 (fastest, may miss prompts) – 5.0 (slow hosts)
    "global_delay_factor": 2.0,
    # IOL has no flash: filesystem — point NAPALM's space check at nvram: instead.
    "dest_file_system": "nvram:",
    # IOL does not support SCP — send config inline over the SSH session.
    "inline_transfer":  True,
    # Module 04+ only — disables SCP at the NAPALM layer as a belt-and-suspenders
    # guard against IOL MD5 checksum errors on some image versions.
    "enable_scp":       False,
}

# On physical Cisco hardware (remove IOL-specific keys):
optional_args = {
    "ssh_config_file": None,
    "session_log":     session_log_path,
}
```

> **On physical hardware:** `dest_file_system`, `inline_transfer`, and `enable_scp`
> are IOL-specific workarounds. Remove them when targeting production equipment.
> NAPALM will use SCP by default on hardware that supports it.

### Merge vs Replace Candidate

NAPALM supports two config models:

| Model | Method | Behavior |
|-------|--------|----------|
| Merge | `load_merge_candidate()` | Adds lines from the candidate to the running config. Does not remove lines absent from the candidate. |
| Replace | `load_replace_candidate()` | Replaces the entire running config with the candidate. Removes anything not in the candidate. |

This project uses merge candidates (Modules 03–04). The limitation: a stray line added
manually to a router will not be removed by a merge candidate re-run. Only a replace
candidate or a manual `no` command will remove it.

---

## 4. Nornir *(Draft)*

### Three Core Concepts

| Concept | What it does |
|---------|--------------|
| **Inventory** | Describes what devices exist and how to connect to them. `SimpleInventory` loads from YAML files. |
| **Task** | A function that runs on one device. `netmiko_send_config`, `netmiko_send_command` are the primary tasks in this project. |
| **Runner** | Controls how tasks are dispatched. Default `RunnerPlugin` runs tasks in parallel across all inventory hosts. |

### `netmiko_send_config` is a Merge Operation

`netmiko_send_config` sends configuration lines to a device using Netmiko's
`send_config_set()` under the hood. It is additive — it pushes the lines in the
rendered template and does not enforce that the device's running config contains
*only* those lines.

Consequence: if a stray configuration line exists on a router that is not in the
Nornir template, re-running the configure script will not remove it.

This is the same limitation as NAPALM's merge candidate model. The difference:
NAPALM explicitly shows you a diff before committing. Nornir's `netmiko_send_config`
does not — changes are applied without a pre-flight diff review.

### Nornir Inventory from Module YAML

Rather than maintaining separate `hosts.yaml` and `groups.yaml` files, the NAMS26
scripts build a Nornir inventory dynamically from the module's existing YAML:

```python
from nornir import InitNornir
from nornir.core.inventory import Inventory, Host, Hosts, Groups

# Build inventory inline from module YAML devices dict
hosts = {}
for name, dev in devices.items():
    hosts[name] = Host(
        name=name,
        hostname=dev["dns_name"],
        username=dev["credentials"]["username"],
        password=dev["credentials"]["password"],
        platform="cisco_ios",
    )

nr = InitNornir(
    runner={"plugin": "threaded", "options": {"num_workers": 5}},
    inventory={"plugin": "SimpleInventory"},
)
nr.inventory = Inventory(hosts=Hosts(hosts), groups=Groups())
```

---

## 5. pyATS / Genie

*(Draft notes and snippets go here.)*

---

## 6. Ansible

*(Draft notes and snippets go here.)*

---

## 7. Jinja2 Templates *(Draft)*

### `ospf_area: 0` Falsy Guard

In Python (and Jinja2), the integer `0` is falsy. This means:

```jinja2
{% if intf.ospf_area %}
```

...will **skip** interfaces assigned to Area 0, because `0` evaluates as `False`.
Always use an explicit null/empty check for OSPF area assignments:

```jinja2
{% if intf.ospf_area is not none and intf.ospf_area != "" %}
 ip ospf {{ ospf.process_id }} area {{ intf.ospf_area }}
{% endif %}
```

This correctly renders Area 0, Area 10, Area 20, and any other valid area number.

---

## 8. YAML Device Inventory *(Draft)*

### Ethernet Interface Variables (Enterprise Reference)

Full set of variables available for an Ethernet interface entry. Not all fields are
required for every module — use the subset relevant to the module's scope.

```yaml
Ethernet1/2:
  description: ""
  ip: ""              # IPv4 CIDR — e.g. 10.12.12.1/24. Empty string if unused.
  shutdown: true
  speed: ""           # Active Ethernet: 100 (unquoted integer). Others: ""
  duplex: ""          # Active Ethernet: full. Others: ""
  mtu: ""
  bandwidth: ""
  delay: ""
```

> **`speed: 100` must be an unquoted YAML integer.** The value `"100"` (quoted
> string) renders correctly in Jinja2 but violates the project standard. Active
> Ethernet interfaces must use `speed: 100` and `duplex: full`. Serial, Loopback,
> and unused interfaces must use empty strings for both.

---

## 9. IOS Command Reference

### IOL: `speed` and `duplex` Not Supported on Ethernet Interfaces

Cisco IOL routers do not implement the `speed` and `duplex` commands on Ethernet
interfaces. Sending them produces `% Invalid input detected` but does **not** abort
the configuration session — the remaining lines are applied normally, and the interface
comes up correctly without them.

When an automation script pushes `speed 100` and `duplex full` to an IOL router, the
errors are benign. No corrective action is required. On real Cisco hardware these
commands are required for forced speed/duplex — they are kept in the YAML and templates
so the scripts work correctly on physical equipment without modification.

### IS-IS Named Mode: `passive-interface` Belongs Under the Process, Not the Interface

In IS-IS **Named Mode**, the interface-level `isis passive` command is not valid. IOS
will reject it with `% Invalid input detected`. The correct syntax places
`passive-interface` under the `router isis` process block:

```
! WRONG — rejected in IS-IS Named Mode
interface Loopback0
 isis passive

! CORRECT — Named Mode syntax
router isis NAMS26
 passive-interface Loopback0
```

This applies to all passive interfaces, including loopbacks and any stub segment that
should participate in IS-IS for prefix advertisement but not form adjacencies.

In **Classic Mode**, `isis passive` on the interface is valid. Named Mode requires the
process-level form. When migrating templates from Classic to Named Mode, audit all
interfaces that were using `isis passive` and move them to `passive-interface` under
the process block.

### IS-IS: `show isis interface` Commands Not Supported on IOL 15.7

Both `show isis interface brief` and `show isis interface` (bare) produce error
output on Cisco IOL 15.7:

- `show isis interface brief` — `% Invalid input detected`
- `show isis interface` — `% Incomplete command.`

Use `show clns interface` instead. It lists all interfaces with their CLNS status.
IS-IS-enabled interfaces show `Routing Protocol: IS-IS` with circuit type, metric,
and adjacency count. Non-IS-IS interfaces show `CLNS protocol processing disabled`.

### IS-IS: `show clns protocol` Displays Area ID and System ID Separately, Not as a Combined NET

IOL 15.7 does not print the full NET string (e.g. `49.0001.0000.0000.0001.00`) on
a single line. The area ID and system ID appear in separate fields:

```
IS-IS Router: NAMS26
  System Id: 0000.0000.0001.00  IS-Type: level-2
  Manual area address(es):
    49.0001
```

To verify a NET programmatically, check the two components separately. Given a NET
in the format `AA.BBBB.SSSS.SSSS.SSSS.00`:

```python
parts     = net.split(".")
area_id   = ".".join(parts[:2])    # e.g. "49.0001"
system_id = ".".join(parts[2:5])   # e.g. "0000.0000.0001"
```

IS type is also abbreviated: `level-2` instead of `level-2-only`, `level-1` instead
of `level-1-only`. Strip `-only` from the YAML value before matching against
`show clns protocol` output.

### `isis circuit-type` not enforced on broadcast interfaces — IOL 15.7

On Cisco IOL 15.7, the `isis circuit-type level-1-only` command is accepted
on broadcast (LAN) interfaces of L1/L2 routers but is not enforced at runtime.
The interface operates as `level-1-2` regardless of the configured circuit-type,
forming adjacencies at both levels on the broadcast segment.

Observed behavior:
- `show running-config interface` shows `isis circuit-type level-1-only` absent
  (command not retained) even after configuration push
- `show clns interface` shows `Circuit Type: level-1-2` regardless of intended
  circuit-type
- L2 adjacencies form on the LAN segment between the ABR and L1-only leaf routers

Impact on Module 06: ABR-1's Et0/2 (DIS LAN segment) operates as level-1-2
instead of level-1-only. The IS-IS domain converges correctly and all routes
are present. DIS election, route leaking, and redistribution all function as
designed. This is an IOL limitation only — on physical Cisco hardware,
`isis circuit-type` on broadcast interfaces is fully enforced.

No script or YAML changes required. The verbal script reflects actual IOL
behavior.

---

## 10. Troubleshooting Reference

*(Draft notes and snippets go here.)*

---

## 11. Credential Security *(Draft)*

Network automation scripts require device credentials. There is a three-stage
progression from least secure (lab-only) to most secure (production-grade):

### Stage 1 — Hardcoded Credentials (Lab Only)

Credentials stored directly in the YAML inventory file:

```yaml
default_credentials: &creds
  username: netadmin
  password: admin
```

**Acceptable for:** isolated lab environments with no external access.
**Never use in production.** If the YAML is committed to a public repository,
the credentials are exposed.

In this project, `netadmin` / `admin` are lab-generic credentials used across all
modules. They are safe to commit because the lab is air-gapped from production networks.

### Stage 2 — Environment Variables

Read credentials from the OS environment at runtime:

```python
import os
username = os.environ.get("NET_USERNAME", "netadmin")
password = os.environ.get("NET_PASSWORD", "")
```

Set before running:
```bash
export NET_USERNAME=netadmin
export NET_PASSWORD=admin
python scripts/configure_ospf_advanced.py
```

Credentials are not stored in any file. They must be set in each shell session.

### Stage 3 — Vault Solutions

For production environments, use a dedicated secrets manager:

- **Ansible Vault** — encrypts credential files; decrypted at runtime with a vault
  password. Covered in Modules 10–12.
- **HashiCorp Vault**, **AWS Secrets Manager**, etc. — external vault services for
  enterprise-scale secret management.

---

## 12. OSPF Reference *(Draft)*

### OSPF Area Types

| Area Type | Key Behavior |
|-----------|-------------|
| **Standard** | Accepts all LSA types (1–5, 7 in NSSA). Default. |
| **Stub** | Blocks Type 5 (external) LSAs. ABR injects default route. |
| **Totally Stubby** | Blocks Type 3 (summary) and Type 5 LSAs. ABR injects default route. Cisco proprietary. |
| **NSSA** | Blocks Type 5 LSAs but allows Type 7 (NSSA external) LSAs. ABR converts Type 7 → Type 5 for Area 0. |
| **Totally NSSA** | NSSA + blocks Type 3 LSAs. ABR injects Type 7 default and converts to Type 5. Cisco proprietary. |

### OSPF Route Designations in the Routing Table

| Code | Meaning |
|------|---------|
| `O` | OSPF intra-area route |
| `O IA` | OSPF inter-area route (Type 3 LSA) |
| `O E1` | OSPF external Type 1 (cost = external cost + internal OSPF cost) |
| `O E2` | OSPF external Type 2 (cost = external cost only, default) |
| `O N1` | OSPF NSSA external Type 1 (within NSSA area) |
| `O N2` | OSPF NSSA external Type 2 (within NSSA area, default) |

> `O E2` is the default redistribution type in OSPF. Use `metric-type 1` to get `O E1`
> behavior. `O N1` and `O N2` are the NSSA equivalents — they appear only within the
> NSSA area. The NSSA ABR converts them to Type 5 (`O E1` or `O E2`) for propagation
> into other areas.

---

*NAMS26 — Student Reference Appendix*
