# EVE-NG Lab Reset SOP — Module 05

## When to run this procedure

After every EVE-NG **Stop → Wipe → Start** cycle. Skipping the Wipe step leaves
stale NVRAM config that causes false FAILs in verify and troubleshoot scripts.

## Reset Sequence

```
Step 1  EVE-NG UI  — Stop all nodes
Step 2  EVE-NG UI  — Wipe all nodes (clears NVRAM / regenerates RSA host keys)
Step 3  EVE-NG UI  — Start all nodes
Step 4  Wait       — Allow ~60 seconds for IOS to boot and SSH to come up
Step 5  Terminal   — bash utils/clear_known_hosts.sh
Step 6  Terminal   — python utils/init_ssh.py
Step 7  Terminal   — python utils/ping_hosts.py
Step 8  Terminal   — python scripts/configure_ipv6_eigrp_ospf.py
Step 9  Terminal   — python scripts/verify_ipv6_eigrp_ospf.py
```

## Why each step matters

| Step | Reason |
|------|--------|
| Wipe | Clears stale NVRAM; IOL regenerates RSA host keys |
| clear_known_hosts.sh | Removes old host key fingerprints before new ones are accepted |
| init_ssh.py | Accepts new host key fingerprints; populates ~/.ssh/known_hosts |
| ping_hosts.py | Confirms ICMP reachability before attempting SSH config push |

## Routers in this lab

| Router | OOB IP          | DNS       | Role             |
|--------|-----------------|-----------|------------------|
| R1     | 192.168.1.101   | r1.lab    | Left ASBR        |
| R2     | 192.168.1.102   | r2.lab    | ABR Area 0/10/20 |
| R3     | 192.168.1.103   | r3.lab    | ABR Area 0/20    |
| R4     | 192.168.1.104   | r4.lab    | ABR Area 10/20   |
| R5     | 192.168.1.105   | r5.lab    | Stub Area 10     |
| R6     | 192.168.1.106   | r6.lab    | Right ASBR       |
| R7     | 192.168.1.107   | r7.lab    | EIGRP 100 spoke  |
| R8     | 192.168.1.108   | r8.lab    | EIGRP 111 spoke  |
| R9     | 192.168.1.109   | r9.lab    | Stub Area 10     |
