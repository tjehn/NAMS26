# Module 02 — EIGRP Classic Mode / Netmiko
## Planning Document — `module02_planning.md`
### NAMS26 | Network Automation Management Station 2026

---

> **Document Purpose**
> This is the planning document for Module 02. It describes the topology,
> learning objectives, and the design of all scripts.
>
> **Audience:** CCNP-level. Routing protocol mechanics are assumed knowledge.
> The focus is on what the automation scripts need to do, not on explaining EIGRP.
>
> **Status:** Complete.

---

## Module Objectives

By the end of Module 02, the following will be in place:

1. **EIGRP AS 100 deployed** across six routers from a YAML source of truth via Netmiko.
2. **MD5 authentication configured** using key chains on R1, R2, and R3 — per-interface, with different key chain names on different segments.
3. **Static EIGRP neighbor relationships** configured between R1 and R2 over `10.12.12.0/24`.
4. **Passive interface behavior demonstrated** — `passive-interface default` with explicit `no passive-interface` for active links, and per-loopback passive statements on R2.
5. **Route summarization configured** at the interface level — R1 summarizing `101.1.4.0/22` outbound on Ethernet0/0, R4 summarizing `101.1.8.0/22` outbound on Ethernet0/0.
6. **Unequal-cost load balancing demonstrated** — R4-R5 link at 25 Mbps, R4-R6 link at 50 Mbps, R5-R6 link at 5 Mbps, establishing the conditions for `variance` demonstration.
7. **Verification script operational** — validates neighbor adjacency state, active interfaces, and route presence across all six routers.
8. **Troubleshooting script operational** — live checks for authentication failures, passive interface issues, and missing routes, plus five failure demonstration scenarios.
9. **Three-file workflow established** — YAML source of truth → Jinja2 template → Python script pattern introduced and used by all subsequent modules.

---

## Lab Topology

### Routers and Roles

| Router | Role | Notes |
|--------|------|-------|
| R1 | Router | Left edge — heavy loopback pool, static neighbor to R2 |
| R2 | Router | Hub — connects R1 and R3, two authenticated segments |
| R3 | Router | Large loopback pool — 16 loopbacks |
| R4 | Router | Center right — connects R3, R5, R6 |
| R5 | Router | Right — dual-homed to R4 and R6 |
| R6 | Router | Right — dual-homed to R4 and R5 |

### Links

| Segment | Subnet | Routers | Notes |
|---------|--------|---------|-------|
| 10.12.12.0/24 | R1, R2 | MD5 auth, static neighbor |
| 192.1.23.0/24 | R2, R3 | MD5 auth |
| 192.1.34.0/24 | R3, R4 | No auth |
| 192.1.45.0/24 | R4, R5 | 25 Mbps bandwidth |
| 192.1.46.0/24 | R4, R6 | 50 Mbps bandwidth |
| 192.1.56.0/24 | R5, R6 | 5 Mbps bandwidth |

### Loopbacks

| Router | Loopbacks | IPs | Notes |
|--------|-----------|-----|-------|
| R1 | Lo1–Lo11 | 10.1.1.1/24, 10.1.2.1/24, 11.1.1.1/24, 150.1.32.1/19, 150.1.64.1/20, 150.1.88.1/21, 150.1.128.1/24, 101.1.4.1–101.1.7.1 /24 | Summarized 101.1.4.0/22 outbound |
| R2 | Lo1–Lo3 | 10.2.2.2/24, 2.0.0.2/8, 22.2.2.2/24 | Explicitly passive per-loopback |
| R3 | Lo1–Lo14 | 3.0.0.3/8, 33.3.3.3/24, 203.1.8–11.3/24, 210.1.1–8.3/24 | Large pool |
| R4 | Lo1–Lo6 | 4.0.0.4/8, 44.4.4.4/24, 101.1.8–11.4/24 | Summarized 101.1.8.0/22 outbound |
| R5 | Lo1–Lo2 | 5.0.0.5/8, 55.5.5.5/24 | |
| R6 | Lo1–Lo2 | 6.0.0.6/8, 66.6.6.6/24 | |

---

## Key Configuration Elements

### Authentication

EIGRP MD5 authentication uses key chains. Key chain names must match exactly on
both ends of a link — not the key string, the key chain name.

| Segment | Key Chain | Key String | Routers |
|---------|-----------|------------|---------|
| 10.12.12.0/24 | `ABC` (R1) / `BBB` (R2) | `Cisco123` | R1, R2 |
| 192.1.23.0/24 | `BC` | `Ccie123` | R2, R3 |

> Note: R1 uses key chain `ABC`, R2 uses key chain `BBB` on the same segment.
> The key strings match — the key chain names intentionally differ to demonstrate
> that it is the key string, not the key chain name, that must match for
> authentication to succeed.

