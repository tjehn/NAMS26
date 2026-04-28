# CoS Claude — Task Instructions
## Session 260427d — Install Tier 1 Skill Library
### Issued by: Claude.ai planning session

---

> **Objective:** Install three new skills into `.claude/commands/`.
> These skills reduce token consumption by giving CoS repeatable,
> standards-compliant procedures for common module development tasks.
>
> Commit to Gitea (`origin`) when complete. Do NOT push to GitHub.

---

## Background

A skill library is being built for the NAMS26 project. The scaffold skill
already exists at `.claude/commands/scaffold-module.md`. Three new Tier 1
skills are being added in this session.

**Skill library after this session:**

```
.claude/commands/
├── scaffold-module.md          ← existing — do not modify
├── check-module.md             ← NEW — install this session
├── gen-verify-script.md        ← NEW — install this session
└── gen-troubleshoot-script.md  ← NEW — install this session
```

---

## Task 1 — Install `check-module.md`

Copy the attached `check-module.md` file to:
```
.claude/commands/check-module.md
```

This skill inspects a module directory and reports completion status
against the Module 04 standard.

**Usage after installation:**
```
/project:check-module 05
```

---

## Task 2 — Install `gen-verify-script.md`

Copy the attached `gen-verify-script.md` file to:
```
.claude/commands/gen-verify-script.md
```

This skill generates a complete, production-ready verify script for a
module by reading the module YAML and applying NAMS26 standards.

**Usage after installation:**
```
/project:gen-verify-script 05 ipv6_eigrp_ospf nornir
```

---

## Task 3 — Install `gen-troubleshoot-script.md`

Copy the attached `gen-troubleshoot-script.md` file to:
```
.claude/commands/gen-troubleshoot-script.md
```

This skill generates a complete, production-ready troubleshoot script.
It enforces the troubleshoot vs verify distinction in the script docstring
— this is a teaching point that must not be omitted.

**Usage after installation:**
```
/project:gen-troubleshoot-script 05 ipv6_eigrp_ospf nornir
```

---

## Task 4 — Fix `scaffold-module.md` — EVE-NG SOP Reference

The existing `scaffold-module.md` has one error to correct.

**Find in Step 4:**
```
- `docs/eve-ng_lab_reset_sop.md` — copy from
  `modules/04_ospf2_napalm/docs/eve-ng_lab_reset_sop.md`
  and update the module number in the title
```

**Replace with:**
```
- `docs/eve-ng_lab_reset_sop.md` — create with single line only:
  `See project-level docs/eve-ng_lab_reset_sop.md for lab reset procedure.`
  Do not copy the full SOP — the consolidated SOP lives at the project level.
```

---

## Task 5 — Smoke Test All Three New Skills

After installing all three skills, run a smoke test on Module 05:

```
/project:check-module 05
/project:gen-verify-script 05 ipv6_eigrp_ospf nornir
/project:gen-troubleshoot-script 05 ipv6_eigrp_ospf nornir
```

**For `check-module 05`:**
- Confirm it produces a structured completion report
- Confirm it identifies verify and troubleshoot scripts as STUB ONLY
- Note any unexpected findings in the session status doc

**For `gen-verify-script` and `gen-troubleshoot-script`:**
- Review the generated scripts before writing them to disk
- Confirm path resolution is correct (four-level chain, LOG_DIR)
- Confirm check categories match the protocols in the Module 05 YAML
- Confirm the troubleshoot script docstring contains the
  troubleshoot vs verify distinction
- Write to disk only after review confirms correctness
- Do NOT overwrite any existing non-stub scripts

---

## Task 6 — Session Status Document

Create `260427d_session_status.md` at the project root documenting:
- Skills installed
- Smoke test results
- Any issues found
- Generated script file paths

---

## Git Commit

After all tasks are complete:

```bash
git add .claude/commands/
git add modules/05_ipv6_eigrp_ospf_nornir/scripts/
git add 260427d_session_status.md
git commit -m "Skills — install check-module, gen-verify-script, gen-troubleshoot-script; fix scaffold-module SOP reference"
git push origin main
```

**Do not push to GitHub.**

---

## Note to CoS Claude

The three skill files are attached to this instruction document.
Place each file exactly as specified — do not rename or reorganize.

The skill library will grow over time. Tier 2 skills (YAML builder,
Ansible scaffolder, pyATS testbed generator) will be added when
Modules 07+ enter active development.

---

*Instructions issued by Claude.ai — Session 260427d*
*NAMS26 — Network Automation Management Station 2026*
