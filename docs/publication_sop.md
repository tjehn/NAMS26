# NAMS26 — Publication SOP
## Pre-Production Checklist and Wrap-Up Procedure
### `docs/publication_sop.md` — Project Root Level

---

> **Document Purpose**
> This SOP defines the steps required to wrap up the NAMS26 project for final
> publication across three deliverables: the Final Product GitHub Repository,
> the PDF Course Document, and the YouTube Video Series.
>
> Steps are organized by deliverable. Where steps repeat across deliverables
> they are noted explicitly rather than assumed.
>
> **This document is an internal production reference — it is NOT published
> to the Final Product GitHub Repository.**

---

## Pre-Production — Global (Complete Before Any Section)

These steps apply to all three deliverables and must be completed first.

### PP-1 — Module Completion Checklist

Confirm each module meets the Module 04 standard before publication:

| Module | Configure Script | Verify Script | Troubleshoot Script | YAML | Template | Verbal Script `_final` | Topology SVG | `moduleNN_guide.md` |
|--------|-----------------|---------------|--------------------|----|----------|----------------------|--------------|---------------------|
| 02 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 03 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 04 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 05 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 06 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 07 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 08 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 09 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 10 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 11 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 12 | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |

### PP-2 — Platform Decision

Confirm recording and demonstration platform before production:

- [ ] **Windows (Work PC / PyCharm)** — no code changes needed
- [ ] **Linux (NAMS26 VM / PyCharm)** — run platform scan before publication (see PP-3)

> **Current preference:** NAMS26 VM (Linux). Confirm before beginning Section 3.

### PP-3 — Platform Scan (Linux VM only — skip if Windows)

If demonstrating on the NAMS26 VM, scan all code and documentation files for
Windows-specific patterns and convert:

- [ ] Path separators: `J:\` and `\\nas01\` references → Linux paths
- [ ] `platform.system() == "Windows"` branches in `ping_hosts.py` — confirm
      Linux branch is correct and tested
- [ ] CRLF line endings → LF (`dos2unix` on all `.py`, `.yaml`, `.j2`, `.md` files)
- [ ] Any `powershell` or `cmd` references in docs → bash equivalents
- [ ] Confirm all scripts run cleanly on the VM after conversion

### PP-4 — AI Reference Scrub

Remove all references to AI generation or co-authorship from files
that will be published to the Final Product GitHub Repository:

- [ ] Search all `.md` files for: `Claude`, `AI`, `CoS`, `CLAUDE.md`, `session_status`
- [ ] Remove or rewrite any references found in student-facing documents
- [ ] Internal files (`CLAUDE.md`, session status docs) are excluded from
      publication and do not need to be scrubbed — see Section 1 exclusion list

### PP-5 — Credential Review

Confirm all credentials in YAML files are lab-generic before publication:

- [ ] SSH username: `netadmin` (lab standard — safe to publish)
- [ ] SSH password: `admin` (lab standard — safe to publish)
- [ ] No personal, production, or site-specific credentials in any file
- [ ] Add credential security note to `APPENDIX.md` if not already present
      (see Appendix credential security section)

---

## Section 1 — Final Product GitHub Repository

### Step 1.1 — Confirm Exclusion List

The following files and directories are **never published to GitHub:**

| Item | Reason |
|------|--------|
| `CLAUDE.md` | Internal — CoS Claude operational instructions |
| `docs/publication_sop.md` (this file) | Internal — production reference |
| `260425*_session_status.md` (all session status files) | Internal — development records |
| `_pdf_reference/` | Internal — reference PDFs |
| `modules/NN/ios_configs/` | Internal — raw IOS config captures |
| `modules/NN/configs/` | Generated — git-ignored, not committed |
| `modules/NN/logs/` | Generated — git-ignored, not committed |
| `.claude/` | Internal — Claude Code settings |
| `APPENDIX.md` | Publish only when complete — confirm before including |

### Step 1.2 — Confirm `.gitignore` Rules

Verify `.gitignore` at project root excludes all items in Step 1.1:

- [ ] `configs/` ignored in all module directories
- [ ] `logs/` ignored in all module directories
- [ ] `_pdf_reference/` ignored
- [ ] `ios_configs/` ignored in all module directories
- [ ] Session status files ignored (add pattern: `*_session_status.md`)
- [ ] `.claude/` ignored

### Step 1.3 — Confirm `moduleNN_guide.md` Complete for Each Module

Each module must have a student-facing guide document at
`modules/NN_name_tool/docs/moduleNN_guide.md` containing:

- [ ] Module objectives
- [ ] Topology diagram embedded as SVG:
      `![Topology](../diagrams/moduleNN_topology_name.svg)`
- [ ] Key configuration concepts
- [ ] Script and YAML reference summary
- [ ] Closing demo summary

### Step 1.4 — Confirm Topology SVGs Exported

For each module:

- [ ] `.drawio` source file present in `diagrams/`
- [ ] `.svg` export present in `diagrams/`
- [ ] SVG renders correctly when opened in a browser
- [ ] SVG is referenced correctly in `moduleNN_guide.md`

### Step 1.5 — README.md Review

- [ ] Project-level `README.md` is current and complete
- [ ] Each module-level `README.md` accurately describes the module
- [ ] No internal references or AI co-authorship mentions
- [ ] Module progression table is accurate

### Step 1.6 — Final GitHub Push

- [ ] All pre-production global steps complete (PP-1 through PP-5)
- [ ] Gitea (`origin`) is fully up to date
- [ ] Final review of diff between Gitea and GitHub
- [ ] Push to GitHub:
      ```bash
      git push github main
      ```
- [ ] Verify repository displays correctly on GitHub — README, diagrams, module structure

---

## Section 2 — PDF Course Document

### Step 2.1 — Confirm All `moduleNN_guide.md` Files Complete

All modules must have complete guide documents before PDF compilation.
Refer to Section 1 Step 1.3 checklist — all boxes must be checked.

### Step 2.2 — Confirm SVGs Scale Correctly

- [ ] Open each SVG in a browser at various zoom levels — confirm readability
- [ ] Test SVG rendering in a sample `pandoc` export before full compilation

### Step 2.3 — Compile PDF with pandoc

Install pandoc if not already available, then compile:

```bash
pandoc \
  docs/cover.md \
  modules/02_eigrp_netmiko/docs/module02_guide.md \
  modules/03_ospf1_napalm/docs/module03_guide.md \
  modules/04_ospf2_napalm/docs/module04_guide.md \
  modules/05_ipv6_eigrp_ospf_nornir/docs/module05_guide.md \
  modules/06_.../docs/module06_guide.md \
  modules/07_.../docs/module07_guide.md \
  modules/08_.../docs/module08_guide.md \
  modules/09_.../docs/module09_guide.md \
  modules/10_.../docs/module10_guide.md \
  modules/11_.../docs/module11_guide.md \
  modules/12_.../docs/module12_guide.md \
  APPENDIX.md \
  -o NAMS26_Course_Document.pdf \
  --toc \
  --toc-depth=2 \
  --pdf-engine=wkhtmltopdf
