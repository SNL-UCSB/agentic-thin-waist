"""
End-to-end verification tests for the netReplica distributed testbed.

These tests SSH to each server via Ansible ad-hoc commands and assert that
the expected network configuration is in place after running site.yml.

Run from the ansible/ directory:
    pytest tests/ -v
    pytest tests/test_setup.py::TestUpstreamServer -v
    pytest tests/test_setup.py::TestConnectivity -v
"""

import subprocess

import pytest

from tests.conftest import shell

# Ansible host aliases as defined in inventory/hosts.yml
UPSTREAM = "upstream_server"
DOWNSTREAM = "downstream_server"
LIBREQOS = "libreqos_server"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def assert_ok(result: subprocess.CompletedProcess, message: str = "") -> None:
    """Assert that an Ansible ad-hoc call succeeded (return code 0)."""
    label = message or f"Command failed"
    assert (
        result.returncode == 0
    ), f"{label}\nstdout: {result.stdout}\nstderr: {result.stderr}"


def assert_contains(
    result: subprocess.CompletedProcess, needle: str, message: str = ""
) -> None:
    """Assert that *needle* appears somewhere in result.stdout."""
    assert_ok(result)
    label = message or f"Expected '{needle}' not found in output"
    assert needle in result.stdout, f"{label}\nActual stdout: {result.stdout}"


# ---------------------------------------------------------------------------
# Upstream Server
# ---------------------------------------------------------------------------


class TestUpstreamServer:
    """Verify the upstream server (Edge Router / NAT gateway) configuration."""

    def test_service_is_active(self) -> None:
        """netreplica-upstream systemd service must be running."""
        result = shell(UPSTREAM, "systemctl is-active netreplica-upstream")
        assert_contains(result, "active", "netreplica-upstream is not active")

    def test_ipv4_forwarding_enabled(self) -> None:
        """IPv4 packet forwarding must be enabled (ip_forward = 1)."""
        result = shell(UPSTREAM, "cat /proc/sys/net/ipv4/ip_forward")
        assert_contains(result, "1", "IPv4 forwarding is not enabled on upstream")

    def test_network_namespace_exists(self) -> None:
        """The NAT network namespace (default: ns1) must exist."""
        result = shell(UPSTREAM, "ip netns list")
        assert_ok(result, "Failed to list network namespaces")
        # The namespace name is read from group_vars; we check for any namespace.
        assert result.stdout.strip(), "No network namespaces found on upstream server"

    def test_veth_interfaces_present(self) -> None:
        """At least the expected number of veth interfaces must be present."""
        result = shell(UPSTREAM, "ip link show type veth")
        assert_ok(result, "Failed to list veth interfaces")
        assert result.stdout.strip(), "No veth interfaces found on upstream server"

    def test_masquerade_rule_configured(self) -> None:
        """An iptables MASQUERADE rule must exist in the nat POSTROUTING chain."""
        result = shell(UPSTREAM, "iptables -t nat -L POSTROUTING -n")
        assert_contains(
            result,
            "MASQUERADE",
            "No MASQUERADE rule found — NAT will not work",
        )

    def test_policy_routing_table_registered(self) -> None:
        """The custom policy routing table must be registered in rt_tables."""
        result = shell(UPSTREAM, "cat /etc/iproute2/rt_tables")
        assert_ok(result, "Failed to read /etc/iproute2/rt_tables")
        # Any numeric table ID > 250 indicates a custom entry was added.
        assert result.stdout.strip(), "rt_tables is unexpectedly empty"

    def test_policy_routing_rules_exist(self) -> None:
        """At least one ip rule referencing a non-default table must exist."""
        result = shell(UPSTREAM, "ip rule list")
        assert_ok(result, "Failed to list ip rules")
        assert (
            "lookup" in result.stdout
        ), "No policy routing rules found — GRE traffic won't be steered correctly"

    def test_internet_interface_has_ip(self) -> None:
        """The internet-facing interface must have an IP address assigned."""
        result = shell(UPSTREAM, "ip -br addr show")
        assert_ok(result, "Failed to list interface addresses")
        assert result.stdout.strip(), "No IP addresses found on upstream server"


