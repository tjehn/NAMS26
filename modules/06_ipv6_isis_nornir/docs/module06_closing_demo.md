# Module 06 — Closing Demonstration: DIS Priority Drift

> **Instructor note**
> This segment is designed as a live demonstration to close Module 06. It ties
> together all three automation scripts introduced in this module —
> `push_config.py`, `troubleshoot_06_ipv6_isis_nornir.py`, and
> `verify_06_ipv6_isis_nornir.py` — and uses a deliberate DIS priority drift
> scenario to make a larger point about the difference between operational state
> validation and configuration compliance.
> Run this live against the lab topology with students watching.

---

## What This Demonstration Shows

Module 06 introduced IS-IS Named Mode, DIS election on a broadcast segment, and
Nornir's role-aware deployment model. This closing segment uses DIS priority as
the fault — specifically, lowering BR-2's `isis priority` to 0 on its LAN
interface.

This fault is chosen deliberately. A failed IS-IS adjacency is straightforward
to catch: a neighbor disappears, the state drops to Init or Down, and every tool
surfaces it immediately. A DIS priority change is harder to catch. All adjacencies
remain Up. IS-IS is fully converged. The LSDB is populated. Prefixes propagate
normally. From every operational metric, BR-2 and the Area 49.0002 broadcast
segment look completely healthy. The only thing that changed is which router holds
the pseudonode — and nothing tells you that unless you're comparing against a
source of truth.

This demonstration will:

1. Establish a clean verified baseline across all IS-IS routers
2. Inject DIS priority drift on BR-2 using `push_config.py`
3. Run the troubleshooting script to show that BR-2 appears operationally healthy
4. Run the verification script to show that BR-2 no longer matches the source of truth
5. Restore from the source of truth using `configure_06_ipv6_isis_nornir.py` and
   confirm the DIS role returns to BR-2
6. Use the result to reinforce the troubleshooter vs. verifier distinction in the
   context of policy-level misconfiguration

---

## Part 1 — Establishing the Baseline

### Step 1 — Confirm Clean State

Before injecting any fault, run a full verify against all IS-IS routers to
establish that the topology is in the expected state.

```bash
python scripts/verify_06_ipv6_isis_nornir.py
```

Expected output: all eleven IS-IS routers return PASS on all checks. BR-2's
neighbors check confirms BR-2 is present in the Circuit Id column of
`show isis neighbors` — it is DIS on the Area 49.0002 LAN segment.

> **Instructor talking point:** This is the baseline. Eleven routers, all clean.
> The YAML is the source of truth — every router's neighbor count, NET address,
> IS type, interface state, and DIS role have been confirmed against what the YAML
> says they should be. This is what production IS-IS automation looks like before
> a change window: verified state captured, discrepancies surfaced, topology known.

---

## Part 2 — Creating the Fault

### Step 2 — Lower BR-2's DIS Priority via `push_config.py`

From the module directory, lower BR-2's DIS priority to 0 on its LAN interface.
This simulates a maintenance operation that went wrong — an `isis priority 0`
entered during a troubleshooting session and never reversed, or a config snippet
applied to the wrong interface tier.

```bash
python utils/push_config.py --router BR-2 --cmd "interface Ethernet0/0" "isis priority 0"
```

Expected output:

```
NAMS26 — Module 06: Ad-hoc Config Push [LIVE]
Targets  : BR-2
Commands :
  interface Ethernet0/0
  isis priority 0

Proceed? [y/N]: y

============================================================
  Device : BR-2   DNS : br-2.lab   OOB : 192.168.1.107/24
============================================================
  [INFO] Connected to BR-2 (br-2.lab)
  [PASS] Configuration applied and saved.

============================================================
Push session complete.
```

BR-2's DIS priority drops from 100 to 0 on Ethernet0/0. IS-IS triggers a new
DIS election on the Area 49.0002 broadcast segment. BR-2 yields — it is now the
lowest-priority router on that segment. BR-1 or BR-3 wins. A new pseudonode LSP
appears in the LSDB. BR-2's pseudonode LSP is withdrawn.

