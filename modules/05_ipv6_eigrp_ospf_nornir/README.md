# Module 05 — IPv6 EIGRP / OSPFv3 Technology

**Tool:** Nornir (netmiko connection plugin)
**Routers:** R1–R9 (9 devices)
**Protocols:** EIGRPv6 AS 100 (left), EIGRPv6 AS 111 (right), OSPFv3 PID 1

## Lab Overview

Pure-IPv6 topology. Two independent EIGRPv6 domains flank a central OSPFv3
multi-area domain. Redistribution runs bidirectionally at R1 (EIGRP 100 ↔ OSPF)
and R6 (EIGRP 111 ↔ OSPF).

| Area | Type           | Notes                           |
|------|----------------|---------------------------------|
| 0    | Backbone       | R1, R2 (Eth), R3 (Eth)          |
| 10   | Totally Stubby | ABR: R2 (`stub no-summary`)     |
| 20   | NSSA           | ABR: R3 (`nssa no-summary`)     |

## Pre-flight (run after every EVE-NG Wipe+Start)

```bash
bash utils/clear_known_hosts.sh
python utils/init_ssh.py
python utils/ping_hosts.py
```

## Deploy / Verify / Troubleshoot

```bash
python scripts/configure_ipv6_eigrp_ospf.py [--dry-run] [--router R1 R2 ...]
python scripts/verify_ipv6_eigrp_ospf.py    [--router R1] [--check neighbors routes]
python scripts/troubleshoot_ipv6_eigrp_ospf.py [--router R1] [--check neighbors process]
```

## Status

Scaffold complete. Scripts not yet implemented — see `docs/module05_planning.md`.