```

### Step 2.4 — Review PDF Output

- [ ] Table of contents generated and accurate
- [ ] All topology SVGs rendered correctly — no missing images
- [ ] Page breaks between modules are clean
- [ ] Code blocks are readable and properly formatted
- [ ] APPENDIX renders as final chapter

### Step 2.5 — Final PDF Naming and Storage

- [ ] Name: `NAMS26_Network_Automation_Management_Station_2026.pdf`
- [ ] Store at project root
- [ ] Add to `.gitignore` (generated file — not committed to repository)
- [ ] Distribute via separate channel (YouTube description link, etc.)

---

## Section 3 — YouTube Video Series

### Step 3.1 — Confirm Platform and Recording Environment

- [ ] Platform decision confirmed (PP-2)
- [ ] Platform scan complete if Linux VM (PP-3)
- [ ] OBS configured and tested
- [ ] PyCharm font size appropriate for screen recording (recommend 16pt minimum)
- [ ] draw.io open and topology diagram loaded for each module
- [ ] Dark theme consistent across PyCharm and PowerPoint slides

### Step 3.2 — PowerPoint Snippet Decks

For each module, prepare a PowerPoint slide deck containing:

- [ ] Key code snippets (dark background, monospace font, syntax highlighted)
- [ ] Key YAML structures
- [ ] Key Jinja2 template blocks
- [ ] Any topology callout slides needed to supplement draw.io

> **Note:** Marp can generate these programmatically from markdown if manual
> PowerPoint becomes burdensome at scale. Revisit after Module 06.

### Step 3.3 — EVE-NG Lab Confirmation

Before recording each module:

- [ ] EVE-NG lab reset complete (Stop → Wipe → Start)
- [ ] Base config applied to all routers via console
- [ ] RSA keys generated
- [ ] Pre-flight complete: `clear_known_hosts.sh` → `init_ssh.py` → `ping_hosts.py`
- [ ] Configure script deployed and verified clean
- [ ] Verify script passes all checks

### Step 3.4 — Verbal Script Review

- [ ] `moduleNN_verbal_script_final.md` confirmed — no draft stubs remaining
- [ ] Closing demo steps confirmed working against live lab
- [ ] Fault injection and restoration steps tested

### Step 3.5 — Recording Sequence Per Module

1. Intro — objectives, topology map (draw.io)
2. Tool introduction / comparison to previous module
3. YAML walkthrough (PyCharm + PowerPoint snippets)
4. Template walkthrough (PyCharm + PowerPoint snippets)
5. Script walkthrough (PyCharm + PowerPoint snippets)
6. Live deploy (terminal)
7. Verification (terminal)
8. Closing demo — fault injection → troubleshooter → verifier → restore
9. Objectives review and module progression

### Step 3.6 — Post-Production Checklist Per Video

- [ ] Intro/outro consistent across all videos
- [ ] Chapters marked in YouTube with timestamps matching verbal script sections
- [ ] Description includes link to GitHub repository and PDF
- [ ] Tags and thumbnail consistent with series branding

---

## Appendix Notes for Publication

The following items should be confirmed present in `APPENDIX.md`
before final publication:

- [ ] Section 2 — Netmiko: timing parameters table (`global_delay_factor`,
      `delay_factor`, `conn_timeout`)
- [ ] Section 3 — NAPALM: IOL compatibility `optional_args` block with
      dual lab/production comments
- [ ] Section 4 — Nornir: core concepts (inventory, task, runner)
- [ ] Section 7 — Jinja2: `ospf_area: 0` falsy guard pattern
- [ ] Section 8 — YAML: Ethernet interface variables table (enterprise reference)
- [ ] Credential security section: hardcoded → environment variables → vault
- [ ] OSPF area descriptions and routing table designation reference table

---

*NAMS26 — Publication SOP — Internal Document — Not for Publication*
*Place at: `docs/publication_sop.md`*
