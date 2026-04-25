#!/usr/bin/env python3
"""
File     : utils/ospf_topology_map.py
Purpose  : Connect to a single Cisco IOS router via NAPALM, retrieve the
           full OSPF Link State Database, parse all LSA types, and render
           a text-format topology map.

           Output has three sections (--map adds the first):
             0. ASCII Map    — graphical topology diagram (--map flag)
             1. Area Tree    — hierarchical view: areas → routers → links
             2. Adjacency Table — router × router neighbor grid

           All LSA types are parsed and displayed:
             Type 1  — Router LSA          (intra-area routers and links)
             Type 2  — Network LSA         (broadcast segment DR and members)
             Type 3  — Summary Net LSA     (inter-area prefixes from ABR)
             Type 4  — Summary ASBR LSA    (ASBR reachability from ABR)
             Type 5  — AS External LSA     (redistributed external routes)
             Type 7  — NSSA External LSA   (external routes in NSSA areas)

CLI Commands Issued:
    show ip ospf database
        Master command — retrieves the full LSDB summary in a single call.
        All LSA type sections below are parsed from this output.

    show ip ospf database router
        Retrieves the full Type 1 Router LSA detail for all routers in
        the area. Each Router LSA contains the complete link descriptions:

          Transit Network links  — router is connected to a broadcast segment.
                                   Link ID = DR interface IP, used to identify
                                   which segment this router belongs to.
          Point-to-Point links   — direct P2P connection to a neighbor router.
                                   Link ID = neighbor Router ID, Link Data =
                                   local interface IP. Used to build exact P2P
                                   pairs (R2↔R5, R4↔R5, R7↔R8).
          Stub Network links     — loopback or stub prefix. Not used for
                                   topology map adjacency building.

        This is the authoritative source for topology map construction.
        It is flooded to all routers in the area so any router gives a
        complete view regardless of its position in the topology.

    The following manual CLI equivalents retrieve each LSA type
    individually and are provided for student reference:

      Type 1 — Router LSA
        show ip ospf database router
        show ip ospf database router <router-id>
        Originated by every router. Describes the router's links,
        interface costs, and adjacency state within an area.

      Type 2 — Network LSA
        show ip ospf database network
        show ip ospf database network <dr-interface-ip>
        Originated by the DR on each broadcast segment. Lists all
        routers attached to that segment.

      Type 3 — Summary Net LSA
        show ip ospf database summary
        show ip ospf database summary <network>
        Originated by the ABR. Advertises prefixes from one area
        into another. Visible as O IA in the routing table.

      Type 4 — Summary ASBR LSA
        show ip ospf database asbr-summary
        show ip ospf database asbr-summary <asbr-router-id>
        Originated by the ABR. Advertises reachability to an ASBR
        into areas that do not contain the ASBR directly.

      Type 5 — AS External LSA
        show ip ospf database external
        show ip ospf database external <network>
        Originated by the ASBR. Advertises redistributed external
        routes throughout the OSPF domain. Visible as O E1 or O E2.

      Type 7 — NSSA External LSA
        show ip ospf database nssa-external
        show ip ospf database nssa-external <network>
        Originated by an ASBR inside an NSSA area. Converted to a
        Type 5 LSA by the ABR at the NSSA boundary. Visible as
        O N1 or O N2 within the NSSA area.

    show ip ospf neighbor detail
        Retrieves full neighbor adjacency detail including neighbor
        Router ID, interface, adjacency state, and neighbor IP address.
        Used to annotate the area tree and populate the adjacency table.

Usage:
    python ospf_topology_map.py --router <IP or DNS>

    # Optional: filter output to a specific area
    python ospf_topology_map.py --router r1.lab --area 0

    # Credentials are prompted interactively — password input is hidden

Examples:
    python utils/ospf_topology_map.py --router r1.lab
    python utils/ospf_topology_map.py --router 192.168.1.101
    python utils/ospf_topology_map.py --router r8.lab --area 10

Pre-flight requirement:
    Run utils/clear_known_hosts.sh and utils/check_ssh.py before executing
    this script after every EVE-NG lab reboot.

Notes:
    - Connect to any router in the topology — the full LSDB is flooded to
      all routers within an area, so any router gives a complete view of
      its area. An ABR (e.g. R8) will show both areas.
    - IOL optional_args (dest_file_system, inline_transfer) are applied
      automatically — no manual configuration required.
    - Output is saved to NAMS26/logs/ospf_topology_map_YYYYMMDD_HHMMSS.log
"""

import os
import re
import sys
import argparse
import getpass
from datetime import datetime
from napalm import get_network_driver
from napalm.base.exceptions import ConnectionException

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)
LOG_DIR      = os.path.join(MODULE_DIR, "logs")

KNOWN_HOSTS_FILE = os.path.expanduser("~/.ssh/known_hosts")

# =============================================================================
# ANSI COLORS
# =============================================================================
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

_ANSI_RE = re.compile(r'\033\[[0-9;]*m')

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)

def emit(line: str, lf=None) -> None:
    print(line)
    if lf:
        lf.write(_strip_ansi(line) + "\n")

