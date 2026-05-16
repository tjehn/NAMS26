# Module 07 — BGP Fundamentals / Ansible
## Planning Document
### `docs/module07_planning.md`
### NAMS26 — Network Automation Management Station 2026

---

## Module at a Glance

| Item | Value |
|------|-------|
| Module | 07 |
| Technology | BGP Fundamentals (eBGP, iBGP, Route Reflectors) |
| Tool | Ansible (Introduction) |
| Config Mode | BGP router configuration mode |
| Lab Fabric | Shared fabric — COSW-01 / COSW-02 |
| Router Count | 12 (R1–R12) |
| IGP Underlay | OSPF (Areas 0, 10, 20) |
| Status | PLANNING |

---

## Learning Objectives

By the end of this module, students will be able to:

### BGP Objectives
1. Explain the difference between eBGP and iBGP peering
2. Configure eBGP peering between autonomous systems
3. Configure iBGP peering within an AS — full mesh and route reflector designs
4. Implement BGP authentication using MD5 passwords
5. Demonstrate the need for `update-source loopback` in iBGP peering
6. Demonstrate the need for `next-hop-self` at ASBR routers
7. Configure a Route Reflector to solve the iBGP full mesh scaling problem
8. Use peer groups for configuration efficiency
9. Understand basic BGP path selection (AS_PATH length, NEXT_HOP reachability)
10. Advertise networks into BGP using `network` statements

### Ansible Objectives
1. Understand Ansible architecture — control node, managed nodes, inventory, playbooks
2. Write a basic Ansible playbook with tasks
3. Use the `cisco.ios.ios_config` module to push configuration
4. Use Jinja2 templates in Ansible (`template` module)
5. Organize variables in `group_vars/` and `host_vars/`
6. Use Ansible inventory (YAML format)
7. Use Ansible's `--check` mode for dry-run validation
8. Use `--limit` to target specific devices
9. Use the `cisco.ios.ios_command` module to gather operational state
10. Register command output and use conditionals to verify state

---

## Technology Scope

### What This Module Covers — BGP

- **BGP Overview:** Autonomous systems, path-vector protocol, TCP-based peering
- **eBGP:** External BGP peering between different ASes (AS 65001 ↔ AS 65002 ↔ AS 65003)
- **iBGP:** Internal BGP peering within an AS
  - Full mesh requirement (AS 65002 demonstrates this)
  - Update-source loopback (why loopback peering is needed)
  - Next-hop-self (ASBR behavior for iBGP-learned routes)
- **Route Reflectors:** Solve iBGP full mesh scaling problem (AS 65001 demonstrates single-cluster RR)
- **Peer Groups:** Configuration efficiency — define once, apply to many neighbors
- **BGP Authentication:** MD5 password protection on peering sessions
- **BGP Path Selection:** Basic demonstration — AS_PATH length, NEXT_HOP reachability
- **Network Advertisement:** `network` statements to inject prefixes into BGP

### What This Module Does NOT Cover (Deferred to Modules 08-09)

- Dynamic BGP neighbors (peer templates) → Module 08
- Route Reflector hierarchy (multiple clusters, redundancy) → Module 08
- Confederations → Module 08
- Multi-path load balancing → Module 08
- AS-Path filtering → Module 09
- Prefix-list / route-map filtering → Module 09
- Summarization / aggregation → Module 09
- Conditional advertisement → Module 09
- Communities → Module 09
- Detailed attribute manipulation (LOCAL_PREF, MED, WEIGHT policy) → Module 09

### What This Module Covers — Ansible

- **Ansible Architecture:** Control node (NAMS26 workstation), managed nodes (R1–R12), agentless SSH
- **Inventory:** YAML-based device inventory with groups
- **Playbooks:** YAML playbooks with tasks, plays, modules
- **Modules:**
  - `cisco.ios.ios_config` — push configuration (lines, src template)
  - `cisco.ios.ios_command` — gather show command output
  - `ansible.builtin.template` — render Jinja2 templates (if used separately)
- **Variables:**
  - `group_vars/all.yml` — global variables (credentials, OSPF process)
  - `host_vars/R1.yml` — per-device BGP config data
- **Jinja2 Templates:** `bgp_config.j2` and `ospf_underlay.j2`
- **Check Mode:** `--check` flag for dry-run (compare against running config)
- **Limit Flag:** `--limit R1` to target specific devices
- **Conditionals:** `when:` clauses, `failed_when:`, `changed_when:`
- **Register:** Capture task output for verification

### What This Module Does NOT Cover — Ansible (Deferred to Module 08)

- Roles (defer to Module 08 "Ansible Deepening")
- Handlers (defer to Module 08)
- Ansible Vault (credentials plaintext in Module 07, encrypted in Module 08)
- Advanced loops (`with_items`, `loop`)
- Custom filters
- Ansible Galaxy

---

## Topology Design

### Three-AS Hierarchical Design

**Design rationale:** Module 07 uses a three-AS topology to demonstrate eBGP, iBGP full mesh, and Route Reflector design in a single lab.

| AS Number | Name | Routers | iBGP Design | Role |
|-----------|------|---------|-------------|------|
| AS 65001 | Core AS | R1, R2, R3, R4, R5 | Route Reflector (RR + 4 clients) | Transit provider core |
| AS 65002 | Edge AS | R6, R7, R8, R9 | Full mesh (4 routers) | Edge provider / enterprise |
| AS 65003 | Stub AS | R10, R11, R12 | No iBGP (stub AS, eBGP only) | Customer stub network |

### Router Roster — 12 Devices

