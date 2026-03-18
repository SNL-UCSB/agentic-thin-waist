#!/usr/bin/env bash
# =============================================================================
# switch.sh — netReplica Switch Configuration Guide (Interactive)
#
# DESCRIPTION:
#   The managed switch does NOT run Linux, so it cannot be configured by a
#   bash service script directly.  Instead, this script:
#     1. Opens a serial console to the switch (via minicom).
#     2. Prints the exact CLI commands you need to paste / type, pre-filled
#        with the values from config.env.
#
#   VLAN layout (on-a-stick topology, see Figure 4 of the paper):
#
#     VLAN_DOWNSTREAM_ID (11 by default)
#       - Switch port connected to downstream server  → ACCESS port
#       - Switch port connected to LibreQoS server   → TRUNK (allowed)
#
#     VLAN_UPSTREAM_ID (22 by default)
#       - Switch port connected to upstream server   → ACCESS port
#       - Switch port connected to LibreQoS server   → TRUNK (allowed)
#
#   The LibreQoS server port must be a TRUNK that carries both VLANs; all
#   other ports are ACCESS ports on their respective VLAN.
#
# USAGE:
#   ./switch.sh <command>
#
#   Commands:
#     connect    — Open a minicom session to the switch console.
#     show-cmds  — Print the switch CLI commands to stdout (for copy-paste).
#     check-deps — Verify that minicom is installed.
#
# REQUIREMENTS:
#   - minicom must be installed: sudo apt-get install minicom
#   - The server must be physically connected to the switch console port via USB
#     serial (usually /dev/ttyUSB0).  Set SWITCH_SERIAL_DEVICE in config.env.
#   - The switch CLI shown here follows Dell/Cisco-style IOS syntax.
#     Adjust if your switch uses a different CLI dialect.
#
# SEE ALSO:
#   config.env  — All configurable parameters (port names, VLAN IDs, etc.).
#   common.sh   — Shared utility functions.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${SCRIPT_DIR}/config.env"

# =============================================================================
# Internal helpers
# =============================================================================

##
# _validate_config
##
_validate_config() {
    local required_vars=(
        SWITCH_SERIAL_DEVICE
        SWITCH_UPSTREAM_PORT SWITCH_DOWNSTREAM_PORT SWITCH_LIBREQOS_PORT
        VLAN_UPSTREAM_ID VLAN_DOWNSTREAM_ID
    )
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required config variable '$var' is not set in config.env."
            exit 1
        fi
    done
}

# =============================================================================
# Commands
# =============================================================================

##
# check_deps
#   Verifies minicom is available and the serial device exists.
##
check_deps() {
    require_cmd minicom minicom
    log_ok "minicom found."

    if [[ ! -e "$SWITCH_SERIAL_DEVICE" ]]; then
        log_warn "Serial device $SWITCH_SERIAL_DEVICE does not exist."
        log_warn "Check that the USB-serial cable is plugged in and that the"
        log_warn "correct device is set in SWITCH_SERIAL_DEVICE (config.env)."
        log_warn "Available serial devices:"
        ls /dev/ttyUSB* /dev/ttyS* 2>/dev/null | sed 's/^/  /' || echo "  (none found)"
    else
        log_ok "Serial device $SWITCH_SERIAL_DEVICE is present."

        # Check that the current user is in the 'dialout' group (required to
        # access /dev/ttyUSB* without sudo).
        if ! id -nG | grep -qw dialout; then
            log_warn "Your user is not in the 'dialout' group."
            log_warn "Add yourself and re-login: sudo usermod -aG dialout \$USER"
        fi
    fi
}

