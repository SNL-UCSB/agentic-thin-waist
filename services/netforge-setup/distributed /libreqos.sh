#!/usr/bin/env bash
# =============================================================================
# libreqos.sh — netReplica LibreQoS Server (Traffic Shaper) Service
#
# DESCRIPTION:
#   Configures the LibreQoS server in "on-a-stick" VLAN mode.  The server has
#   a single trunk interface connected to the switch; two VLAN sub-interfaces
#   are created on it:
#     • VLAN_UPSTREAM_ID   — faces the upstream (edge router) side
#     • VLAN_DOWNSTREAM_ID — faces the downstream (core router) side
#
#   LibreQoS intercepts all traffic flowing between the two VLANs and applies
#   per-subscriber bandwidth policies using an XDP bridge.
#
#   After running 'start', update the LibreQoS config files as described in
#   the comments of the 'service_configure_libreqos' function, then start the
#   LibreQoS daemon normally.
#
# USAGE:
#   sudo ./libreqos.sh <command>
#
#   Commands:
#     start      — Create VLAN sub-interfaces and apply kernel settings.
#     stop       — Remove VLAN sub-interfaces.
#     status     — Show current VLAN and LibreQoS state.
#     configure  — Write LibreQoS config files from the values in config.env.
#     install    — Install a systemd service unit (auto-start on boot).
#     uninstall  — Remove the systemd service unit.
#     deps       — Install/check system-level dependencies.
#
# REQUIREMENTS:
#   - Must be run as root (or via sudo).
#   - LibreQoS must already be installed (see https://libreqos.readthedocs.io).
#   - Packages: vlan (8021q module), ethtool (auto-checked by deps).
#
# SEE ALSO:
#   config.env  — All configurable parameters.
#   common.sh   — Shared utility functions.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_config "${SCRIPT_DIR}/config.env"

readonly SERVICE_NAME="netreplica-libreqos"

# Derived sub-interface names (e.g. enp216s0f0.100 and enp216s0f0.200).
# The .100 suffix is used for the upstream VLAN, .200 for the downstream VLAN.
# These are purely cosmetic – the VLAN ID is what the switch reads.
VLAN_UPSTREAM_SUBIF="${LIBREQOS_SWITCH_IFACE}.100"
VLAN_DOWNSTREAM_SUBIF="${LIBREQOS_SWITCH_IFACE}.200"

# =============================================================================
# Internal helpers
# =============================================================================

##
# _validate_config
##
_validate_config() {
    local required_vars=(
        LIBREQOS_SWITCH_IFACE LIBREQOS_MGMT_IFACE
        LIBREQOS_VLAN_UPSTREAM_IP LIBREQOS_VLAN_DOWNSTREAM_IP
        VLAN_UPSTREAM_ID VLAN_DOWNSTREAM_ID
        LIBREQOS_ISP_CONFIG LIBREQOS_LQOS_CONF
    )

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required config variable '$var' is not set in config.env."
            exit 1
        fi
    done

    require_iface "$LIBREQOS_SWITCH_IFACE"
}

##
# _subif_exists <name>
##
_subif_exists() {
    ip link show "$1" &>/dev/null 2>&1
}

# =============================================================================
# Service lifecycle functions
# =============================================================================

##
# service_deps
#   Installs the vlan package and loads the 8021q kernel module.
##
service_deps() {
    require_root
    log_info "Checking / installing dependencies for LibreQoS service …"

    DEBIAN_FRONTEND=noninteractive apt-get install -y vlan ethtool

    if ! lsmod | grep -q 8021q; then
        modprobe 8021q
        log_ok "Loaded 8021q kernel module."
    else
        log_info "8021q module already loaded."
    fi

    # Persist the module across reboots.
    if ! grep -q '^8021q$' /etc/modules 2>/dev/null; then
        echo '8021q' >> /etc/modules
        log_ok "8021q added to /etc/modules."
    fi

    log_ok "Dependencies satisfied."
}

