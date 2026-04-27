# Session Status — 260426c
## NAMS26 Curriculum Restructuring
**Date:** 2026-04-27
**Session:** 260426c (curriculum restructure — issued by Claude.ai planning session)

---

## Summary

This session implemented the NAMS26 curriculum restructuring decided in a Claude.ai planning
session. Modules 06–13 were redesigned for better pedagogical flow, tool progression, and
Cisco technology depth. All changes are reflected in `CLAUDE.md`, `NAMS26_context.md`,
`README.md`, and the `modules/` scaffold.

---

## Changes Made

### 1. NAMS26_context.md

- **Tool progression table** — replaced with revised curriculum (Nornir 05–06, Ansible 07–09, Ansible+pyATS 10–12, Flask+Mixed 13)
- **Module Status section** — replaced flat "Modules 05–12: NOT STARTED" block with per-module detail entries for Modules 05–13, including full scope notes and tool assignments

### 2. CLAUDE.md

- **Tool-per-module table** — replaced with full 12-module revised curriculum table (Module, Name, Technology, Tool, Structure columns)
- **Protocol Configuration Mode Standard** — updated to include "IS-IS Named Mode" in the Module 06 onward entry
- **Two-Act Module Structure (Modules 10–12)** — new section added
- **Module 09 — Route Policy Standard** — new section added

### 3. README.md

- **Module progression table** — updated to reflect revised curriculum including Module 13 and correct tools/technologies for Modules 06–13

### 4. Module Scaffold Directory Renames (git mv)

| Old Name | New Name |
|----------|----------|
| `06_ipv6_isis_nornir` | `06_isis_nornir` |
| `07_isis_nornir` | `07_bgp1_ansible` |
| `08_bgp1_pyats` | `08_bgp2_ansible` |
| `09_bgp2_pyats` | `09_route_policy_ansible` |
| `10_bgp_mpls_ansible` | `10_bgp_mpls_ansible_pyats` |
| `11_mpls_vpn_ansible` | `11_mpls_vpn_ansible_pyats` |
| `12_vpn_gre_ansible` | `12_vpn_gre_ansible_pyats` |

Internal `NN_ios_configs/` subdirectories were also renamed to match the new module numbers
for modules 07–12.

### 5. New Module 13 Scaffold

`modules/13_capstone_flask/` created with full standard scaffold:
`data/`, `templates/`, `scripts/`, `utils/`, `configs/`, `logs/`, `docs/`,
`diagrams/`, `verbal_script/`, `13_ios_configs/` — all with `.gitkeep` placeholders.

### 6. Missing Scaffold Directories Added

All modules 06–12 received the complete standard scaffold:
`data/`, `templates/`, `scripts/`, `docs/`, `diagrams/`, `verbal_script/`, `configs/`, `logs/`
— all with `.gitkeep` placeholders.

---

## Revised Curriculum Table

| Module | Name | Technology | Tool | Structure |
|--------|------|-----------|------|-----------|
| 02 | EIGRP Classic | EIGRP | Netmiko | Single act — COMPLETE |
| 03 | OSPF Classic | OSPF | NAPALM | Single act — COMPLETE |
| 04 | OSPF Advanced | OSPF Advanced | NAPALM | Single act — COMPLETE |
| 05 | IPv6 EIGRP + OSPFv3 | IPv6 EIGRP + OSPFv3 | Nornir | Single act — IN PROGRESS |
| 06 | IS-IS | IS-IS (IPv4 + IPv6 zone) | Nornir | Single act — NOT STARTED |
| 07 | BGP Part 1 | BGP | Ansible | Single act — NOT STARTED |
| 08 | BGP Part 2 | BGP Advanced | Ansible | Single act — NOT STARTED |
| 09 | Route Policy | Route Maps, Prefix Lists, AD, Redistribution | Ansible | Single act — NOT STARTED |
| 10 | BGP + MPLS | BGP + MPLS | Ansible + pyATS/Genie | Two acts — NOT STARTED |
| 11 | MPLS VPN | MPLS VPN | Ansible + pyATS/Genie | Two acts — NOT STARTED |
| 12 | VPN / GRE | VPN / GRE | Ansible + pyATS/Genie | Two acts — NOT STARTED |
| 13 | Capstone | Multi-site Enterprise | Flask + Mixed | Capstone — PLANNED |

---

## Key Design Decisions (from Claude.ai planning session)

1. Nornir scope reduced to Modules 05–06 (was 05–07)
2. IS-IS moved to Module 06 — IPv4 primary with one IPv6 zone to reinforce Module 05
3. Ansible introduced at Module 07 and runs through Module 12 (six modules)
4. Dedicated Route Policy module (09) added — route maps, prefix lists, AD manipulation, conditional redistribution
5. pyATS/Genie introduced progressively across Modules 10–12 alongside Ansible (two-act structure)
6. Module 13 confirmed as enterprise multi-site capstone — Flask change control + pyATS/Genie verification

---

## Outstanding Items

- Module 05 (`05_ipv6_eigrp_ospf_nornir`) — IN PROGRESS, content development continues
- All modules 06–13 — scaffold only; no content development started
- Module 06 (`06_isis_nornir`) — `06_ios_configs/` contains pre-existing IOS config reference files from prior lab captures (retained)
- Modules 07–12 README.md files — placeholder stubs from previous scaffold; content to be updated during module development
- Module 13 capstone design — deferred until Module 12 is complete

---

## Conflicts / Flags

- None. All changes applied cleanly.
- The old `06_ipv6_isis_nornir/06_ios_configs/` reference files (Day_6/Day_7 and R01–R09) are retained under the new `06_isis_nornir/06_ios_configs/` path. These were existing lab captures; they may or may not be relevant to the revised Module 06 scope (IS-IS IPv4 primary + one IPv6 zone). Flag for review during Module 06 development.

---

*Session 260426c — Curriculum restructure*
*NAMS26 — Network Automation Management Station 2026*
