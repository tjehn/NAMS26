# Module 04 — Closing Demonstration: Configuration Drift and Redistribution

> **Instructor note**
> This segment is designed as a live demonstration to close Module 04. It ties
> together all three automation scripts introduced in this module — `push_config.py`,
> `troubleshoot_ospf_advanced.py`, and `verify_ospf_advanced.py` — and uses a
> deliberate redistribution drift scenario to make a larger point about the
> difference between operational state validation and configuration compliance.
> Run this live against the lab topology with students watching.

---

## What This Demonstration Shows

Module 04 introduced redistribution between OSPF and two independent EIGRP domains.
This closing segment uses redistribution as the fault — specifically, removing the
`redistribute eigrp 100` statement from R1's OSPF process.

This fault is chosen deliberately. A missing network statement — the fault used in
Module 03 — is relatively easy to catch: a prefix disappears from the routing table
and the router itself loses reachability to something. A missing redistribution
statement is harder to catch. OSPF adjacencies remain FULL. The OSPF process is
running. The router IDs are correct. The LSDB is populated with R1's own Router LSA.
From every operational metric, R1 looks completely healthy. The only thing missing is
the policy that connects the EIGRP domain to the OSPF domain — and nothing tells you
that unless you're comparing against a source of truth.

This demonstration will:

1. Introduce redistribution drift by removing R1's OSPF redistribution statement using `push_config.py`
2. Run the troubleshooting script to show that R1 appears operationally healthy
3. Run the verification script to show that R1 no longer matches the source of truth
4. Restore from the source of truth using `configure_ospf_advanced.py` and observe the NAPALM diff
5. Use the result to reinforce the troubleshooter vs. verifier distinction in the
   context of policy-level misconfiguration

---

## Part 1 — Creating the Fault

### Step 1 — Remove Redistribution via `push_config.py`

From the `utils/` directory, remove R1's EIGRP-to-OSPF redistribution statement.
This simulates a maintenance operation that went wrong — a `no redistribute` entered
during a troubleshooting session, or a configuration rollback that removed one line
too many.

```bash
python utils/push_config.py --router R1 \
  --cmd "router ospf 1" "no redistribute eigrp 100 metric-type 1 subnets"
```

Expected output:

```
NAMS26 — Module 04: Ad-hoc Config Push [LIVE]
Targets  : R1
Commands :
  router ospf 1
  no redistribute eigrp 100 metric-type 1 subnets

Proceed? [y/N]: y

============================================================
  Device : R1   DNS : r1.lab   OOB : 192.168.1.101/24
============================================================
  [INFO] Connected to R1 (r1.lab)
  [PASS] Configuration applied and saved.

============================================================
Push session complete.
```

R1 immediately stops originating Type 5 AS External LSAs for the EIGRP 100 prefixes.
The following disappear from the OSPF domain within seconds:

- R7's loopbacks: `7.0.0.0/8`, `77.0.0.0/8`, `107.7.7.7/24`
- R8's loopbacks: `8.0.0.0/8`, `88.0.0.0/8`, `108.8.8.8/24`
- The `192.1.17.0/24` and `192.1.18.0/24` link segments

All OSPF adjacencies remain FULL. R1 and its neighbors continue exchanging hellos
normally. The protocol is working. The policy is gone.

---

## Part 2 — Troubleshooter Shows a Healthy Router

### Step 2 — Run the Troubleshooter Against R1

From the `scripts/` directory:

```bash
python scripts/troubleshoot_ospf_advanced.py --router R1 --check neighbors process
```

Expected output:

- **Neighbors** — R1 has FULL adjacencies with R2 (via Ethernet0/0) and R3 (via
  Ethernet0/1). `[PASS] At least one FULL adjacency confirmed`.
- **Process** — OSPF process 1 running, router ID `0.0.0.1` confirmed. EIGRP AS 100
  confirmed running. `[PASS] OSPF process 1 confirmed running`.
  `[PASS] OSPF Router ID 0.0.0.1 confirmed`.
  `[PASS] EIGRP AS 100 confirmed running`.

> **Instructor talking point:** Ask the class what the troubleshooter told us.
> The answer is: *R1 is working*. Neighbors are FULL. The OSPF process is running
> with the correct router ID. EIGRP AS 100 is confirmed running. From an operational
> standpoint, R1 is completely healthy.
>
> Both protocols are running. The adjacencies are up. There is no alarm, no flap,
> no error message anywhere in the output.
>
> Now ask: did the troubleshooter tell us whether R1 is redistributing between them?
> It did not. The troubleshooter checks operational state — is the protocol running,
> are the neighbors up, is the process configured. Redistribution is a policy.
> Policy compliance is a different question.

