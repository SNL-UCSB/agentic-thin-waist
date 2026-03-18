"""
Pytest configuration and shared fixtures for netReplica Ansible verification tests.

Run from the ansible/ directory:
    pytest tests/ -v
    pytest tests/ -v --tb=short
"""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

# Path resolution: tests/ lives one level inside ansible/
ANSIBLE_DIR = Path(__file__).parent.parent
INVENTORY_FILE = ANSIBLE_DIR / "inventory" / "hosts.yml"
GROUP_VARS_FILE = ANSIBLE_DIR / "inventory" / "group_vars" / "all.yml"


def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a subprocess command with sensible defaults."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        **kwargs,
    )


@pytest.fixture(scope="session")
def inventory() -> dict:
    """
    Load the full Ansible inventory as a parsed dict.

    Uses `ansible-inventory --list` so host_vars, group_vars, and
    dynamic variables are all resolved before the tests run.
    """
    result = _run(
        [
            "ansible-inventory",
            "-i",
            str(INVENTORY_FILE),
            "--list",
        ]
    )
    if result.returncode != 0:
        pytest.fail(
            f"Failed to load Ansible inventory.\n"
            f"stderr: {result.stderr}\n"
            f"Make sure `ansible-inventory` is on your PATH and "
            f"inventory/hosts.yml is filled in."
        )
    return json.loads(result.stdout)


@pytest.fixture(scope="session")
def host_vars(inventory: dict) -> dict:
    """Return a dict mapping each hostname to its resolved Ansible variables."""
    return inventory.get("_meta", {}).get("hostvars", {})


@pytest.fixture(scope="session")
def group_vars() -> dict:
    """Load group_vars/all.yml as a plain dict (no Jinja2 resolution)."""
    with open(GROUP_VARS_FILE) as fh:
        return yaml.safe_load(fh) or {}


def ansible_ad_hoc(
    host: str,
    module: str,
    args: str = "",
    become: bool = True,
    inventory: str = str(INVENTORY_FILE),
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """
    Run an Ansible ad-hoc command against *host* using *module*.

    Returns the raw CompletedProcess so callers can inspect rc, stdout, stderr.
    """
    cmd = ["ansible", host, "-i", inventory, "-m", module]
    if become:
        cmd.append("--become")
    if args:
        cmd.extend(["-a", args])
    return _run(cmd, timeout=timeout)


def shell(
    host: str,
    command: str,
    become: bool = True,
) -> subprocess.CompletedProcess:
    """Shorthand: run a shell command on *host* via the Ansible shell module."""
    return ansible_ad_hoc(host, "shell", command, become=become)


@pytest.fixture(scope="session")
def ansible_shell():
    """
    Fixture that exposes the `shell` helper so tests can call
    ``ansible_shell(host, cmd)`` without importing the module.
    """
    return shell