| Router | Hostname | Physical | AS | BGP Role | OSPF Area | Notes |
|--------|----------|----------|-----|----------|-----------|-------|
| R1 | CORE-RR1 | R1 | 65001 | Route Reflector | Area 0 | RR for AS 65001, iBGP with R2/R3/R4/R5 |
| R2 | CORE-PE1 | R2 | 65001 | RR Client | Area 0 | iBGP to RR1, eBGP to EDGE-PE1 (R6) |
| R3 | CORE-PE2 | R3 | 65001 | RR Client | Area 0 | iBGP to RR1, eBGP to EDGE-PE2 (R7) |
| R4 | CORE-P1 | R4 | 65001 | RR Client | Area 10 | iBGP to RR1 only (no eBGP peers) |
| R5 | CORE-P2 | R5 | 65001 | RR Client | Area 10 | iBGP to RR1 only (no eBGP peers) |
| R6 | EDGE-PE1 | R6 | 65002 | iBGP Full Mesh | Area 0 | eBGP to CORE-PE1 (R2), iBGP full mesh to R7/R8/R9 |
| R7 | EDGE-PE2 | R7 | 65002 | iBGP Full Mesh | Area 0 | eBGP to CORE-PE2 (R3), iBGP full mesh to R6/R8/R9 |
| R8 | EDGE-P1 | R8 | 65002 | iBGP Full Mesh | Area 20 | eBGP to STUB-BR1 (R10), iBGP full mesh to R6/R7/R9 |
| R9 | EDGE-P2 | R9 | 65002 | iBGP Full Mesh | Area 20 | eBGP to STUB-BR2 (R11), iBGP full mesh to R6/R7/R8 |
| R10 | STUB-BR1 | R10 | 65003 | eBGP only | — | eBGP to EDGE-P1 (R8), no OSPF, no iBGP |
| R11 | STUB-BR2 | R11 | 65003 | eBGP only | — | eBGP to EDGE-P2 (R9), no OSPF, no iBGP |
| R12 | STUB-BR3 | R12 | 65003 | eBGP only | — | eBGP to EDGE-P2 (R9), no OSPF, no iBGP |

**Notes:**
- **AS 65001 (CORE):** Route Reflector design — CORE-RR1 is the RR, all other routers are RR clients. No iBGP full mesh required.
- **AS 65002 (EDGE):** Full mesh iBGP — all 4 routers peer with each other (6 iBGP sessions total). This demonstrates the scaling problem that RR solves.
- **AS 65003 (STUB):** No iBGP — routers are not meshed. Each router only has eBGP peering to AS 65002. This is a simple stub AS (customer site).

### OSPF Underlay Design

OSPF provides reachability for iBGP NEXT_HOP (loopback-to-loopback peering requires IGP).

**AS 65001 OSPF:**
- Area 0: CORE-RR1, CORE-PE1, CORE-PE2
- Area 10: CORE-P1, CORE-P2 (ABRs: CORE-RR1)
- Process ID: 1

**AS 65002 OSPF:**
- Area 0: EDGE-PE1, EDGE-PE2
- Area 20: EDGE-P1, EDGE-P2 (ABRs: EDGE-PE1, EDGE-PE2)
- Process ID: 2

**AS 65003:** No OSPF (stub AS, static routes or connected-only)

---

## Addressing Strategy — RFC 2544 Test Space

Module 07 introduces a realistic addressing design that distinguishes "public" (inter-AS) from "private" (intra-AS) address space:

**RFC 2544 Test Address Space (198.18.0.0/15):**
- Reserved specifically for network testing and benchmarking (RFC 2544)
- Range: `198.18.0.0` through `198.19.255.255`
- Safe to use in lab documentation, videos, screenshots without conflicting with production networks
- Used for:
  - **eBGP peering links** (inter-AS connections)
  - **BGP-advertised loopbacks** (simulates "public" IP space advertised on the internet)

**RFC 1918 Private Address Space (10.0.0.0/8):**
- Used for:
  - **Intra-AS point-to-point links** (IGP underlay within each AS)
  - **OSPF-advertised networks** (internal routing, not advertised into BGP)

**Benefits:**
- **Realistic design** — mirrors real service provider networks (public BGP, private IGP)
- **Visual clarity** — students immediately recognize which IPs are "public-facing" vs "internal"
- **Documentation safety** — RFC 2544 space won't conflict with real public internet addresses
- **Sets pattern for Modules 08-14** — MPLS/VPN modules will use same addressing strategy

**Example:**
- CORE-PE1 loopback: `198.18.0.2/32` (advertised in BGP, simulates public IP)
- CORE-PE1 ↔ CORE-RR1 link: `10.7.10.0/30` (OSPF-only, not in BGP)
- CORE-PE1 ↔ EDGE-PE1 eBGP link: `198.18.11.0/30` (inter-AS peering, simulates public peering)

---

## IP Addressing Plan

### Loopback Addresses

All loopbacks are /32 (host routes). OSPF advertises loopbacks within each AS. BGP advertises loopbacks as "public prefixes" using RFC 2544 test address space (198.18.0.0/15). BGP uses loopbacks as `update-source` and `neighbor` targets for iBGP.

**Addressing design:**
- **Loopback IPs:** RFC 2544 space (198.18.x.x) — simulates "public" prefixes advertised in BGP
- **Intra-AS links:** RFC 1918 space (10.7.x.x) — simulates "private" IGP underlay
- **Inter-AS links:** RFC 2544 space (198.18.x.x) — simulates "public" peering

#### AS 65001 (CORE)

| Router | Hostname | Loopback0 | Advertised in OSPF | Advertised in BGP |
|--------|----------|-----------|-------------------|-------------------|
| R1 | CORE-RR1 | 198.18.0.1/32 | Yes (Area 0) | Yes (`network` statement) |
| R2 | CORE-PE1 | 198.18.0.2/32 | Yes (Area 0) | Yes |
| R3 | CORE-PE2 | 198.18.0.3/32 | Yes (Area 0) | Yes |
| R4 | CORE-P1 | 198.18.0.4/32 | Yes (Area 10) | Yes |
| R5 | CORE-P2 | 198.18.0.5/32 | Yes (Area 10) | Yes |

#### AS 65002 (EDGE)

| Router | Hostname | Loopback0 | Advertised in OSPF | Advertised in BGP |
|--------|----------|-----------|-------------------|-------------------|
| R6 | EDGE-PE1 | 198.18.1.1/32 | Yes (Area 0) | Yes |
| R7 | EDGE-PE2 | 198.18.1.2/32 | Yes (Area 0) | Yes |
| R8 | EDGE-P1 | 198.18.1.3/32 | Yes (Area 20) | Yes |
| R9 | EDGE-P2 | 198.18.1.4/32 | Yes (Area 20) | Yes |

#### AS 65003 (STUB)

| Router | Hostname | Loopback0 | Advertised in OSPF | Advertised in BGP |
|--------|----------|-----------|-------------------|-------------------|
| R10 | STUB-BR1 | 198.18.2.1/32 | No (no OSPF) | Yes (originated locally) |
| R11 | STUB-BR2 | 198.18.2.2/32 | No (no OSPF) | Yes |
| R12 | STUB-BR3 | 198.18.2.3/32 | No (no OSPF) | Yes |

### Point-to-Point Link Addressing

All point-to-point links use /30 subnets. OSPF advertises these networks (in AS 65001 and AS 65002). BGP does NOT advertise transit links (only loopbacks are advertised in BGP).

#### AS 65001 Intra-AS Links (OSPF Area 0 and Area 10)

