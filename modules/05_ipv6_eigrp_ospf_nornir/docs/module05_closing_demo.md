# Module 05 — Closing Demonstration: Redistribution Drift and the Nornir Merge Limitation

> **Instructor note**
> This segment is designed as a live demonstration to close Module 05. It ties
> together all three automation scripts introduced in this module — `push_config.py`,
> `troubleshoot_ipv6_eigrp_ospf.py`, and `verify_ipv6_eigrp_ospf.py` — and uses a
> deliberate redistribution drift scenario to make a larger point about what Nornir
> can and cannot do. Run this live against the lab topology with students watching.

---

## What This Demonstration Shows

Module 05 introduced Nornir as the automation framework and EIGRPv6/OSPFv3 as the
routing topology. This closing segment uses redistribution as the fault — specifically,
removing the `redistribute ospf 1` statement from R1's EIGRPv6 AS 100 process.

This is the same class of fault used in Module 04 — a silent policy gap. EIGRPv6 and
OSPFv3 continue to operate. Neighbor adjacencies remain up. All processes stay running.
But the bridge between the two routing domains is gone: OSPFv3 routes stop being
redistributed into EIGRPv6 AS 100, and R7 loses all visibility into the OSPF domain.

This demonstration will:

1. Introduce redistribution drift by removing R1's EIGRP redistribute statement using `push_config.py`
2. Run the troubleshooting script to show that R1 appears operationally healthy
3. Run the verification script to show the full impact across all nine routers
4. Restore from the source of truth using `configure_ipv6_eigrp_ospf.py` and observe
   that Nornir re-adds the missing line — but with no diff preview
5. Inject a stray line and re-run the configure script to show what Nornir cannot fix
6. Use the result to reinforce the troubleshooter vs. verifier distinction and the
   limits of Nornir's merge model

---

## Part 1 — Creating the Fault

### Step 1 — Remove Redistribution via `push_config.py`

Remove R1's OSPFv3-to-EIGRPv6 redistribution statement. This simulates a maintenance
operation where a `no redistribute` was entered during a troubleshooting session —
or a partial rollback that removed one line too many.

```
python utils/push_config.py --router R1 --cmd "ipv6 router eigrp 100" "no redistribute ospf 1 metric 10000 100 255 1 1500"
```

Expected output:

```
NAMS26 — Module 05: Ad-hoc Config Push [LIVE]
Targets  : R1
Commands :
  ipv6 router eigrp 100
  no redistribute ospf 1 metric 10000 100 255 1 1500

Proceed? [y/N]: y

============================================================
  Device : R1   DNS : r1.lab   OOB : 192.168.1.101/24
============================================================
  [INFO] Connected to R1 (r1.lab)
  [PASS] Configuration applied and saved.

============================================================
Push session complete.
```

R1 immediately stops originating redistributed OSPFv3 routes into EIGRPv6 AS 100.
Within seconds, R7 loses all routes learned from the OSPFv3 domain. R7's route table
is reduced to only its directly connected and locally originated prefixes. The EIGRPv6
adjacency between R1 and R7 remains up. OSPFv3 adjacencies remain FULL. Every
protocol health metric looks normal.

---

## Part 2 — Troubleshooter Shows a Healthy Router

### Step 2 — Run the Troubleshooter Against R1

```
python scripts/troubleshoot_ipv6_eigrp_ospf.py --router R1 --check neighbors process
```

Expected output:

- **Neighbors** — R1 has FULL OSPFv3 adjacencies with R2 and R3 on Ethernet0/0.
  EIGRPv6 neighbor R7 is active on Ethernet0/1. All adjacencies report as UP.
- **Process** — OSPFv3 process 1 running, router-id 1.1.1.1 confirmed. EIGRPv6
  AS 100 running, router-id 1.1.1.1 confirmed.