Run the full troubleshoot check to confirm all five pass:

```bash
python scripts/troubleshoot_ospf_advanced.py --router R1
```

All five checks — neighbors, database, routes, redistribution, process — will pass
or return INFO. Note that even the troubleshoot script's own `redistribution` check
passes at this point, because it detects that EIGRP AS 100 is running and OSPF is
running — but it does not validate whether the `redistribute` statement connecting
them is configured. That is by design. The troubleshooter confirms the protocols are
operational. Whether they are connected is the verifier's job.

---

## Part 3 — Verification Reveals the Drift

### Step 3 — Run the Verification Script Against R1

```bash
python scripts/verify_ospf_advanced.py --router R1 --check redistribution
```

Expected output:

```
  ──────────────────────────────────────────────────────
  Redistribution Validation
  ──────────────────────────────────────────────────────
  [PASS] EIGRP AS 100: 0 D EX route(s) present...
  [FAIL] OSPF: no external routes (E1/E2/N1/N2) found
         — EIGRP -> OSPF redistribution may have failed
```

> **Instructor talking point:** This is configuration drift. The YAML says R1 should
> be redistributing EIGRP 100 into OSPF. The live router is not. The external routes
> that should propagate from EIGRP 100 into the OSPF domain are absent. R7 and R8's
> prefixes — which every OSPF router in the topology should see as `O E1` routes —
> are gone.
>
> The troubleshooter passed. The verifier failed. Both answers are correct.
>
> This is the same lesson as Module 03 — but the stakes are higher. In Module 03,
> a missing network statement meant one prefix was absent. A network engineer looking
> at the routing table on another router would likely notice. Here, an entire external
> domain has disappeared from the OSPF routing domain. R7 and R8 are unreachable from
> any OSPF router. But the protocol itself looks healthy on every single device.
>
> This is exactly what happens in production. Redistribution statements get removed
> during maintenance. Nobody notices until a service call comes in. The troubleshooter
> confirms the protocol is working. Only the verifier — comparing against the source
> of truth — catches the policy gap.

---

## Part 4 — Restoring to Baseline with NAPALM Diff

### Step 4 — Restore from Source of Truth

```bash
python scripts/configure_ospf_advanced.py --router R1
```

Watch the diff output before the commit:

```
============================================================
  Device : R1   DNS : r1.lab   OOB : 192.168.1.101/24
============================================================
  [INFO] Connecting to R1 (r1.lab)...
  [PASS] Connected to R1.
  [INFO] Loading configuration candidate...
  [INFO] Configuration diff for R1:
+router ospf 1
+ redistribute eigrp 100 metric-type 1 subnets
  [INFO] Committing configuration...
  [PASS] Configuration committed on R1.
  [PASS] Configuration saved on R1.
```

> **Instructor talking point:** One line in the diff. Before a single character was
> applied to the router, NAPALM showed us exactly what was going to change —
> `redistribute eigrp 100 metric-type 1 subnets`. That is the diff-before-commit
> model in action. The operator sees the change, confirms it is exactly what was
> expected, and commits.
>
> In Module 02, Netmiko pushed lines without preview. Here, you reviewed the impact
> before it landed. That is a meaningful operational improvement.

### Step 5 — Confirm with Verification

```bash
python scripts/verify_ospf_advanced.py --router R1
```

All five checks should return PASS or INFO. The redistribution check will now confirm
`O E1` routes are present in R1's OSPF routing table, and `D EX` entries are present
in R1's EIGRP table. The EIGRP 100 domain is visible in OSPF again.

---

## Part 5 — The Bigger Conversation

### The Troubleshooter vs. the Verifier

This demonstration makes the clearest possible case for running both tools.

The troubleshooter answers: *Is OSPF working?* In this scenario, yes — completely.
The process is running, the neighbors are FULL, the database is populated. The
troubleshooter is correct.

The verifier answers: *Does this router match what the source of truth says it should
look like?* In this scenario, no — R1 was missing a redistribution statement. The
verifier is also correct.

A router can be operationally healthy and still be wrong. That is the central point.

In Module 03, the fault was a missing network statement — a relatively visible gap.
The prefix disappeared from the LSDB, and a careful look at the routing table on any
other router would surface it. In Module 04, the fault is invisible to protocol
monitoring. OSPF is working. EIGRP is working. The gap is in the policy that connects
them. No protocol check, no neighbor state inspection, no LSDB analysis will surface
it. Only a comparison against the intended configuration will.

