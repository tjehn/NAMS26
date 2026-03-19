# Module 02 — EIGRP Classic Mode
**Automation Tool:** Netmiko  
**Series:** NAMS26 — Network Automation Management Station 2026

---

## 1. Module Objectives

Upon completion of this module, the student will be able to:

- Configure EIGRP (Enhanced Interior Gateway Routing Protocol) Classic Mode on Cisco IOS routers using both manual CLI and Python automation
- Use Netmiko to establish SSH sessions, render device configurations from YAML and Jinja2 templates, and deploy them programmatically
- Implement EIGRP MD5 authentication using key chains on a per-interface basis
- Configure and verify EIGRP route summarization at the interface level
- Demonstrate unequal-cost load balancing using the EIGRP `variance` command
- Validate EIGRP neighbor adjacencies, routing tables, and topology tables using automation-driven verification scripts
- Identify and resolve common EIGRP failure scenarios using structured troubleshooting scripts and CLI commands
- Understand the end-to-end relationship between YAML variable files, Jinja2 templates, and Python automation scripts

**Automation tool introduced in this module:** Netmiko

---

## 2. Lab Topology

> Topology diagram: `diagrams/eigrp_classic.drawio.svg`  
> *(Embed diagram here once exported from draw.io)*

### Device Inventory

| Hostname | Role   | Interface   | IP Address        | Neighbor       |
|----------|--------|-------------|-------------------|----------------|
| R1       | Router | Ethernet0/0 | 10.12.12.1/24     | R2             |
|          |        | Ethernet1/3 | 192.168.1.101/24  | OOB Management |
|          |        | Loopback1   | 10.1.1.1/24       |                |
|          |        | Loopback2   | 10.1.2.1/24       |                |
|          |        | Loopback3   | 11.1.1.1/24       |                |
|          |        | Loopback4   | 150.1.32.1/19     |                |
|          |        | Loopback5   | 150.1.64.1/20     |                |
|          |        | Loopback6   | 150.1.88.1/21     |                |
|          |        | Loopback7   | 150.1.128.1/24    |                |
|          |        | Loopback8   | 101.1.4.1/24      |                |
|          |        | Loopback9   | 101.1.5.1/24      |                |
|          |        | Loopback10  | 101.1.6.1/24      |                |
|          |        | Loopback11  | 101.1.7.1/24      |                |
| R2       | Router | Ethernet0/0 | 10.12.12.2/24     | R1             |
|          |        | Ethernet0/1 | 192.1.23.2/24     | R3             |
|          |        | Ethernet1/3 | 192.168.1.102/24  | OOB Management |
|          |        | Loopback1   | 10.2.2.2/24       |                |
|          |        | Loopback2   | 2.0.0.2/8         |                |
|          |        | Loopback3   | 22.2.2.2/24       |                |
| R3       | Router | Ethernet0/0 | 192.1.23.3/24     | R2             |
|          |        | Ethernet0/1 | 192.1.34.3/24     | R4             |
|          |        | Ethernet1/3 | 192.168.1.103/24  | OOB Management |
|          |        | Loopback1   | 3.0.0.3/8         |                |
|          |        | Loopback2   | 33.3.3.3/24       |                |
|          |        | Loopback3–6 | 203.1.8–11.3/24   |                |
|          |        | Loopback7–14| 210.1.1–8.3/24    |                |
| R4       | Router | Ethernet0/0 | 192.1.34.4/24     | R3             |
|          |        | Ethernet0/1 | 192.1.45.4/24     | R5             |
|          |        | Ethernet0/2 | 192.1.46.4/24     | R6             |
|          |        | Ethernet1/3 | 192.168.1.104/24  | OOB Management |
|          |        | Loopback1   | 4.0.0.4/8         |                |
|          |        | Loopback2   | 44.4.4.4/24       |                |
|          |        | Loopback3–6 | 101.1.8–11.4/24   |                |
| R5       | Router | Ethernet0/0 | 192.1.45.5/24     | R4             |
|          |        | Ethernet0/1 | 192.1.56.5/24     | R6             |
|          |        | Ethernet1/3 | 192.168.1.105/24  | OOB Management |
|          |        | Loopback1   | 5.0.0.5/8         |                |
|          |        | Loopback2   | 55.5.5.5/24       |                |
| R6       | Router | Ethernet0/0 | 192.1.46.6/24     | R4             |
|          |        | Ethernet0/1 | 192.1.56.6/24     | R5             |
|          |        | Ethernet1/3 | 192.168.1.106/24  | OOB Management |
|          |        | Loopback1   | 6.0.0.6/8         |                |
|          |        | Loopback2   | 66.6.6.6/24       |                |

