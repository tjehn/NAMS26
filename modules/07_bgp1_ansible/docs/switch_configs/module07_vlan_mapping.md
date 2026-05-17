# Module 07 — VLAN Mapping Reference
## BGP Part 1 / Ansible
## COSW-01 and COSW-02 VLAN Assignments

---

## VLAN Allocation — Module 07

**VLAN Range:** 710-742 (15 VLANs total)

---

## AS 65001 (CORE) — Internal Links

| VLAN | Link Name | Router A | Intf A | Router B | Intf B | Subnet | Type |
|------|-----------|----------|--------|----------|--------|--------|------|
| 710 | CORE-RR1 ↔ CORE-PE1 | R1 | E0/0 | R2 | E0/0 | 10.7.10.0/30 | OSPF Area 0 |
| 711 | CORE-RR1 ↔ CORE-PE2 | R1 | E0/1 | R3 | E0/0 | 10.7.10.4/30 | OSPF Area 0 |
| 712 | CORE-RR1 ↔ CORE-P1 | R1 | E0/2 | R4 | E0/0 | 10.7.10.8/30 | OSPF Area 0/10 |
| 713 | CORE-RR1 ↔ CORE-P2 | R1 | E0/3 | R5 | E0/0 | 10.7.10.12/30 | OSPF Area 0/10 |
| 714 | CORE-P1 ↔ CORE-P2 | R4 | E0/1 | R5 | E0/1 | 10.7.10.16/30 | OSPF Area 10 |

---

## eBGP Inter-AS — AS 65001 ↔ AS 65002

| VLAN | Link Name | Router A | Intf A | Router B | Intf B | Subnet | Type |
|------|-----------|----------|--------|----------|--------|--------|------|
| 720 | CORE-PE1 ↔ EDGE-PE1 | R2 | E0/1 | R6 | E0/0 | 198.18.11.0/30 | eBGP |
| 721 | CORE-PE2 ↔ EDGE-PE2 | R3 | E0/1 | R7 | E0/0 | 198.18.11.4/30 | eBGP |

---

## AS 65002 (EDGE) — Internal Links

| VLAN | Link Name | Router A | Intf A | Router B | Intf B | Subnet | Type |
|------|-----------|----------|--------|----------|--------|--------|------|
| 730 | EDGE-PE1 ↔ EDGE-PE2 | R6 | E0/1 | R7 | E0/1 | 10.7.12.0/30 | OSPF Area 0 |
| 731 | EDGE-PE1 ↔ EDGE-P1 | R6 | E0/2 | R8 | E0/0 | 10.7.12.4/30 | OSPF Area 0/20 |
| 732 | EDGE-PE2 ↔ EDGE-P2 | R7 | E0/2 | R9 | E0/0 | 10.7.12.8/30 | OSPF Area 0/20 |
| 733 | EDGE-P1 ↔ EDGE-P2 | R8 | E0/1 | R9 | E0/1 | 10.7.12.12/30 | OSPF Area 20 |

---

## eBGP Inter-AS — AS 65002 ↔ AS 65003

| VLAN | Link Name | Router A | Intf A | Router B | Intf B | Subnet | Type |
|------|-----------|----------|--------|----------|--------|--------|------|
| 740 | EDGE-P1 ↔ STUB-BR1 | R8 | E0/2 | R10 | E0/0 | 198.18.13.0/30 | eBGP |
| 741 | EDGE-P2 ↔ STUB-BR2 | R9 | E0/2 | R11 | E0/0 | 198.18.13.4/30 | eBGP |
| 742 | EDGE-P2 ↔ STUB-BR3 | R9 | E0/3 | R12 | E0/0 | 198.18.13.8/30 | eBGP |

---

## Switch Port Assignments

### COSW-01 (DC02-B005-COSW-01)

