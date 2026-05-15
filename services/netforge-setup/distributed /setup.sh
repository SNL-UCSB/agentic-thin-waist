#!/usr/bin/env bash
# =============================================================================
# setup.sh — netReplica Distributed Setup Orchestrator
#
# DESCRIPTION:
#   Top-level entry point for setting up the netReplica distributed testbed.
#   Guides you through configuring each of the three servers and the switch.
#
#   Architecture (Figure 4 — https://arxiv.org/pdf/2507.13476):
#
#                      [Internet]
#                          |
#                  ┌───────────────┐
#                  │ Upstream      │  Edge router, NAT gateway
#                  │ Server        │  upstream.sh
#                  └───────┬───────┘
#                          │  VLAN 22 (access port)
#                  ┌───────┴───────┐
#                  │    Switch     │  Managed L2, VLAN isolation
#                  │  switch.sh   │
#                  └──┬────────┬──┘
#          VLAN 11    │        │  VLAN 11,22 (trunk)
#       (access port) │        │
#              ┌──────┴──┐  ┌──┴──────────┐
#              │Downstream│  │  LibreQoS   │
#              │ Server   │  │  Server     │
#              │downstream│  │ libreqos.sh │
#              └──────────┘  └─────────────┘
#                   |
#            GRE tunnels to Pinot / client nodes
#
# USAGE:
#   ./setup.sh <command> [--role <role>]
#
#   Commands:
#     guide          — Interactive step-by-step setup guide.
#     deps           — Install dependencies for a specific role.
#     start          — Apply network configuration for a specific role.
#     stop           — Tear down network configuration for a specific role.
#     status         — Show status for a specific role.
#     install-all    — Install systemd services for a specific role.
#     check-config   — Validate config.env without applying anything.
#
#   Roles (use --role <name>):
#     upstream    — Run on the upstream (edge router / NAT) server.
#     downstream  — Run on the downstream (core router / aggregator) server.
#     libreqos    — Run on the LibreQoS (traffic shaper) server.
#     switch      — Show switch configuration commands.
#
#   Examples:
#     sudo ./setup.sh start --role upstream
#     sudo ./setup.sh start --role downstream
#     sudo ./setup.sh status --role libreqos
#     ./setup.sh guide
#
# SEE ALSO:
#   config.env     — Edit this first with your interface names and IP addresses.
#   upstream.sh    — Upstream server service script.
#   downstream.sh  — Downstream server service script.
#   libreqos.sh    — LibreQoS server service script.
#   switch.sh      — Switch configuration guide.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

# =============================================================================
# Helpers
# =============================================================================

##
# _service_script <role>
#   Returns the path to the service script for the given role.
##
_service_script() {
    case "$1" in
        upstream)   echo "${SCRIPT_DIR}/upstream.sh"   ;;
        downstream) echo "${SCRIPT_DIR}/downstream.sh" ;;
        libreqos)   echo "${SCRIPT_DIR}/libreqos.sh"   ;;
        switch)     echo "${SCRIPT_DIR}/switch.sh"      ;;
        *)
            log_error "Unknown role: $1"
            log_error "Valid roles: upstream, downstream, libreqos, switch"
            exit 1
            ;;
    esac
}

##
# _run_role <role> <command> [args…]
#   Delegates a command to the appropriate service script.
##
_run_role() {
    local role="$1"; shift
    local script
    script="$(_service_script "$role")"

    if [[ ! -x "$script" ]]; then
        chmod +x "$script"
    fi

    "$script" "$@"
}

# =============================================================================
# check-config
# =============================================================================

##
# cmd_check_config
#   Sources config.env and performs basic sanity checks without touching the
#   network.  Useful before deploying to verify there are no obvious errors.
##
cmd_check_config() {
    load_config "${SCRIPT_DIR}/config.env"

    log_info "config.env loaded successfully."
    echo ""
    echo "Key values:"
    printf "  %-35s %s\n" "UPSTREAM_SWITCH_IFACE:"    "${UPSTREAM_SWITCH_IFACE:-<unset>}"
    printf "  %-35s %s\n" "UPSTREAM_INTERNET_IFACE:"  "${UPSTREAM_INTERNET_IFACE:-<unset>}"
    printf "  %-35s %s\n" "UPSTREAM_SWITCH_IP:"       "${UPSTREAM_SWITCH_IP:-<unset>}"
    printf "  %-35s %s\n" "DOWNSTREAM_SWITCH_IFACE:"  "${DOWNSTREAM_SWITCH_IFACE:-<unset>}"
    printf "  %-35s %s\n" "DOWNSTREAM_SWITCH_IP:"     "${DOWNSTREAM_SWITCH_IP:-<unset>}"
    printf "  %-35s %s\n" "LIBREQOS_SWITCH_IFACE:"    "${LIBREQOS_SWITCH_IFACE:-<unset>}"
    printf "  %-35s %s\n" "VLAN_UPSTREAM_ID:"         "${VLAN_UPSTREAM_ID:-<unset>}"
    printf "  %-35s %s\n" "VLAN_DOWNSTREAM_ID:"       "${VLAN_DOWNSTREAM_ID:-<unset>}"
    printf "  %-35s %s\n" "SWITCH_UPSTREAM_PORT:"     "${SWITCH_UPSTREAM_PORT:-<unset>}"
    printf "  %-35s %s\n" "SWITCH_DOWNSTREAM_PORT:"   "${SWITCH_DOWNSTREAM_PORT:-<unset>}"
    printf "  %-35s %s\n" "SWITCH_LIBREQOS_PORT:"     "${SWITCH_LIBREQOS_PORT:-<unset>}"
    printf "  %-35s %s\n" "PINOT_IPS:"                "${PINOT_IPS:-<unset>}"
    echo ""
    log_ok "Configuration check passed."
}