##
# service_start
#   Creates the VLAN sub-interfaces and applies the ethtool flag required by
#   LibreQoS on-a-stick mode.
##
service_start() {
    require_root
    _validate_config

    log_info "Starting LibreQoS service …"

    # ------------------------------------------------------------------
    # 1. Load 8021q module (idempotent).
    # ------------------------------------------------------------------
    if ! lsmod | grep -q 8021q; then
        modprobe 8021q
        log_ok "Loaded 8021q module."
    fi

    # ------------------------------------------------------------------
    # 2. Bring up the trunk interface.
    # ------------------------------------------------------------------
    bring_up "$LIBREQOS_SWITCH_IFACE"

    # ------------------------------------------------------------------
    # 3. Create sub-interface for the UPSTREAM VLAN.
    #    This VLAN faces the edge router (upstream server).
    # ------------------------------------------------------------------
    if _subif_exists "$VLAN_UPSTREAM_SUBIF"; then
        log_info "Sub-interface $VLAN_UPSTREAM_SUBIF already exists – skipping."
    else
        ip link add link "$LIBREQOS_SWITCH_IFACE" \
            name "$VLAN_UPSTREAM_SUBIF" \
            type vlan id "$VLAN_UPSTREAM_ID"
        log_ok "Created $VLAN_UPSTREAM_SUBIF (VLAN $VLAN_UPSTREAM_ID, upstream)."
    fi

    add_ip_addr "$LIBREQOS_VLAN_UPSTREAM_IP" "$VLAN_UPSTREAM_SUBIF"
    bring_up "$VLAN_UPSTREAM_SUBIF"

    # ------------------------------------------------------------------
    # 4. Create sub-interface for the DOWNSTREAM VLAN.
    #    This VLAN faces the core router (downstream server).
    # ------------------------------------------------------------------
    if _subif_exists "$VLAN_DOWNSTREAM_SUBIF"; then
        log_info "Sub-interface $VLAN_DOWNSTREAM_SUBIF already exists – skipping."
    else
        ip link add link "$LIBREQOS_SWITCH_IFACE" \
            name "$VLAN_DOWNSTREAM_SUBIF" \
            type vlan id "$VLAN_DOWNSTREAM_ID"
        log_ok "Created $VLAN_DOWNSTREAM_SUBIF (VLAN $VLAN_DOWNSTREAM_ID, downstream)."
    fi

    add_ip_addr "$LIBREQOS_VLAN_DOWNSTREAM_IP" "$VLAN_DOWNSTREAM_SUBIF"
    bring_up "$VLAN_DOWNSTREAM_SUBIF"

    # ------------------------------------------------------------------
    # 5. Disable VLAN hardware offload on the trunk interface.
    #    LibreQoS on-a-stick requires the kernel (not the NIC) to handle VLAN
    #    tagging so that the XDP program sees the tagged frames.
    # ------------------------------------------------------------------
    if command -v ethtool &>/dev/null; then
        ethtool -K "$LIBREQOS_SWITCH_IFACE" rxvlan off 2>/dev/null && \
            log_ok "Disabled VLAN RX offload on $LIBREQOS_SWITCH_IFACE." || \
            log_warn "Could not disable VLAN RX offload on $LIBREQOS_SWITCH_IFACE (driver may not support it)."
    else
        log_warn "ethtool not found; skipping VLAN offload disable (LibreQoS XDP may not work correctly)."
    fi

    # ------------------------------------------------------------------
    # 6. Remind the operator to run 'configure' and restart LibreQoS.
    # ------------------------------------------------------------------
    log_ok "LibreQoS VLAN interfaces ready."
    log_info "Next step: run  sudo $0 configure  to update ispConfig.py and lqos.conf,"
    log_info "then restart LibreQoS: sudo systemctl restart lqosd  (or the appropriate service)."
}

##
# service_stop
#   Removes the VLAN sub-interfaces.
##
service_stop() {
    require_root
    _validate_config

    log_info "Stopping LibreQoS service …"

    for subif in "$VLAN_UPSTREAM_SUBIF" "$VLAN_DOWNSTREAM_SUBIF"; do
        if _subif_exists "$subif"; then
            ip link set "$subif" down
            ip link del "$subif"
            log_ok "Removed sub-interface $subif."
        else
            log_info "Sub-interface $subif not present – nothing to remove."
        fi
    done

    log_ok "LibreQoS service stopped."
}

