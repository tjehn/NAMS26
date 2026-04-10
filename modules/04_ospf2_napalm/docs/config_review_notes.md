# Module 04 — ios_configs Review Notes
*Logged by NAMS26 Claude — 2026-03-31*
*Status: Pending user correction — do not build from these configs*

---

## Lab Scope

Configs delivered for R01–R10 (10 routers). Context doc said R1–R6. Confirm final scope before build.

---

## Issue 1 — IP Address Mismatch (R1 and R4)

Interface IPs use `192.168.x.x` but OSPF network statements reference `192.1.x.x`. These must match.

**R1:**
| Interface | Configured IP | OSPF network statement |
|-----------|--------------|----------------------|
| Ethernet0/0 | 192.168.12.1 | network 192.1.12.0 area 0 |
| Ethernet0/1 | 192.168.13.1 | network 192.1.13.0 area 0 |

**R4:**
| Interface | Configured IP | OSPF network statement |
|-----------|--------------|----------------------|
| Ethernet0/0 | 192.168.24.4 | network 192.1.24.0 area 10 |
| Ethernet0/1 | 192.168.40.4 | network 192.1.40.0 area 10 |

**Question:** Which is correct — `192.168.x.x` or `192.1.x.x`?

---

## Issue 2 — Misplaced Area Commands

**R3** has `area 10 stub` — R3 is in Area 0 and Area 20, not Area 10. Likely a copy/paste error.
- Remove `area 10 stub` from R3.
- R3 should have `area 20 nssa` and `area 20 nssa default-information-originate` (it is the Area 20 ABR).

**R4** has `area 20 nssa` and `area 20 nssa default-information-originate` — R4 is in Area 10, not Area 20.
- Remove both `area 20` lines from R4.
- R4 should only have `area 10 stub`.

---

## Issue 3 — R10 Missing `area 10 stub`

R10 is in Area 10 but does not have `area 10 stub`. All routers in a stub area require this command, including internal routers.

- Add `area 10 stub` to R10's ospf config.

---

## Issue 4 — R1 Redistribution Errors

**Under `Router eigrp 100`:**
- `redistribute eigrp 100` — redistributing EIGRP into itself. Not valid. Remove.
- `redistribute ospf 1 metric 100000 10 255 1 1500` — correct, keep.

**Under `Router ospf 1`:**
- `redistribute ospf 1 metric 10 10 10 10 10` — redistributing OSPF into itself. Not valid. Remove.
- `redistribute eigrp 100 metric-type 1` — correct form.
- `redistribute eigrp 100` — duplicate of above without metric-type. Remove. Keep only the metric-type 1 version.

---

## Typos (cosmetic — fix before final delivery)

Multiple configs have `ip adress` or `ip addres` (missing one or two characters). Full list:

| Router | Line |
|--------|------|
| R01 | `ip addres 11.0.0.1` (loopback1) |
| R01 | `ip addres 192.1.17.1` (Eth0/2) |
| R01 | `ip addres 192.1.18.1` (Eth0/3) |
| R02 | `ip addrss 22.0.0.2` (loopback1) |
| R05 | `ip adress 5.0.0.5` (loopback0) |
| R06 | `ip adress 6.0.0.6` (loopback0) |
| R07 | `ip adress 7.0.0.7` (loopback0) |
| R08 | `ip adress 8.0.0.8` (loopback0) |
| R09 | `ip adress 9.0.0.9` (loopback0) |

---

## Summary — Do Not Build Until

- [ ] IP address mismatch resolved (Issue 1)
- [ ] Misplaced area commands corrected (Issue 2)
- [ ] R10 stub command added (Issue 3)
- [ ] R1 redistribution cleaned up (Issue 4)
- [ ] Typos corrected
- [ ] Configs validated in EVE-NG lab