| Link | Subnet | Left Router | Left IP | Right Router | Right IP | OSPF Area |
|------|--------|-------------|---------|--------------|----------|-----------|
| CORE-RR1 ↔ CORE-PE1 | 10.7.10.0/30 | CORE-RR1 (R1) | .1 | CORE-PE1 (R2) | .2 | 0 |
| CORE-RR1 ↔ CORE-PE2 | 10.7.10.4/30 | CORE-RR1 (R1) | .5 | CORE-PE2 (R3) | .6 | 0 |
| CORE-RR1 ↔ CORE-P1 | 10.7.10.8/30 | CORE-RR1 (R1) | .9 | CORE-P1 (R4) | .10 | 0 (RR1 side), 10 (P1 side) |
| CORE-RR1 ↔ CORE-P2 | 10.7.10.12/30 | CORE-RR1 (R1) | .13 | CORE-P2 (R5) | .14 | 0 (RR1 side), 10 (P2 side) |
| CORE-P1 ↔ CORE-P2 | 10.7.10.16/30 | CORE-P1 (R4) | .17 | CORE-P2 (R5) | .18 | 10 |

**OSPF Area boundary:** CORE-RR1 is an ABR between Area 0 and Area 10.

#### eBGP Inter-AS Links — AS 65001 ↔ AS 65002

These links use RFC 2544 test address space (198.18.x.x) to simulate "public peering" between autonomous systems.

| Link | Subnet | AS 65001 Router | IP | AS 65002 Router | IP | OSPF |
|------|--------|-----------------|----|-----------------|----|------|
| CORE-PE1 ↔ EDGE-PE1 | 198.18.11.0/30 | CORE-PE1 (R2) | .1 | EDGE-PE1 (R6) | .2 | No (inter-AS) |
| CORE-PE2 ↔ EDGE-PE2 | 198.18.11.4/30 | CORE-PE2 (R3) | .5 | EDGE-PE2 (R7) | .6 | No (inter-AS) |

**Note:** eBGP sessions run over directly connected interfaces. No OSPF on these links (they span AS boundaries).

#### AS 65002 Intra-AS Links (OSPF Area 0 and Area 20)

| Link | Subnet | Left Router | Left IP | Right Router | Right IP | OSPF Area |
|------|--------|-------------|---------|--------------|----------|-----------|
| EDGE-PE1 ↔ EDGE-PE2 | 10.7.12.0/30 | EDGE-PE1 (R6) | .1 | EDGE-PE2 (R7) | .2 | 0 |
| EDGE-PE1 ↔ EDGE-P1 | 10.7.12.4/30 | EDGE-PE1 (R6) | .5 | EDGE-P1 (R8) | .6 | 0 (PE1 side), 20 (P1 side) |
| EDGE-PE2 ↔ EDGE-P2 | 10.7.12.8/30 | EDGE-PE2 (R7) | .9 | EDGE-P2 (R9) | .10 | 0 (PE2 side), 20 (P2 side) |
| EDGE-P1 ↔ EDGE-P2 | 10.7.12.12/30 | EDGE-P1 (R8) | .13 | EDGE-P2 (R9) | .14 | 20 |

**OSPF Area boundary:** EDGE-PE1 and EDGE-PE2 are ABRs between Area 0 and Area 20.

#### eBGP Inter-AS Links — AS 65002 ↔ AS 65003

These links use RFC 2544 test address space (198.18.x.x) to simulate "public peering" between autonomous systems.

| Link | Subnet | AS 65002 Router | IP | AS 65003 Router | IP | OSPF |
|------|--------|-----------------|----|-----------------|----|------|
| EDGE-P1 ↔ STUB-BR1 | 198.18.13.0/30 | EDGE-P1 (R8) | .1 | STUB-BR1 (R10) | .2 | No (inter-AS) |
| EDGE-P2 ↔ STUB-BR2 | 198.18.13.4/30 | EDGE-P2 (R9) | .5 | STUB-BR2 (R11) | .6 | No (inter-AS) |
| EDGE-P2 ↔ STUB-BR3 | 198.18.13.8/30 | EDGE-P2 (R9) | .9 | STUB-BR3 (R12) | .10 | No (inter-AS) |

**Note:** AS 65003 routers have no OSPF process. Loopback reachability via static routes or BGP `network` statements only.

---

## BGP Peering Matrix

### eBGP Peering Sessions

All eBGP peering uses RFC 2544 test address space (198.18.x.x) to simulate public internet peering.

| Local Router | Local AS | Local IP | Remote Router | Remote AS | Remote IP | Auth | Notes |
|--------------|----------|----------|---------------|-----------|-----------|------|-------|
| CORE-PE1 (R2) | 65001 | 198.18.11.1 | EDGE-PE1 (R6) | 65002 | 198.18.11.2 | MD5: `eBGP_R2_R6` | Directly connected |
| CORE-PE2 (R3) | 65001 | 198.18.11.5 | EDGE-PE2 (R7) | 65002 | 198.18.11.6 | MD5: `eBGP_R3_R7` | Directly connected |
| EDGE-P1 (R8) | 65002 | 198.18.13.1 | STUB-BR1 (R10) | 65003 | 198.18.13.2 | MD5: `eBGP_R8_R10` | Directly connected |
| EDGE-P2 (R9) | 65002 | 198.18.13.5 | STUB-BR2 (R11) | 65003 | 198.18.13.6 | MD5: `eBGP_R9_R11` | Directly connected |
| EDGE-P2 (R9) | 65002 | 198.18.13.9 | STUB-BR3 (R12) | 65003 | 198.18.13.10 | MD5: `eBGP_R9_R12` | Directly connected |

**eBGP Notes:**
- All eBGP sessions use directly connected interface IPs (no `update-source` needed for eBGP over point-to-point links)
- MD5 authentication on all eBGP sessions
- `next-hop-self` configured on ASBRs (CORE-PE1, CORE-PE2, EDGE-PE1, EDGE-PE2, EDGE-P1, EDGE-P2) for routes advertised into iBGP

### iBGP Peering Sessions — AS 65001 (Route Reflector Design)

iBGP sessions use RFC 2544 loopback addresses (198.18.0.x) as BGP router-IDs and peering endpoints.

