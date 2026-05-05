# NAMS26 — Reusable Lab Topology Foundation
## Interface Labeling Session Summary
**Date:** 2026-05-04  
**Scope:** Project-root `utils/` toolkit — standalone, no module dependency

---

## Overview

This document records the design decisions, procedures, and scripts produced
during the foundation setup session for the NAMS26 shared lab topology.
The goal was to establish a reusable physical fabric that Modules 06–13 can
build logical topologies on top of, without rewiring EVE-NG between modules.

---

## Lab Physical Fabric

### Devices

| Device | Role | OOB IP | DNS Name |
|--------|------|--------|----------|
| R1–R12 | IOL Routers (IOS 15.7) | 192.168.1.101–.112 | r1.lab–r12.lab |
| COSW-01 | IOL Core Switch (IOS 15.2) | 192.168.1.236 | cosw-01.lab |
| COSW-02 | IOL Core Switch (IOS 15.2) | 192.168.1.237 | cosw-02.lab |
| OOB_SW01 | IOL OOB Switch (IOS 15.2) | 192.168.1.240 | oob_sw01.lab |

### Router Interface Layout (all routers identical)

| Interface | Role |
|-----------|------|
| Ethernet0/0–0/3 | Logical topology interfaces (connected to core switches) |
| Ethernet1/0–1/2 | Additional logical topology interfaces (shutdown when unused) |
| Ethernet1/3 | OOB Management — permanent, never modified by automation |

### Core Switch Fabric

- COSW-01 and COSW-02 are trunked together (E0/0–E0/3 inter-switch links)
- Each router has four physical interfaces connected into the switch fabric
- Logical links between routers are defined by VLAN assignments on the switches
- The switches are transparent to the student — topology diagrams show router-to-router links only

### OOB Switch

- OOB_SW01 connects to every router's E1/3 (management interface)
- OOB_SW01 E0/0 connects to the EVE-NG Cloud0 bridge (work PC access) — **never shut down**
- OOB_SW01 E6/0 → COSW-01 E11/3, E6/1 → COSW-02 E11/3

---

## utils/ Toolkit

All scripts live at `NAMS26_V03/utils/` and read from `utils/hosts.yaml`.
No module YAML dependency. Covers all 15 lab devices.

### hosts.yaml

Single source of truth for all lab devices. Contains DNS names, OOB IPs,
and credentials. All Python utils read from this file.

```
utils/
├── hosts.yaml              ← device inventory (all 15 devices)
├── clear_known_hosts.sh    ← purge stale SSH host keys
├── init_ssh.py             ← SSH lab initialization
├── check_ssh.py            ← SSH connectivity diagnostic
├── ping_hosts.py           ← ICMP reachability check
└── label_interfaces.py     ← CDP-based interface labeling
```

### Usage — Lab Reset Sequence

Run in this order after every EVE-NG Wipe+Start:

```bash
# 1. Purge stale host keys (IOL regenerates RSA keys on every wipe)
bash utils/clear_known_hosts.sh

# 2. Accept new host keys, populate known_hosts
python utils/init_ssh.py

# 3. Confirm ICMP reachability
python utils/ping_hosts.py
```

### Usage — Interface Labeling

Run once when setting up the lab foundation, or after rewiring:

```bash
# Dry run — preview only, no push
python utils/label_interfaces.py --dry-run

# Live — label all devices
python utils/label_interfaces.py

# Specific devices only
python utils/label_interfaces.py --device R1 COSW-01
```

---

## Interface Labeling — Design and Logic

### label_interfaces.py

Connects to each device via SSH, runs `show cdp neighbors detail`,
and applies interface descriptions based on CDP neighbor data.

#### Description Rules

| Condition | Description Applied |
|-----------|-------------------|
| CDP neighbor is OOB_SW01 | `OOB Management` |
| CDP neighbor is any other device | `R2 Eth 0/1` (short name + remote interface) |
| No CDP neighbor — exempt interface | Fixed description (see below) |
| No CDP neighbor — all others | `UNUSED` + `shutdown` |

#### Exempt Interfaces