### Topology Notes

All six routers run EIGRP Autonomous System (AS) 100. R1 and R2 are connected via a static EIGRP neighbor relationship over `10.12.12.0/24` with MD5 authentication using key chain `ABC`/`BBB`. R2 and R3 are connected over `192.1.23.0/24` with MD5 authentication using key chain `BC`. R4 sits at the center of the right-hand segment connecting to R3, R5, and R6. The R4–R5 link is set to 25 Mbps bandwidth and the R4–R6 link to 50 Mbps, establishing the conditions for unequal-cost load balancing demonstrations. R5 and R6 are also directly connected via a 5 Mbps link.

EIGRP `passive-interface default` is applied on all routers except R2, which uses explicit passive statements per loopback. All physical routed interfaces are explicitly removed from passive state via `no passive-interface`. OOB management interfaces (`Ethernet1/3`) are excluded from EIGRP entirely.

---

## 3. Tool Overview — Netmiko

Netmiko is an open-source Python library built on top of Paramiko that simplifies SSH connections to network devices. It was created to solve a specific problem: Paramiko provides raw SSH transport but requires significant boilerplate to handle the interactive CLI behavior of network operating systems — timing issues, prompts, paging, and mode changes. Netmiko abstracts all of that into a clean, device-aware interface.

**What problem it solves:** Connecting to a Cisco IOS device via SSH and sending configuration commands requires handling `enable` mode, config mode prompts, terminal length settings, and variable response timing. Netmiko handles all of this automatically once you specify the `device_type`.

**Advantages:**
- Simple, readable API — `ConnectHandler`, `send_command`, `send_config_set`
- Broad multi-vendor support (Cisco IOS, IOS-XE, IOS-XR, NX-OS, Juniper, Arista, and many more)
- Built-in session logging for audit trails and troubleshooting
- Handles SSH timing and prompt detection without manual tuning in most cases
- Low abstraction — output is raw CLI text, giving full visibility into what the device returned

**Limitations:**
- Does not provide structured data output — parsing raw CLI text requires additional libraries (TextFSM, Genie) or manual string handling
- No built-in idempotency — running the same script twice will push the same commands again
- Not designed for large-scale parallel execution across hundreds of devices (use Nornir for that)
- No native configuration rollback or diff capability

**When to use Netmiko vs. alternatives:**

| Scenario | Recommended Tool |
|----------|-----------------|
| Direct SSH config push to a small number of devices | Netmiko |
| Need structured/parsed output (diffs, validation) | NAPALM |
| Large-scale parallel execution across many devices | Nornir |
| Compliance testing and state validation | pyATS/Genie |
| Full infrastructure-as-code with roles and playbooks | Ansible |

In this module, Netmiko is the right tool because the goal is foundational: establish an SSH session, push rendered configuration lines, and save. The directness of Netmiko makes the underlying mechanics visible, which is exactly what a first automation module should demonstrate.

---

## 4. Configuration

### 4.1 Automation Workflow

```
eigrp_classic.yaml  →  eigrp_classic.j2  →  configure_eigrp_classic.py  →  Router
   (variables)           (template)              (Netmiko SSH push)
```

### 4.2 YAML Variable File

**File:** `data/eigrp_classic.yaml`

The YAML file is the single source of truth for all device data in this module. It defines per-device interface addressing, EIGRP process parameters, key chains, authentication, and summarization. Credentials are defined once at the top level using a YAML anchor (`&creds`) and referenced on each device with an alias (`*creds`).

Each device entry includes:

- `hostname` — used by the Jinja2 template to set the router hostname
- `dns_name` — used by all scripts as the SSH connection target, resolved via lab DNS at `192.168.1.12`
- `oob_ip` — documented for reference; not used as a connection target
- `oob_interface` — excluded from EIGRP and physical interface rendering in the template
- `interfaces` — physical interface parameters including IP, bandwidth, and shutdown state
- `loopbacks` — loopback interface addresses
- `eigrp` — EIGRP process block containing AS number, networks, passive interface configuration, key chains, authentication, summarization, and variance

### 4.3 Jinja2 Template

**File:** `templates/eigrp_classic.j2`

The Jinja2 template renders a complete Cisco IOS configuration block from the YAML variable data. It uses `trim_blocks=True` and `lstrip_blocks=True` to produce clean output without extra blank lines. A custom filter `cidr_to_netmask` is registered in `configure_eigrp_classic.py` to convert CIDR prefix lengths (e.g. `/24`) to dotted-decimal subnet masks (e.g. `255.255.255.0`).