##
# show_cmds
#   Prints the exact switch CLI commands, pre-filled from config.env, ready
#   to paste into the switch console session.
##
show_cmds() {
    _validate_config

    cat <<EOF
# ============================================================
# netReplica Switch Configuration Commands
# Generated from config.env on $(date)
#
# Topology:
#   Port $SWITCH_DOWNSTREAM_PORT → Downstream server   (ACCESS, VLAN $VLAN_DOWNSTREAM_ID)
#   Port $SWITCH_UPSTREAM_PORT   → Upstream server     (ACCESS, VLAN $VLAN_UPSTREAM_ID)
#   Port $SWITCH_LIBREQOS_PORT   → LibreQoS server     (TRUNK,  VLAN $VLAN_DOWNSTREAM_ID,$VLAN_UPSTREAM_ID)
#
# Paste these commands at the switch CLI prompt.
# Hit Enter a few times after connecting if no prompt appears.
# ============================================================

! --- Enter global configuration mode ---
enable
configure terminal

! --- Create VLAN for downstream traffic (core router side) ---
vlan $VLAN_DOWNSTREAM_ID
exit

! --- Create VLAN for upstream traffic (edge router side) ---
vlan $VLAN_UPSTREAM_ID
exit

! --- Downstream server port: ACCESS on VLAN $VLAN_DOWNSTREAM_ID ---
interface $SWITCH_DOWNSTREAM_PORT
 switchport mode access
 switchport access vlan $VLAN_DOWNSTREAM_ID
 no shutdown
exit

! --- Upstream server port: ACCESS on VLAN $VLAN_UPSTREAM_ID ---
interface $SWITCH_UPSTREAM_PORT
 switchport mode access
 switchport access vlan $VLAN_UPSTREAM_ID
 no shutdown
exit

! --- LibreQoS server port: TRUNK carrying both VLANs ---
interface $SWITCH_LIBREQOS_PORT
 switchport mode trunk
 switchport trunk allowed vlan $VLAN_DOWNSTREAM_ID,$VLAN_UPSTREAM_ID
 no shutdown
exit

! --- Save the configuration ---
end
write memory

! --- Verify ---
show vlan brief
show interfaces $SWITCH_DOWNSTREAM_PORT switchport
show interfaces $SWITCH_UPSTREAM_PORT   switchport
show interfaces $SWITCH_LIBREQOS_PORT   switchport
EOF
}

##
# connect
#   Opens a minicom serial session to the switch.
#   Saves a minicom profile named 'netreplica' on first run.
##
connect() {
    _validate_config
    require_cmd minicom minicom

    local profile="netreplica"
    local minirc_path="$HOME/.minirc.${profile}"

    # Write the minicom profile if it doesn't already exist.
    if [[ ! -f "$minirc_path" ]]; then
        log_info "Creating minicom profile '$profile' at $minirc_path …"
        cat > "$minirc_path" <<MINIRC
# Minicom profile for netReplica switch console
# Generated by switch.sh
pu port             ${SWITCH_SERIAL_DEVICE}
pu baudrate         9600
pu bits             8
pu parity           N
pu stopbits         1
pu rtscts           No
pu xonxoff          No
pu linewrap         Yes
MINIRC
        log_ok "Profile written.  Connecting …"
    fi

    echo ""
    echo "========================================================="
    echo " Connecting to switch console on $SWITCH_SERIAL_DEVICE"
    echo " Baud: 9600 8N1  |  No flow control"
    echo " Press Ctrl-A then X to exit minicom."
    echo ""
    echo " TIP: Hit Enter several times if no prompt appears."
    echo "      Run '$0 show-cmds' in another terminal for the"
    echo "      commands to paste."
    echo "========================================================="
    echo ""

    # Check if user needs to be in dialout group.
    if [[ ! -w "$SWITCH_SERIAL_DEVICE" ]]; then
        log_warn "No write permission on $SWITCH_SERIAL_DEVICE."
        log_warn "Trying with sudo …"
        sudo minicom "$profile"
    else
        minicom "$profile"
    fi
}

# =============================================================================
# Entry point
# =============================================================================

usage() {
    cat <<EOF
Usage: $0 <command>

Commands:
  check-deps   Verify minicom is installed and serial device exists.
  show-cmds    Print switch CLI commands to stdout (pre-filled from config.env).
  connect      Open a minicom console session to the switch.
EOF
}

case "${1:-}" in
    check-deps) check_deps  ;;
    show-cmds)  show_cmds   ;;
    connect)    connect     ;;
    *)          usage; exit 1 ;;
esac