All adjacencies remain Up. IS-IS is fully converged. The DIS role has simply moved.

---

## Part 3 — Troubleshooter Shows Healthy Adjacencies

### Step 3 — Run the Troubleshooter Against BR-2

```bash
python scripts/troubleshoot_06_ipv6_isis_nornir.py --router BR-2 --check adjacency
```

Expected output:

- **Adjacency** — BR-2 reports neighbors in Up state. ABR-1, BR-1, and BR-3 are
  all present. `[PASS] IS-IS adjacencies: N Up, 0 Down, 0 Init`.

> **Instructor talking point:** Watch the output. BR-2's adjacencies are completely
> healthy. Every neighbor is Up. The troubleshooter's question is: "are IS-IS
> adjacencies working?" The answer is yes — unambiguously.
>
> The troubleshooter has no visibility into whether the DIS role matches what the
> source of truth says it should be. That is not its job. It checks operational
> state — are neighbors Up, are interfaces IS-IS enabled, is the process running.
> All of those things are true. A DIS re-election does not break any adjacency.
> The protocol is healthy, and the troubleshooter correctly says so.

---

## Part 4 — Verification Reveals the Drift

### Step 4 — Run the Verification Script Against BR-2

```bash
python scripts/verify_06_ipv6_isis_nornir.py --router BR-2 --check neighbors
```

Expected output:

```
  ──────────────────────────────────────────────────────
  Neighbor Validation
  ──────────────────────────────────────────────────────
  [PASS] Neighbor count: 5 (expected 5)
  [WARN] BR-2 not found in Circuit Id column — DIS role lost
         YAML isis_priority: 100 — expected BR-2 to hold DIS on this segment
=== DRIFT DETECTED — BR-2 — 260510 ===
  Router   : BR-2
  Check    : neighbors
  Finding  : BR-2 absent from Circuit Id column despite isis_priority: 100
  Impact   : DIS role has moved to another router — pseudonode LSP no longer owned by BR-2
=======================================
```

> **Instructor talking point:** This is configuration drift. The YAML says BR-2
> should hold DIS on the Area 49.0002 broadcast segment — `isis_priority: 100` is
> in the YAML under BR-2's Ethernet0/0. The live router has priority 0. Another
> router won DIS election. The verifier found this because it knows what the YAML
> says and compared it against what `show isis neighbors` actually shows.
>
> The troubleshooter passed. The verifier warned. Both answers are correct.
>
> This is the same lesson as Module 04 — but the fault is subtler. In Module 04,
> a missing redistribution statement caused an entire external domain to disappear
> from OSPF. That fault had a visible routing impact. Here, the DIS re-election has
> zero impact on reachability. Prefixes propagate identically regardless of which
> router holds the pseudonode. The topology works. But the intended configuration —
> the policy that says BR-2 is the designated IS — has drifted silently.
>
> In production, this matters. The DIS role affects pseudonode LSP ownership, link
> state database efficiency, and the behavior of future DIS elections on that
> segment. An operator who set `isis priority 100` on BR-2 for a reason — traffic
> engineering, topology stability, operational discipline — cannot detect that the
> setting drifted without a source-of-truth comparison. The troubleshooter will
> never surface it.

---

## Part 5 — Restoring to Baseline

### Step 5 — Restore from Source of Truth

```bash
python scripts/configure_06_ipv6_isis_nornir.py --router BR-2
```

Nornir reconnects to BR-2, renders the template from the YAML, and pushes the
configuration. `isis priority 100` is restored on Ethernet0/0. IS-IS triggers
another DIS election — BR-2 wins. The pseudonode LSP returns to BR-2.

> **Instructor talking point:** Notice what restoring from source of truth means
> here. No one remembered the command. No one looked up what priority BR-2 was
> supposed to have. The configure script was run — Nornir loaded the YAML, rendered
> the template, and pushed exactly what the source of truth says BR-2 should have.
>
> That is idempotent restore. Whether `isis priority 100` was already there or not,
> the script produces the same result: BR-2's configuration matches the YAML.
>
> The YAML is always the answer.

