# Module 03 — Closing Demonstration: Configuration Drift and the NAPALM Diff

> **Instructor note**
> This segment is designed as a live demonstration to close Module 03. It ties
> together all three automation scripts introduced in this module — `push_config.py`,
> `troubleshoot_ospf_classic.py`, and `verify_ospf_classic.py` — and uses a
> deliberate configuration drift scenario to make a larger point about the
> difference between operational state validation and configuration compliance.
> Run this live against the lab topology with students watching.

---

## What This Demonstration Shows

By the end of Module 03 the student has seen automation used to configure, verify,
and troubleshoot an OSPF Classic Mode network. This closing segment introduces one
more concept that ties it all together: **configuration drift**.

Configuration drift happens when the state of a running network device diverges from
the documented, intended, or automated baseline. It can happen through manual CLI
changes, emergency fixes that never get documented, or incremental adjustments made
by different team members over time. In a small network it is manageable. In an
enterprise network it becomes a significant operational risk.

This demonstration will:

1. Introduce a deliberate drift by removing a network statement from R1 using `push_config.py`
2. Run the troubleshooting script to show that R1 appears to be operating normally
3. Run the verification script to show that R1 no longer matches the source of truth
4. Restore from the source of truth using `configure_ospf_classic.py` and observe the NAPALM diff
5. Use the result to open a discussion about what NAPALM's merge model can and cannot do

---

## Part 1 — Creating the Fault

### Step 1 — Remove a Network Statement via `push_config.py`

From the `utils/` directory, remove R1's loopback network statement. This simulates
a manual CLI change — the kind of configuration removal that gets made during a
miscommunication or a partial rollback and never gets restored.

```bash
python utils/push_config.py --router R1 --cmd "router ospf 1" "no network 1.0.0.0 0.255.255.255 area 0"
```

Expected output:

```
NAMS26 — Ad-hoc Config Push [LIVE]
Targets  : R1
Commands :
  router ospf 1
  no network 1.0.0.0 0.255.255.255 area 0

Proceed? [y/N]: y

============================================================
  Device : R1   DNS : r1.lab   OOB : 192.168.1.101/24
============================================================
  [INFO] Connected to R1 (r1.lab)
  [PASS] Configuration applied and saved.

============================================================
Push session complete.
```

R1's loopback network statement is now removed. R1 is no longer advertising
`1.0.0.0/8` into OSPF. All adjacencies remain up — the Ethernet0/0 network
statement is still present, so hellos continue normally. The drift is silent from
a protocol perspective.

---

## Part 2 — Troubleshooting Shows a Healthy Router

### Step 2 — Run the Troubleshooter Against R1

From the `scripts/` directory:

```bash
python scripts/troubleshoot_ospf_classic.py --router R1
```

The output will show all five checks passing:

- **Neighbors** — R1 has three OSPF neighbors on Ethernet0/0 (R2, R3, R11). FULL
  adjacencies present. `[PASS] At least one FULL adjacency confirmed`.
- **Authentication** — Plain-text authentication confirmed on Ethernet0/0.
  `[PASS] Ethernet0/0 — plain-text authentication confirmed`.
- **Database** — Router LSA for `0.0.0.1` present in LSDB. Router Link States
  section confirmed. `[PASS] Router LSA for 0.0.0.1 present in LSDB`.
- **Routes** — OSPF routes present in routing table. R1 has a full table of
  intra-area and inter-area routes. `[PASS] OSPF routes present in routing table`.
- **Process** — OSPF process 1 running, router ID `0.0.0.1` confirmed.
  `[PASS] OSPF process 1 confirmed running`.

> **Instructor talking point:** Ask the class what the troubleshooter told us.
> The answer is: *R1 is working*. Every check passed. OSPF adjacencies are up,
> the LSDB is populated with R1's own Router LSA, routes are present, the process
> is running. From a pure operational standpoint, R1 looks completely healthy.
>
> Now ask: *Did the troubleshooter tell us whether R1 is advertising everything it
> should be?* It did not. That is not its job. The troubleshooter answers the
> question "is OSPF working?" — it does not answer the question "is this router
> configured the way it's supposed to be?"