| Local Router | Local Loopback | Remote Router | Remote Loopback | Peer Type | Auth | Notes |
|--------------|----------------|---------------|-----------------|-----------|------|-------|
| CORE-RR1 (R1) | 198.18.0.1 | CORE-PE1 (R2) | 198.18.0.2 | RR ↔ Client | MD5: `iBGP_AS65001` | RR session |
| CORE-RR1 (R1) | 198.18.0.1 | CORE-PE2 (R3) | 198.18.0.3 | RR ↔ Client | MD5: `iBGP_AS65001` | RR session |
| CORE-RR1 (R1) | 198.18.0.1 | CORE-P1 (R4) | 198.18.0.4 | RR ↔ Client | MD5: `iBGP_AS65001` | RR session |
| CORE-RR1 (R1) | 198.18.0.1 | CORE-P2 (R5) | 198.18.0.5 | RR ↔ Client | MD5: `iBGP_AS65001` | RR session |

**AS 65001 iBGP Notes:**
- CORE-RR1 is configured as route reflector: `neighbor <ip> route-reflector-client`
- All clients (R2, R3, R4, R5) peer only with CORE-RR1 — no client-to-client iBGP sessions
- All iBGP sessions use loopback IPs with `update-source Loopback0`
- Single shared MD5 password for all iBGP sessions in AS 65001
- Total iBGP sessions in AS 65001: **4** (RR-centric, not full mesh)

### iBGP Peering Sessions — AS 65002 (Full Mesh Design)

iBGP sessions use RFC 2544 loopback addresses (198.18.1.x) as BGP router-IDs and peering endpoints.

| Local Router | Local Loopback | Remote Router | Remote Loopback | Auth | Notes |
|--------------|----------------|---------------|-----------------|------|-------|
| EDGE-PE1 (R6) | 198.18.1.1 | EDGE-PE2 (R7) | 198.18.1.2 | MD5: `iBGP_AS65002` | Full mesh |
| EDGE-PE1 (R6) | 198.18.1.1 | EDGE-P1 (R8) | 198.18.1.3 | MD5: `iBGP_AS65002` | Full mesh |
| EDGE-PE1 (R6) | 198.18.1.1 | EDGE-P2 (R9) | 198.18.1.4 | MD5: `iBGP_AS65002` | Full mesh |
| EDGE-PE2 (R7) | 198.18.1.2 | EDGE-P1 (R8) | 198.18.1.3 | MD5: `iBGP_AS65002` | Full mesh |
| EDGE-PE2 (R7) | 198.18.1.2 | EDGE-P2 (R9) | 198.18.1.4 | MD5: `iBGP_AS65002` | Full mesh |
| EDGE-P1 (R8) | 198.18.1.3 | EDGE-P2 (R9) | 198.18.1.4 | MD5: `iBGP_AS65002` | Full mesh |

**AS 65002 iBGP Notes:**
- Full mesh design — every router peers with every other router
- 4 routers → `n(n-1)/2 = 6` iBGP sessions
- All iBGP sessions use loopback IPs with `update-source Loopback0`
- Single shared MD5 password for all iBGP sessions in AS 65002
- **Pedagogical point:** Students see why full mesh doesn't scale (6 sessions for 4 routers, 10 sessions for 5 routers, etc.)

### iBGP Peering Sessions — AS 65003 (No iBGP)

AS 65003 is a stub AS. No iBGP sessions configured. Each router (R10, R11, R12) only has eBGP peering to AS 65002.

---

## BGP Network Advertisements

### AS 65001 — Network Statements

Each router in AS 65001 advertises its loopback into BGP using RFC 2544 test address space:

| Router | Network Statement | Origin |
|--------|------------------|--------|
| CORE-RR1 (R1) | `network 198.18.0.1 mask 255.255.255.255` | IGP (i) |
| CORE-PE1 (R2) | `network 198.18.0.2 mask 255.255.255.255` | IGP (i) |
| CORE-PE2 (R3) | `network 198.18.0.3 mask 255.255.255.255` | IGP (i) |
| CORE-P1 (R4) | `network 198.18.0.4 mask 255.255.255.255` | IGP (i) |
| CORE-P2 (R5) | `network 198.18.0.5 mask 255.255.255.255` | IGP (i) |

**Result:** All 5 loopbacks are visible throughout AS 65001 via iBGP, and exported to AS 65002 via eBGP (with AS_PATH prepended: 65001).

### AS 65002 — Network Statements

Each router in AS 65002 advertises its loopback into BGP using RFC 2544 test address space:

| Router | Network Statement | Origin |
|--------|------------------|--------|
| EDGE-PE1 (R6) | `network 198.18.1.1 mask 255.255.255.255` | IGP (i) |
| EDGE-PE2 (R7) | `network 198.18.1.2 mask 255.255.255.255` | IGP (i) |
| EDGE-P1 (R8) | `network 198.18.1.3 mask 255.255.255.255` | IGP (i) |
| EDGE-P2 (R9) | `network 198.18.1.4 mask 255.255.255.255` | IGP (i) |

**Result:** All 4 loopbacks visible throughout AS 65002 via iBGP, and exported to AS 65001 (via eBGP at R2/R3) and AS 65003 (via eBGP at R8/R9).

### AS 65003 — Network Statements

Each router in AS 65003 advertises its loopback into BGP using RFC 2544 test address space:

| Router | Network Statement | Origin |
|--------|------------------|--------|
| STUB-BR1 (R10) | `network 198.18.2.1 mask 255.255.255.255` | IGP (i) |
| STUB-BR2 (R11) | `network 198.18.2.2 mask 255.255.255.255` | IGP (i) |
| STUB-BR3 (R12) | `network 198.18.2.3 mask 255.255.255.255` | IGP (i) |

**Result:** Each stub router advertises its loopback into BGP. AS 65002 receives these routes via eBGP. AS 65001 receives them via eBGP from AS 65002 (with AS_PATH: 65002 65003).

---

## Key Design Decisions

### Route Reflector in AS 65001 Only

**Why:** AS 65001 demonstrates the RR solution to iBGP full mesh. AS 65002 intentionally uses full mesh to show the scaling problem. Students can compare the two designs in the same lab.

**Configuration on CORE-RR1 (R1):**
```
router bgp 65001
 neighbor 10.7.0.2 route-reflector-client
 neighbor 10.7.0.3 route-reflector-client
 neighbor 10.7.0.4 route-reflector-client
 neighbor 10.7.0.5 route-reflector-client
```

**Verification:**
- `show ip bgp summary` on CORE-RR1 → 4 iBGP peers (RR clients)
- `show ip bgp` on CORE-PE1 (R2) → sees routes learned from CORE-P1 (R4) via RR reflection (198.18.0.4/32)
- `show ip bgp <prefix>` → ORIGINATOR_ID and CLUSTER_LIST attributes visible on reflected routes