> **Instructor talking point:** Ask the class what the troubleshooter told us.
> The answer is: *R1 is working*. OSPFv3 adjacencies are FULL. EIGRPv6 AS 100 is
> running. Router IDs are correct. From an operational standpoint, R1 is completely
> healthy.
>
> Now ask: did the troubleshooter tell us whether R1 is redistributing between them?
> It did not. The troubleshooter checks operational state — is the protocol running,
> are the neighbors up, is the process configured. Redistribution is a policy.
> Policy compliance is a different question.

---

## Part 3 — Verifier Surfaces the Impact

### Step 3 — Run the Verification Script Across All Routers

```
python scripts/verify_ipv6_eigrp_ospf.py --check redistribution
```

#### Verification Detail

```
============================================================
  Device : R1   DNS : r1.lab   OOB : 192.168.1.101/24
============================================================
    [INFO] Connected to R1 (r1.lab)
    [FAIL] EIGRPv6 AS 100: 'redistribute ospf' NOT found — OSPFv3 → EIGRPv6 redistribution missing
    [PASS] OSPFv3 PID 1: 'redistribute eigrp' configured — EIGRPv6 → OSPFv3 redistribution present
    [PASS] EIGRP AS 111 routes visible as OE2/ON2 in OSPFv3 table

============================================================
  Device : R2   DNS : r2.lab   OOB : 192.168.1.102/24
============================================================
    [INFO] Connected to R2 (r2.lab)
    [INFO] 4 OSPFv3 external route(s) (OE2/ON2) present
    [PASS] EIGRP AS 100 prefixes visible as OE2/ON2 in OSPFv3 table
    [PASS] EIGRP AS 111 prefixes visible as OE2/ON2 in OSPFv3 table

============================================================
  Device : R3   DNS : r3.lab   OOB : 192.168.1.103/24
============================================================
    [INFO] Connected to R3 (r3.lab)
    [INFO] 4 OSPFv3 external route(s) (OE2/ON2) present
    [PASS] EIGRP AS 100 prefixes visible as OE2/ON2 in OSPFv3 table
    [PASS] EIGRP AS 111 prefixes visible as OE2/ON2 in OSPFv3 table

============================================================
  Device : R4   DNS : r4.lab   OOB : 192.168.1.104/24
============================================================
    [INFO] Connected to R4 (r4.lab)
    [INFO] EIGRP AS 100: ASBR is outside NSSA Area 20 — Type 5 LSAs do not enter NSSA areas; routes not expected here
    [PASS] EIGRP AS 111 prefixes visible as ON2 — NSSA-local redistribution working

============================================================
  Device : R5   DNS : r5.lab   OOB : 192.168.1.105/24
============================================================
    [INFO] Connected to R5 (r5.lab)
    [INFO] R5 is in a stub/totally-stubby area — external OSPFv3 routes are filtered by design. See 'routes' check for OI ::/0 default route validation.

============================================================
  Device : R6   DNS : r6.lab   OOB : 192.168.1.106/24
============================================================
    [INFO] Connected to R6 (r6.lab)
    [PASS] EIGRPv6 AS 111: 'redistribute ospf' configured — OSPFv3 → EIGRPv6 redistribution present
    [PASS] OSPFv3 PID 1: 'redistribute eigrp' configured — EIGRPv6 → OSPFv3 redistribution present
    [INFO] EIGRP AS 100: ASBR is outside NSSA Area 20 — Type 5 LSAs do not enter NSSA areas; routes not expected here

============================================================
  Device : R7   DNS : r7.lab   OOB : 192.168.1.107/24
============================================================
    [INFO] Connected to R7 (r7.lab)
    [FAIL] No EX routes in route table — check ASBR 'redistribute ospf' in EIGRPv6
    [FAIL] EIGRP AS 111 prefixes NOT visible as EX routes — check ASBR redistribution for AS 111

============================================================
  Device : R8   DNS : r8.lab   OOB : 192.168.1.108/24
============================================================
    [INFO] Connected to R8 (r8.lab)
    [PASS] 5 EX route(s) in route table — redistributed OSPFv3 routes received from ASBR
    [INFO] EIGRP AS 100: ASBR is outside NSSA Area 20 — Type 5 LSAs do not enter NSSA areas; routes not expected at this router

============================================================
  Device : R9   DNS : r9.lab   OOB : 192.168.1.109/24
============================================================
    [INFO] Connected to R9 (r9.lab)
    [INFO] R9 is in a stub/totally-stubby area — external OSPFv3 routes are filtered by design. See 'routes' check for OI ::/0 default route validation.
============================================================
```