Authentication is applied per-interface:
```
interface Ethernet0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 ABC
```

### Passive Interface Configuration

Two models demonstrated:

**`passive-interface default` + `no passive-interface`** (R1, R3, R4, R5, R6):
```
router eigrp 100
 passive-interface default
 no passive-interface Ethernet0/0
```
All interfaces are passive by default. Active interfaces are explicitly unblocked.

**Explicit per-loopback passive** (R2):
```
router eigrp 100
 passive-interface Loopback1
 passive-interface Loopback2
 passive-interface Loopback3
```
R2 does not use `passive-interface default` — loopbacks are listed individually.

### Static Neighbor Relationship

R1 and R2 use a static neighbor relationship over `10.12.12.0/24`:
```
router eigrp 100
 neighbor 10.12.12.2 Ethernet0/0   ! on R1
 neighbor 10.12.12.1 Ethernet0/0   ! on R2
```
Static neighbors suppress multicast hellos on the interface. Both sides must
configure the static neighbor statement.

### Route Summarization

Applied at the interface level, not inside the EIGRP process block:

```
interface Ethernet0/0
 ip summary-address eigrp 100 101.1.4.0 255.255.252.0   ! R1
 ip summary-address eigrp 100 101.1.8.0 255.255.252.0   ! R4
```

R1 summarizes its four `101.1.4.x/24` loopbacks into a single `101.1.4.0/22`
advertisement outbound toward R2. R4 summarizes its four `101.1.8.x/24` loopbacks
into `101.1.8.0/22` outbound toward R3.

The summary route appears as a Null0 entry in the local routing table when active.

### Bandwidth and Unequal-Cost Load Balancing

Link bandwidths establish the conditions for `variance` demonstration:

| Link | Bandwidth | EIGRP Metric Impact |
|------|-----------|---------------------|
| R4-R5 (192.1.45.0/24) | 25 Mbps | Higher metric |
| R4-R6 (192.1.46.0/24) | 50 Mbps | Lower metric |
| R5-R6 (192.1.56.0/24) | 5 Mbps | Highest metric |

With `variance 2` on R4, both the R4-R5 and R4-R6 paths are installed in the
routing table for unequal-cost load balancing toward destinations reachable
through both R5 and R6.

---

## Tool: Netmiko

Netmiko is the first automation tool introduced in the NAMS26 series. It provides
direct SSH access to network device CLIs with device-aware prompt handling.

The deployment workflow established in Module 02:

```python
with ConnectHandler(**params) as conn:
    conn.send_config_set(config_lines)
    conn.save_config()
```

**What Netmiko does not provide** (setting up the Module 03 transition):
- No candidate configuration — lines are applied immediately, no preview
- No diff before commit — changes land without a safety checkpoint
- No rollback capability
- Raw CLI text output — no structured parsing

These limitations motivate the move to NAPALM in Module 03.

**Key Netmiko parameters for this lab:**
```python
params = {
    "device_type":         "cisco_ios",
    "host":                dns_name,
    "username":            creds.get("username"),
    "password":            creds.get("password"),
    "global_delay_factor": 2.0,
}
```

---

## Data Model — YAML Design

Module 02 establishes the YAML conventions used by all subsequent modules:

- YAML anchor for credentials at the top (`&creds`), aliased per device (`*creds`)
- `dns_name` as the SSH connection target — never `oob_ip`
- `oob_interface` drives template exclusion of the OOB interface
- Physical interfaces and loopbacks in **separate dictionaries** — `interfaces`
  and `loopbacks` (Module 03 consolidates these into one dict)

### Per-device EIGRP block

```yaml
eigrp:
  as: 100
  passive_default: true          # passive-interface default
  no_passive_interfaces:         # explicitly unblocked
    - Ethernet0/0
  passive_interfaces: []         # explicit per-interface passive (R2)
  networks:
    - network: 10.12.12.0
      wildcard: 0.0.0.255
  static_neighbors:
    - ip: 10.12.12.2
      interface: Ethernet0/0
  key_chains:
    - name: ABC
      keys:
        - id: 1
          string: Cisco123
  authentication:
    - interface: Ethernet0/0
      mode: md5
      key_chain: ABC
  summaries:
    - interface: Ethernet0/0
      prefix: 101.1.4.0
      mask: 255.255.252.0
  variance: 1
  auto_summary: false
```

---

## Template Design — Jinja2

The `eigrp_classic.j2` template renders sections in this order:

1. **Hostname**
2. **Physical interfaces** (excluding OOB) — ip address, bandwidth, speed/duplex
3. **Loopback interfaces** — ip address
4. **Key chains** (if defined) — rendered before the EIGRP process block so
   they exist on the router before authentication references them