### Next-Hop-Self at ASBRs

**Why:** When CORE-PE1 (R2) learns a route via eBGP from EDGE-PE1 (R6), the NEXT_HOP is set to R6's interface IP (198.18.11.2). This IP is not reachable within AS 65001's IGP. Without `next-hop-self`, iBGP peers in AS 65001 cannot reach the NEXT_HOP and will not install the route.

**Configuration on all ASBRs:**
- CORE-PE1 (R2): `neighbor 198.18.0.1 next-hop-self` (toward RR)
- CORE-PE2 (R3): `neighbor 198.18.0.1 next-hop-self` (toward RR)
- EDGE-PE1 (R6): `neighbor <iBGP peers> next-hop-self` (toward R7/R8/R9)
- EDGE-PE2 (R7): `neighbor <iBGP peers> next-hop-self` (toward R6/R8/R9)
- EDGE-P1 (R8): `neighbor <iBGP peers> next-hop-self` (toward R6/R7/R9)
- EDGE-P2 (R9): `neighbor <iBGP peers> next-hop-self` (toward R6/R7/R8)

**Verification:**
- Before `next-hop-self`: `show ip bgp` on CORE-P1 (R4) shows AS 65002 routes with unreachable NEXT_HOP (198.18.11.x)
- After `next-hop-self`: `show ip bgp` on CORE-P1 shows AS 65002 routes with NEXT_HOP = CORE-PE1 loopback (198.18.0.2)

### Peer Groups for Configuration Efficiency

**Why:** Defining a peer group once and applying it to multiple neighbors reduces configuration repetition.

**Example on CORE-RR1 (R1):**
```
router bgp 65001
 neighbor IBGP_CLIENTS peer-group
 neighbor IBGP_CLIENTS remote-as 65001
 neighbor IBGP_CLIENTS update-source Loopback0
 neighbor IBGP_CLIENTS password iBGP_AS65001
 neighbor IBGP_CLIENTS route-reflector-client
 !
 neighbor 198.18.0.2 peer-group IBGP_CLIENTS
 neighbor 198.18.0.3 peer-group IBGP_CLIENTS
 neighbor 198.18.0.4 peer-group IBGP_CLIENTS
 neighbor 198.18.0.5 peer-group IBGP_CLIENTS
```

**Same pattern applies to AS 65002 full mesh (define peer group, apply to all iBGP neighbors).**

### MD5 Authentication

**Why:** Protects BGP sessions from spoofing and unauthorized peering.

**Passwords:**
- eBGP sessions: unique per peering (e.g., `eBGP_R2_R6`, `eBGP_R3_R7`, etc.)
- iBGP sessions within AS: shared password per AS (e.g., `iBGP_AS65001`, `iBGP_AS65002`)

**Configuration:**
```
router bgp 65001
 neighbor 198.18.11.2 password eBGP_R2_R6
```

**Verification:**
- `show ip bgp summary` → peer state should be `Established`
- Wrong password → peer state stuck in `Active` or `Idle`
- `debug ip bgp` or `debug ip tcp transactions` shows MD5 signature mismatch

### OSPF Underlay — Areas and ABRs

**AS 65001:**
- Area 0: CORE-RR1, CORE-PE1, CORE-PE2
- Area 10: CORE-P1, CORE-P2
- ABR: CORE-RR1 (connects Area 0 and Area 10)

**AS 65002:**
- Area 0: EDGE-PE1, EDGE-PE2
- Area 20: EDGE-P1, EDGE-P2
- ABRs: EDGE-PE1, EDGE-PE2 (both connect Area 0 and Area 20)

**Why these areas?** Demonstrates multi-area OSPF for students who completed Modules 03-04. The area design is simple enough to not distract from BGP, but realistic enough to show IGP/BGP interaction.

### No OSPF in AS 65003

**Why:** AS 65003 is a stub AS with no iBGP. No IGP is needed. Each router (R10, R11, R12) advertises its loopback into BGP via `network` statement. Reachability between AS 65003 routers (if needed for future modules) can be handled via static routes or BGP-learned routes.

---

## Ansible Implementation Plan

### Directory Structure

Module 07 uses **flat playbooks + templates** (no roles). Roles are deferred to Module 08 ("Ansible Deepening").

```
ansible/
├── ansible.cfg                   # Ansible configuration
├── inventory/
│   └── module07_bgp.yml          # YAML inventory (all 12 routers)
├── group_vars/
│   └── all.yml                   # Global variables (credentials, OSPF process ID)
├── host_vars/
│   ├── CORE-RR1.yml              # Per-device BGP + OSPF config data
│   ├── CORE-PE1.yml
│   ├── CORE-PE2.yml
│   ├── CORE-P1.yml
│   ├── CORE-P2.yml
│   ├── EDGE-PE1.yml
│   ├── EDGE-PE2.yml
│   ├── EDGE-P1.yml
│   ├── EDGE-P2.yml
│   ├── STUB-BR1.yml
│   ├── STUB-BR2.yml
│   └── STUB-BR3.yml
├── playbooks/
│   ├── configure_bgp.yml         # Deploy BGP + OSPF config
│   ├── verify_bgp.yml            # Verify BGP state (neighbors, routes)
│   └── troubleshoot_bgp.yml      # Troubleshoot BGP operational state
└── templates/
    ├── bgp_config.j2             # BGP configuration template
    └── ospf_underlay.j2          # OSPF underlay template
```

### Inventory File — `inventory/module07_bgp.yml`

```yaml
---
all:
  children:
    core_as:
      hosts:
        CORE-RR1:
          ansible_host: core-rr1.lab
        CORE-PE1:
          ansible_host: core-pe1.lab
        CORE-PE2:
          ansible_host: core-pe2.lab
        CORE-P1:
          ansible_host: core-p1.lab
        CORE-P2:
          ansible_host: core-p2.lab
    edge_as:
      hosts:
        EDGE-PE1:
          ansible_host: edge-pe1.lab
        EDGE-PE2:
          ansible_host: edge-pe2.lab
        EDGE-P1:
          ansible_host: edge-p1.lab
        EDGE-P2:
          ansible_host: edge-p2.lab
    stub_as:
      hosts:
        STUB-BR1:
          ansible_host: stub-br1.lab
        STUB-BR2:
          ansible_host: stub-br2.lab
        STUB-BR3:
          ansible_host: stub-br3.lab
  vars:
    ansible_network_os: ios
    ansible_connection: network_cli
```

**Groups:**
- `core_as` → AS 65001 routers
- `edge_as` → AS 65002 routers
- `stub_as` → AS 65003 routers