`OOB_SW01 Ethernet0/0` is permanently exempt from the UNUSED + shutdown rule.
This interface connects to the EVE-NG Cloud0 bridge — shutting it down severs
the work PC's access to the entire lab. It receives the description `NAMS` instead.

Defined in `EXEMPT_INTERFACES` at the top of `label_interfaces.py`:

```python
EXEMPT_INTERFACES = {
    "OOB_SW01": {"Ethernet0/0": "NAMS"},
}
```

#### OOB_SW01 Special Handling

OOB_SW01 (IOL switch with underscore in hostname) drops SSH sessions when
receiving large config blocks. The script detects this and writes the config
to a text file instead of pushing via SSH:

```
utils/OOB_SW01_label_config.txt
```

Paste this file into the OOB_SW01 EVE-NG console to apply the descriptions.

#### Name Normalization

CDP neighbor hostnames are normalized before use in descriptions:

| Raw CDP Device ID | Normalized |
|-------------------|------------|
| `R1.lab.local` | `R1` |
| `DC02-B005-COSW-01.lab.local` | `COSW-01` |
| `OOB_SW01` | `OOB Management` (description override) |

---

## IOL Compatibility Notes

### SSH — Legacy Algorithm Requirements

IOL 15.7 routers and IOL 15.2 switches run SSH version 1.99 and only support
legacy algorithms that modern OpenSSH clients do not offer by default.

`init_ssh.py` uses a raw `paramiko.Transport` connection to inject legacy
algorithms before the SSH handshake:

| Parameter | Values |
|-----------|--------|
| KEX | `diffie-hellman-group14-sha1`, `group-exchange-sha1`, `group1-sha1` |
| Ciphers | `aes128-ctr`, `aes192-ctr`, `aes256-ctr`, `aes128-cbc`, `3des-cbc` |
| MACs | `hmac-sha1`, `hmac-sha1-96` |
| Host key types | `ssh-rsa` |

For manual SSH from PowerShell, pass these flags explicitly:

```powershell
ssh -o KexAlgorithms=diffie-hellman-group14-sha1 `
    -o MACs=hmac-sha1 `
    -o HostKeyAlgorithms=ssh-rsa `
    netadmin@192.168.1.236
```

### IOL Switch SSH — Version Requirement

IOL switches must run SSH version 1.99 (`ip ssh version 1` in IOS config).
Setting `ip ssh version 2` prevents SSH from binding on IOL switch images.
Vlan1 must be `no shutdown` for SSH to have an interface to bind to.

### DNS — Synology NAS Throttling

The lab DNS server runs on a Synology NAS with limited resources.
`ping_hosts.py` uses `MAX_WORKERS = 5` and `LAUNCH_STAGGER = 0.3s` to
avoid saturating the DNS server with simultaneous resolution requests.
Firing all 15 pings in parallel causes DNS query drops and false FAILs.

### clear_known_hosts.sh — Name Form Coverage

IOL regenerates RSA host keys on every Wipe+Start cycle. The clear script
removes all three name forms for each device to ensure no stale entry remains:

- Short name (e.g. `cosw-01`)
- DNS name (e.g. `cosw-01.lab`)
- OOB IP (e.g. `192.168.1.236`)

OOB_SW01 requires both hyphen and underscore forms:
`oob-sw01`, `oob_sw01`, `oob-sw01.lab`, `oob_sw01.lab`, `192.168.1.240`

---

## Topology Map Considerations (Future — Module 13)

The CDP-based topology map script used in earlier modules will require
modification for the shared fabric topology. CDP on each router shows
`COSW-01` or `COSW-02` as neighbors — not other routers.

The topology map must derive logical links from VLAN assignments:

> Two routers are logically connected if their interfaces share the same
> VLAN on the core switches. The switches must not appear in the map.

The `label_interfaces.py` CDP data (which switch port connects to which
router interface) provides the bridge between physical fabric and logical
topology and can be used as input to the topology map script.

---

*NAMS26 — Network Automation Management Station 2026*  
*Session: 260504 — Reusable Lab Topology Foundation*
