# EVE-NG Lab Reset & Sea Trials SOP
## Module 03 — OSPF Classic Mode

---

## Responsibilities

| Scope | Owner |
|-------|-------|
| Base configuration (hostname, credentials, OOB, VTY, NTP) | Lab Admin |
| OSPF configuration (interfaces, routing, authentication) | NAMS26 Automation Scripts |

**Base configuration** is pre-loaded onto each router via console after every Wipe. It is the pre-condition for SSH access. The automation scripts assume it is already in place and do not touch it.

---

## Working Directory

```
/home/netauto/PycharmProjects/NAMS26/modules/03_ospf1_napalm/utils
```

---

## Phase 1 — EVE-NG Node Reset (EVE-NG Web UI)

1. Stop all nodes
2. Wipe all nodes
3. Start all nodes
4. Open consoles in SecureCRT

---

## Phase 2 — Base Configuration (Console — R1–R11)

Apply the base configuration to each router via console. This establishes hostname, credentials, OOB management, SSH access, and NTP before handing off to automation.

```
hostname Rn
!
no ip domain lookup
ip domain name lab.local
!
username netadmin privilege 15 secret 5 <hash>
!
interface Ethernet1/3
 no shutdown
 description OOB Management
 ip address 192.168.1.10n 255.255.255.0
 duplex auto
!
line con 0
 exec-timeout 0 0
 logging synchronous
line aux 0
line vty 0 4
 login local
 transport input ssh
!
ntp server <ntp-ip>
ntp server pool.ntp.org
!
end
```

Save config after applying:
```
write memory
```

---

## Phase 3 — Router Baseline Verification

5. Confirm OOB reachability:
   ```
   python ping_hosts.py
   ```
   Expected: 11/11 hosts reachable. Only OOB IP (Ethernet1/3) should be configured.

---

## Phase 4 — SSH Preparation

6. Generate RSA keys on each router (via console, R1–R11):
   ```
   configure terminal
   crypto key generate rsa modulus 1024
   end
   write memory
   ```

7. Clear stale known hosts entries (workstation):
   ```
   bash clear_known_hosts.sh
   ```

8. Verify SSH connectivity and refresh known_hosts:
   ```
   python check_ssh.py
   ```
   Expected: 11/11 hosts SSH reachable. Host keys written to ~/.ssh/known_hosts
   under FQDN (r1.lab through r11.lab).
   > Note: Always use FQDN for manual SSH sessions (ssh netadmin@r1.lab).

---

## Phase 5 — Configuration Deployment

9. Dry run — validate rendering, no SSH push:
   ```
   python configure_ospf_classic.py --dry-run
   ```

10. Deploy configuration to all routers:
    ```
    python configure_ospf_classic.py
    ```

---

## Phase 6 — Verification

11. Run automated verification:
    ```
    python verify_ospf_classic.py
    ```

12. Review session logs:
    ```
    modules/03_ospf1_napalm/logs/
    ```

13. Review rendered configuration files:
    ```
    modules/03_ospf1_napalm/configs/
    ```

---

## Quick Reference — Full Sequence

```
# EVE-NG Web UI
Stop all nodes → Wipe all nodes → Start all nodes
Open consoles in SecureCRT

# Each Router (via console, R1–R11)
[Apply base configuration]
write memory
crypto key generate rsa modulus 1024
write memory

# NAMS26 Workstation — utils/
python ping_hosts.py
bash clear_known_hosts.sh
python check_ssh.py

# NAMS26 Workstation — scripts/
python configure_ospf_classic.py --dry-run
python configure_ospf_classic.py
python verify_ospf_classic.py
```