Key template behaviors:

- Physical interfaces are rendered for all interfaces except `oob_interface`
- Optional parameters (`bandwidth`, `delay`, `speed`, `duplex`, `mtu`) are only rendered when non-empty
- Key chains are rendered before the EIGRP process block so they exist on the router before authentication is applied
- Authentication supports both a single mapping and a list — handles devices with one or multiple authenticated interfaces
- Summarization is rendered as a separate interface stanza after the EIGRP process block

### 4.4 Python Automation Script

**File:** `scripts/configure_eigrp_classic.py`

```
Usage:
  python configure_eigrp_classic.py                     # deploy to all routers
  python configure_eigrp_classic.py --dry-run           # render configs only, no SSH push
  python configure_eigrp_classic.py --router R1 R2      # target specific routers
  python configure_eigrp_classic.py --dry-run --router R1
```

The script follows this sequence for each target device:

1. Load `eigrp_classic.yaml` and inject default credentials into any device not defining its own
2. Load `eigrp_classic.j2` via Jinja2 `FileSystemLoader` with the `cidr_to_netmask` custom filter registered
3. Render the configuration string for the device
4. Write the rendered config to `configs/<HOSTNAME>_eigrp_classic.cfg`
5. If `--dry-run` is not set, open a Netmiko `ConnectHandler` SSH session to `dns_name`
6. Send each configuration line individually via `send_command` to avoid IOL buffer issues
7. Send `end` and `write memory` to exit config mode and save
8. Write a timestamped session log to `modules/logs/`

A temporary SSH config file is written per connection to suppress host key checking — required in the EVE-NG IOL environment where host keys do not persist across reboots.

### 4.5 CLI Reference Configuration

The following are the manual CLI configurations that the automation script replicates. These serve as the baseline reference for verification and comparison.

**R1**
```
key chain ABC
 key 1
  key-string Cisco123
!
router eigrp 100
 passive-interface default
 no passive-interface Ethernet0/0
 network 10.12.12.0 0.0.0.255
 network 10.1.1.0 0.0.0.255
 network 10.1.2.0 0.0.0.255
 network 11.1.1.0 0.0.0.255
 network 150.1.32.0 0.0.31.255
 network 150.1.64.0 0.0.15.255
 network 150.1.88.0 0.0.7.255
 network 150.1.128.0 0.0.0.255
 network 101.1.4.0 0.0.0.255
 network 101.1.5.0 0.0.0.255
 network 101.1.6.0 0.0.0.255
 network 101.1.7.0 0.0.0.255
 neighbor 10.12.12.2 Ethernet0/0
!
interface Ethernet0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 ABC
 ip summary-address eigrp 100 101.1.4.0 255.255.252.0
```

**R2**
```
key chain BBB
 key 1
  key-string Cisco123
key chain BC
 key 1
  key-string Ccie123
!
router eigrp 100
 passive-interface Loopback1
 passive-interface Loopback2
 passive-interface Loopback3
 network 10.12.12.0 0.0.0.255
 network 192.1.23.0 0.0.0.255
 network 10.2.2.0 0.0.0.255
 network 2.0.0.0 0.255.255.255
 network 22.2.2.0 0.0.0.255
 neighbor 10.12.12.1 Ethernet0/0
!
interface Ethernet0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 BBB
!
interface Ethernet0/1
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 BC
```

**R3**
```
key chain BC
 key 1
  key-string Ccie123
!
router eigrp 100
 passive-interface default
 no passive-interface Ethernet0/0
 no passive-interface Ethernet0/1
 network 192.1.23.0 0.0.0.255
 network 192.1.34.0 0.0.0.255
 network 3.0.0.0 0.255.255.255
 network 33.3.3.0 0.0.0.255
 network 203.1.8.0 0.0.0.255
 network 203.1.9.0 0.0.0.255
 network 203.1.10.0 0.0.0.255
 network 203.1.11.0 0.0.0.255
 network 210.1.1.0 0.0.0.255
 network 210.1.2.0 0.0.0.255
 network 210.1.3.0 0.0.0.255
 network 210.1.4.0 0.0.0.255
 network 210.1.5.0 0.0.0.255
 network 210.1.6.0 0.0.0.255
 network 210.1.7.0 0.0.0.255
 network 210.1.8.0 0.0.0.255
!
interface Ethernet0/0
 ip authentication mode eigrp 100 md5
 ip authentication key-chain eigrp 100 BC
```

