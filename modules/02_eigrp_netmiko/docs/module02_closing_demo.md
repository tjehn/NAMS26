# Module 02 — Closing Demonstration: Configuration Drift and the Limits of Netmiko

> **Instructor note**  
> This segment is designed as a live demonstration to close Module 02. It ties
> together all three automation scripts introduced in this module — `push_config.py`,
> `troubleshoot_eigrp_classic.py`, and `verify_eigrp_classic.py` — and uses a
> deliberate configuration drift scenario to make a larger point about automation
> methodology and scalability. Run this live against the lab topology with students
> watching.

---

## What This Demonstration Shows

By the end of Module 02 the student has seen automation used to configure, verify,
and troubleshoot an EIGRP Classic Mode network. This closing segment introduces one
more concept that ties it all together: **configuration drift**.

Configuration drift happens when the state of a running network device diverges from
the documented, intended, or automated baseline. It can happen through manual CLI
changes, emergency fixes that never get documented, or incremental adjustments made
by different team members over time. In a small network it is manageable. In an
enterprise network it becomes a significant operational risk.

This demonstration will:

1. Introduce a deliberate drift by pushing a manual configuration change to R4
2. Run the troubleshooting script to show that the router appears to be operating normally
3. Run the verification script to show that the router no longer matches the source of truth
4. Use the result to open a discussion about what Netmiko can and cannot do at scale

---

## Part 1 — Creating the Fault

### Step 1 — Inject a Configuration Change via `push_config.py`

From the `utils/` directory, push a network statement to R4 that does not exist in
`eigrp_classic.yaml`. This simulates a manual CLI change — the kind of ad-hoc fix
that gets made during an incident and never gets cleaned up or documented.

```bash
python utils/push_config.py --router R4 --cmd "router eigrp 100" "network 192.1.99.0"
```

Expected output:

```
NAMS26 — Ad-hoc Config Push [LIVE]
Targets  : R4
Commands :
  router eigrp 100
  network 192.1.99.0

Proceed? [y/N]: y

============================================================
  Device : R4   DNS : r4.lab   OOB : 192.168.1.104/24
============================================================
  [INFO] Connected to R4 (r4.lab)

  Sending configuration:

  configure terminal
  ...
  R4(config-router)#network 192.1.99.0
  R4(config-router)#end
  R4#

  [PASS] Configuration applied and saved.
  [INFO] Disconnected from R4

============================================================
Push session complete.
```

The configuration is now live on R4 and saved to NVRAM. The router is advertising
`192.1.99.0` into EIGRP AS 100 — a network that has no corresponding interface on
R4 and no entry in the YAML source of truth.

---

## Part 2 — Troubleshooting Shows a Healthy Router

### Step 2 — Run the Troubleshooter Against R4

From the `scripts/` directory:

```bash
python scripts/troubleshoot_eigrp_classic.py --router R4
```

The output will show all five checks passing or producing expected informational
results:

- **Neighbors** — R4 has three active EIGRP neighbors (R3, R5, R6). All present.
- **Authentication** — R4 has no authentication configured. The script correctly
  reports `[INFO] No authentication configured in YAML for this device` and moves on.
- **Passive interfaces** — All three active interfaces (Et0/0, Et0/1, Et0/2) are
  confirmed active. The passive check passes.
- **Routes / Topology** — The routing table is populated. All topology entries are
  in Passive state. `[PASS] All topology entries passive — EIGRP is converged`.
- **Process** — `[PASS] EIGRP AS 100 confirmed in process output`.

> **Instructor talking point:** Ask the class what the troubleshooter told us.
> The answer is: *R4 is working*. Every check passed. EIGRP is up, neighbors are
> formed, the topology is converged, the process is running. From a pure
> operational standpoint, R4 looks healthy.
>
> Now ask: *Did the troubleshooter tell us whether R4 matches our intended
> configuration?* It did not. That is not its job. The troubleshooter answers
> the question "is EIGRP working?" — it does not answer the question "is this
> router configured the way it's supposed to be?"

---

## Part 3 — Verification Reveals the Drift

### Step 3 — Run the Verification Script Against R4

```bash
python scripts/verify_eigrp_classic.py --router R4
```

Scroll to the **EIGRP Network / Interface State Validation** section of the output.
Fifteen network statements will return `[PASS]`. Then:

```
  [FAIL] Network 192.1.99.0 0.0.0.255 (classful inferred) — no interface found
         with a matching IP on R4
```

> **Instructor talking point:** This is configuration drift. The router has a
> network statement advertised into EIGRP that does not correspond to any interface
> on the device, and that does not exist anywhere in our YAML source of truth.
>
> The router passed troubleshooting. It failed verification. Both of those
> statements are true at the same time. That distinction matters.
>
> The verification script is not asking "is EIGRP working?" — it is asking "does
> this router match what our YAML says it should look like?" Those are fundamentally
> different questions, and in production you need both answers.

---

## Part 4 — Restoring to Baseline

### Step 4 — Remove the Drift and Restore from Source of Truth

The right way to restore R4 is not to manually undo the change — it is to re-run
the configuration script, which will push the correct state from the YAML file:

```bash
python scripts/configure_eigrp_classic.py --router R4
```