### Step 6 — Confirm with Verification

```bash
python scripts/verify_06_ipv6_isis_nornir.py --router BR-2 --check neighbors
```

Expected output: `[PASS] BR-2 confirmed as DIS — found in Circuit Id column`.

The DIS drift is resolved. BR-2 holds the pseudonode again. The source of truth
and the live state agree.

---

## Part 6 — The Bigger Conversation

### The Troubleshooter vs. the Verifier

This demonstration makes the clearest possible case for running both tools.

The troubleshooter answers: *Is IS-IS working on BR-2?* In this scenario, yes —
completely. Adjacencies are Up, the process is running, interfaces are IS-IS
enabled. The troubleshooter is correct.

The verifier answers: *Does BR-2 match what the source of truth says it should
look like?* In this scenario, no — BR-2 was missing its DIS priority. The verifier
is also correct.

A router can be operationally healthy and still be wrong. That is the central point.

In Module 04, the fault was a missing redistribution statement — it had a routing
impact that a careful engineer could detect by looking at routing tables on other
routers. Here, the fault is invisible to every routing metric. The topology
functions identically with or without BR-2 as DIS. There is no routing impact,
no reachability loss, no protocol error to trace. The only way to detect this drift
is to know what the intended state is — and that knowledge lives in the YAML.

This is why source-of-truth automation matters. Not just for deploying
configuration — for detecting when that configuration has drifted, even when the
protocol itself cannot tell you.

### What Nornir's Task Model Can and Cannot Do

The restore step demonstrated Nornir's idempotent task model. The configure script
rendered the template from the YAML and pushed the result — exactly the same output
regardless of what was on the router before. Unlike NAPALM's merge candidate model,
there is no diff preview before the push. The lines go to the router.

This is a meaningful difference worth stating explicitly. NAPALM showed you a diff
before committing. Nornir's `netmiko_send_config` does not. The trade-off: Nornir's
model is simpler and faster to implement; NAPALM's model gives the operator a review
gate before applying changes.

In production, the lack of a pre-flight diff is managed by:
- Running `--dry-run` first to inspect the rendered template
- Using the verify script before and after to confirm state
- Trusting the YAML as the single source of truth

The configure script with `--router BR-2` targeted a single device. In a full
deployment, the same script across all eleven IS-IS routers would apply the same
idempotent logic — each router gets exactly what its YAML entry says.

> **Instructor note:** Before closing, confirm a full clean verify run across all
> routers to restore the demonstration to the baseline state from Step 1:
>
> ```bash
> python scripts/verify_06_ipv6_isis_nornir.py
> ```

---

## Demonstration Summary

| Step | Action | Script | What It Shows |
|------|--------|--------|---------------|
| 1 | Full verify — all routers | `verify_06_ipv6_isis_nornir.py` | Clean baseline — all checks PASS |
| 2 | Lower BR-2 isis priority to 0 | `utils/push_config.py` | Silent policy drift — no adjacency alarm |
| 3 | Troubleshoot BR-2 adjacency | `troubleshoot_06_ipv6_isis_nornir.py` | Router appears healthy — adjacency PASS |
| 4 | Verify BR-2 neighbors | `verify_06_ipv6_isis_nornir.py --check neighbors` | Drift detected — WARN on DIS role loss |
| 5 | Restore from source of truth | `configure_06_ipv6_isis_nornir.py --router BR-2` | Nornir pushes YAML — isis priority 100 restored |
| 6 | Re-verify BR-2 neighbors | `verify_06_ipv6_isis_nornir.py --check neighbors` | PASS — BR-2 confirmed as DIS |
| 7 | Full verify — all routers | `verify_06_ipv6_isis_nornir.py` | Clean baseline restored |

---

*Module 06 — IPv6 IS-IS / Tool: Nornir / NAMS26*
