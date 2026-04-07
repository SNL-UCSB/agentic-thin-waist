from __future__ import annotations

import os
import shutil
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional dependency

    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False


load_dotenv()


def get_execution_namespace() -> str:
    namespace = os.getenv(
        "SUBSTRATE_SHELL_NAMESPACE",
        os.getenv("SUBSTRATE_BROWSER_NAMESPACE", "ns1"),
    ).strip()
    return namespace or "ns1"


def get_namespace_pid_file(namespace: str) -> Path:
    raw_path = os.getenv("SUBSTRATE_NAMESPACE_PID_FILE", "").strip()
    if raw_path:
        return Path(raw_path.replace("${namespace}", namespace))
    return Path(f"/var/run/substrate/{namespace}.pid")


def get_namespace_pid(namespace: str) -> str:
    pid_file = get_namespace_pid_file(namespace)
    if not pid_file.is_file():
        raise RuntimeError(f"Missing namespace PID file: {pid_file}")
    return pid_file.read_text(encoding="utf-8").strip()


def use_local_execution() -> bool:
    return True


def build_execution_command(*, binary: str, args: list[str]) -> list[str]:
    namespace_pid = get_namespace_pid(get_execution_namespace())
    return ["nsenter", "-t", namespace_pid, "-n", "--", binary, *args]


def require_execution_binary(binary: str) -> None:
    if shutil.which(binary) is None:
        raise FileNotFoundError(f"Unable to find binary '{binary}' on PATH")
    if shutil.which("nsenter") is None:
        raise RuntimeError(
            "Unable to find 'nsenter' on PATH. Namespace execution requires util-linux."
        )
    get_namespace_pid(get_execution_namespace())