5. **EIGRP process block** — AS number, passive interface configuration, network
   statements, static neighbors, variance, auto-summary
6. **Authentication** — per-interface `ip authentication` commands rendered
   as separate interface stanzas after the EIGRP block
7. **Summarization** — per-interface `ip summary-address` commands rendered
   as separate interface stanzas

Key template behaviors:
- Optional parameters (`bandwidth`, `delay`, `speed`, `duplex`, `mtu`) rendered
  only when non-empty
- Authentication supports both single mapping and list — handles single and
  multiple authenticated interfaces per device
- Key chains render before authentication references to satisfy IOS dependency order

---

## Script Design

### `configure_eigrp_classic.py`

- 4-level path resolution from `__file__`
- `--dry-run` and `--router` flags
- Jinja2 environment with `cidr_to_netmask` filter registered
- Netmiko `ConnectHandler` with `send_config_set`
- Per-device session logs to `logs/`
- Rendered configs written to `configs/` on every run

### `verify_eigrp_classic.py`

Checks available via `--check` flag: `neighbors`, `interfaces`, `routes`

**`check_neighbors`** — runs `show ip eigrp neighbors`. Cross-references
`static_neighbors` in YAML against live neighbor table. PASS if all expected
neighbor IPs are present.

**`check_interfaces`** — runs `show ip eigrp interfaces`. Informational display.
Compares active interfaces against `no_passive_interfaces` in YAML.

**`check_routes`** — runs `show ip route eigrp`. Cross-references EIGRP `networks`
in YAML against live routing table. WARN for locally-sourced prefixes.

### `troubleshoot_eigrp_classic.py`

**Live checks:** `neighbors`, `authentication`, `passive`, `routes`, `process`

**`check_neighbors`** — `show ip eigrp neighbors detail`. Neighbors stuck in INIT
indicate authentication failure.

**`check_authentication`** — `show ip eigrp interfaces detail` and `show key chain`.
Authentication send/receive failure counters confirm auth mismatch. Key chain
name and key string must match on both ends of the link.

**`check_passive`** — `show ip protocols`. Active interfaces incorrectly listed
as passive surface here.

**`check_routes`** — `show ip route eigrp` and `show ip eigrp topology`. Missing
routes traced from routing table → topology table → source router.

**`check_process`** — `show ip protocols`. EIGRP AS number mismatch detected here.

**Failure demonstration scenarios:**

| Scenario | Fault Injected | Key Symptom |
|----------|---------------|-------------|
| `missing-keychain` | Key chain definition removed | Authentication fails silently — no neighbor |
| `keychain-mismatch` | Key chain name in auth does not match defined name | Authentication fails — no neighbor |
| `wrong-as` | EIGRP AS number changed | Neighbor never forms — different AS |
| `passive-active` | Active interface moved to passive | Neighbor times out, no error message |
| `missing-network` | Network statement removed | Prefix disappears from topology table |

---

## Closing Demonstration

Module 02 establishes the same closing demonstration pattern used in Modules 03
and 04 — inject a drift, run the troubleshooter, run the verifier, restore.

The specific fault and commands are documented in `docs/module02_closing_demo.md`.

**Instructor talking point established here:** The troubleshooter answers "is
the protocol working?" The verifier answers "does the device match the source
of truth?" This lesson is introduced in Module 02 and reinforced in every
subsequent module.

---

## Comparison to Module 01

| Dimension | Module 01 | Module 02 |
|-----------|-----------|-----------|
| Routers | None (intro) | 6 (R1-R6) |
| Protocol | None | EIGRP AS 100 |
| Tool | None | Netmiko |
| Config model | None | Direct push via send_config_set |
| Authentication | None | MD5 key chains |
| Workflow | None | YAML -> Jinja2 -> Python established |

---

## Lab Reset Sequence (Module 02)

See `docs/eve-ng_lab_reset_sop.md` for the full procedure.

```
# EVE-NG Web UI
Stop all nodes -> Wipe all nodes -> Start all nodes
Open consoles in SecureCRT (R1-R6)

# Each Router via console (R1-R6)
[Apply base configuration: hostname, credentials, Ethernet1/3 OOB, VTY SSH, NTP]
write memory
crypto key generate rsa modulus 1024
write memory

# NAMS26 Workstation - modules/02_eigrp_netmiko/utils/
python ping_hosts.py
bash clear_known_hosts.sh
python init_ssh.py

# NAMS26 Workstation - modules/02_eigrp_netmiko/scripts/
python configure_eigrp_classic.py --dry-run
python configure_eigrp_classic.py
python verify_eigrp_classic.py
```

---

*End of Module 02 Planning Document*
*NAMS26 - Network Automation Management Station 2026*
