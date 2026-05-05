# NAMS26 — Pinned Items Discussion
## Context Document for Claude.ai Planning Session
### Date: 2026-05-05

---

## Purpose

This document provides context for a focused discussion of pinned items
accumulated during NAMS26 Modules 02–05 development. These items require
planning decisions before Module 06 development begins.

---

## Project Context (Brief)

NAMS26 is a 12-module network automation curriculum using Python and Cisco
IOS (IOL) routers in an EVE-NG lab. Modules 02–05 development is complete.
Next: Module 06 (IS-IS / Nornir / Named Mode).

Project files for full context:
- `NAMS26_context.md` — project overview and module status
- `CLAUDE.md` — coding standards and architecture
- Current session status doc

---

## Pinned Items for Discussion

---

### PIN-01 — Structured Development Process Document

**What:** A formal document defining the ordered steps for developing each
module, with role assignments (You / CoS / Claude.ai).

**Why:** As we move into Modules 06–12, a repeatable process will save
planning time and reduce errors. The ad-hoc approach worked for 02–05
but needs structure for the remaining eight modules.

**Discussion needed:**
- What are the ordered steps from "module planned" to "module complete"?
- Which steps are Claude.ai (planning), CoS (execution), or instructor (lab)?
- How do we handle dependencies between steps?
- Should this live in CLAUDE.md or as a standalone `docs/development_sop.md`?

---

### PIN-02 — Standardized Topology Template (Modules 06–12)

**What:** A reusable physical fabric already built in EVE-NG:
- R1–R12 (IOL routers)
- SW21, SW22 (IOL core switches — VLAN-based logical topology)
- OOB_SW01 (management switch)
- Project-root `utils/` toolkit for lab management

**Reference:** `260504_reusable_topology_foundation.md`

**Status:** Physical fabric built, toolkit scripts written but untested.

**Discussion needed:**
- How do VLAN assignments map to logical topologies per module?
- Which routers participate in which modules?
- Does the 12-router fabric support all planned topologies (IS-IS, BGP,
  MPLS, VPN, GRE)?
- When does the project-root utils toolkit get validated?

---

### PIN-03 — Network Automation MCP Server

**What:** Three versions of a FastMCP + Scrapli async SSH server reviewed:
1. `mcp_automation_server.py` — basic (password auth)
2. `mcp_automation_server_v2.py` — security/performance (SSH key + async)
3. `MCPServer.py` — full production (intent, snapshots, maintenance window,
   risk assessment)

Source: Udemy course "Automate Network Tasks with Claude and MCP"

**Discussion needed:**
- Can this MCP server be wired to the NAMS26 lab so Claude.ai can run
  show commands directly against live routers?
- What would the workflow change look like?
- Is this a Module 13 topic or a development workflow tool?
- NAMS27 scope vs NAMS26 scope?

---

### PIN-04 — EVE-NG Topology Builder MCP

**What:** An MCP server that accepts structured topology requests and
produces EVE-NG `.unl` topology files, device inventory YAML, and
cabling tables automatically.

**Example request that triggered this pin:**
> Two core switches (16 interfaces each), eight distribution switches
> (16 interfaces each), twelve access switches (20 interfaces each)
> with cabling instructions.

**Discussion needed:**
- Python-based generator or direct EVE-NG API integration?
- Module 13 proof-of-concept or NAMS27 full implementation?
- How does this interact with PIN-02 (physical fabric)?

---

### PIN-05 — SNMP/CDP Topology Map Generator

**What:** A tool that uses SNMP and CDP to discover and map network
topology automatically — render in Flask.

**Note:** CDP on the shared fabric (PIN-02) shows switch neighbors,
not router-to-router links. Logical topology must be derived from
VLAN assignments on SW21/SW22.

**Discussion needed:**
- Module 13 proof-of-concept vs NAMS27 full implementation?
- Relationship to `label_interfaces.py` already built in project-root utils?
- Data flow: CDP discovery → VLAN correlation → topology graph → Flask render

---

### PIN-06 — n8n MCP Integration

**What:** n8n workflow automation platform now has an official MCP
connection allowing Claude to build and edit n8n workflows directly.

**Relevance:** n8n + Claude MCP as a network operations orchestration
platform — trigger verification runs, route alerts, generate reports.

**Discussion needed:**
- NAMS27 scope only?
- Any relevance to NAMS26 Module 13 capstone?

---

### PIN-07 — Nmap Vulnerability Scanning

**What:** Udemy course "Automate Network Vulnerability Scanning with
Python and Nmap" from the same instructor as the MCP course.

**Discussion needed:**
- NAMS27 scope confirmed?
- Buy the course or build from scratch?
- Integration with CVE MCP server (already pinned for NAMS27)?

---

### PIN-08 — Linux Adaptation Addendum

**What:** NAMS26 is developed on Windows 10. A future addendum in
`APPENDIX.md` will explain how students can adapt scripts for Linux/macOS.

**Key differences to document:**
- `python` vs `python3`
- `ping_hosts.py` already has platform branching
- `init_ssh.py` uses paramiko — cross-platform
- Path separators handled by `os.path`

**Decision needed:**
- Written after Module 12 complete (current plan)?
- Or written per module as each module is completed?

---

### PIN-09 — moduleNN_guide.md (Student-Facing Lab Guide)

**What:** Each module needs a student-facing guide document for GitHub
publication. Vision: one document that follows the verbal script but
written for the student reading independently.

**Contents:**
- Module objectives
- Topology diagram (SVG embedded)
- Tool introduction
- Lab walkthrough at student level
- Key commands and expected output
- Closing demo summary (what student should reproduce)

**Decision needed:**
- Written during module development or during production phase?
- Current decision: production phase (after video recording) — confirm?
- Template needed before Module 06?

---

### PIN-10 — NAMS27 Scope Definition

**What:** NAMS27 is the "second book" — AI-augmented network and security
operations. Items confirmed for NAMS27:
- Network Automation MCP Server (full implementation)
- EVE-NG Topology Builder MCP (full implementation)
- SNMP/CDP Topology Map Generator (full implementation)
- n8n MCP integration
- CVE MCP Server (cybersecurity news reference)
- Nmap vulnerability scanning

**Discussion needed:**
- Formal scope document for NAMS27?
- When does NAMS27 planning begin — after Module 12 or earlier?
- Any NAMS27 topics that should be pulled forward into NAMS26 Module 13?

---

## Suggested Discussion Order

1. PIN-01 — Development process document (unblocks Module 06)
2. PIN-02 — Topology template validation plan (unblocks Module 06 lab)
3. PIN-09 — Student guide decision (impacts all remaining modules)
4. PIN-03 through PIN-08 — MCP, tools, NAMS27 scope
5. PIN-10 — NAMS27 formal scope

---

*NAMS26 — Network Automation Management Station 2026*
*Pinned Items Discussion Document — 2026-05-05*
