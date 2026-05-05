#!/usr/bin/env bash
# =============================================================================
# File     : utils/clear_known_hosts.sh
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
#              - Short name   (e.g. r1)
#              - DNS name     (e.g. r1.lab)
#              - OOB IP       (e.g. 192.168.1.101)
#            All three forms are removed to ensure no stale entry remains
#            regardless of how the management station previously connected.
#
# Devices  : R1–R12, COSW-01, COSW-02, OOB-SW01
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
# Lab node inventory
# Format per entry: "short_name  dns_name  oob_ip"
# All three forms are cleared for each device.
# -----------------------------------------------------------------------------
declare -A HOSTS=(
    [R1]="r1  r1.lab  192.168.1.101"
    [R2]="r2  r2.lab  192.168.1.102"
    [R3]="r3  r3.lab  192.168.1.103"
    [R4]="r4  r4.lab  192.168.1.104"
    [R5]="r5  r5.lab  192.168.1.105"
    [R6]="r6  r6.lab  192.168.1.106"
    [R7]="r7  r7.lab  192.168.1.107"
    [R8]="r8  r8.lab  192.168.1.108"
    [R9]="r9  r9.lab  192.168.1.109"
    [R10]="r10  r10.lab  192.168.1.110"
    [R11]="r11  r11.lab  192.168.1.111"
    [R12]="r12  r12.lab  192.168.1.112"
    [COSW-01]="cosw-01  cosw-01.lab  192.168.1.236"
    [COSW-02]="cosw-02  cosw-02.lab  192.168.1.237"
    [OOB_SW01]="oob_sw01  oob_sw01.lab  192.168.1.240"
)

KNOWN_HOSTS="${HOME}/.ssh/known_hosts"

# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
echo -e "\n${CYAN}${BOLD}$(printf '─%.0s' {1..60})${RESET}"
echo -e "${CYAN}${BOLD}  NAMS26 — Clear Known Hosts (All Lab Devices)${RESET}"
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
echo -e "  $( printf '%-10s' 'HOST' )  $( printf '%-20s' 'TARGET' )  RESULT"
echo -e "  $(printf '─%.0s' {1..55})"

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
            echo -e "  ${BOLD}$(printf '%-10s' "${node}")${RESET}  $(printf '%-20s' "${target}")  ${GREEN}${BOLD}REMOVED${RESET}"
            (( REMOVED++ )) || true
        else
            echo -e "  ${BOLD}$(printf '%-10s' "${node}")${RESET}  $(printf '%-20s' "${target}")  ${YELLOW}NOT FOUND${RESET}"
            (( SKIPPED++ )) || true
        fi
    done
done

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo -e "\n  $(printf '─%.0s' {1..55})"
echo -e "  ${BOLD}Entries removed : ${REMOVED}${RESET}"
echo -e "  ${BOLD}Not found       : ${SKIPPED}${RESET}"

if [[ ${REMOVED} -gt 0 ]]; then
    echo -e "\n  ${GREEN}${BOLD}Done. Known hosts cleared — lab is ready for SSH init.${RESET}\n"
else
    echo -e "\n  ${YELLOW}${BOLD}No entries removed — known_hosts may already be clean.${RESET}\n"
fi
