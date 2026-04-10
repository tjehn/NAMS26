# EVE-NG Lab Reset & Sea Trials SOP
## NAMS26 | Network Automation Management Station 2026

---

## Working Directory

```
modules/<module_dir>/utils/
```

---

## Phase 1 — EVE-NG Node Reset (EVE-NG Web UI)

1. Stop all nodes
2. Wipe all nodes
3. Start all nodes
4. Open consoles in SecureCRT

---

## Phase 2 — Node Baseline Verification

5. Confirm OOB reachability for all nodes:
   ```
   python ping_hosts.py
   ```
   Expected: all nodes reachable. Only OOB IP (Ethernet1/3) should be configured.

---

## Phase 3 — SSH Initialization

6. Apply base configuration to all nodes (via console):
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

8. Initialize SSH — accept host keys and populate known_hosts:
   ```
   python init_ssh.py
   ```
   Expected: all nodes SSH reachable. Host keys written to ~/.ssh/known_hosts.
   > Note: Always use FQDN for manual SSH sessions (e.g. ssh netadmin@r1.lab).

---

## Phase 4 — Configuration Deployment

9. Dry run — validate rendering, no SSH push:
   ```
   python configure_*.py --dry-run
   ```

10. Deploy configuration to all nodes:
    ```
    python configure_*.py
    ```

---

## Phase 5 — Verification

11. Run automated verification:
    ```
    python verify_*.py
    ```

12. Review session logs:
    ```
    modules/<module_dir>/logs/
    ```

13. Review rendered configuration files:
    ```
    modules/<module_dir>/configs/
    ```

---

## Quick Reference — Full Sequence

```
# EVE-NG Web UI
Stop all nodes → Wipe all nodes → Start all nodes
Open consoles in SecureCRT

# All nodes (via console)
configure terminal
crypto key generate rsa modulus 1024
end
write memory

# NAMS26 Workstation — utils/
python ping_hosts.py
bash clear_known_hosts.sh
python init_ssh.py

# NAMS26 Workstation — scripts/
python configure_*.py --dry-run
python configure_*.py
python verify_*.py
```

---

*NAMS26 — Network Automation Management Station 2026*
