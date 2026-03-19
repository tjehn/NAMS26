# EVE-NG Lab Reset & Sea Trials SOP
## Module 02 — EIGRP Classic Mode

---

## Working Directory

```
/home/netauto/PycharmProjects/NAMS26/modules/02_eigrp_netmiko/utils
```

---

## Phase 1 — EVE-NG Node Reset (EVE-NG Web UI)

1. Stop all nodes
2. Wipe all nodes
3. Start all nodes
4. Open consoles in SecureCRT

---

## Phase 2 — Router Baseline Verification

5. Confirm OOB reachability:
   ```
   python ping_hosts.py
   ```
   Expected: 6/6 hosts reachable. Only OOB IP (Ethernet1/3) should be configured.

---

## Phase 3 — SSH Preparation

6. Generate RSA keys on each router (via console, R1–R6):
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
   Expected: 6/6 hosts SSH reachable. Host keys written to ~/.ssh/known_hosts under FQDN (r1.lab, etc.).
   > Note: Always use FQDN for manual SSH sessions (ssh netadmin@r1.lab).

---

## Phase 4 — Configuration Deployment

9. Dry run — validate rendering, no SSH push:
   ```
   python configure_eigrp_classic.py --dry-run
   ```

10. Deploy configuration to all routers:
    ```
    python configure_eigrp_classic.py
    ```

---

## Phase 5 — Verification

11. Run automated verification:
    ```
    python verify_eigrp_classic.py
    ```

12. Review session logs:
    ```
    NAMS26/modules/logs/
    ```

13. Review rendered configuration files:
    ```
    NAMS26/modules/02_eigrp_netmiko/configs/
    ```

---

## Quick Reference — Full Sequence

```
# EVE-NG Web UI
Stop all nodes → Wipe all nodes → Start all nodes
Open consoles in SecureCRT

# Each Router (via console)
configure terminal
crypto key generate rsa modulus 1024
end
write memory

# NAMS26 Workstation — utils/
python ping_hosts.py
bash clear_known_hosts.sh
python check_ssh.py

# NAMS26 Workstation — scripts/
python configure_eigrp_classic.py --dry-run
python configure_eigrp_classic.py
python verify_eigrp_classic.py
```