This is why source-of-truth automation matters. Not just for deploying configuration —
for detecting when that configuration has drifted.

### What NAPALM's Merge Model Can and Cannot Do

The restore step demonstrated the merge candidate's strength: precision. The configure
script produced the following diff on R1 before committing:

```
=== DIFF DETECTED — R1 — configure_ospf_advanced ===
+router ospf 1
+ redistribute eigrp 100 metric-type 1 subnets
=====================================================
```

> **What the diff means:** The `+` prefix indicates lines that NAPALM will add.
> NAPALM is showing exactly one statement — `redistribute eigrp 100` — that is
> present in the YAML source of truth but absent from R1's running configuration.
> Nothing else changed. No other lines were touched.
>
> **Why the troubleshooter missed it:** The troubleshooter checks operational state
> — is the protocol running, are the neighbors up, is the process configured. It
> confirmed all of those things. It did not check whether the policy connecting
> the two protocols — the `redistribute` statement — was present. That is by design.
>
> **Why the verify script caught it:** The verify script compares live state against
> the YAML source of truth. The `redistribution` check confirmed that `show ip route
> ospf` on backbone routers no longer showed R7 and R8's prefixes as `O E1`. The
> expected prefixes were absent. That is a FAIL regardless of what the protocol
> health checks showed.
>
> **The log as a production audit trail:** Every verify run writes a timestamped
> log to `modules/04_ospf2_napalm/logs/`. The FAIL entry — showing exactly which
> router, which check, and which prefixes were missing — is preserved as a record.
> In a production environment this log is the evidence: when did the drift occur,
> what was missing, and when was it corrected. The configure script run that
> restored the state produces a similar log showing the diff and the timestamp.
> Together these form a change audit trail from a YAML source of truth.

One line changed. Nothing else was touched. The diff confirmed it before the commit.

It also has a limit that is worth stating explicitly. If R1 had a *stray*
redistribution statement — one that should not be there — the merge candidate would
not remove it. The merge model is additive. It applies what is in the YAML. It does
not remove what is not.

To demonstrate this, push a stray redistribution statement to R1 and then run the
configure script:

```bash
python utils/push_config.py --router R1 \
  --cmd "router ospf 1" "redistribute connected subnets"
python scripts/configure_ospf_advanced.py --router R1
```

The diff will show no changes. NAPALM sees no difference between the candidate and
the running configuration because the candidate does not contain the stray line —
and the merge model does not remove what is absent from the candidate. The verify
script will catch it — the redistribution check will surface unexpected behavior in
the routing table — but the configure script cannot correct it automatically.

> **Instructor talking point:** The verify script catches the drift. The configure
> script, using a merge candidate, cannot fix it. The operator must remove the stray
> line manually with `push_config.py`, or the team must move to a replace candidate
> model that requires a complete device configuration as the baseline.
>
> This is the boundary between NAPALM merge and NAPALM replace. And it is the
> boundary between this module and the declarative automation that comes later in
> the series — where Ansible's desired state model says not just "add these lines"
> but "this is the complete intended configuration, remove everything else."

> **Instructor note:** Before closing, remove the stray redistribution statement
> if the optional drift was injected, and confirm a clean verify run:
>
> ```bash
> python utils/push_config.py --router R1 \
>   --cmd "router ospf 1" "no redistribute connected subnets"
> python scripts/verify_ospf_advanced.py --router R1
> ```

---

## Demonstration Summary

| Step | Action | Script | What It Shows |
|------|--------|--------|---------------|
| 1 | Remove redistribution statement on R1 | `utils/push_config.py` | Silent policy drift — no protocol alarm |
| 2 | Run troubleshoot checks on R1 | `troubleshoot_ospf_advanced.py` | Router appears healthy — all checks pass |
| 3 | Run redistribution verification on R1 | `verify_ospf_advanced.py --check redistribution` | Drift detected — FAIL on external routes |
| 4 | Restore from source of truth | `configure_ospf_advanced.py` | NAPALM diff shows exactly one line before commit |
| 5 | Re-run full verification | `verify_ospf_advanced.py` | All checks pass — drift resolved |
| 6 | Optional: inject stray redistribution | `utils/push_config.py` | Merge model limitation demonstrated |
| 7 | Optional: re-run configure | `configure_ospf_advanced.py` | No diff — merge cannot remove stray lines |
| 8 | Optional: restore manually | `utils/push_config.py` | Operator intervention required for removal |

---

*Module 04 — OSPF Advanced / Tool: NAPALM / NAMS26*
