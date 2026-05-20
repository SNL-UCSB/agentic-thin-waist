"""Unit tests for the per-experiment shell-command deadline.

The substrate worker monkey-patches NetGent's ``utils.execution.run_subprocess``
at module load so any shell command dispatched via the workflow is bounded by
a wallclock deadline carried in a ``ContextVar``. These tests exercise the
patched function directly — no FastAPI / workflow plumbing needed.
"""

from __future__ import annotations

import asyncio

import substrate.main_local as main_local


def _run(coro):
    return asyncio.run(coro)


def test_deadline_unset_returns_normal_result(monkeypatch):
    """When no deadline is set the patched runner is a transparent passthrough."""
    rc, stdout, stderr = _run(
        main_local._run_subprocess_with_deadline(
            ["/bin/sh", "-c", "echo hello && echo err 1>&2"]
        )
    )
    assert rc == 0
    assert "hello" in stdout
    assert "err" in stderr
    # Triggered flag is a fresh list per /run; this test never set one.
    assert main_local._SHELL_DEADLINE_TRIGGERED.get() == [False]


def test_deadline_short_terminates_subprocess(monkeypatch):
    """A sleep longer than the deadline is killed and returns 124.

    The triggered flag must also be set in the shared list so the /run
    handler can surface it in the response envelope.
    """
    triggered_box: list = [False]

    async def _go():
        tok_box = main_local._SHELL_DEADLINE_TRIGGERED.set(triggered_box)
        tok_dl = main_local._SHELL_DEADLINE_SECONDS.set(0.3)
        try:
            return await main_local._run_subprocess_with_deadline(
                ["/bin/sh", "-c", "sleep 5"]
            )
        finally:
            main_local._SHELL_DEADLINE_SECONDS.reset(tok_dl)
            main_local._SHELL_DEADLINE_TRIGGERED.reset(tok_box)

    rc, stdout, stderr = _run(_go())
    assert rc == 124
    assert "terminated at experiment-duration deadline" in stderr
    assert triggered_box[0] is True


def test_deadline_long_allows_completion(monkeypatch):
    """A subprocess shorter than the deadline finishes normally."""

    async def _go():
        token = main_local._SHELL_DEADLINE_SECONDS.set(5.0)
        try:
            return await main_local._run_subprocess_with_deadline(
                ["/bin/sh", "-c", "echo ok"]
            )
        finally:
            main_local._SHELL_DEADLINE_SECONDS.reset(token)

    rc, stdout, _ = _run(_go())
    assert rc == 0
    assert "ok" in stdout


def test_deadline_applies_to_any_shell_command(monkeypatch):
    """The deadline patch lives below the adapter layer, so it bounds any
    shell command — ping, iperf3, curl, ndt — not just wget. Simulate a
    ping-like long-running command to confirm.
    """
    triggered_box: list = [False]

    async def _go():
        tok_box = main_local._SHELL_DEADLINE_TRIGGERED.set(triggered_box)
        tok_dl = main_local._SHELL_DEADLINE_SECONDS.set(0.4)
        try:
            # Mimics `ping -c <large> 8.8.8.8` — emits a line per second
            # until killed.
            return await main_local._run_subprocess_with_deadline(
                [
                    "python3",
                    "-u",
                    "-c",
                    "import time; i=0\nwhile True: print('icmp_seq=', i); "
                    "i+=1; time.sleep(1)",
                ]
            )
        finally:
            main_local._SHELL_DEADLINE_SECONDS.reset(tok_dl)
            main_local._SHELL_DEADLINE_TRIGGERED.reset(tok_box)

    rc, stdout, stderr = _run(_go())
    assert rc == 124
    assert triggered_box[0] is True
    assert "terminated at experiment-duration deadline" in stderr


def test_deadline_captures_partial_output(monkeypatch):
    """Stdout written before the kill is preserved in the return tuple.

    Use Python with an explicit flush — `sh -c 'echo …'` fully-buffers stdout
    when it's a pipe, so the marker would be stuck in the libc buffer when the
    shell gets SIGTERMed and would never reach our communicate() drain.
    """

    async def _go():
        # Give the Python interpreter time to start + flush the marker before
        # we kill it. ~200 ms startup + print → 1.5 s deadline is generous.
        token = main_local._SHELL_DEADLINE_SECONDS.set(1.5)
        try:
            return await main_local._run_subprocess_with_deadline(
                [
                    "python3",
                    "-u",  # unbuffered stdout/stderr
                    "-c",
                    "import sys,time; sys.stdout.write('START_MARKER\\n'); "
                    "sys.stdout.flush(); time.sleep(30)",
                ]
            )
        finally:
            main_local._SHELL_DEADLINE_SECONDS.reset(token)

    rc, stdout, stderr = _run(_go())
    assert rc == 124
    assert "START_MARKER" in stdout
    assert "terminated at experiment-duration deadline" in stderr