#### Verification Summary

```
============================================================
  Verification Summary
============================================================
  Device    redistribution
  ────────────────────────
  R1        FAIL
  R2        PASS
  R3        PASS
  R4        PASS
  R5        INFO
  R6        PASS
  R7        FAIL
  R8        PASS
  R9        INFO
  ────────────────────────
  Totals    PASS:5  FAIL:2  INFO:2
============================================================
```

> **Instructor talking point:** Two FAILs from a single removed line — R1 (the
> policy is gone) and R7 (the downstream impact). R2, R3, R4, R6, and R8 all
> continue to pass. R5 and R9 are INFO because they are in stub areas where
> external routes are filtered by design.
>
> The troubleshooter saw a healthy router. The verifier saw a broken topology.
> Both answers are correct. The DRIFT DETECTED blocks in the raw output name the
> exact finding and its impact — by router, by check, by timestamp. That block is
> the audit evidence: this drift existed, this is when it was detected.
>
> One line on R1 reached across the entire EIGRPv6 AS 100 domain and silenced R7's
> view of the world. Nobody sent an alert. No adjacency flapped. No process crashed.
> Visibility requires a verifier.

---

## Part 4 — Restoring with Nornir

### Step 4 — Restore from Source of Truth

```
python scripts/configure_ipv6_eigrp_ospf.py --router R1
```

Nornir dispatches `netmiko_send_config` to R1. The rendered template contains the
`redistribute ospf 1 metric 10000 100 255 1 1500` statement. Because
`netmiko_send_config` is additive, the missing line is re-added. The script reports
success.

Unlike Module 04, there is no diff preview. Nornir does not produce a before/after
comparison before applying. The change lands silently. The operator cannot confirm
what changed before it happened.

### Step 5 — Confirm with Verification

```
python scripts/verify_ipv6_eigrp_ospf.py --check redistribution
```

R1 and R7 should now return PASS. The redistribution statement is restored.

> **Instructor talking point:** Nornir fixed it — because the missing line was in
> the template. But compare what the operator saw in Module 04 versus here. In
> Module 04, NAPALM showed a diff before committing:
> `+ redistribute eigrp 100 metric-type 1 subnets`. You reviewed it. You confirmed
> it. Then it was applied.
>
> In Module 05, Nornir pushed the config. Something changed on R1. We know it
> worked because the verify passed — but we never saw what the change was before
> it happened. That is the operational difference.

---

## Part 5 — The Merge Limitation

### Step 6 — Inject a Stray Line

The previous scenario showed what Nornir *can* restore: a missing line that exists
in the template. Now show what it *cannot* remove: a line that does not belong.

```
python utils/push_config.py --router R1 --cmd "ipv6 router eigrp 100" "redistribute connected"
```

R1 now has `redistribute connected` in its EIGRPv6 process. This statement is not
in the source of truth. It is not in the Jinja2 template. R7 begins receiving
connected routes from R1 as EX entries — stray, unintended redistribution.

### Step 7 — Re-run the Configure Script

```
python scripts/configure_ipv6_eigrp_ospf.py --router R1
```

Nornir renders the template and sends the config lines to R1. The rendered config
does not contain `redistribute connected`. Nornir adds what is in the template — it
does not remove what is not. The stray line remains in R1's running config.