### Group Variables — `group_vars/all.yml`

```yaml
---
# Global credentials (plaintext for Module 07, vault in Module 08)
ansible_user: netadmin
ansible_password: admin

# OSPF process IDs per AS
ospf_process_id_as65001: 1
ospf_process_id_as65002: 2

# BGP AS numbers
bgp_as_core: 65001
bgp_as_edge: 65002
bgp_as_stub: 65003
```

### Host Variables — Example `host_vars/CORE-RR1.yml`

```yaml
---
hostname: CORE-RR1

# Loopback (RFC 2544 test address space for BGP)
loopback0_ip: 198.18.0.1
loopback0_mask: 255.255.255.255

# Interfaces
interfaces:
  - name: Ethernet0/0
    description: "to CORE-PE1"
    ip: 10.7.10.1
    mask: 255.255.255.252
    ospf_area: 0
  - name: Ethernet0/1
    description: "to CORE-PE2"
    ip: 10.7.10.5
    mask: 255.255.255.252
    ospf_area: 0
  - name: Ethernet0/2
    description: "to CORE-P1"
    ip: 10.7.10.9
    mask: 255.255.255.252
    ospf_area: 0
  - name: Ethernet0/3
    description: "to CORE-P2"
    ip: 10.7.10.13
    mask: 255.255.255.252
    ospf_area: 0

# OSPF
ospf_process_id: 1
ospf_router_id: 198.18.0.1

# BGP
bgp_as: 65001
bgp_router_id: 198.18.0.1

# BGP Networks
bgp_networks:
  - network: 198.18.0.1
    mask: 255.255.255.255

# iBGP Neighbors (RR clients)
ibgp_neighbors:
  - ip: 198.18.0.2
    peer_group: IBGP_CLIENTS
  - ip: 198.18.0.3
    peer_group: IBGP_CLIENTS
  - ip: 198.18.0.4
    peer_group: IBGP_CLIENTS
  - ip: 198.18.0.5
    peer_group: IBGP_CLIENTS

# Peer Group Definition
bgp_peer_groups:
  - name: IBGP_CLIENTS
    remote_as: 65001
    update_source: Loopback0
    password: iBGP_AS65001
    route_reflector_client: true

# eBGP Neighbors (none for RR1)
ebgp_neighbors: []
```

**Similar structure for all 12 routers** — each `host_vars/<hostname>.yml` defines interfaces, OSPF, BGP neighbors, networks, etc.

### Playbook — `playbooks/configure_bgp.yml`

```yaml
---
- name: Configure BGP and OSPF Underlay
  hosts: all
  gather_facts: no
  tasks:
    - name: Configure OSPF underlay
      cisco.ios.ios_config:
        src: ../templates/ospf_underlay.j2
      when: ospf_process_id is defined

    - name: Configure BGP
      cisco.ios.ios_config:
        src: ../templates/bgp_config.j2

    - name: Save configuration
      cisco.ios.ios_command:
        commands:
          - write memory
```

**Usage:**
```bash
# Dry-run (check mode) — compare rendered config to running config
ansible-playbook playbooks/configure_bgp.yml --check --diff

# Deploy to all routers
ansible-playbook playbooks/configure_bgp.yml

# Deploy to specific router
ansible-playbook playbooks/configure_bgp.yml --limit CORE-RR1

# Deploy to specific group
ansible-playbook playbooks/configure_bgp.yml --limit core_as
```

### Playbook — `playbooks/verify_bgp.yml`

```yaml
---
- name: Verify BGP Neighbors and Routes
  hosts: all
  gather_facts: no
  tasks:
    - name: Check BGP summary
      cisco.ios.ios_command:
        commands:
          - show ip bgp summary
      register: bgp_summary

    - name: Display BGP summary
      debug:
        var: bgp_summary.stdout_lines

    - name: Check BGP neighbor state
      cisco.ios.ios_command:
        commands:
          - show ip bgp summary | include Established
      register: bgp_neighbors
      failed_when: "'Established' not in bgp_neighbors.stdout[0]"

    - name: Check BGP routes
      cisco.ios.ios_command:
        commands:
          - show ip bgp
      register: bgp_routes

    - name: Display BGP routes
      debug:
        var: bgp_routes.stdout_lines

    - name: Verify expected prefix count
      assert:
        that:
          - bgp_routes.stdout[0] | regex_findall('198.18.') | length >= expected_prefix_count
        fail_msg: "BGP table has fewer prefixes than expected"
        success_msg: "BGP table has expected prefix count"
      when: expected_prefix_count is defined
```

**Usage:**
```bash
# Verify all routers
ansible-playbook playbooks/verify_bgp.yml

# Verify specific router
ansible-playbook playbooks/verify_bgp.yml --limit CORE-PE1
```

### Playbook — `playbooks/troubleshoot_bgp.yml`

```yaml
---
- name: Troubleshoot BGP Operational State
  hosts: all
  gather_facts: no
  tasks:
    - name: Check BGP neighbor details
      cisco.ios.ios_command:
        commands:
          - show ip bgp neighbors
      register: bgp_neighbor_detail

    - name: Display neighbor details
      debug:
        var: bgp_neighbor_detail.stdout_lines

    - name: Check for BGP authentication failures
      cisco.ios.ios_command:
        commands:
          - show ip bgp summary
      register: auth_check
      failed_when: "'Active' in auth_check.stdout[0] or 'Idle' in auth_check.stdout[0]"
      ignore_errors: yes

    - name: Report authentication issues
      debug:
        msg: "WARNING: BGP peer in Active or Idle state — possible authentication mismatch"
      when: auth_check is failed

    - name: Check BGP next-hop reachability
      cisco.ios.ios_command:
        commands:
          - show ip route | include 198.18.
      register: route_check

    - name: Display routing table
      debug:
        var: route_check.stdout_lines
```

### Jinja2 Template — `templates/bgp_config.j2`