---

## Part 3 — Verification Reveals the Drift

### Step 3 — Run the Verification Script Against R1

```bash
python scripts/verify_ospf_classic.py --router R1 --check routes
```

The route table section will display normally. Then scroll to the **OSPF Network
Statement Validation** section:

```
  [PASS] Network 192.1.100.0 0.0.0.255 area 0 — Ethernet0/0 (192.1.100.1/24) is up/up
  [FAIL] Network 1.0.0.0 0.255.255.255 area 0 — no interface found with a matching IP on R1
```

> **Instructor talking point:** This is configuration drift. The YAML says R1
> should be advertising `1.0.0.0/8` — the loopback network — into OSPF area 0.
> The live router is not. That discrepancy is the drift.
>
> The router passed troubleshooting. It failed verification. Both of those
> statements are true at the same time. That distinction matters.
>
> The verification script is not asking "is OSPF working?" — it is asking "does
> this router match what our YAML says it should look like?" Those are fundamentally
> different questions, and in production you need both answers.
>
> Notice also what the troubleshooter could not tell you: R1's loopback `1.1.1.1`
> is no longer reachable from any other router in the topology. That prefix has
> disappeared from the LSDB and from every routing table in the network. The
> troubleshooter checked whether OSPF is working — and it is. It did not check
> whether every prefix that should be in the network is actually there.

---

## Part 4 — Restoring to Baseline with NAPALM Diff

### Step 4 — Restore from Source of Truth

The right way to restore R1 is to re-run the configuration script, which will load
the correct state from the YAML as a NAPALM candidate configuration:

```bash
python scripts/configure_ospf_classic.py --router R1
```

Watch the diff output before the commit:

```
============================================================
  Device : R1   DNS : r1.lab   OOB : 192.168.1.101/24
============================================================
  [INFO] Connected to R1 (r1.lab)
  [INFO] Loading configuration candidate...
  [INFO] Configuration diff for R1:
+router ospf 1
+ network 1.0.0.0 0.255.255.255 area 0
  [INFO] Committing configuration...
  [PASS] Configuration committed on R1.
  [PASS] Configuration saved on R1.
```

> **Instructor talking point:** This is the NAPALM diff in action. Before a single
> line was applied to the router, NAPALM showed us exactly what was going to change.
> One network statement. That's it. The diff gives the operator a checkpoint —
> an opportunity to review the impact before committing.
>
> In Module 2, Netmiko pushed lines and the configuration landed. There was no
> preview. The diff-before-commit model is one of the concrete improvements NAPALM
> brings over direct CLI automation.

### Step 5 — Confirm with Verification

```bash
python scripts/verify_ospf_classic.py --router R1 --check routes
```

Both network statements should now return `[PASS]`:

```
  [PASS] Network 192.1.100.0 0.0.0.255 area 0 — Ethernet0/0 (192.1.100.1/24) is up/up
  [PASS] Network 1.0.0.0 0.255.255.255 area 0 — Loopback0 (1.1.1.1/8) is up/up
```

---

## Part 5 — The Bigger Conversation: NAPALM in Context

### What NAPALM Adds Over Netmiko

In Module 02 the configure script sent lines to the router and the configuration
landed. There was no preview, no diff, and no safety checkpoint before commit.
NAPALM changes that with the candidate configuration model:

- **Load** — the configuration is staged but not applied
- **Diff** — NAPALM compares the candidate to the running configuration and shows
  what will change
- **Commit** — the candidate is applied only after the operator has reviewed the diff
- **Discard** — if the diff reveals something unexpected, the candidate can be
  discarded without any change landing on the router