**R4**
```
router eigrp 100
 passive-interface default
 no passive-interface Ethernet0/0
 no passive-interface Ethernet0/1
 no passive-interface Ethernet0/2
 network 192.1.34.0 0.0.0.255
 network 192.1.45.0 0.0.0.255
 network 192.1.46.0 0.0.0.255
 network 4.0.0.0 0.255.255.255
 network 44.4.4.0 0.255.255.255
 network 101.1.8.0 0.0.0.255
 network 101.1.9.0 0.0.0.255
 network 101.1.10.0 0.0.0.255
 network 101.1.11.0 0.0.0.255
!
interface Ethernet0/0
 ip summary-address eigrp 100 101.1.8.0 255.255.252.0
```

**R5**
```
router eigrp 100
 auto-summary
 passive-interface default
 no passive-interface Ethernet0/0
 no passive-interface Ethernet0/1
 network 192.1.45.0 0.0.0.255
 network 192.1.56.0 0.0.0.255
 network 5.0.0.0 0.255.255.255
 network 55.5.5.0 0.0.0.255
```

**R6**
```
router eigrp 100
 auto-summary
 passive-interface default
 no passive-interface Ethernet0/0
 no passive-interface Ethernet0/1
 network 192.1.46.0 0.0.0.255
 network 192.1.56.0 0.0.0.255
 network 6.0.0.0 0.255.255.255
 network 66.6.6.0 0.0.0.255
```

---

## 5. Verification

### 5.1 Automation-Driven Verification

**File:** `scripts/verify_eigrp_classic.py`

```
Usage:
  python verify_eigrp_classic.py                        # all routers, all checks
  python verify_eigrp_classic.py --router R1 R2         # specific routers
  python verify_eigrp_classic.py --check neighbors      # specific check
  python verify_eigrp_classic.py --check neighbors routes
  python verify_eigrp_classic.py --route 101.1.4.0      # filtered route lookup
  python verify_eigrp_classic.py --list-checks          # show available checks
```

**Available checks:**

| Check | Command | Validation Logic |
|-------|---------|-----------------|
| `neighbors` | `show ip eigrp neighbors` | Cross-references `static_neighbors` in YAML against live output. PASS if all expected neighbor IPs are present. |
| `interfaces` | `show ip eigrp interfaces` | Informational display. Compares active interfaces against `no_passive_interfaces` in YAML. |
| `routes` | `show ip route eigrp` | Cross-references EIGRP `networks` in YAML against live routing table. WARN for locally sourced prefixes. |
| `--route <IP>` | `show ip route \| include <IP>` | Spot-check reachability to a specific prefix or host. |

### 5.2 Expected Output — Neighbors (R1)

```
============================================================
  Device : R1   DNS : r1.lab   OOB : 192.168.1.101/24
============================================================

  ──────────────────────────────────────────────────────
  EIGRP Neighbors — show ip eigrp neighbors
  ──────────────────────────────────────────────────────

IP-EIGRP neighbors for process 100
H   Address         Interface   Hold Uptime    SRTT  RTO   Q  Seq
                                (sec)          (ms)       Cnt Num
0   10.12.12.2      Et0/0       11   00:04:23  1     200   0  12

  [PASS] Neighbor 10.12.12.2 (Ethernet0/0) — PRESENT
```

### 5.3 Manual CLI Verification Commands

```
show ip eigrp neighbors
show ip eigrp neighbors detail
show ip eigrp interfaces
show ip eigrp interfaces detail
show ip route eigrp
show ip eigrp topology
show ip eigrp topology all-links
show ip protocols
show key chain
show run | section router eigrp
show run | section key chain
show run | section interface
```

---

## 6. Troubleshooting

### 6.1 Automation-Assisted Troubleshooting

**File:** `scripts/troubleshoot_eigrp_classic.py`

```
Usage:
  python troubleshoot_eigrp_classic.py                          # all routers, all checks
  python troubleshoot_eigrp_classic.py --router R1              # specific router
  python troubleshoot_eigrp_classic.py --check authentication   # specific check
  python troubleshoot_eigrp_classic.py --demo-failure wrong-as  # failure demo (no router changes)
  python troubleshoot_eigrp_classic.py --list-checks            # show live checks
  python troubleshoot_eigrp_classic.py --list-failures          # show failure scenarios
```

**Live troubleshooting checks:**

| Check | Commands Run | What It Looks For |
|-------|-------------|-------------------|
| `neighbors` | `show ip eigrp neighbors detail` | Neighbors stuck in INIT, missing expected neighbors |
| `authentication` | `show ip eigrp interfaces detail`, `show key chain` | Auth failure counters, missing key chains |
| `passive` | `show ip protocols` | Active interfaces incorrectly listed as passive |
| `routes` | `show ip route eigrp`, `show ip eigrp topology` | Missing routes, active (reconverging) topology entries |
| `process` | `show ip protocols` | EIGRP AS number mismatch, process not running |