```jinja2
!
router bgp {{ bgp_as }}
 bgp router-id {{ bgp_router_id }}
 bgp log-neighbor-changes
 !
{% if bgp_peer_groups is defined %}
{% for pg in bgp_peer_groups %}
 neighbor {{ pg.name }} peer-group
 neighbor {{ pg.name }} remote-as {{ pg.remote_as }}
 neighbor {{ pg.name }} update-source {{ pg.update_source }}
{% if pg.password is defined %}
 neighbor {{ pg.name }} password {{ pg.password }}
{% endif %}
{% if pg.route_reflector_client is defined and pg.route_reflector_client %}
 neighbor {{ pg.name }} route-reflector-client
{% endif %}
{% if pg.next_hop_self is defined and pg.next_hop_self %}
 neighbor {{ pg.name }} next-hop-self
{% endif %}
 !
{% endfor %}
{% endif %}
{% if ibgp_neighbors is defined %}
{% for neighbor in ibgp_neighbors %}
 neighbor {{ neighbor.ip }} peer-group {{ neighbor.peer_group }}
{% endfor %}
{% endif %}
{% if ebgp_neighbors is defined %}
{% for neighbor in ebgp_neighbors %}
 neighbor {{ neighbor.ip }} remote-as {{ neighbor.remote_as }}
{% if neighbor.password is defined %}
 neighbor {{ neighbor.ip }} password {{ neighbor.password }}
{% endif %}
{% if neighbor.next_hop_self is defined and neighbor.next_hop_self %}
 neighbor {{ neighbor.ip }} next-hop-self
{% endif %}
{% endfor %}
{% endif %}
 !
 address-family ipv4
{% if ibgp_neighbors is defined %}
{% for neighbor in ibgp_neighbors %}
  neighbor {{ neighbor.ip }} activate
{% endfor %}
{% endif %}
{% if ebgp_neighbors is defined %}
{% for neighbor in ebgp_neighbors %}
  neighbor {{ neighbor.ip }} activate
{% endfor %}
{% endif %}
{% if bgp_networks is defined %}
{% for net in bgp_networks %}
  network {{ net.network }} mask {{ net.mask }}
{% endfor %}
{% endif %}
 exit-address-family
!
```

### Jinja2 Template — `templates/ospf_underlay.j2`

```jinja2
!
router ospf {{ ospf_process_id }}
 router-id {{ ospf_router_id }}
 passive-interface Loopback0
!
interface Loopback0
 ip ospf {{ ospf_process_id }} area 0
!
{% for intf in interfaces %}
{% if intf.ospf_area is defined %}
interface {{ intf.name }}
 ip ospf {{ ospf_process_id }} area {{ intf.ospf_area }}
{% endif %}
{% endfor %}
!
```

---

## Ansible Introduction — Teaching Points

Module 07 is the **first Ansible module**. The verbal script and demonstrations must introduce Ansible concepts clearly:

### Core Concepts to Cover

1. **Ansible Architecture:**
   - Control node (NAMS26 workstation) — where playbooks run
   - Managed nodes (R1–R12) — devices being configured
   - Agentless — uses SSH, no software installed on routers

2. **Inventory:**
   - YAML format
   - Groups (core_as, edge_as, stub_as)
   - `ansible_host` variable maps inventory name to DNS name

3. **Playbooks:**
   - YAML syntax (key: value, lists, dictionaries)
   - Plays (target host group, tasks)
   - Tasks (name, module, parameters)

4. **Modules:**
   - `cisco.ios.ios_config` — push configuration (lines or template)
   - `cisco.ios.ios_command` — run show commands
   - Return values (stdout, stdout_lines)

5. **Variables:**
   - `group_vars/all.yml` — global variables
   - `host_vars/<hostname>.yml` — per-device variables
   - Jinja2 references in templates: `{{ variable_name }}`

6. **Templates:**
   - Jinja2 syntax (variables, loops, conditionals)
   - `{% for %}` loops for repeated config blocks
   - `{% if %}` conditionals for optional config

7. **Check Mode:**
   - `--check` flag for dry-run
   - `--diff` shows what would change
   - Safe testing before live deployment

8. **Limit Flag:**
   - `--limit <hostname>` targets one device
   - `--limit <group>` targets a group
   - Selective deployment

9. **Registered Variables:**
   - `register: variable_name` captures task output
   - Use in subsequent tasks (debug, conditionals, assertions)

10. **Conditionals:**
    - `when:` clause
    - `failed_when:` custom failure conditions
    - `changed_when:` suppress change state

---

## Closing Demo Plan

The closing demo demonstrates the automation story — how Ansible detects and repairs config drift.

### Demo Sequence

**Beat 1 — Clean State Verify**

Run verify playbook against all routers. All BGP neighbors Established. All routes present.

```bash
ansible-playbook playbooks/verify_bgp.yml
```

**Expected output:** All tasks PASS, all neighbors Established.

---

**Beat 2 — Fault Injection (MD5 Authentication Mismatch)**

Manually change BGP neighbor password on CORE-PE1 (R2) for the eBGP peer EDGE-PE1 (R6). Use wrong password.

```bash
# Via console or utils/push_config.py equivalent
ssh netadmin@core-pe1.lab
conf t
router bgp 65001
 neighbor 10.7.11.2 password WRONG_PASSWORD
end
write memory
```

**Result:** BGP session CORE-PE1 ↔ EDGE-PE1 drops (Active or Idle state). Routes between AS 65001 and AS 65002 disappear on some routers.

---

**Beat 3 — Troubleshoot (Operational State Check)**

Run troubleshoot playbook. It detects the peering failure.

```bash
ansible-playbook playbooks/troubleshoot_bgp.yml --limit CORE-PE1
```

**Expected output:**
- Task "Check for BGP authentication failures" → FAILED (peer in Active/Idle state)
- Warning message: "BGP peer in Active or Idle state — possible authentication mismatch"

**Narrative:** The troubleshooter detects the operational symptom (peer down), but cannot detect the root cause (wrong password vs source of truth). That's what the verifier does.

---

**Beat 4 — Verify (Config Drift Detection)**

Run verify playbook against CORE-PE1. It compares running config to source of truth.

```bash
ansible-playbook playbooks/verify_bgp.yml --limit CORE-PE1 --check --diff
```

**Expected output:**
- `--diff` shows password mismatch:
  - Running config: `neighbor 10.7.11.2 password WRONG_PASSWORD`
  - Source of truth (rendered template): `neighbor 10.7.11.2 password eBGP_R2_R6`
- Task reports CHANGED (config drift detected)

**Narrative:** The verifier catches what the troubleshooter cannot — the running config does not match the source of truth.

---

**Beat 5 — Restore from Source of Truth**

Run configure playbook to push correct config from Ansible source of truth.

```bash
ansible-playbook playbooks/configure_bgp.yml --limit CORE-PE1
```

**Expected output:**
- Ansible renders BGP config from `host_vars/CORE-PE1.yml` and `templates/bgp_config.j2`
- Correct password (`eBGP_R2_R6`) pushed to router
- BGP session CORE-PE1 ↔ EDGE-PE1 re-establishes
- Routes restored

---