##
# service_configure
#   Writes the LibreQoS ispConfig.py and lqos.conf files based on values in
#   config.env.  A timestamped backup of each file is created before writing.
#
#   Run this AFTER 'start' and BEFORE launching the LibreQoS daemon.
##
service_configure() {
    require_root
    _validate_config

    log_info "Writing LibreQoS configuration files …"

    # ------------------------------------------------------------------
    # ispConfig.py — Python-style config consumed by LibreQoS scheduler.
    # ------------------------------------------------------------------
    if [[ -f "$LIBREQOS_ISP_CONFIG" ]]; then
        local backup="${LIBREQOS_ISP_CONFIG}.bak.$(date '+%Y%m%d_%H%M%S')"
        cp "$LIBREQOS_ISP_CONFIG" "$backup"
        log_info "Backed up $LIBREQOS_ISP_CONFIG → $backup"
    fi

    cat > "$LIBREQOS_ISP_CONFIG" <<PYEOF
# ispConfig.py — auto-generated by netreplica libreqos.sh
# Do not edit manually; re-run 'sudo ./libreqos.sh configure' instead.

# On-a-stick mode: both interfaceA and interfaceB point to the same physical
# trunk interface.  The VLAN IDs below tell LibreQoS which tag is "core"
# (downstream) and which is "edge" (upstream).
interfaceA = '${LIBREQOS_SWITCH_IFACE}'   # Interface toward the core router (downstream)
interfaceB = '${LIBREQOS_SWITCH_IFACE}'   # Interface toward the edge router (upstream)

OnAStick = True
StickVlanA = ${VLAN_DOWNSTREAM_ID}   # VLAN facing downstream / core router
StickVlanB = ${VLAN_UPSTREAM_ID}     # VLAN facing upstream / edge router

ignoreSubnets = []
allowedSubnets = ['100.64.0.0/10', '192.168.0.0/16']
PYEOF

    log_ok "Wrote $LIBREQOS_ISP_CONFIG."

    # ------------------------------------------------------------------
    # /etc/lqos.conf — TOML config consumed by the lqosd daemon.
    # ------------------------------------------------------------------
    if [[ -f "$LIBREQOS_LQOS_CONF" ]]; then
        local backup="${LIBREQOS_LQOS_CONF}.bak.$(date '+%Y%m%d_%H%M%S')"
        cp "$LIBREQOS_LQOS_CONF" "$backup"
        log_info "Backed up $LIBREQOS_LQOS_CONF → $backup"
    fi

    cat > "$LIBREQOS_LQOS_CONF" <<TOMLEOF
# /etc/lqos.conf — auto-generated by netreplica libreqos.sh
# Do not edit manually; re-run 'sudo ./libreqos.sh configure' instead.

[bridge]
use_xdp_bridge = true
interface_mapping = [
    { name = "${LIBREQOS_SWITCH_IFACE}", redirect_to = "${LIBREQOS_SWITCH_IFACE}", scan_vlans = true }
]
vlan_mapping = [
    { parent = "${LIBREQOS_SWITCH_IFACE}", tag = ${VLAN_DOWNSTREAM_ID}, redirect_to = ${VLAN_UPSTREAM_ID} },
    { parent = "${LIBREQOS_SWITCH_IFACE}", tag = ${VLAN_UPSTREAM_ID},   redirect_to = ${VLAN_DOWNSTREAM_ID} }
]
TOMLEOF

    log_ok "Wrote $LIBREQOS_LQOS_CONF."
    log_info "Restart LibreQoS to apply: sudo systemctl restart lqosd"
}

##
# service_status
##
service_status() {
    echo "=== LibreQoS Service Status ==="
    echo ""
    echo "--- Trunk interface ($LIBREQOS_SWITCH_IFACE) ---"
    ip addr show dev "$LIBREQOS_SWITCH_IFACE" 2>/dev/null | sed 's/^/  /' || echo "  (not found)"

    echo ""
    echo "--- VLAN sub-interfaces ---"
    for subif in "$VLAN_UPSTREAM_SUBIF" "$VLAN_DOWNSTREAM_SUBIF"; do
        printf "  %-25s " "$subif:"
        if _subif_exists "$subif"; then
            ip -br addr show dev "$subif" 2>/dev/null
        else
            echo "NOT present"
        fi
    done

    echo ""
    echo "--- 8021q module ---"
    lsmod | grep -E '^8021q' | sed 's/^/  /' || echo "  NOT loaded"

    echo ""
    echo "--- LibreQoS daemon ---"
    systemctl status lqosd 2>/dev/null | head -5 | sed 's/^/  /' || echo "  (lqosd service not found)"
}

##
# service_install / service_uninstall
##
service_install() {
    require_root
    local script_path
    script_path="$(readlink -f "${BASH_SOURCE[0]}")"
    install_systemd_service \
        "$SERVICE_NAME" \
        "netReplica LibreQoS Server (VLAN trunk / XDP traffic shaper)" \
        "$script_path"
}

service_uninstall() {
    require_root
    uninstall_systemd_service "$SERVICE_NAME"
}

# =============================================================================
# Entry point
# =============================================================================

usage() {
    cat <<EOF
Usage: sudo $0 <command>

Commands:
  deps       Install / verify system dependencies.
  start      Create VLAN sub-interfaces and apply kernel settings (idempotent).
  stop       Remove VLAN sub-interfaces.
  status     Show current state.
  configure  Write LibreQoS ispConfig.py and lqos.conf from config.env.
  install    Register as a systemd service (auto-starts on boot).
  uninstall  Remove the systemd service registration.
EOF
}

case "${1:-}" in
    deps)      service_deps       ;;
    start)     service_start      ;;
    stop)      service_stop       ;;
    status)    service_status     ;;
    configure) service_configure  ;;
    install)   service_install    ;;
    uninstall) service_uninstall  ;;
    *)         usage; exit 1      ;;
esac
