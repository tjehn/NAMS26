#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 05
File     : modules/05_ipv6_eigrp_ospf_nornir/scripts/verify_ipv6_eigrp_ospf.py
Purpose  : Verify IPv6 EIGRP and OSPFv3 operational state across all lab routers
           using Nornir. Connects in parallel, runs show commands, and compares
           live state against expected values from the YAML inventory.

Usage:
    python verify_ipv6_eigrp_ospf.py                         # verify all routers
    python verify_ipv6_eigrp_ospf.py --router R1 R6          # specific routers
    python verify_ipv6_eigrp_ospf.py --check neighbors routes redistribution
"""

import os
import sys
import yaml
import argparse
from datetime import datetime

# =============================================================================
# PATH RESOLUTION
# =============================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR   = os.path.dirname(SCRIPT_DIR)
MODULES_DIR  = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)
LOG_DIR      = os.path.join(MODULE_DIR, "logs")
DATA_FILE    = os.path.join(MODULE_DIR, "data", "ipv6_eigrp_ospf.yaml")

# =============================================================================
# CHECK CATEGORIES (--check options)
# neighbors     : show ipv6 eigrp neighbors / show ipv6 ospf neighbor
# routes        : show ipv6 route — verify expected prefixes present
# redistribution: verify redistributed prefixes visible on ASBRs
# areas         : verify OSPF area types (stub/NSSA) applied correctly
# =============================================================================

# TODO: implement Nornir-based verify logic


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NAMS26 Module 05 — Verify IPv6 EIGRP/OSPFv3 via Nornir"
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help="Verify specific routers only.",
    )
    parser.add_argument(
        "--check",
        nargs="*",
        metavar="CATEGORY",
        choices=["neighbors", "routes", "redistribution", "areas"],
        help="Limit verification to specific check categories.",
    )
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)

    # TODO: implement
    print("[INFO] verify_ipv6_eigrp_ospf.py — stub, not yet implemented")
    sys.exit(0)


if __name__ == "__main__":
    main()