Then confirm with the verification script:

```bash
python scripts/verify_eigrp_classic.py --router R4
```

All network statements should now return `[PASS]` with no failures.

> **Instructor note:** You may also choose to remove the stray network statement
> directly using `push_config.py` before running `configure_eigrp_classic.py`, to
> show both recovery paths. Either approach is valid for demonstration purposes.
>
> ```bash
> python utils/push_config.py --router R4 --cmd "router eigrp 100" "no network 192.1.99.0"
> ```

---

## Part 5 — The Bigger Conversation: Netmiko in Context

### What Netmiko Does Well

Netmiko is an excellent tool for getting started with network automation. It is
approachable, well-documented, and makes the underlying mechanics of SSH-based
automation visible in a way that higher-abstraction tools do not. In this module
it has been used to:

- Render and deploy EIGRP configurations from a YAML and Jinja2 template pipeline
- Verify live EIGRP state against expected values defined in a source of truth
- Troubleshoot EIGRP failures with structured, targeted show commands
- Inject and remove configuration changes for demonstration and recovery purposes

For a small network — a lab environment, a branch site, a handful of devices — this
approach works well. The scripts are readable, the workflow is transparent, and the
connection between the YAML data and the running configuration is easy to follow.

### Where Netmiko Reaches Its Limits

The approach demonstrated in this module does not scale to an enterprise network.
Understanding why is as important as understanding how to use it.

**1. Connection management is serial by default.**  
Each script in this module connects to one router at a time, runs its commands,
disconnects, and moves on to the next. In a six-router lab this is fast enough to
be invisible. In a network with hundreds or thousands of devices, a serial
connection model becomes a significant bottleneck. Concurrent execution is possible
with Python threading or `concurrent.futures`, but it requires additional engineering
and introduces complexity around error handling and output ordering.

**2. There is no state awareness.**  
Netmiko sends commands and receives output. It has no model of the network, no
understanding of device state across runs, and no awareness of what changed between
the last execution and this one. The verification script in this module compares
live output against a YAML file — but that comparison is performed line by line in
Python, written manually for this specific use case. It does not generalize
automatically to new features, new devices, or new protocols.

**3. Configuration management is additive, not declarative.**  
When `configure_eigrp_classic.py` runs, it pushes configuration lines to the
router. It does not verify what is already there, remove lines that should no longer
exist, or enforce the complete intended state. The `192.1.99.0` network statement
in this demonstration survived a `configure_eigrp_classic.py` run — because the
script adds lines, it does not reconcile them. A truly idempotent, declarative
configuration tool would detect the drift and correct it automatically.

**4. Error recovery is manual.**  
If a push fails midway through — a timeout, an authentication error, an IOS syntax
rejection — the device may be left in a partial configuration state. Netmiko will
surface the error, but it will not roll back the changes. The operator must
intervene manually. Enterprise-grade automation platforms handle partial failure,
rollback, and retry as first-class concerns.

**5. There is no inventory or orchestration layer.**  
The YAML file in this module is a flat device inventory written for this specific
lab. It has no concept of device groups, roles, regions, or hierarchical data
inheritance. Tools like Nornir, Ansible, and pyATS introduce structured inventory
models that allow a single task to be applied intelligently across thousands of
devices, filtered by role, site, or platform, with results aggregated and reported
at scale.

### Where This Course Goes Next

Each module in this series introduces the next tool in a deliberate progression
from low-level to high-level abstraction:

| Module | Protocol  | Tool          | What It Adds                              |
|--------|-----------|---------------|-------------------------------------------|
| 02     | EIGRP     | Netmiko       | Direct SSH, explicit command control      |
| 03–04  | OSPF      | NAPALM        | Structured getters, config diff, rollback |
| 05–06  | IPv6/IS-IS| Nornir        | Concurrent execution, inventory model     |
| 10–12  | BGP       | pyATS/Genie   | Structured parsing, stateful testing      |
| 07–12  | MPLS/VPN  | Ansible       | Declarative intent, idempotency at scale  |

Netmiko is not the wrong tool — it is the right tool for this stage of the
learning progression. It keeps the mechanics visible. Every SSH connection, every
command, every line of output is explicit in the code. That visibility is exactly
what a first automation module should provide.

The limitations noted above are not defects to be fixed in the Netmiko scripts —
they are the motivation for everything that comes next.

---

## Demonstration Summary

| Step | Action                            | Script                          | What It Shows                          |
|------|-----------------------------------|---------------------------------|----------------------------------------|
| 1    | Inject network 192.1.99.0 on R4   | `utils/push_config.py`          | Manual CLI drift introduced            |
| 2    | Run all troubleshooting checks    | `troubleshoot_eigrp_classic.py` | Router appears healthy — all pass      |
| 3    | Run full verification             | `verify_eigrp_classic.py`       | Drift detected — FAIL on 192.1.99.0   |
| 4    | Restore from source of truth      | `configure_eigrp_classic.py`    | YAML is the authoritative baseline     |
| 5    | Re-run verification               | `verify_eigrp_classic.py`       | All checks pass — drift resolved       |

---

*Module 02 — EIGRP Classic Mode / Tool: Netmiko / NAMS26*
