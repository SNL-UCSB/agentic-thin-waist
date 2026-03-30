from __future__ import annotations

import os
import shutil
import subprocess

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional dependency

    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False


load_dotenv()

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def use_local_execution() -> bool:
    raw_value = os.getenv("NETGENT_USE_LOCAL", "true").strip().lower()
    return raw_value in _TRUTHY_VALUES


def get_execution_namespace() -> str:
    namespace = os.getenv("NETGENT_NAMESPACE", "ns1").strip()
    return namespace or "ns1"


def build_execution_command(*, binary: str, args: list[str]) -> list[str]:
    if use_local_execution():
        return [binary, *args]

    namespace = get_execution_namespace()
    return [
        "nsenter",
        "-t",
        "1",
        "-m",
        "--",
        "ip",
        "netns",
        "exec",
        namespace,
        binary,
        *args,
    ]


def require_execution_binary(binary: str) -> None:
    if shutil.which(binary) is None:
        raise FileNotFoundError(f"Unable to find binary '{binary}' on PATH")

    if use_local_execution():
        return

    if shutil.which("ip") is None:
        raise RuntimeError(
            "Unable to find 'ip' on PATH. Namespace execution requires iproute2."
        )
    if shutil.which("nsenter") is None:
        raise RuntimeError(
            "Unable to find 'nsenter' on PATH. Namespace execution requires util-linux."
        )

    namespace = get_execution_namespace()
    namespaces = _list_namespaces()
    if namespace not in namespaces:
        raise RuntimeError(
            f"Network namespace '{namespace}' not found. "
            "Ensure the substrate worker namespace setup is active before "
            "running NetGent with NETGENT_USE_LOCAL=false."
        )


def _list_namespaces() -> set[str]:
    completed = subprocess.run(
        ["nsenter", "-t", "1", "-m", "--", "ip", "netns", "list"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"Failed to list network namespaces via 'ip netns list': {detail}"
        )

    namespaces: set[str] = set()
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        namespaces.add(line.split()[0])
    return namespaces