**Failure demonstration scenarios** (`--demo-failure`):

| Scenario | Description |
|----------|-------------|
| `missing-keychain` | Key chain definition removed — authentication fails silently |
| `keychain-mismatch` | Key chain name referenced in authentication does not match defined name |
| `wrong-as` | EIGRP AS number changed — neighbors use different AS, adjacency never forms |
| `passive-active` | Active interface moved to passive — neighbor times out with no error |
| `missing-network` | Network statement removed — prefix disappears from topology table |

Each `--demo-failure` run injects the fault into an in-memory copy of the YAML data, renders both the correct and broken configurations, diffs them side by side, and walks through the CLI symptoms and fix. No changes are pushed to any router.

### 6.2 Common Failure Scenarios

**Neighbor adjacency not forming**

The most common causes in this topology are authentication misconfiguration and passive interface errors. Check `show ip eigrp neighbors detail` first — a neighbor stuck in INIT state almost always indicates an authentication failure. Zero neighbors with no INIT state typically indicates a passive interface or missing network statement. Verify with `show ip protocols` to confirm which interfaces are passive and which AS number the process is running.

**Authentication failures**

EIGRP MD5 authentication failures are silent — the neighbor simply does not appear. The key chain name referenced under `ip authentication key-chain eigrp 100 <name>` must exactly match the name defined in the `key chain` block. Key strings must also match on both ends of the link. Use `show ip eigrp interfaces detail` to view authentication send and receive counters — non-zero failure counters confirm the problem is authentication-related.

**Routes missing from routing table**

If a prefix is missing from `show ip route eigrp` on a remote router, verify the originating router has the correct `network` statement in the EIGRP process. Use `show ip eigrp topology` on the router that should be receiving the route to confirm whether it appears in the topology table at all. If it is absent from the topology table, the problem is at the source. If it is in the topology table but not the routing table, check for a feasibility condition failure.

**Summarization not appearing**

Route summarization with `ip summary-address eigrp` is applied at the interface level, not inside the EIGRP process block. Verify the summary command is present on the correct outbound interface using `show run | section interface`. The summary route will appear as a Null0 entry in the local routing table when active.

### 6.3 CLI Troubleshooting Reference

```
show ip eigrp neighbors
show ip eigrp neighbors detail
show ip eigrp interfaces detail
show ip eigrp topology
show ip eigrp topology all-links
show ip protocols
show key chain
debug eigrp packets
debug ip routing
```

---

## 7. Verbal Script

> See `verbal_script/eigrp_classic_verbal.md`

---

## File Index

| File | Location | Purpose |
|------|----------|---------|
| `eigrp_classic.yaml` | `data/` | Device variable data — single source of truth |
| `eigrp_classic.j2` | `templates/` | Jinja2 configuration template |
| `configure_eigrp_classic.py` | `scripts/` | YAML → Jinja2 → Netmiko deployment script |
| `verify_eigrp_classic.py` | `scripts/` | Automated EIGRP state verification |
| `troubleshoot_eigrp_classic.py` | `scripts/` | Live troubleshooting and failure demonstration |
| `R1–R6_eigrp_classic.cfg` | `configs/` | Rendered per-device configurations |
| `eigrp_classic.drawio` | `diagrams/` | Editable topology source file |
| `eigrp_classic.drawio.svg` | `diagrams/` | SVG topology for Markdown embedding |
| `check_ssh.py` | `utils/` | Pre-flight SSH connectivity check |
| `ping_hosts.py` | `utils/` | Pre-flight ICMP reachability check |
| `clear_known_hosts.sh` | `utils/` | Clears stale SSH host keys after lab reboot |

---

## Lab Preparation Sequence

```
# 1. After every EVE-NG lab reboot — clear stale SSH host keys
bash utils/clear_known_hosts.sh

# 2. Confirm L3 reachability to all nodes
python utils/ping_hosts.py

# 3. Confirm SSH is up on all nodes
python utils/check_ssh.py

# 4. Dry-run — render configs and review before pushing
python scripts/configure_eigrp_classic.py --dry-run

# 5. Deploy configuration to all routers
python scripts/configure_eigrp_classic.py

# 6. Verify EIGRP state
python scripts/verify_eigrp_classic.py

# 7. Troubleshoot if needed
python scripts/troubleshoot_eigrp_classic.py
```
