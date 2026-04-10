# NAMS26 — Workflow Migration Planning Note
## Post-Module 04 | Claude.ai Planning Session

---

## Context

After Module 04 completion, the development workflow will be migrated from
the current split-brain setup (Claude.ai planning + Claude Code on VM) to a
consolidated environment on the Work PC.

---

## Target Architecture

```
Obsidian Vault (planning / context / documentation)
        ↓
PyCharm + Claude Code (Work PC — single development and execution environment)
        ↓
ESXi / EVE-NG lab (192.168.1.0/24) — direct SSH to r1.lab through r10.lab
        ↓
Synology NAS (clean staging / archive after reorganization)
```

## Why This Makes Sense

- Work PC, EVE-NG server, and Synology are all on 192.168.1.0/24 — no VPN,
  no tunneling, no execution layer split needed
- Eliminates the file shuttle between Claude.ai and Claude Code on the VM
- Obsidian vault becomes the single source of truth for planning context —
  Claude Code reads directly from vault rather than uploaded documents
- Synology becomes a clean archive rather than a staging mess

---

## Migration Steps (post-Module 04)

1. Install PyCharm on Work PC
2. Install Claude Code extension in PyCharm
3. Clone or link NAMS26 repository from Synology to Work PC
4. Configure Python environment (.venv, pip install dependencies)
5. Verify SSH connectivity: Work PC → r1.lab through r10.lab
6. Synology cleanup — first Claude Code task on the new setup
7. Obsidian vault integration design (separate discussion — see below)
8. Module 05 begins from the new environment

---

## Synology Cleanup

Current state: a couple of unorganized directories used for ad-hoc SCP
staging along the way. Not a blocker — easy to address.

Approach: once PyCharm + Claude Code is configured on the Work PC, point
Claude Code at the Synology NAMS26 directories, have it inventory what is
there, propose a clean structure consistent with the established module
layout, and reorganize. Low risk, good first task for the new environment.

---

## Obsidian Vault Integration — To Be Designed

This warrants a dedicated planning conversation. Key questions to resolve:

- Where does the vault live? (Local on Work PC, or on Synology/shared drive?)
- How is vault content surfaced to Claude Code? Options include:
  - Direct file path access (Claude Code reads .md files from vault directory)
  - MCP server for Obsidian (if one exists or can be configured)
  - Structured export of relevant notes into the project docs/ directory
- What moves into the vault vs. stays in the project docs/ directory?
  - Planning documents (module04_planning.md style) — good vault candidates
  - SOPs and checklists — good vault candidates
  - Script design specs — probably stay in project docs/
- How does the NAMS26_context.md pattern evolve in the new workflow?

Defer this discussion until Module 04 is fully complete and the basic
PyCharm + Claude Code setup on the Work PC is confirmed working.

---

## Current VM Git Setup (for reference)

- Git remote `origin` → Gitea at 192.168.1.12:8418 (dev)
- Git remote `github` → GitHub (production)
- Option to sync at end of project for demonstration and video purposes
- No obligation to maintain the VM workflow after migration — the VM Git
  can be a final sync target rather than the primary development environment

---

*Pinned for post-Module 04 discussion*
*NAMS26 — Network Automation Management Station 2026*
