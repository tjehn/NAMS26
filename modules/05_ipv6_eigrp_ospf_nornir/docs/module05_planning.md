# Module 05 Planning — IPv6 EIGRP/OSPFv3 Technology

## Status
SCAFFOLD COMPLETE — scripts not yet implemented

## Lab Overview

9-router pure-IPv6 topology combining two EIGRPv6 domains with a central
OSPFv3 multi-area domain. Redistribution at both edges.

## Topology Summary

```
R7 (EIGRP 100) ──── R1 (ASBR) ────┐
                                    │
                              LAN (Area 0)
                            R1  R2  R3
                                │     └── R3 ── R4 ── R6 (ASBR) ── R8 (EIGRP 111)
                                │           Area 20 (NSSA)
                                └── R2 Serial ── R5 ── R9
                                        Area 10 (Totally Stubby)
```

## OSPF Areas

| Area | Type            | ABR(s)   | Notes                              |
|------|-----------------|----------|------------------------------------|
| 0    | Backbone        | —        | R1, R2, R3                         |
| 10   | Totally Stubby  | R2, R4   | `stub no-summary` on R2 (ABR)      |
| 20   | NSSA            | R3, R4   | `nssa no-summary` on R3 (ABR)      |

## EIGRP Domains

| AS  | Routers    | Redistribution point |
|-----|------------|----------------------|
| 100 | R1, R7     | R1 (bidirectional)   |
| 111 | R6, R8     | R6 (bidirectional)   |

## Key Learning Objectives

- IPv6 unicast routing (`ipv6 unicast-routing`, `ipv6 cef`)
- OSPFv3 interface-level area assignment (`ipv6 ospf <pid> area <area>`)
- EIGRPv6 interface-level assignment (`ipv6 eigrp <as>`)
- Bidirectional redistribution between OSPFv3 and EIGRPv6
- OSPFv3 stub and NSSA area types
- Explicit EIGRP/OSPF router-id for routers with no IPv4 addresses
- Nornir parallel task execution across 9 routers

## Nornir Architecture

- Inventory: SimpleInventory built from `data/ipv6_eigrp_ospf.yaml`
- Connection plugin: `netmiko` (cisco_ios)
- Tasks: `netmiko_send_config` for configure, `netmiko_send_command` for verify/troubleshoot
- Results: `print_result` from `nornir_utils`

## TODO

- [ ] Implement configure_ipv6_eigrp_ospf.py
- [ ] Implement verify_ipv6_eigrp_ospf.py
- [ ] Implement troubleshoot_ipv6_eigrp_ospf.py
- [ ] Implement templates/ipv6_eigrp_ospf.j2
- [ ] Create topology diagram (diagrams/module05_topology_ipv6_eigrp_ospf.drawio)
- [ ] Write verbal script
- [ ] Complete closing demo doc