# =============================================================================
# Interactive guide
# =============================================================================

##
# cmd_guide
#   Walks the user through the full deployment process interactively.
##
cmd_guide() {
    cat <<'BANNER'
╔══════════════════════════════════════════════════════════════════╗
║           netReplica Distributed Testbed Setup Guide            ║
╚══════════════════════════════════════════════════════════════════╝

This guide covers the one-time setup of the three-server topology.
You will run different steps on each server.

Prerequisites:
  • Edit config.env on each server with the correct interface names
    and IP addresses for YOUR hardware.
  • Ensure all three servers can reach the switch (cabled correctly).
  • The switch console port should be accessible from the downstream
    server via a USB-serial cable.

BANNER

    local step=0
    _step() {
        step=$(( step + 1 ))
        printf "\n\033[1;36mStep %d — %s\033[0m\n" "$step" "$*"
    }

    # ------------------------------------------------------------------
    _step "Edit config.env"
    cat <<EOF
  Open config.env in an editor and fill in values for your hardware:
    - Interface names (run 'ip -br link' to list them)
    - IP addresses for each server's switch-facing interface
    - Switch port identifiers
    - Public IPs and Pinot node IPs for GRE tunnels

  Command:
    nano ${SCRIPT_DIR}/config.env

  Then run on any server to validate:
    ./setup.sh check-config

EOF

    # ------------------------------------------------------------------
    _step "Configure the switch"
    cat <<EOF
  On the server connected to the switch console (usually downstream):
    1. Check the serial device:    ./switch.sh check-deps
    2. Show the commands to paste: ./switch.sh show-cmds
    3. Connect and apply them:     ./switch.sh connect

EOF

    # ------------------------------------------------------------------
    _step "Set up the LibreQoS server  (run ON the libreqos server)"
    cat <<EOF
  Install LibreQoS first: https://libreqos.readthedocs.io

  Then:
    sudo ./libreqos.sh deps          # install 8021q module + ethtool
    sudo ./libreqos.sh start         # create VLAN sub-interfaces
    sudo ./libreqos.sh configure     # write ispConfig.py and lqos.conf
    sudo ./libreqos.sh install       # register as a systemd service

  Verify:
    sudo ./libreqos.sh status

EOF

    # ------------------------------------------------------------------
    _step "Set up the upstream server  (run ON the upstream server)"
    cat <<EOF
  sudo ./upstream.sh deps      # install iptables, switch to legacy if needed
  sudo ./upstream.sh start     # configure namespace, veth pairs, NAT, routing
  sudo ./upstream.sh install   # register as a systemd service

  Verify:
    sudo ./upstream.sh status

EOF

    # ------------------------------------------------------------------
    _step "Set up the downstream server  (run ON the downstream server)"
    cat <<EOF
  sudo ./downstream.sh deps      # install iproute2, load ip_gre module
  sudo ./downstream.sh start     # configure GRE tunnels, routing, Docker network
  sudo ./downstream.sh install   # register as a systemd service

  Verify:
    sudo ./downstream.sh status

EOF

    # ------------------------------------------------------------------
    _step "Start LibreQoS"
    cat <<EOF
  On the LibreQoS server:
    sudo systemctl start lqosd

  Check the dashboard is reachable on the management interface.

EOF

    # ------------------------------------------------------------------
    _step "Verify end-to-end connectivity"
    cat <<EOF
  From a Pinot node, ping the GRE tunnel server address and an internet host.
  Traffic should flow:

    Pinot → GRE tunnel → Downstream server → Switch (VLAN 11)
         → LibreQoS (XDP shaping) → Switch (VLAN 22)
         → Upstream server (NAT) → Internet

  Troubleshooting:
    - Run 'status' on each service script for per-host state.
    - Check 'ip route', 'iptables -t nat -L -n', 'ip netns list'.
    - Verify the switch port VLANs with 'show vlan brief' on the switch.

EOF

    log_ok "Setup guide complete.  Good luck!"
}

# =============================================================================
# Entry point
# =============================================================================

usage() {
    cat <<EOF
Usage: $0 <command> [--role <role>]

Commands:
  guide          Interactive setup guide (no changes made).
  check-config   Validate config.env without touching the network.
  deps           Install dependencies.        Requires --role.
  start          Apply network configuration. Requires --role.
  stop           Tear down configuration.     Requires --role.
  status         Show current state.          Requires --role.
  install-all    Register systemd services.   Requires --role.

Roles: upstream | downstream | libreqos | switch

Examples:
  $0 guide
  sudo $0 start --role upstream
  sudo $0 status --role downstream
  $0 check-config
EOF
}

# Parse arguments.
COMMAND="${1:-}"
ROLE=""

shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --role)
            ROLE="${2:-}"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

case "$COMMAND" in
    guide)
        cmd_guide
        ;;
    check-config)
        cmd_check_config
        ;;
    deps|start|stop|status)
        if [[ -z "$ROLE" ]]; then
            log_error "'$COMMAND' requires --role <upstream|downstream|libreqos|switch>"
            usage
            exit 1
        fi
        _run_role "$ROLE" "$COMMAND"
        ;;
    install-all)
        if [[ -z "$ROLE" ]]; then
            log_error "'install-all' requires --role <upstream|downstream|libreqos>"
            usage
            exit 1
        fi
        _run_role "$ROLE" install
        ;;
    "")
        usage
        exit 1
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
