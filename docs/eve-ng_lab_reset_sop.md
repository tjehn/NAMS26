# EVE-NG Lab Reset SOP
## NAMS26 | Network Automation Management Station 2026

---

> **This procedure applies to all EVE-NG labs in the NAMS26 project. Run before
> exercising any module lab.**
>
> This SOP is an instructor preparation procedure. It is not referenced in any
> student-facing module instructions or docs.

---

## Working Directory

Run all `utils/` commands from the module's own `utils/` directory:

```
modules/<NN_name_tool>/utils/
```

---

## Phase 1 — EVE-NG Node Reset (EVE-NG Web UI)

1. Stop all nodes
2. **Wipe all nodes** — this step is critical. Skipping it leaves stale NVRAM config
   (passive interfaces, test faults) that causes false FAILs in verify and troubleshoot
   scripts. Always wipe before starting.
3. Start all nodes
4. Open consoles in SecureCRT

---

## Phase 2 — Node Baseline Verification

5. Confirm OOB reachability for all nodes:
   ```bash
   python ping_hosts.py
   ```
   Expected: all nodes reachable. Only OOB IP (`Ethernet1/3`) should be configured.

---

## Phase 3 — SSH Initialization

6. Apply base configuration to all nodes (via console):
   ```
   configure terminal
   crypto key generate rsa modulus 1024
   end
   write memory
   ```
   Base config includes: hostname, `netadmin` credentials, domain, VTY SSH,
   NTP, and `Ethernet1/3` OOB address. This is applied manually from the
   pre-loaded base config template — scripts do not manage this.

7. Clear stale known hosts entries (workstation):
   ```bash
   bash clear_known_hosts.sh
   ```

8. Initialize SSH — accept host keys and populate known_hosts:
   ```bash
   python init_ssh.py
   ```
   Expected: all nodes SSH reachable. Host keys written to `~/.ssh/known_hosts`.
   Always use FQDN for manual SSH sessions (e.g. `ssh netadmin@r1.lab`).

---

## Phase 4 — Configuration Deployment

9. Dry run — validate rendering, no SSH push:
   ```bash
   python configure_*.py --dry-run
   ```

10. Deploy configuration to all nodes:
    ```bash
    python configure_*.py
    ```

---

## Phase 5 — Verification

11. Run automated verification:
    ```bash
    python verify_*.py
    ```

12. Review session logs:
    ```
    modules/<NN_name_tool>/logs/
    ```

---

## Utility Script Reference

| Script | Purpose | When to Run |
|--------|---------|-------------|
| `ping_hosts.py` | ICMP reachability check — all devices in module YAML | After EVE-NG Start (Phase 2) |
| `clear_known_hosts.sh` | Remove lab router entries from `~/.ssh/known_hosts` | Before SSH init (Phase 3) |
| `init_ssh.py` | Accept host key fingerprints, populate `known_hosts` | After console base config (Phase 3) |
| `check_ssh.py` | Verify SSH connectivity to all lab routers — PASS/FAIL per host | Troubleshooting only — not part of reset |
| `push_config.py` | Ad-hoc config push to one or more routers | On-demand — bypasses full configure script |

> **`check_ssh.py`** — Verifies SSH connectivity to all lab routers. Attempts an SSH
> connection to each router and reports PASS/FAIL per host. Run after `init_ssh.py` to
> confirm the lab is ready for script deployment. This is a troubleshooting diagnostic —
> it is not part of the standard reset sequence.

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

# NAMS26 Workstation — modules/<NN_name_tool>/utils/
python ping_hosts.py
bash clear_known_hosts.sh
python init_ssh.py

# NAMS26 Workstation — modules/<NN_name_tool>/scripts/
python configure_*.py --dry-run
python configure_*.py
python verify_*.py
```

---

*NAMS26 — Network Automation Management Station 2026*
*Project-level SOP — applies to all modules*