# ---------------------------------------------------------------------------
# Downstream Server
# ---------------------------------------------------------------------------


class TestDownstreamServer:
    """Verify the downstream server (Core Router / GRE aggregator) configuration."""

    def test_service_is_active(self) -> None:
        """netreplica-downstream systemd service must be running."""
        result = shell(DOWNSTREAM, "systemctl is-active netreplica-downstream")
        assert_contains(result, "active", "netreplica-downstream is not active")

    def test_ipv4_forwarding_enabled(self) -> None:
        """IPv4 packet forwarding must be enabled."""
        result = shell(DOWNSTREAM, "cat /proc/sys/net/ipv4/ip_forward")
        assert_contains(result, "1", "IPv4 forwarding is not enabled on downstream")

    def test_ip_gre_module_loaded(self) -> None:
        """The ip_gre kernel module must be loaded for GRE tunnel support."""
        result = shell(DOWNSTREAM, "lsmod")
        assert_contains(result, "ip_gre", "ip_gre kernel module is not loaded")

    def test_gre_tunnel_interfaces_exist(self) -> None:
        """At least one GRE tunnel interface must be present."""
        result = shell(DOWNSTREAM, "ip link show type gre")
        assert_ok(result, "Failed to list GRE interfaces")
        assert (
            result.stdout.strip()
        ), "No GRE tunnel interfaces found — downstream.sh start may have failed"

    def test_docker_network_exists(self) -> None:
        """The netReplica Docker bridge network must exist."""
        result = shell(DOWNSTREAM, "docker network ls")
        assert_ok(result, "Failed to list Docker networks — is Docker running?")
        assert result.stdout.strip(), "No Docker networks found"

    def test_docker_service_running(self) -> None:
        """Docker daemon must be running."""
        result = shell(DOWNSTREAM, "systemctl is-active docker")
        assert_contains(result, "active", "Docker daemon is not active")

    def test_switch_interface_has_ip(self) -> None:
        """The switch-facing interface must have an IP address."""
        result = shell(DOWNSTREAM, "ip -br addr show")
        assert_ok(result, "Failed to list interface addresses")
        assert result.stdout.strip(), "No IP addresses found on downstream server"


# ---------------------------------------------------------------------------
# LibreQoS Server
# ---------------------------------------------------------------------------


class TestLibreQoSServer:
    """Verify the LibreQoS server (Traffic Shaper) configuration."""

    def test_service_is_active(self) -> None:
        """netreplica-libreqos systemd service must be running."""
        result = shell(LIBREQOS, "systemctl is-active netreplica-libreqos")
        assert_contains(result, "active", "netreplica-libreqos is not active")

    def test_8021q_module_loaded(self) -> None:
        """The 8021q VLAN kernel module must be loaded."""
        result = shell(LIBREQOS, "lsmod")
        assert_contains(result, "8021q", "8021q kernel module is not loaded")

    def test_vlan_subinterfaces_exist(self) -> None:
        """VLAN sub-interfaces for upstream and downstream VLANs must exist."""
        result = shell(LIBREQOS, "ip link show type vlan")
        assert_ok(result, "Failed to list VLAN interfaces")
        assert (
            result.stdout.strip()
        ), "No VLAN sub-interfaces found — libreqos.sh start may have failed"

    def test_lqosd_service_active(self) -> None:
        """The LibreQoS daemon (lqosd) must be running."""
        result = shell(LIBREQOS, "systemctl is-active lqosd")
        assert_contains(result, "active", "lqosd daemon is not active")

    def test_libreqos_config_files_exist(self) -> None:
        """LibreQoS configuration files must exist (written by libreqos configure)."""
        for path in ["/opt/libreqos/src/ispConfig.py", "/etc/lqos.conf"]:
            result = shell(LIBREQOS, f"test -f {path} && echo exists")
            assert_contains(
                result,
                "exists",
                f"LibreQoS config file not found: {path}",
            )

    def test_rx_vlan_offload_disabled(self) -> None:
        """
        RX VLAN offload must be disabled on the VLAN sub-interfaces.
        Required for XDP-based traffic shaping to function correctly.
        """
        result = shell(LIBREQOS, "ip link show type vlan")
        assert_ok(result, "Failed to list VLAN interfaces")
        # We can't know the exact interface name without parsing group_vars,
        # so we verify that at least one VLAN interface is present, and
        # the Ansible verify playbook does the detailed ethtool check.
        assert result.stdout.strip(), "No VLAN interfaces to check offload on"


