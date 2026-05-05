# NAMS27 — Scope Plan
## AI-Augmented Network Operations

---

## Core Concept

NAMS26 teaches Python driving Cisco infrastructure.
NAMS27 teaches AI driving the automation.

Same lab, same routers — different layer of abstraction on top.

**The key distinction:**
- NAMS26 — Engineer writes Python scripts that drive the network
- NAMS27 — Engineer converses with Claude; Claude drives the network through MCP tools

NAMS26 builds the foundation. NAMS27 is where that foundation meets AI orchestration.

---

## Confirmed Topics

| Topic | What It Is |
|-------|-----------|
| Network Automation MCP Server | FastMCP + Scrapli — Claude talks directly to routers via MCP tools (`run_show`, `push_config`, `snapshot_state`, `check_maintenance_window`, `assess_risk`) |
| EVE-NG Topology Builder MCP | Claude builds EVE-NG lab topologies conversationally from structured requests |
| SNMP/CDP Topology Map Generator | Claude discovers and maps live network topology via CDP/SNMP, renders in Flask |
| n8n MCP Integration | Claude orchestrates network operations workflows through n8n |
| CVE MCP Server | Claude cross-references network devices against live CVE vulnerability database |
| Nmap Vulnerability Scanning | Python + Nmap automated vulnerability scanning against network devices |

---

## Tool Progression (Draft)

| Modules | Tool | Focus |
|---------|------|-------|
| TBD | FastMCP + Scrapli | Claude as network operator |
| TBD | n8n + MCP | Claude as workflow orchestrator |
| TBD | Nmap + CVE MCP | Claude as security analyst |
| TBD | Flask + All tools | AI-augmented NOC capstone |

---

## Relationship to NAMS26

- Same EVE-NG lab and router fabric as NAMS26
- NAMS26 automation scripts (Netmiko, NAPALM, Nornir, Ansible, pyATS/Genie) are the foundation
- NAMS27 adds the AI orchestration layer on top of that foundation
- Students should complete NAMS26 before NAMS27

---

## Planning Status

- **Scope:** Defined — this document
- **Module count:** TBD
- **Detailed design:** Begins after NAMS26 Module 12 development is complete
- **Detailed design method:** Claude.ai collaboration session (same process as NAMS26)

---

*NAMS27 — AI-Augmented Network Operations*
*Scope Plan — 2026-05-05*
*Internal planning document*
