#!/usr/bin/env bash
# =============================================================================
# Module   : NAMS26 Project Utility
# File     : modules/06_ipv6_isis_nornir/utils/clear_known_hosts.sh
# Purpose  : Remove stale SSH host key entries for all lab nodes from the
#            management station's known_hosts file.
#
#            Cisco IOL nodes in EVE-NG do not persist RSA host keys across
#            reboots. Each lab restart generates a new key, causing SSH to
#            reject connections with a host key mismatch warning. This script
#            must be run after every EVE-NG lab reboot before executing any
#            automation scripts or manual SSH sessions.
#
# Targets  : All lab nodes by three forms:
#              - Short name   (e.g. bb-1)
#              - DNS name     (e.g. bb-1.lab)
#              - OOB IP       (e.g. 192.168.1.101)
#            All three forms are removed to ensure no stale entry remains
#            regardless of how the management station previously connected.
#
# Usage    : bash utils/clear_known_hosts.sh
#            ./utils/clear_known_hosts.sh        (if executable)
#
# Requires : ssh-keygen
#            Lab DNS resolving .lab domain via 192.168.1.12
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# ANSI Colors
# -----------------------------------------------------------------------------
GREEN="\033[92m"
RED="\033[91m"
YELLOW="\033[93m"
CYAN="\033[96m"
RESET="\033[0m"
BOLD="\033[1m"

# -----------------------------------------------------------------------------
# Lab node inventory — BB-1 through OSPF-1 (Module 06 has 12 routers)
# Short name, DNS name, and OOB IP are all cleared for each node.
# -----------------------------------------------------------------------------
declare -A HOSTS=(
    [BB-1]="bb-1  bb-1.lab  192.168.1.101"
    [BB-2]="bb-2  bb-2.lab  192.168.1.102"
    [ABR-1]="abr-1  abr-1.lab  192.168.1.103"
    [ABR-2]="abr-2  abr-2.lab  192.168.1.104"
    [ABR-3]="abr-3  abr-3.lab  192.168.1.105"
    [BR-1]="br-1  br-1.lab  192.168.1.106"
    [BR-2]="br-2  br-2.lab  192.168.1.107"
    [BR-3]="br-3  br-3.lab  192.168.1.108"
    [BR-4]="br-4  br-4.lab  192.168.1.109"
    [BR-5]="br-5  br-5.lab  192.168.1.110"
    [ASBR-1]="asbr-1  asbr-1.lab  192.168.1.111"
    [OSPF-1]="ospf-1  ospf-1.lab  192.168.1.112"
)

KNOWN_HOSTS="${HOME}/.ssh/known_hosts"

# -----------------------------------------------------------------------------
# Preflight check
# -----------------------------------------------------------------------------
echo -e "\n${CYAN}${BOLD}$(printf '─%.0s' {1..60})${RESET}"
echo -e "${CYAN}${BOLD}  NAMS26 — Module 06: Clear Known Hosts${RESET}"
echo -e "${CYAN}${BOLD}  Target : ${KNOWN_HOSTS}${RESET}"
echo -e "${CYAN}${BOLD}$(printf '─%.0s' {1..60})${RESET}\n"

if [[ ! -f "${KNOWN_HOSTS}" ]]; then
    echo -e "  ${YELLOW}${BOLD}[WARN]${RESET}  ${KNOWN_HOSTS} does not exist — nothing to clear.\n"
    exit 0
fi

# -----------------------------------------------------------------------------
# Backup known_hosts before modifying
# -----------------------------------------------------------------------------
BACKUP="${KNOWN_HOSTS}.bak"
cp "${KNOWN_HOSTS}" "${BACKUP}"
echo -e "  ${CYAN}[INFO]${RESET}  Backup created : ${BACKUP}\n"
echo -e "  $( printf '%-8s' 'HOST' )  $( printf '%-18s' 'TARGET' )  RESULT"
echo -e "  $(printf '─%.0s' {1..52})"

# -----------------------------------------------------------------------------
# Remove entries for each node
# -----------------------------------------------------------------------------
REMOVED=0
SKIPPED=0

for node in $(echo "${!HOSTS[@]}" | tr ' ' '\n' | sort); do
    targets="${HOSTS[$node]}"
    for target in ${targets}; do
        if ssh-keygen -F "${target}" -f "${KNOWN_HOSTS}" &>/dev/null; then
            ssh-keygen -R "${target}" -f "${KNOWN_HOSTS}" &>/dev/null
            echo -e "  ${BOLD}$(printf '%-8s' "${node}")${RESET}  $(printf '%-18s' "${target}")  ${GREEN}${BOLD}REMOVED${RESET}"
            (( REMOVED++ )) || true
        else
            echo -e "  ${BOLD}$(printf '%-8s' "${node}")${RESET}  $(printf '%-18s' "${target}")  ${YELLOW}NOT FOUND${RESET}"
            (( SKIPPED++ )) || true
        fi
    done
done

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo -e "\n  $(printf '─%.0s' {1..52})"
echo -e "  ${BOLD}Entries removed : ${REMOVED}${RESET}"
echo -e "  ${BOLD}Not found       : ${SKIPPED}${RESET}"

if [[ ${REMOVED} -gt 0 ]]; then
    echo -e "\n  ${GREEN}${BOLD}Done. Known hosts cleared — lab is ready for SSH.${RESET}\n"
else
    echo -e "\n  ${YELLOW}${BOLD}No entries removed — known_hosts may already be clean.${RESET}\n"
fi