### Step 8 — Verify Catches the Stray

```
python scripts/verify_ipv6_eigrp_ospf.py --router R1 --check redistribution
```

The redistribution check surfaces unexpected behavior in R1's route table. The
configure script cannot correct it automatically — operator intervention is required.

> **Instructor talking point:** This is the boundary of the merge model. Nornir
> adds lines. It does not enforce complete intended state. If a stray configuration
> element exists on the device that is absent from the template, it persists
> indefinitely — through every configure run, every deployment cycle. The verify
> script catches it. The configure script cannot fix it.
>
> This is the distinction between push-based automation and desired-state
> enforcement. Nornir (parallel push) and NAPALM (merge candidate) both have
> this limitation. The next step in the progression is Ansible — which, with the
> right module and configuration, says not "add these lines" but "this is the
> complete intended state, remove everything else." That transition begins in
> Module 07.
>
> Before moving on: remove the stray line manually.

### Cleanup

```
python utils/push_config.py --router R1 --cmd "ipv6 router eigrp 100" "no redistribute connected"
python scripts/verify_ipv6_eigrp_ospf.py --router R1
```

All checks should return PASS or INFO.

---

## Part 6 — The Bigger Conversation

### Nornir's Contribution

Nornir added one meaningful capability over NAPALM: parallel dispatch. Nine routers
configured simultaneously. In a topology with more routers or more complex
configuration, the time savings compound quickly. Nornir handles the parallel
execution and result aggregation that NAPALM requires manual scripting to achieve.

What Nornir did not add: configuration enforcement. The merge limitation is unchanged.
The lack of diff preview is a regression from NAPALM's `load_merge_candidate` /
`commit_config` workflow. Nornir trades operational visibility for execution speed.

### The Troubleshooter vs. the Verifier — Again

Both tools answered correctly in this demonstration:

- The troubleshooter said: *R1's protocols are running and its neighbors are up.*
  That is true. It was true throughout the fault.
- The verifier said: *R1's configuration does not match the source of truth.*
  That is also true. The `redistribute ospf` statement was absent. R7 was dark.

A router can be operationally healthy and still be wrong. This is the same lesson
as Module 04 — but Module 05 adds a new dimension. The fault affected R7, not just
R1. A single policy line on one router produced two FAILs across a nine-router
topology. The verify script found both, named both, and timestamped both.

---

## Demonstration Summary

| Step | Action | Script | What It Shows |
|------|--------|--------|---------------|
| 1 | Remove EIGRP redistribution on R1 | `utils/push_config.py` | Silent policy drift — no protocol alarm |
| 2 | Run troubleshoot on R1 | `troubleshoot_ipv6_eigrp_ospf.py` | Router appears healthy — all checks pass |
| 3 | Run redistribution verification — all routers | `verify_ipv6_eigrp_ospf.py --check redistribution` | R1 FAIL + R7 FAIL — one line, domain-wide impact |
| 4 | Restore from source of truth | `configure_ipv6_eigrp_ospf.py --router R1` | Nornir re-adds missing line — no diff preview |
| 5 | Re-run full verification | `verify_ipv6_eigrp_ospf.py --check redistribution` | All checks pass — drift resolved |
| 6 | Inject stray redistribution | `utils/push_config.py` | Stray line outside the template |
| 7 | Re-run configure | `configure_ipv6_eigrp_ospf.py --router R1` | No change — merge model cannot remove stray lines |
| 8 | Verify catches the stray | `verify_ipv6_eigrp_ospf.py --router R1 --check redistribution` | Drift detected — configure cannot correct it |
| 9 | Remove stray manually, re-verify | `utils/push_config.py` + `verify_ipv6_eigrp_ospf.py --router R1` | Operator intervention required for removal |

---

*Module 05 — IPv6 EIGRP + OSPFv3 / Tool: Nornir / NAMS26*