def emit_raw(text: str, lf=None) -> None:
    print(text)
    if lf:
        lf.write(_strip_ansi(text) + "\n")


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logger() -> object:
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = os.path.join(LOG_DIR, f"ospf_topology_map_{timestamp}.log")
    lf = open(log_path, "w", encoding="utf-8")
    lf.write("NAMS26 — OSPF Topology Map\n")
    lf.write(f"Log created : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lf.write(f"Log file    : {log_path}\n")
    lf.write("=" * 70 + "\n\n")
    print(f"{CYAN}  [INFO]{RESET} Logging to  : {log_path}")
    return lf


# =============================================================================
# NAPALM CONNECTION
# =============================================================================

def connect(router: str, username: str, password: str, lf=None):
    if not os.path.isfile(KNOWN_HOSTS_FILE):
        emit(f"{YELLOW}  [WARN]{RESET} known_hosts not found — run clear_known_hosts.sh then check_ssh.py first", lf)

    driver = get_network_driver("ios")
    optional_args = {
        "ssh_config_file":  None,
        # IOL has no flash: filesystem — redirect NAPALM's dir space check to nvram:
        "dest_file_system": "nvram:",
        # Send config over the SSH session instead of SCP — IOL does not support SCP
        "inline_transfer":  True,
        # global_delay_factor is forwarded by NAPALM to the underlying Netmiko connection.
        # Doubles all Netmiko internal timing constants to accommodate slow IOL responses.
        # Current: 2.0   Range: 1.0 (fastest, may miss prompts) – 5.0 (slow hosts)
        "global_delay_factor": 2.0,
    }
    try:
        device = driver(
            hostname=router,
            username=username,
            password=password,
            optional_args=optional_args,
        )
        device.open()
        emit(f"{GREEN}  [PASS]{RESET} Connected to {router}", lf)
        return device
    except ConnectionException as exc:
        emit(f"{RED}  [FAIL]{RESET} Connection failed to {router}: {exc}", lf)
    except Exception as exc:
        emit(f"{RED}  [FAIL]{RESET} Connection error: {exc}", lf)
    return None


# =============================================================================
# LSDB PARSERS
# =============================================================================

def _parse_lsdb(raw: str) -> dict:
    """Parse full 'show ip ospf database' output into a structured dict.

    Returns:
        {
            "areas": {
                "0": {
                    "router":   [ {link_id, adv_router, age, seq, checksum, links}, ... ],
                    "network":  [ {link_id, adv_router, age, seq, checksum}, ... ],
                    "summary":  [ {link_id, adv_router, age, seq, checksum}, ... ],
                    "asbr":     [ {link_id, adv_router, age, seq, checksum}, ... ],
                    "nssa":     [ {link_id, adv_router, age, seq, checksum}, ... ],
                },
                ...
            },
            "external": [ {link_id, adv_router, age, seq, checksum, tag}, ... ],
            "router_id": "0.0.0.1",
            "process_id": "1",
        }
    """
    result = {
        "areas"     : {},
        "external"  : [],
        "router_id" : "",
        "process_id": "",
    }

    # Header: OSPF Router with ID (0.0.0.1) (Process ID 1)
    hdr_re = re.compile(
        r'OSPF Router with ID \((\S+)\)\s+\(Process ID (\d+)\)',
        re.IGNORECASE
    )
    m = hdr_re.search(raw)
    if m:
        result["router_id"]  = m.group(1)
        result["process_id"] = m.group(2)

    # Section headers identify LSA type and area
    # IOS format uses tab indentation: \t\tRouter Link States (Area 0)
    # e.g. "\t\tRouter Link States (Area 0)"
    #      "\t\tSummary Net Link States (Area 10)"
    #      "\t\tType-5 AS External Link States"
    #      "\t\tType-7 AS External Link States (Area 1)"
    section_re = re.compile(
        r'^[ \t]*([\w][\w\s\-]+Link States)(?:\s+\(Area\s+(\S+)\))?[ \t]*$',
        re.IGNORECASE | re.MULTILINE
    )

    # LSA data line (standard 5-column or 6-column with link count)
    lsa_re = re.compile(
        r'^(\d+\.\d+\.\d+\.\d+)\s+'   # Link ID
        r'(\d+\.\d+\.\d+\.\d+)\s+'    # ADV Router
        r'(\d+)\s+'                    # Age
        r'(0x[0-9A-Fa-f]+)\s+'        # Seq#
        r'(0x[0-9A-Fa-f]+)'           # Checksum
        r'(?:\s+(\d+))?',              # Link count (optional)
        re.MULTILINE
    )

    # Tag line for Type-5 (external tag)
    tag_re = re.compile(r'External\s+Tag:\s+(\S+)', re.IGNORECASE)

    # Split raw into sections
    sections = list(section_re.finditer(raw))

    for idx, sec_match in enumerate(sections):
        sec_title = sec_match.group(1).strip().lower()
        area      = sec_match.group(2) if sec_match.group(2) else None

        # Determine LSA type from section title
        if "router link" in sec_title:
            lsa_type = "router"
        elif "net link" in sec_title and "summary" not in sec_title:
            lsa_type = "network"
        elif "summary net" in sec_title:
            lsa_type = "summary"
        elif "summary asbr" in sec_title or "asbr" in sec_title:
            lsa_type = "asbr"
        elif "type-7" in sec_title or "nssa" in sec_title:
            lsa_type = "nssa"
        elif "external" in sec_title or "type-5" in sec_title:
            lsa_type = "external"
        else:
            lsa_type = "unknown"

        # Extract text block for this section
        sec_start = sec_match.end()
        sec_end   = sections[idx + 1].start() if idx + 1 < len(sections) else len(raw)
        sec_text  = raw[sec_start:sec_end]

        # Parse LSA entries in this block
        entries = []
        for lsa_match in lsa_re.finditer(sec_text):
            entry = {
                "link_id"    : lsa_match.group(1),
                "adv_router" : lsa_match.group(2),
                "age"        : lsa_match.group(3),
                "seq"        : lsa_match.group(4),
                "checksum"   : lsa_match.group(5),
                "links"      : lsa_match.group(6) or "",
            }
            # Check for external tag on next line(s)
            after = sec_text[lsa_match.end():lsa_match.end() + 80]
            tag_m = tag_re.search(after)
            entry["tag"] = tag_m.group(1) if tag_m else ""
            entries.append(entry)

        if not entries:
            continue

        # Store entries in result
        if lsa_type == "external":
            result["external"].extend(entries)
        else:
            if area is None:
                area = "0"
            if area not in result["areas"]:
                result["areas"][area] = {
                    "router" : [],
                    "network": [],
                    "summary": [],
                    "asbr"   : [],
                    "nssa"   : [],
                }
            result["areas"][area][lsa_type].extend(entries)

    return result


def _parse_ospf_neighbor_detail(raw: str) -> dict:
    """Parse 'show ip ospf neighbor detail' into adjacency dict.

    Returns:
        { neighbor_rid: { "interface": str, "state": str, "address": str }, ... }
    """
    neighbors = {}
    # Pattern: Neighbor <rid>, interface address <ip>
    #          In the area <area> via interface <intf>
    #          Neighbor priority is <n>, State is <state>
    nbr_re   = re.compile(r'Neighbor\s+(\S+),\s+interface address\s+(\S+)', re.IGNORECASE)
    intf_re  = re.compile(r'via interface\s+(\S+)', re.IGNORECASE)
    state_re = re.compile(r'State is\s+(\S+)', re.IGNORECASE)

    current_rid  = None
    current_addr = None

    for line in raw.splitlines():
        m = nbr_re.search(line)
        if m:
            current_rid  = m.group(1)
            current_addr = m.group(2)
            neighbors[current_rid] = {"interface": "", "state": "", "address": current_addr}
            continue
        if current_rid:
            m2 = intf_re.search(line)
            if m2:
                neighbors[current_rid]["interface"] = m2.group(1)
            m3 = state_re.search(line)
            if m3:
                neighbors[current_rid]["state"] = m3.group(1)

    return neighbors


# =============================================================================
# TOPOLOGY RENDERERS
# =============================================================================

def _render_area_tree(lsdb: dict, neighbors: dict, filter_area: str, lf=None) -> None:
    """Render Section 1 — hierarchical area tree."""

    bar    = "=" * 70
    thin   = "─" * 70

    emit(f"\n{BOLD}{bar}{RESET}", lf)
    emit(f"{BOLD}  OSPF Topology Map — Area Tree{RESET}", lf)
    emit(f"{BOLD}  Router ID : {lsdb['router_id']}   Process ID : {lsdb['process_id']}{RESET}", lf)
    emit(f"{BOLD}{bar}{RESET}", lf)

    areas = lsdb["areas"]
    if filter_area and filter_area not in areas:
        emit(f"{YELLOW}  [WARN]{RESET} Area {filter_area} not found in LSDB.", lf)
        return

    target_areas = {filter_area: areas[filter_area]} if filter_area else areas

    for area_id, area_data in sorted(target_areas.items(), key=lambda x: int(x[0])):
        router_lsas  = area_data.get("router",  [])
        network_lsas = area_data.get("network", [])
        summary_lsas = area_data.get("summary", [])
        asbr_lsas    = area_data.get("asbr",    [])
        nssa_lsas    = area_data.get("nssa",    [])

        # Area header
        area_label = f"Area {area_id} (Backbone)" if area_id == "0" else f"Area {area_id}"
        emit(f"\n{BOLD}{CYAN}┌─ {area_label}{RESET}", lf)
        emit(f"{CYAN}│{RESET}", lf)

        # ── Type 1: Router LSAs ──
        if router_lsas:
            emit(f"{CYAN}│  {BOLD}[Type 1] Router LSAs{RESET}", lf)
            for lsa in sorted(router_lsas, key=lambda x: x["link_id"]):
                rid     = lsa["link_id"]
                adv     = lsa["adv_router"]
                links   = lsa["links"]
                age     = lsa["age"]
                seq     = lsa["seq"]
                is_self = (rid == lsdb["router_id"])
                is_nbr  = rid in neighbors

                marker = f"{GREEN}◉{RESET}" if is_self else (f"{CYAN}●{RESET}" if is_nbr else "○")
                state  = f" {GREEN}[THIS ROUTER]{RESET}" if is_self else \
                         (f" {GREEN}[FULL — {neighbors[rid]['interface']}]{RESET}" if is_nbr else "")

                emit(f"{CYAN}│    {marker} {BOLD}{rid}{RESET}{state}", lf)
                emit(f"{CYAN}│      {DIM}adv={adv}  links={links}  age={age}s  seq={seq}{RESET}", lf)

        # ── Type 2: Network LSAs ──
        if network_lsas:
            emit(f"{CYAN}│{RESET}", lf)
            emit(f"{CYAN}│  {BOLD}[Type 2] Network LSAs (Broadcast Segments){RESET}", lf)
            for lsa in sorted(network_lsas, key=lambda x: x["link_id"]):
                dr_ip  = lsa["link_id"]
                dr_rid = lsa["adv_router"]
                age    = lsa["age"]
                seq    = lsa["seq"]
                emit(f"{CYAN}│    ▸ {YELLOW}DR {dr_rid}{RESET}  segment={dr_ip}  age={age}s  seq={seq}", lf)

        # ── Type 3: Summary Net LSAs ──
        if summary_lsas:
            emit(f"{CYAN}│{RESET}", lf)
            emit(f"{CYAN}│  {BOLD}[Type 3] Summary Net LSAs (Inter-Area — from ABR){RESET}", lf)
            for lsa in sorted(summary_lsas, key=lambda x: x["link_id"]):
                prefix = lsa["link_id"]
                abr    = lsa["adv_router"]
                age    = lsa["age"]
                seq    = lsa["seq"]
                emit(f"{CYAN}│    ▸ {BLUE}O IA{RESET}  {prefix}  via ABR {abr}  age={age}s  seq={seq}", lf)

        # ── Type 4: Summary ASBR LSAs ──
        if asbr_lsas:
            emit(f"{CYAN}│{RESET}", lf)
            emit(f"{CYAN}│  {BOLD}[Type 4] Summary ASBR LSAs (ASBR Reachability){RESET}", lf)
            for lsa in sorted(asbr_lsas, key=lambda x: x["link_id"]):
                asbr_rid = lsa["link_id"]
                adv      = lsa["adv_router"]
                age      = lsa["age"]
                seq      = lsa["seq"]
                emit(f"{CYAN}│    ▸ {YELLOW}ASBR{RESET}  {asbr_rid}  advertised by {adv}  age={age}s  seq={seq}", lf)

        # ── Type 7: NSSA External LSAs ──
        if nssa_lsas:
            emit(f"{CYAN}│{RESET}", lf)
            emit(f"{CYAN}│  {BOLD}[Type 7] NSSA External LSAs (O N1/N2){RESET}", lf)
            for lsa in sorted(nssa_lsas, key=lambda x: x["link_id"]):
                prefix = lsa["link_id"]
                adv    = lsa["adv_router"]
                age    = lsa["age"]
                seq    = lsa["seq"]
                tag    = f"  tag={lsa['tag']}" if lsa.get("tag") else ""
                emit(f"{CYAN}│    ▸ {YELLOW}O N{RESET}   {prefix}  adv={adv}  age={age}s  seq={seq}{tag}", lf)

        emit(f"{CYAN}└{'─' * 66}{RESET}", lf)

    # ── Type 5: AS External LSAs (not area-scoped) ──
    external_lsas = lsdb.get("external", [])
    if external_lsas and not filter_area:
        emit(f"\n{BOLD}{CYAN}┌─ External Routes{RESET}", lf)
        emit(f"{CYAN}│{RESET}", lf)
        emit(f"{CYAN}│  {BOLD}[Type 5] AS External LSAs (O E1/E2 — redistributed){RESET}", lf)
        for lsa in sorted(external_lsas, key=lambda x: x["link_id"]):
            prefix = lsa["link_id"]
            adv    = lsa["adv_router"]
            age    = lsa["age"]
            seq    = lsa["seq"]
            tag    = f"  tag={lsa['tag']}" if lsa.get("tag") else ""
            emit(f"{CYAN}│    ▸ {RED}O E{RESET}   {prefix}  adv={adv}  age={age}s  seq={seq}{tag}", lf)
        emit(f"{CYAN}└{'─' * 66}{RESET}", lf)


def _render_adjacency_table(lsdb: dict, neighbors: dict, filter_area: str, lf=None) -> None:
    """Render Section 2 — router × router adjacency table."""

    bar = "=" * 70

    emit(f"\n{BOLD}{bar}{RESET}", lf)
    emit(f"{BOLD}  OSPF Adjacency Table{RESET}", lf)
    emit(f"{BOLD}{bar}{RESET}", lf)

    areas = lsdb["areas"]
    target_areas = {filter_area: areas[filter_area]} if (filter_area and filter_area in areas) else areas

    for area_id, area_data in sorted(target_areas.items(), key=lambda x: int(x[0])):
        router_lsas = area_data.get("router", [])
        if not router_lsas:
            continue

        area_label = f"Area {area_id} (Backbone)" if area_id == "0" else f"Area {area_id}"
        emit(f"\n{CYAN}  {area_label}{RESET}", lf)

        # Collect all router IDs in this area
        rids = sorted(set(lsa["link_id"] for lsa in router_lsas))

        # Shorten RIDs for column headers — use last octet only
        def short(rid: str) -> str:
            parts = rid.split(".")
            return f"0.0.0.{parts[-1]}" if len(parts) == 4 else rid

        W_RID = 12
        W_COL = 10

        # Header row
        header = f"  {'Router ID':<{W_RID}}"
        for rid in rids:
            header += f"  {short(rid):<{W_COL}}"
        emit(f"{BOLD}{header}{RESET}", lf)
        emit(f"  {'─' * (W_RID + (W_COL + 2) * len(rids))}", lf)

        # Data rows — one per router
        for row_rid in rids:
            is_self = (row_rid == lsdb["router_id"])
            row_label = f"{short(row_rid)}"
            if is_self:
                row_label += "*"

            row = f"  {row_label:<{W_RID}}"

            for col_rid in rids:
                if row_rid == col_rid:
                    cell = f"{'—':<{W_COL}}"
                    row += f"  {DIM}{cell}{RESET}"
                elif col_rid in neighbors and neighbors[col_rid].get("state", "").upper().startswith("FULL"):
                    cell = f"{'FULL':<{W_COL}}"
                    row += f"  {GREEN}{cell}{RESET}"
                elif col_rid in neighbors:
                    state = neighbors[col_rid].get("state", "?")[:8]
                    cell  = f"{state:<{W_COL}}"
                    row  += f"  {YELLOW}{cell}{RESET}"
                else:
                    # Both in same area LSDB but not directly adjacent
                    cell = f"{'·':<{W_COL}}"
                    row += f"  {DIM}{cell}{RESET}"
            emit(row, lf)

        emit(f"  {'─' * (W_RID + (W_COL + 2) * len(rids))}", lf)
        emit(f"  {DIM}* = this router   FULL = direct adjacency   · = same area, not adjacent{RESET}", lf)

    # Neighbor detail block
    if neighbors:
        emit(f"\n{BOLD}  Direct Neighbors (from show ip ospf neighbor detail){RESET}", lf)
        emit(f"  {'─' * 60}", lf)
        W_N = 14
        W_I = 16
        W_S = 12
        W_A = 16
        hdr = f"  {'Neighbor RID':<{W_N}}  {'Interface':<{W_I}}  {'State':<{W_S}}  {'Address':<{W_A}}"
        emit(f"{BOLD}{hdr}{RESET}", lf)
        emit(f"  {'─' * 60}", lf)
        for rid, data in sorted(neighbors.items()):
            state = data.get("state", "")
            color = GREEN if state.upper().startswith("FULL") else YELLOW
            row = (
                f"  {rid:<{W_N}}  "
                f"{data.get('interface',''):<{W_I}}  "
                f"{color}{state:<{W_S}}{RESET}  "
                f"{data.get('address',''):<{W_A}}"
            )
            emit(row, lf)
        emit(f"  {'─' * 60}", lf)


def _render_lsdb_counts(lsdb: dict, lf=None) -> None:
    """Render a summary count of LSAs per area per type."""

    emit(f"\n{BOLD}  LSA Count Summary{RESET}", lf)
    emit(f"  {'─' * 60}", lf)

    W = 10
    header = f"  {'Area':<8}  {'Type1':>{W}}  {'Type2':>{W}}  {'Type3':>{W}}  {'Type4':>{W}}  {'Type7':>{W}}"
    emit(f"{BOLD}{header}{RESET}", lf)
    emit(f"  {'─' * 60}", lf)

    for area_id, area_data in sorted(lsdb["areas"].items(), key=lambda x: int(x[0])):
        row = (
            f"  {area_id:<8}"
            f"  {len(area_data.get('router',  [])):>{W}}"
            f"  {len(area_data.get('network', [])):>{W}}"
            f"  {len(area_data.get('summary', [])):>{W}}"
            f"  {len(area_data.get('asbr',    [])):>{W}}"
            f"  {len(area_data.get('nssa',    [])):>{W}}"
        )
        emit(row, lf)

    ext_count = len(lsdb.get("external", []))
    if ext_count:
        emit(f"  {'External':<8}  {'':>{W}}  {'':>{W}}  {'':>{W}}  {'':>{W}}  {'':>{W}}  Type5={ext_count}", lf)

    emit(f"  {'─' * 60}", lf)
    emit(f"  {DIM}Type1=Router  Type2=Network  Type3=SummaryNet  Type4=SummaryASBR  Type7=NSSA{RESET}", lf)


# =============================================================================
# ASCII GRAPHICAL TOPOLOGY MAP
# =============================================================================

def _parse_router_lsa_detail(raw: str) -> dict:
    """Parse 'show ip ospf database router' detail output.

    Extracts per-router link descriptions grouped by area. Each Router LSA
    entry contains three link types relevant to topology mapping:

      Transit Network  — router is on a broadcast segment.
                         Link ID = DR interface IP (identifies the segment).
                         Link Data = this router's interface IP on that segment.
      Point-to-Point   — direct P2P link to a neighbor.
                         Link ID = neighbor Router ID.
                         Link Data = this router's interface IP on the link.
      Stub Network     — loopback or stub prefix. Informational only.

    Returns:
        {
            "0": {                          # area ID
                "0.0.0.2": {                # advertising router ID
                    "transit": [
                        { "dr_ip": "192.1.100.2", "intf_ip": "192.1.100.2",
                          "metric": "10" },
                        ...
                    ],
                    "p2p": [
                        { "peer_rid": "0.0.0.5", "intf_ip": "192.1.101.2",
                          "metric": "64" },
                        ...
                    ],
                    "stub": [
                        { "network": "2.0.0.0", "mask": "255.0.0.0",
                          "metric": "1" },
                        ...
                    ],
                },
            },
            "10": { ... },
        }
    """
    result: dict = {}
    current_area = None
    current_adv  = None
    current_link_type  = None
    current_link_id    = None
    current_link_data  = None

    # Section header: \t\tRouter Link States (Area 0)
    area_re     = re.compile(r'Router Link States \(Area\s+(\S+)\)', re.IGNORECASE)
    adv_re      = re.compile(r'Advertising Router:\s+(\S+)', re.IGNORECASE)
    link_re     = re.compile(r'Link connected to:\s+(.+)', re.IGNORECASE)
    link_id_re  = re.compile(r'\(Link ID\)\s+[^:]+:\s+(\S+)', re.IGNORECASE)
    link_dat_re = re.compile(r'\(Link Data\)\s+[^:]+:\s+(\S+)', re.IGNORECASE)
    metric_re   = re.compile(r'TOS 0 Metrics:\s+(\d+)', re.IGNORECASE)

    def _save_link():
        """Save the current link to result when metric line is reached."""
        if not current_area or not current_adv or not current_link_type:
            return
        result.setdefault(current_area, {})
        result[current_area].setdefault(current_adv, {
            "transit": [], "p2p": [], "stub": []
        })
        ltype = current_link_type.lower()
        if "transit" in ltype:
            result[current_area][current_adv]["transit"].append({
                "dr_ip"  : current_link_id,
                "intf_ip": current_link_data,
                "metric" : metric,
            })
        elif "point-to-point" in ltype or "another router" in ltype:
            result[current_area][current_adv]["p2p"].append({
                "peer_rid": current_link_id,
                "intf_ip" : current_link_data,
                "metric"  : metric,
            })
        elif "stub" in ltype:
            result[current_area][current_adv]["stub"].append({
                "network": current_link_id,
                "mask"   : current_link_data,
                "metric" : metric,
            })

    for line in raw.splitlines():
        # Detect area section
        m = area_re.search(line)
        if m:
            current_area = m.group(1).rstrip(")")
            current_adv  = None
            continue

        # Advertising router
        m = adv_re.search(line)
        if m:
            current_adv = m.group(1)
            continue

        # Link type
        m = link_re.search(line)
        if m:
            current_link_type = m.group(1).strip()
            current_link_id   = None
            current_link_data = None
            continue

        # Link ID
        m = link_id_re.search(line)
        if m:
            current_link_id = m.group(1)
            continue

        # Link Data
        m = link_dat_re.search(line)
        if m:
            current_link_data = m.group(1)
            continue

        # Metric — save link when reached
        m = metric_re.search(line)
        if m:
            metric = m.group(1)
            _save_link()

    return result


def _build_topology_graph(lsdb: dict, router_lsa_detail: dict) -> dict:
    """Build an adjacency graph from Type 1 Router LSA detail data.

    Uses 'show ip ospf database router' detail for exact topology:
      - Transit links  → broadcast segments (DR IP identifies segment,
                         all routers sharing same DR IP are co-members)
      - P2P links      → exact point-to-point pairs with interface IPs
      - Area context   → derived from the Router LSA section headers,
                         preventing cross-area contamination on ABRs

    Returns:
        {
            "areas": {
                "0": {
                    "routers"  : ["0.0.0.1", ...],
                    "segments" : [
                        { "subnet": "192.1.100.2", "dr": "0.0.0.2",
                          "members": ["0.0.0.1", "0.0.0.2", ...] },
                        ...
                    ],
                    "p2p_links": [
                        { "a": "0.0.0.2", "b": "0.0.0.5",
                          "subnet_a": "192.1.101.2", "subnet_b": "" },
                        ...
                    ],
                },
            },
            "abrs": ["0.0.0.8"],
        }
    """
    areas  = lsdb.get("areas", {})
    graph  = {"areas": {}, "abrs": []}

    # Identify ABRs — router IDs present in multiple areas
    rid_to_areas: dict = {}
    for area_id, area_data in areas.items():
        for lsa in area_data.get("router", []):
            rid_to_areas.setdefault(lsa["link_id"], set()).add(area_id)
    graph["abrs"] = [rid for rid, a in rid_to_areas.items() if len(a) > 1]

    for area_id, area_data in areas.items():
        router_lsas = area_data.get("router", [])
        routers     = sorted(set(lsa["link_id"] for lsa in router_lsas))

        # Get per-router link detail for this specific area only
        area_detail = router_lsa_detail.get(area_id, {})

        # ── Build broadcast segments from Transit links ──
        # Group routers by DR IP — all routers with the same Transit link DR IP
        # are on the same broadcast segment.
        dr_to_members: dict = {}   # dr_ip → set of router IDs
        dr_to_rid: dict    = {}    # dr_ip → DR router ID (router whose intf_ip == dr_ip)

        for rid, links in area_detail.items():
            if rid not in set(routers):
                continue
            for t in links.get("transit", []):
                dr_ip = t["dr_ip"]
                dr_to_members.setdefault(dr_ip, set()).add(rid)
                # If this router's interface IP equals the DR IP, it is the DR
                if t["intf_ip"] == dr_ip:
                    dr_to_rid[dr_ip] = rid

        segments = []
        segment_members: set = set()
        for dr_ip, members in sorted(dr_to_members.items()):
            dr_rid = dr_to_rid.get(dr_ip, "")
            seg_members = sorted(members)
            segments.append({
                "subnet" : dr_ip,
                "dr"     : dr_rid,
                "members": seg_members,
            })
            segment_members.update(seg_members)

        # ── Build P2P links from Point-to-Point links ──
        p2p_links  = []
        p2p_seen   = set()   # frozenset of (a, b) to avoid duplicates

        for rid, links in area_detail.items():
            if rid not in set(routers):
                continue
            for p in links.get("p2p", []):
                peer = p["peer_rid"]
                if peer not in set(routers):
                    continue
                pair = frozenset([rid, peer])
                if pair not in p2p_seen:
                    p2p_seen.add(pair)
                    p2p_links.append({
                        "a"       : rid,
                        "b"       : peer,
                        "intf_a"  : p["intf_ip"],
                        "intf_b"  : "",
                        "metric"  : p["metric"],
                    })

        # Fill in interface IP for the B side from B's own LSA if available
        for link in p2p_links:
            b_links = area_detail.get(link["b"], {})
            for p in b_links.get("p2p", []):
                if p["peer_rid"] == link["a"]:
                    link["intf_b"] = p["intf_ip"]
                    break

        # ── Routers with no transit or P2P links (serial-only not yet paired) ──
        p2p_routers_in_links = set()
        for lnk in p2p_links:
            p2p_routers_in_links.add(lnk["a"])
            p2p_routers_in_links.add(lnk["b"])

        orphan_routers = [
            r for r in routers
            if r not in segment_members and r not in p2p_routers_in_links
        ]

        graph["areas"][area_id] = {
            "routers"  : routers,
            "segments" : segments,
            "p2p_links": p2p_links,
            "orphans"  : orphan_routers,
        }

    return graph


def _short_rid(rid: str) -> str:
    """Return abbreviated router label from router ID.
    0.0.0.1 → R1,  0.0.0.11 → R11,  1.1.1.1 → 1.1.1.1 (non-standard)
    """
    parts = rid.split(".")
    if parts[0] == "0" and parts[1] == "0" and parts[2] == "0":
        return f"R{parts[3]}"
    return rid


def _render_ascii_map(lsdb: dict, neighbors: dict, router_lsa_detail: dict,
                      filter_area: str, lf=None) -> None:
    """Render a graphical ASCII topology map from LSDB data.

    Layout:
      - Areas drawn top-to-bottom: Area 0 first, then non-backbone areas
      - Each area is a labeled box
      - Broadcast segments shown as a horizontal bus: DR first, then members
      - P2P / Serial links shown as === connections between router pairs
      - ABR routers shown with gold [=Rn=] marker
      - Inter-area summary prefixes listed at the area boundary
      - Serial/P2P links derived from routers absent from all broadcast segments

    Symbols:
      [ Rn ]   internal router
      [=Rn=]   ABR router
      [*Rn*]   this router (the connected router)
      ---      Ethernet / broadcast segment link
      ===      P2P / Serial link
      ~~~      inter-area ABR boundary
    """
    bar = "=" * 70

    emit(f"\n{BOLD}{bar}{RESET}", lf)
    emit(f"{BOLD}  OSPF ASCII Topology Map{RESET}", lf)
    emit(f"{BOLD}  Router ID : {lsdb['router_id']}   Process ID : {lsdb['process_id']}{RESET}", lf)
    emit(f"{BOLD}{bar}{RESET}", lf)

    areas  = lsdb.get("areas", {})
    graph  = _build_topology_graph(lsdb, router_lsa_detail)
    my_rid = lsdb["router_id"]
    abrs   = set(graph["abrs"])

    filter_areas  = {filter_area: areas[filter_area]} if (filter_area and filter_area in areas) else areas
    sorted_area_ids = sorted(filter_areas.keys(), key=lambda x: int(x))

    for area_idx, area_id in enumerate(sorted_area_ids):
        area_data  = areas[area_id]
        g_area     = graph["areas"].get(area_id, {})
        routers    = g_area.get("routers",   [])
        segments   = g_area.get("segments",  [])
        p2p_links  = g_area.get("p2p_links", [])
        orphans    = g_area.get("orphans",   [])
        summary    = area_data.get("summary", [])
        nssa       = area_data.get("nssa",    [])

        area_label = f" Area {area_id} — Backbone " if area_id == "0" else f" Area {area_id} "
        box_width  = 68

        # ── Area box top ──
        emit(f"\n{CYAN}  ┌{'─' * (box_width - 2)}┐{RESET}", lf)
        emit(f"{CYAN}  │{BOLD}{area_label.center(box_width - 2)}{RESET}{CYAN}│{RESET}", lf)
        emit(f"{CYAN}  │{'─' * (box_width - 2)}│{RESET}", lf)

        if not routers:
            emit(f"{CYAN}  │{'  (no router LSAs found)'.center(box_width - 2)}│{RESET}", lf)
            emit(f"{CYAN}  └{'─' * (box_width - 2)}┘{RESET}", lf)
            continue

        # ── Node label helpers ──
        def node(rid: str) -> str:
            label = _short_rid(rid)
            if rid == my_rid:
                return f"[{GREEN}*{label}*{RESET}]"
            elif rid in abrs:
                return f"[{YELLOW}={label}={RESET}]"
            else:
                return f"[ {label} ]"

        # ── Broadcast segments ──
        if segments:
            emit(f"{CYAN}  │{RESET}", lf)
            emit(f"{CYAN}  │  {BOLD}Broadcast Segments:{RESET}", lf)

            for seg in segments:
                dr_rid  = seg["dr"]
                subnet  = seg["subnet"]
                members = seg["members"]

                if not members:
                    continue

                # DR first, then remaining members sorted
                ordered = [dr_rid] + [r for r in sorted(members) if r != dr_rid]

                # Build bus line
                bus = ""
                for i, rid in enumerate(ordered):
                    bus += node(rid) if i == 0 else f"---{node(rid)}"

                dr_label = _short_rid(dr_rid)
                emit(f"{CYAN}  │{RESET}", lf)
                emit(f"{CYAN}  │    {bus}", lf)
                emit(f"{CYAN}  │    {DIM}subnet={subnet}  DR={dr_label}{RESET}", lf)

        # ── P2P / Serial links ──
        if p2p_links:
            emit(f"{CYAN}  │{RESET}", lf)
            emit(f"{CYAN}  │  {BOLD}Point-to-Point / Serial Links:{RESET}", lf)
            emit(f"{CYAN}  │{RESET}", lf)
            for link in p2p_links:
                a_rid   = link["a"]
                b_rid   = link["b"]
                intf_a  = link.get("intf_a", "")
                intf_b  = link.get("intf_b", "")
                metric  = link.get("metric", "")
                # Build subnet label from interface IPs
                if intf_a and intf_b:
                    subnet_info = f"[{intf_a} === {intf_b}  cost={metric}]"
                elif intf_a:
                    subnet_info = f"[{intf_a}  cost={metric}]"
                else:
                    subnet_info = ""
                connector = f"==={subnet_info}===" if subnet_info else "==="
                emit(f"{CYAN}  │    {node(a_rid)} {connector} {node(b_rid)}", lf)

        # ── Orphan routers (no transit or P2P links found) ──
        if orphans:
            emit(f"{CYAN}  │{RESET}", lf)
            emit(f"{CYAN}  │  {BOLD}Unresolved Routers:{RESET}", lf)
            emit(f"{CYAN}  │{RESET}", lf)
            for rid in orphans:
                emit(f"{CYAN}  │    {node(rid)}  (no link detail available)", lf)

        # ── All routers summary line ──
        emit(f"{CYAN}  │{RESET}", lf)
        all_nodes = "  ".join(node(r) for r in routers)
        emit(f"{CYAN}  │  {BOLD}Routers:{RESET}  {all_nodes}", lf)
        emit(f"{CYAN}  │{RESET}", lf)

        # ── Area box bottom ──
        emit(f"{CYAN}  └{'─' * (box_width - 2)}┘{RESET}", lf)

        # ── ABR boundary between areas ──
        abrs_in_area = [r for r in routers if r in abrs]
        if abrs_in_area and area_idx < len(sorted_area_ids) - 1:
            abr_labels = "  ".join(
                f"{YELLOW}{_short_rid(r)}{RESET}" for r in abrs_in_area
            )
            emit(f"\n{YELLOW}  {'~' * box_width}{RESET}", lf)
            emit(f"{YELLOW}  ABR: {abr_labels}   Summary LSAs into Area {sorted_area_ids[area_idx + 1]}:{RESET}", lf)
            if summary:
                for lsa in sorted(summary, key=lambda x: x["link_id"])[:8]:
                    emit(f"{BLUE}    O IA  {lsa['link_id']:<20}  via {_short_rid(lsa['adv_router'])}{RESET}", lf)
                if len(summary) > 8:
                    emit(f"{DIM}    ... and {len(summary) - 8} more{RESET}", lf)
            emit(f"{YELLOW}  {'~' * box_width}{RESET}", lf)

        # ── NSSA note ──
        if nssa:
            emit(f"\n{YELLOW}  [NSSA] {len(nssa)} Type 7 External LSA(s) in Area {area_id}{RESET}", lf)
            for lsa in sorted(nssa, key=lambda x: x["link_id"])[:4]:
                emit(f"{YELLOW}    O N   {lsa['link_id']}  adv={_short_rid(lsa['adv_router'])}{RESET}", lf)

    # ── Type 5 External LSAs ──
    external = lsdb.get("external", [])
    if external and not filter_area:
        emit(f"\n{RED}  {'─' * 70}", lf)
        emit(f"  [Type 5] {len(external)} AS External LSA(s) — redistributed routes (O E1/E2){RESET}", lf)
        for lsa in sorted(external, key=lambda x: x["link_id"])[:8]:
            emit(f"{RED}    O E   {lsa['link_id']:<20}  adv={_short_rid(lsa['adv_router'])}{RESET}", lf)
        if len(external) > 8:
            emit(f"{DIM}    ... and {len(external) - 8} more{RESET}", lf)

    # ── Legend ──
    emit(f"\n{BOLD}  Legend:{RESET}", lf)
    emit(f"  {DIM}[ Rn ]   internal router    [=Rn=]  ABR     [*Rn*]  this router{RESET}", lf)
    emit(f"  {DIM}---      Ethernet segment    ===     P2P / Serial link{RESET}", lf)
    emit(f"  {DIM}~~~      inter-area boundary  O IA   inter-area route{RESET}", lf)
    emit(f"  {DIM}O N      NSSA external        O E    AS external route{RESET}", lf)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "OSPF Topology Map — text-format topology from live LSDB data.\n"
            "Connects to a single router and parses all LSA types.\n"
            "Output: area tree + adjacency table + LSA count summary.\n"
            "Add --map for a graphical ASCII topology diagram."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python ospf_topology_map.py --router r1.lab\n"
            "  python ospf_topology_map.py --router r1.lab --map\n"
            "  python ospf_topology_map.py --router 192.168.1.101\n"
            "  python ospf_topology_map.py --router r8.lab --area 10\n"
            "  python ospf_topology_map.py --router r8.lab --map --area 10\n"
        ),
    )
    parser.add_argument("--router", required=True, help="Router IP address or DNS name to connect to")
    parser.add_argument("--area",   default=None,  help="Filter output to a specific OSPF area (e.g. --area 0)")
    parser.add_argument("--pid",    default=None,  help="OSPF process ID to target (informational — IOS shows all)")
    parser.add_argument("--map",    action="store_true",
                        help="Render a graphical ASCII topology diagram in addition to standard output.")
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Prompt for credentials
    # -------------------------------------------------------------------------
    print(f"\nConnecting to {args.router}")
    username = input("  Username : ")
    password = getpass.getpass("  Password : ")

    # -------------------------------------------------------------------------
    # Open log file
    # -------------------------------------------------------------------------
    lf = setup_logger()

    try:
        # Header
        emit(f"\n{BOLD}NAMS26 — OSPF Topology Map{RESET}", lf)
        emit(f"Target : {args.router}", lf)
        if args.area:
            emit(f"Filter : Area {args.area}", lf)
        emit("=" * 70, lf)

        # -------------------------------------------------------------------------
        # Connect
        # -------------------------------------------------------------------------
        device = connect(args.router, username, password, lf)
        if device is None:
            emit(f"{RED}  [FAIL]{RESET} Cannot connect — exiting.", lf)
            sys.exit(1)

        try:
            # -------------------------------------------------------------------------
            # Collect — raw output goes to log file only, not terminal
            # -------------------------------------------------------------------------
            lf.write(f"\n  [INFO] Collecting LSDB data from {args.router}...\n")

            raw_lsdb       = device.cli(["show ip ospf database"])["show ip ospf database"]
            raw_nbr        = device.cli(["show ip ospf neighbor detail"])["show ip ospf neighbor detail"]
            raw_router_lsa = device.cli(["show ip ospf database router"])["show ip ospf database router"]

            # Log raw output — log file only
            lf.write("\n" + "─" * 70 + "\n")
            lf.write("RAW: show ip ospf database\n")
            lf.write("─" * 70 + "\n")
            lf.write(raw_lsdb + "\n\n")
            lf.write("─" * 70 + "\n")
            lf.write("RAW: show ip ospf database router\n")
            lf.write("─" * 70 + "\n")
            lf.write(raw_router_lsa + "\n\n")
            lf.write("─" * 70 + "\n")
            lf.write("RAW: show ip ospf neighbor detail\n")
            lf.write("─" * 70 + "\n")
            lf.write(raw_nbr + "\n\n")

            # -------------------------------------------------------------------------
            # Parse — log file only
            # -------------------------------------------------------------------------
            lf.write("  [INFO] Parsing LSDB...\n")
            lsdb              = _parse_lsdb(raw_lsdb)
            neighbors         = _parse_ospf_neighbor_detail(raw_nbr)
            router_lsa_detail = _parse_router_lsa_detail(raw_router_lsa)

            if not lsdb["areas"] and not lsdb["external"]:
                emit(f"{YELLOW}  [WARN]{RESET} No LSA data found — OSPF may not be running on this router.", lf)
                sys.exit(0)

            lf.write(
                f"  [PASS] LSDB parsed — "
                f"{sum(len(a.get('router',[]))+len(a.get('network',[]))+len(a.get('summary',[]))+len(a.get('asbr',[]))+len(a.get('nssa',[])) for a in lsdb['areas'].values())} "
                f"intra/inter LSAs across {len(lsdb['areas'])} area(s), "
                f"{len(lsdb.get('external',[]))} external LSA(s).\n"
            )

            # -------------------------------------------------------------------------
            # Render — ASCII map first (terminal + log), then detailed sections
            # -------------------------------------------------------------------------
            if args.map:
                _render_ascii_map(lsdb, neighbors, router_lsa_detail, args.area, lf)

            _render_area_tree(lsdb, neighbors, args.area, lf)
            _render_adjacency_table(lsdb, neighbors, args.area, lf)
            _render_lsdb_counts(lsdb, lf)

        finally:
            device.close()
            lf.write("\n  [INFO] Disconnected\n")

        emit(f"\n{'=' * 70}", lf)
        emit(f"{GREEN}  [PASS]{RESET} Topology map complete.", lf)

    finally:
        lf.close()


if __name__ == "__main__":
    main()
