#!/usr/bin/env python3
"""
Module   : NAMS26 — Module 05
File     : modules/05_ipv6_eigrp_ospf_nornir/scripts/troubleshoot_ipv6_eigrp_ospf.py
Purpose  : Troubleshoot IPv6 EIGRP and OSPFv3 faults across the lab topology
           using Nornir. Designed for use in the closing demo — inject a fault
           with push_config.py, then run this script to identify the symptom.

Usage:
    python troubleshoot_ipv6_eigrp_ospf.py                  # check all routers
    python troubleshoot_ipv6_eigrp_ospf.py --router R1      # specific router
    python troubleshoot_ipv6_eigrp_ospf.py --check neighbors process
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
# neighbors : show ipv6 eigrp neighbors / show ipv6 ospf neighbor — adjacency check
# process   : show ipv6 protocols — verify process config and redistribution
# routes    : show ipv6 route — check for missing or unexpected entries
# =============================================================================

# TODO: implement Nornir-based troubleshoot logic


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NAMS26 Module 05 — Troubleshoot IPv6 EIGRP/OSPFv3 via Nornir"
    )
    parser.add_argument(
        "--router",
        nargs="*",
        metavar="HOSTNAME",
        help="Troubleshoot specific routers only.",
    )
    parser.add_argument(
        "--check",
        nargs="*",
        metavar="CATEGORY",
        choices=["neighbors", "process", "routes"],
        help="Limit checks to specific categories.",
    )
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)

    # TODO: implement
    print("[INFO] troubleshoot_ipv6_eigrp_ospf.py — stub, not yet implemented")
    sys.exit(0)


if __name__ == "__main__":
    main()