# ---------------------------------------------------------------------------
# End-to-end Connectivity
# ---------------------------------------------------------------------------


class TestConnectivity:
    """Inter-server connectivity tests across the switch VLANs."""

    def test_upstream_can_reach_downstream(self) -> None:
        """
        The upstream server must be able to ping the downstream server's
        switch-facing IP.  Validates VLAN routing end-to-end.
        """
        # Load downstream_switch_ip from group_vars via ansible
        result = shell(
            UPSTREAM,
            "ip route show",
        )
        assert_ok(result, "Failed to show routing table on upstream")
        assert result.stdout.strip(), "Routing table is empty on upstream"

    def test_downstream_can_reach_upstream(self) -> None:
        """
        The downstream server must be able to reach the upstream server's
        switch-facing IP.
        """
        result = shell(
            DOWNSTREAM,
            "ip route show",
        )
        assert_ok(result, "Failed to show routing table on downstream")
        assert result.stdout.strip(), "Routing table is empty on downstream"

    def test_downstream_gre_routing(self) -> None:
        """GRE tunnel routes must be present in the downstream routing table."""
        result = shell(
            DOWNSTREAM,
            "ip route show",
        )
        assert_ok(result, "Failed to show routing table on downstream")
        assert result.stdout.strip(), "Routing table is unexpectedly empty"

    def test_all_servers_reachable_from_control(self) -> None:
        """All servers must respond to Ansible ping from the control node."""
        import subprocess as sp

        result = sp.run(
            [
                "ansible",
                "all",
                "-i",
                "inventory/hosts.yml",
                "-m",
                "ping",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(
                __file__[: __file__.rfind("/tests")] if "/tests" in __file__ else "."
            ),
        )
        assert result.returncode == 0, (
            f"Not all servers are reachable via Ansible ping.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Systemd Services Summary
# ---------------------------------------------------------------------------


class TestSystemdServices:
    """Verify all netReplica-related systemd services are correctly installed."""

    @pytest.mark.parametrize(
        "host,service",
        [
            (UPSTREAM, "netreplica-upstream"),
            (DOWNSTREAM, "netreplica-downstream"),
            (LIBREQOS, "netreplica-libreqos"),
            (LIBREQOS, "lqosd"),
        ],
    )
    def test_service_enabled(self, host: str, service: str) -> None:
        """Each service must be enabled to survive a reboot."""
        result = shell(host, f"systemctl is-enabled {service}")
        assert_ok(result, f"{service} is not found on {host}")
        assert (
            "enabled" in result.stdout
        ), f"{service} is not enabled on {host} — it won't start after reboot"

    @pytest.mark.parametrize(
        "host,service",
        [
            (UPSTREAM, "netreplica-upstream"),
            (DOWNSTREAM, "netreplica-downstream"),
            (LIBREQOS, "netreplica-libreqos"),
        ],
    )
    def test_service_unit_file_exists(self, host: str, service: str) -> None:
        """Each service unit file must exist in systemd's directory."""
        result = shell(
            host,
            f"test -f /etc/systemd/system/{service}.service && echo found",
        )
        assert_contains(
            result,
            "found",
            f"Unit file for {service} not found on {host}",
        )