| Switch Port | Router | Router Intf | VLAN | Description |
|-------------|--------|-------------|------|-------------|
| Eth 1/0 | R1 (CORE-RR1) | E0/0 | 710 | to CORE-PE1 |
| Eth 1/1 | R1 (CORE-RR1) | E0/1 | 711 | to CORE-PE2 |
| Eth 1/2 | R1 (CORE-RR1) | E0/2 | 712 | to CORE-P1 |
| Eth 1/3 | R1 (CORE-RR1) | E0/3 | 713 | to CORE-P2 |
| Eth 2/0 | R2 (CORE-PE1) | E0/0 | 710 | to CORE-RR1 |
| Eth 2/1 | R2 (CORE-PE1) | E0/1 | 720 | to EDGE-PE1 (eBGP) |
| Eth 2/2 | R2 (CORE-PE1) | E0/2 | — | UNUSED |
| Eth 2/3 | R2 (CORE-PE1) | E0/3 | — | UNUSED |
| Eth 3/0 | R5 (CORE-P2) | E0/0 | 713 | to CORE-RR1 |
| Eth 3/1 | R5 (CORE-P2) | E0/1 | 714 | to CORE-P1 |
| Eth 3/2 | R5 (CORE-P2) | E0/2 | — | UNUSED |
| Eth 3/3 | R5 (CORE-P2) | E0/3 | — | UNUSED |
| Eth 4/0 | R6 (EDGE-PE1) | E0/0 | 720 | to CORE-PE1 (eBGP) |
| Eth 4/1 | R6 (EDGE-PE1) | E0/1 | 730 | to EDGE-PE2 |
| Eth 4/2 | R6 (EDGE-PE1) | E0/2 | 731 | to EDGE-P1 |
| Eth 4/3 | R6 (EDGE-PE1) | E0/3 | — | UNUSED |
| Eth 5/0 | R9 (EDGE-P2) | E0/0 | 732 | to EDGE-PE2 |
| Eth 5/1 | R9 (EDGE-P2) | E0/1 | 733 | to EDGE-P1 |
| Eth 5/2 | R10 (STUB-BR1) | E0/0 | 740 | to EDGE-P1 (eBGP) |
| Eth 5/3 | R10 (STUB-BR1) | E0/1 | — | UNUSED |

### COSW-02 (DC02-B005-COSW-02)

| Switch Port | Router | Router Intf | VLAN | Description |
|-------------|--------|-------------|------|-------------|
| Eth 1/0 | R3 (CORE-PE2) | E0/0 | 711 | to CORE-RR1 |
| Eth 1/1 | R3 (CORE-PE2) | E0/1 | 721 | to EDGE-PE2 (eBGP) |
| Eth 1/2 | R3 (CORE-PE2) | E0/2 | — | UNUSED |
| Eth 1/3 | R3 (CORE-PE2) | E0/3 | — | UNUSED |
| Eth 2/0 | R4 (CORE-P1) | E0/0 | 712 | to CORE-RR1 |
| Eth 2/1 | R4 (CORE-P1) | E0/1 | 714 | to CORE-P2 |
| Eth 2/2 | R4 (CORE-P1) | E0/2 | — | UNUSED |
| Eth 2/3 | R4 (CORE-P1) | E0/3 | — | UNUSED |
| Eth 3/0 | R7 (EDGE-PE2) | E0/0 | 721 | to CORE-PE2 (eBGP) |
| Eth 3/1 | R7 (EDGE-PE2) | E0/1 | 730 | to EDGE-PE1 |
| Eth 3/2 | R7 (EDGE-PE2) | E0/2 | 732 | to EDGE-P2 |
| Eth 3/3 | R7 (EDGE-PE2) | E0/3 | — | UNUSED |
| Eth 4/0 | R8 (EDGE-P1) | E0/0 | 731 | to EDGE-PE1 |
| Eth 4/1 | R8 (EDGE-P1) | E0/1 | 733 | to EDGE-P2 |
| Eth 4/2 | R8 (EDGE-P1) | E0/2 | 740 | to STUB-BR1 (eBGP) |
| Eth 4/3 | R8 (EDGE-P1) | E0/3 | — | UNUSED |
| Eth 5/0 | R11 (STUB-BR2) | E0/0 | 741 | to EDGE-P2 (eBGP) |
| Eth 5/1 | R11 (STUB-BR2) | E0/1 | — | UNUSED |
| Eth 5/2 | R12 (STUB-BR3) | E0/0 | 742 | to EDGE-P2 (eBGP) |
| Eth 5/3 | R12 (STUB-BR3) | E0/1 | — | UNUSED |

---

## VLAN Trunking Between COSW-01 and COSW-02

**Trunk ports:** Ethernet 0/0-0/3 (4-port EtherChannel recommended)

**Allowed VLANs:** 710-742

**Sample trunk configuration (on both switches):**
```
interface range Ethernet0/0-3
 description Trunk to other COSW switch
 switchport trunk encapsulation dot1q
 switchport mode trunk
 switchport trunk allowed vlan 710-742
 no shutdown
```

---

## Verification Commands

```
! Verify VLANs created
show vlan brief

! Verify interface VLAN assignments
show interface status

! Verify trunk status
show interfaces trunk

! Verify spanning-tree (all VLANs should be forwarding)
show spanning-tree brief
```

---

*Module 07 — BGP Part 1 / Ansible*  
*VLAN Mapping Reference*  
*VLANs 710-742 (15 total)*