In this demonstration the diff showed a single network statement. In a larger
deployment — pushing a new OSPF area, adding authentication to a segment,
configuring summarization — the diff shows the full scope of the change before
anything is committed. That visibility is operationally important and is exactly
what was missing from the Netmiko workflow.

### Where NAPALM's Merge Model Reaches Its Limits

The restore step in this demonstration highlighted something important: NAPALM's
merge candidate is **additive**. It added back the missing network statement —
but it would not have removed anything that shouldn't be there.

To demonstrate this, push a stray network statement to R1 and then run the
configure script:

```bash
python utils/push_config.py --router R1 --cmd "router ospf 1" "network 192.1.99.0 0.0.0.255 area 0"
python scripts/configure_ospf_classic.py --router R1
```

The diff will show no changes — NAPALM sees no difference between the candidate and
the running configuration, because the candidate only contains what's in the YAML,
and the stray network statement is not in the YAML. NAPALM's merge model does not
remove lines that are present on the router but absent from the candidate.

A **replace candidate** would remove the stray line. That's a different NAPALM
operation — `load_replace_candidate()` instead of `load_merge_candidate()` — and it
requires a complete, full-device configuration as the candidate, not just the delta.
That level of configuration management is where tools like Ansible and its
declarative model become the right choice.

> **Instructor talking point:** The verify script catches this drift — it will FAIL
> on `192.1.99.0` because no interface on R1 has a matching IP. But the configure
> script, using a merge candidate, cannot correct it automatically. The operator
> must either use `push_config.py` to remove the stray line manually, or move to
> a replace candidate model.
>
> This is the boundary between NAPALM merge and NAPALM replace — and it's the
> boundary between this module and the declarative automation that comes later in
> the series.

### Where This Course Goes Next

| Module | Protocol   | Tool          | What It Adds                                   |
|--------|------------|---------------|------------------------------------------------|
| 02     | EIGRP      | Netmiko       | Direct SSH, explicit command control           |
| 03–04  | OSPF       | NAPALM        | Candidate config, diff before commit, rollback |
| 05–06  | IPv6/IS-IS | Nornir        | Concurrent execution, inventory model          |
| 10–12  | BGP        | pyATS/Genie   | Structured parsing, stateful testing           |
| 07–12  | MPLS/VPN   | Ansible       | Declarative intent, idempotency at scale       |

NAPALM is not the wrong tool — it is the right tool for this stage of the learning
progression. The diff-before-commit model is a meaningful step up from Module 02.
The limitations of the merge candidate are the motivation for everything that comes
next.

> **Instructor note:** Before proceeding to Module 04, restore R1 to clean
> baseline by removing the stray network statement if the second drift was injected:
>
> ```bash
> python utils/push_config.py --router R1 --cmd "router ospf 1" "no network 192.1.99.0 0.0.0.255 area 0"
> python scripts/verify_ospf_classic.py --router R1 --check routes
> ```

---

## Demonstration Summary

| Step | Action | Script | What It Shows |
|------|--------|--------|---------------|
| 1 | Remove loopback network statement on R1 | `utils/push_config.py` | Silent configuration drift introduced |
| 2 | Run all troubleshooting checks on R1 | `troubleshoot_ospf_classic.py` | Router appears healthy — all five checks pass |
| 3 | Run route verification on R1 | `verify_ospf_classic.py --check routes` | Drift detected — FAIL on loopback network |
| 4 | Restore from source of truth | `configure_ospf_classic.py` | NAPALM diff shows exactly one change before commit |
| 5 | Re-run verification | `verify_ospf_classic.py --check routes` | All checks pass — drift resolved |
| 6 | Optional: inject additive drift | `utils/push_config.py` | Merge model limitation demonstrated |
| 7 | Optional: re-run configure | `configure_ospf_classic.py` | No diff — merge cannot remove stray lines |
| 8 | Optional: restore manually | `utils/push_config.py` | Operator intervention required for removal |

---

*Module 03 — OSPF Classic Mode / Tool: NAPALM / NAMS26*