**Beat 6 — Confirm Fix**

Run verify playbook again. All checks PASS.

```bash
ansible-playbook playbooks/verify_bgp.yml --limit CORE-PE1
```

**Expected output:** BGP neighbor Established, routes present, no config drift.

---

**Closing statement:** "Ansible is the source of truth. When config drifts, Ansible detects it and restores the intended state from code."

---

## Files Required (Phase 2 Onward)

| File | Phase | Notes |
|------|-------|-------|
| `ansible/ansible.cfg` | 2 | Ansible configuration (roles_path, host_key_checking) |
| `ansible/inventory/module07_bgp.yml` | 2 | Device inventory (YAML format, 12 routers, 3 groups) |
| `ansible/group_vars/all.yml` | 2 | Global variables (credentials, OSPF process IDs) |
| `ansible/host_vars/CORE-RR1.yml` | 2 | Per-device BGP + OSPF config data (12 files total) |
| `ansible/host_vars/CORE-PE1.yml` | 2 | " |
| `ansible/host_vars/CORE-PE2.yml` | 2 | " |
| `ansible/host_vars/CORE-P1.yml` | 2 | " |
| `ansible/host_vars/CORE-P2.yml` | 2 | " |
| `ansible/host_vars/EDGE-PE1.yml` | 2 | " |
| `ansible/host_vars/EDGE-PE2.yml` | 2 | " |
| `ansible/host_vars/EDGE-P1.yml` | 2 | " |
| `ansible/host_vars/EDGE-P2.yml` | 2 | " |
| `ansible/host_vars/STUB-BR1.yml` | 2 | " |
| `ansible/host_vars/STUB-BR2.yml` | 2 | " |
| `ansible/host_vars/STUB-BR3.yml` | 2 | " |
| `ansible/templates/bgp_config.j2` | 3 | BGP Jinja2 template |
| `ansible/templates/ospf_underlay.j2` | 3 | OSPF Jinja2 template |
| `ansible/playbooks/configure_bgp.yml` | 3 | Deploy playbook |
| `ansible/playbooks/verify_bgp.yml` | 3 | Verification playbook |
| `ansible/playbooks/troubleshoot_bgp.yml` | 3 | Troubleshooting playbook |
| `verbal_script/module07_verbal_script.md` | 5 | Draft verbal script (renamed to `_final` at Phase 6) |
| `docs/module07_closing_demo.md` | 6 | Closing demo procedure |
| `diagrams/module07_topology_bgp.drawio` | 5 | Topology diagram (drawio source) |
| `diagrams/module07_topology_bgp.drawio.svg` | 5 | Exported SVG |

---

## Outstanding Questions / Decisions Needed

### DNS Hostnames

The physical routers are currently named R1–R12 in lab DNS. The logical hostnames for Module 07 are:

| Physical | Logical Hostname | DNS Name Needed |
|----------|-----------------|-----------------|
| R1 | CORE-RR1 | `core-rr1.lab` |
| R2 | CORE-PE1 | `core-pe1.lab` |
| R3 | CORE-PE2 | `core-pe2.lab` |
| R4 | CORE-P1 | `core-p1.lab` |
| R5 | CORE-P2 | `core-p2.lab` |
| R6 | EDGE-PE1 | `edge-pe1.lab` |
| R7 | EDGE-PE2 | `edge-pe2.lab` |
| R8 | EDGE-P1 | `edge-p1.lab` |
| R9 | EDGE-P2 | `edge-p2.lab` |
| R10 | STUB-BR1 | `stub-br1.lab` |
| R11 | STUB-BR2 | `stub-br2.lab` |
| R12 | STUB-BR3 | `stub-br3.lab` |

**Question:** Should we:
1. Add new DNS entries for `core-rr1.lab` → `192.168.1.101` (R1), etc.?
2. Or use existing `r1.lab` → `192.168.1.101` and change `ansible_host` in inventory to `r1.lab`?

**Recommendation:** Add new DNS entries. Logical hostnames in the Ansible inventory make the playbooks self-documenting. Students see `CORE-RR1` and immediately understand the router's role.

---

### Ansible Collection — `cisco.ios`

The playbooks use `cisco.ios.ios_config` and `cisco.ios.ios_command` modules. These are part of the `cisco.ios` collection.

**Installation (on NAMS26 workstation):**
```bash
ansible-galaxy collection install cisco.ios
```

**Verification:**
```bash
ansible-galaxy collection list | grep cisco.ios
```

**Add to Phase 1 pre-flight sequence** (after EVE-NG lab reset, before playbook execution).

---

### Base Configuration

Module 07 assumes the following base config is already on each router (applied via console during Phase 1):

- Hostname (e.g., `hostname CORE-RR1`)
- OOB interface `Ethernet1/3` with IP `192.168.1.10x/24`
- Default route `ip route 0.0.0.0 0.0.0.0 192.168.1.1`
- SSH enabled, RSA keys generated
- VTY lines configured for SSH access (`transport input ssh`)
- Local user `netadmin` privilege 15 password `admin`
- Domain name `lab`

Ansible playbooks do NOT render or modify these base config items.

---

## Resolved Items

All items resolved during planning:

- [x] Topology architecture selected — Option C (3 AS, hierarchical)
- [x] IGP underlay selected — OSPF
- [x] Ansible workflow selected — flat playbooks, defer roles to Module 08
- [x] Credentials management — plaintext in Module 07, vault in Module 08
- [x] Verification approach — native `--check` mode, separate verify/troubleshoot playbooks
- [x] Closing demo fault — MD5 authentication mismatch
- [x] BGP content split across Modules 07/08/09 confirmed
- [x] Curriculum expanded to 14 modules (added one BGP module)
- [x] Addressing strategy — RFC 2544 space (198.18.0.0/15) for BGP/eBGP, RFC 1918 (10.x.x.x) for IGP underlay

---

## Next Steps (Phase 1)

1. Tom builds topology in EVE-NG (assign R1–R12 to logical roles)
2. Tom applies base configs via console (hostname, OOB, SSH)
3. Tom configures OSPF underlay manually (for verification during playbook testing)
4. Tom captures running configs to `modules/07_bgp1_ansible/07_ios_configs/`
5. Planning session review — Claude.ai confirms topology matches this document
6. Claude.ai produces serialized CoS instruction for scaffold and initial files

---

*NAMS26 — Network Automation Management Station 2026*
*Module 07 Planning Document — `docs/module07_planning.md`*
*Status: PLANNING COMPLETE — Ready for Phase 1 Lab Build*
*Internal document — not for publication*
