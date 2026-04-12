"""Tests for scripts/run_experiment.py — validates the integration with the
NetGent shared client, parameter handling, and namespace configuration."""

import json
import os
from pathlib import Path
from unittest import mock

import pytest

WORKFLOWS_DIR = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_url_response(body: dict, code: int = 200):
    """Create a mock urllib response context manager."""
    encoded = json.dumps(body).encode("utf-8")
    resp = mock.MagicMock()
    resp.read.return_value = encoded
    resp.status = code
    resp.__enter__ = mock.MagicMock(return_value=resp)
    resp.__exit__ = mock.MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# Tests for apply_shaping
# ---------------------------------------------------------------------------

class TestApplyShaping:
    def test_sends_correct_payload(self):
        import run_experiment

        mock_resp = _make_url_response({"status": "ok"})
        with mock.patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            run_experiment.apply_shaping(50.0, 10.0, 20.0, "fq_codel", "both")

            call_args = mock_open.call_args[0][0]
            payload = json.loads(call_args.data.decode("utf-8"))
            assert payload["download_mbps"] == 50.0
            assert payload["upload_mbps"] == 10.0
            assert payload["latency_ms"] == 20.0
            assert payload["qdisc"] == "fq_codel"
            assert payload["upstream_iface"] == "veth4"
            assert payload["downstream_iface"] == "veth2"
            assert payload["latency_location"] == "both"

    def test_no_latency_location_when_zero_latency(self):
        import run_experiment

        mock_resp = _make_url_response({"status": "ok"})
        with mock.patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            run_experiment.apply_shaping(100.0, 100.0, 0.0, "pfifo", "both")

            call_args = mock_open.call_args[0][0]
            payload = json.loads(call_args.data.decode("utf-8"))
            assert "latency_location" not in payload

    def test_exits_on_failure(self):
        import run_experiment

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=run_experiment.urllib.error.URLError("connection refused"),
        ):
            with pytest.raises(SystemExit):
                run_experiment.apply_shaping(100.0, 100.0, 0.0, "pfifo", "both")


# ---------------------------------------------------------------------------
# Tests for apply_congestion
# ---------------------------------------------------------------------------

class TestApplyCongestion:
    def test_sends_correct_payload(self):
        import run_experiment

        mock_resp = _make_url_response({"current_algorithm": "bbr"})
        with mock.patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            run_experiment.apply_congestion("bbr")

            call_args = mock_open.call_args[0][0]
            payload = json.loads(call_args.data.decode("utf-8"))
            assert payload["algorithm"] == "bbr"
            assert payload["namespace"] == "ns1"

    def test_exits_on_failure(self):
        import run_experiment

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=run_experiment.urllib.error.URLError("connection refused"),
        ):
            with pytest.raises(SystemExit):
                run_experiment.apply_congestion("cubic")


# ---------------------------------------------------------------------------
# Tests for run_workflow
# ---------------------------------------------------------------------------

class TestRunWorkflow:
    def _write_workflow(self, tmp_path, workflow: dict) -> str:
        path = tmp_path / "workflow.json"
        path.write_text(json.dumps(workflow))
        return str(path)

    def test_exits_if_workflow_file_missing(self, tmp_path):
        import run_experiment

        with pytest.raises(SystemExit):
            run_experiment.run_workflow("/nonexistent/workflow.json", "shell", {})

    def test_calls_netgent_run_workflow_with_params(self, tmp_path):
        import run_experiment

        workflow = {
            "specification": "Ping a host",
            "states": [
                {
                    "checks": [{"type": "always_true", "params": {}}],
                    "actions": [
                        {"type": "ping", "params": {"host": "{{host}}", "count": "{{count}}"}}
                    ],
                    "end_state": "done",
                }
            ],
            "parameters": ["host", "count"],
        }
        workflow_path = self._write_workflow(tmp_path, workflow)
        parameters = {"host": "8.8.8.8", "count": "3"}

        mock_result = [{"success": True, "output": [{"rtt_avg": 10.5}]}]

        def mock_run(self_client, wf, *, parameters=None, type=None):
            return mock_result

        with mock.patch(
            "clients.netgent.src.main.NetGent.run_workflow", mock_run
        ):
            run_experiment.run_workflow(workflow_path, "shell", parameters)

        assert os.environ.get("NETGENT_USE_LOCAL") == "false"
        assert os.environ.get("NETGENT_NAMESPACE") == "ns1"

    def test_passes_runtime_type_to_client(self, tmp_path):
        import run_experiment

        workflow = {
            "specification": "Go to a website",
            "states": [
                {
                    "checks": [{"type": "always_true", "params": {}}],
                    "actions": [
                        {"type": "go_to_url", "params": {"url": "https://example.com"}}
                    ],
                    "end_state": "done",
                }
            ],
        }
        workflow_path = self._write_workflow(tmp_path, workflow)

        captured_kwargs = {}

        def mock_run(self_client, wf, *, parameters=None, type=None):
            captured_kwargs["type"] = type
            captured_kwargs["parameters"] = parameters
            return []

        with mock.patch(
            "clients.netgent.src.main.NetGent.run_workflow", mock_run
        ):
            run_experiment.run_workflow(workflow_path, "browser", {"url": "https://test.com"})

        assert captured_kwargs["type"] == "browser"
        assert captured_kwargs["parameters"] == {"url": "https://test.com"}

    def test_empty_parameters_when_none_provided(self, tmp_path):
        import run_experiment

        workflow = {"specification": "Simple test", "states": []}
        workflow_path = self._write_workflow(tmp_path, workflow)

        captured_kwargs = {}

        def mock_run(self_client, wf, *, parameters=None, type=None):
            captured_kwargs["parameters"] = parameters
            return []

        with mock.patch(
            "clients.netgent.src.main.NetGent.run_workflow", mock_run
        ):
            run_experiment.run_workflow(workflow_path, "shell", {})

        assert captured_kwargs["parameters"] == {}


# ---------------------------------------------------------------------------
# Tests for CLI argument parsing
# ---------------------------------------------------------------------------

class TestMainCLI:
    def test_param_flag_parsed_correctly(self):
        import run_experiment

        mock_shaping = mock.MagicMock()
        mock_congestion = mock.MagicMock()
        mock_run = mock.MagicMock()

        with (
            mock.patch.object(run_experiment, "apply_shaping", mock_shaping),
            mock.patch.object(run_experiment, "apply_congestion", mock_congestion),
            mock.patch.object(run_experiment, "run_workflow", mock_run),
            mock.patch(
                "sys.argv",
                [
                    "run_experiment.py",
                    "--workflow", "/tmp/test.json",
                    "--runtime", "shell",
                    "--param", "host=8.8.8.8",
                    "--param", "count=5",
                    "--download", "50",
                    "--cca", "bbr",
                ],
            ),
        ):
            run_experiment.main()

        mock_shaping.assert_called_once_with(50.0, 100.0, 0.0, "pfifo", "both")
        mock_congestion.assert_called_once_with("bbr")
        mock_run.assert_called_once_with(
            "/tmp/test.json", "shell", {"host": "8.8.8.8", "count": "5"}
        )

    def test_no_params_passes_empty_dict(self):
        import run_experiment

        mock_run = mock.MagicMock()

        with (
            mock.patch.object(run_experiment, "apply_shaping", mock.MagicMock()),
            mock.patch.object(run_experiment, "apply_congestion", mock.MagicMock()),
            mock.patch.object(run_experiment, "run_workflow", mock_run),
            mock.patch(
                "sys.argv",
                ["run_experiment.py", "--workflow", "/tmp/test.json"],
            ),
        ):
            run_experiment.main()

        mock_run.assert_called_once_with("/tmp/test.json", "shell", {})


# ---------------------------------------------------------------------------
# Tests against actual workflow JSON files
# ---------------------------------------------------------------------------

class TestWorkflowFiles:
    """Verify each test workflow file loads, has parameters declared, and
    that run_workflow passes the correct workflow + parameters to NetGent."""

    def test_shell_workflow_with_parameters(self):
        import run_experiment

        workflow_path = str(WORKFLOWS_DIR / "test_shell_workflow.json")
        params = {"host": "1.1.1.1", "count": "5"}
        captured = {}

        def mock_run(self_client, wf, *, parameters=None, type=None):
            captured["workflow"] = wf
            captured["parameters"] = parameters
            captured["type"] = type
            return [{"success": True, "output": []}]

        with mock.patch(
            "clients.netgent.src.main.NetGent.run_workflow", mock_run
        ):
            run_experiment.run_workflow(workflow_path, "shell", params)

        wf = captured["workflow"]
        assert wf["parameters"] == ["host", "count"]
        assert wf["states"][0]["actions"][0]["params"]["host"] == "{{host}}"
        assert wf["states"][0]["actions"][0]["params"]["count"] == "{{count}}"
        assert captured["parameters"] == {"host": "1.1.1.1", "count": "5"}
        assert captured["type"] == "shell"

    def test_ndt_workflow_with_parameters(self):
        import run_experiment

        workflow_path = str(WORKFLOWS_DIR / "test_ndt_workflow.json")
        params = {"download": "true", "upload": "false"}
        captured = {}

        def mock_run(self_client, wf, *, parameters=None, type=None):
            captured["workflow"] = wf
            captured["parameters"] = parameters
            captured["type"] = type
            return [{"success": True, "output": []}]

        with mock.patch(
            "clients.netgent.src.main.NetGent.run_workflow", mock_run
        ):
            run_experiment.run_workflow(workflow_path, "shell", params)

        wf = captured["workflow"]
        assert wf["parameters"] == ["download", "upload"]
        assert wf["states"][0]["actions"][0]["params"]["download"] == "{{download}}"
        assert wf["states"][0]["actions"][0]["params"]["upload"] == "{{upload}}"
        assert captured["parameters"] == {"download": "true", "upload": "false"}

    def test_iperf_workflow_with_parameters(self):
        import run_experiment

        workflow_path = str(WORKFLOWS_DIR / "test_iperf_workflow.json")
        params = {"host": "10.0.0.1", "port": "5201", "duration": "10"}
        captured = {}

        def mock_run(self_client, wf, *, parameters=None, type=None):
            captured["workflow"] = wf
            captured["parameters"] = parameters
            captured["type"] = type
            return [{"success": True, "output": []}]

        with mock.patch(
            "clients.netgent.src.main.NetGent.run_workflow", mock_run
        ):
            run_experiment.run_workflow(workflow_path, "shell", params)

        wf = captured["workflow"]
        assert wf["parameters"] == ["host", "port", "duration"]
        assert wf["states"][0]["actions"][0]["params"]["host"] == "{{host}}"
        assert wf["states"][0]["actions"][0]["params"]["port"] == "{{port}}"
        assert wf["states"][0]["actions"][0]["params"]["duration_seconds"] == "{{duration}}"
        assert captured["parameters"] == {
            "host": "10.0.0.1",
            "port": "5201",
            "duration": "10",
        }
        assert captured["type"] == "shell"

    def test_browser_workflow_with_parameters(self):
        import run_experiment

        workflow_path = str(WORKFLOWS_DIR / "test_browser_workflow.json")
        params = {"url": "https://google.com"}
        captured = {}

        def mock_run(self_client, wf, *, parameters=None, type=None):
            captured["workflow"] = wf
            captured["parameters"] = parameters
            captured["type"] = type
            return [{"success": True, "output": []}]

        with mock.patch(
            "clients.netgent.src.main.NetGent.run_workflow", mock_run
        ):
            run_experiment.run_workflow(workflow_path, "browser", params)

        wf = captured["workflow"]
        assert wf["parameters"] == ["url"]
        assert wf["states"][0]["actions"][0]["params"]["url"] == "{{url}}"
        assert captured["parameters"] == {"url": "https://google.com"}
        assert captured["type"] == "browser"

    def test_shell_workflow_cli_end_to_end(self):
        """Simulate a full CLI invocation with the shell workflow file."""
        import run_experiment

        workflow_path = str(WORKFLOWS_DIR / "test_shell_workflow.json")
        captured = {}

        def mock_run(self_client, wf, *, parameters=None, type=None):
            captured["workflow"] = wf
            captured["parameters"] = parameters
            captured["type"] = type
            return [{"success": True, "output": [{"rtt_avg": 12.3}]}]

        mock_shaping_resp = _make_url_response({"status": "ok"})
        mock_congestion_resp = _make_url_response({"current_algorithm": "bbr"})

        responses = [mock_shaping_resp, mock_congestion_resp]

        with (
            mock.patch(
                "urllib.request.urlopen", side_effect=responses
            ),
            mock.patch(
                "clients.netgent.src.main.NetGent.run_workflow", mock_run
            ),
            mock.patch(
                "sys.argv",
                [
                    "run_experiment.py",
                    "--workflow", workflow_path,
                    "--runtime", "shell",
                    "--download", "50",
                    "--upload", "10",
                    "--latency", "20",
                    "--cca", "bbr",
                    "--param", "host=8.8.8.8",
                    "--param", "count=3",
                ],
            ),
        ):
            run_experiment.main()

        assert captured["parameters"] == {"host": "8.8.8.8", "count": "3"}
        assert captured["type"] == "shell"
        assert captured["workflow"]["parameters"] == ["host", "count"]
        assert os.environ.get("NETGENT_USE_LOCAL") == "false"
        assert os.environ.get("NETGENT_NAMESPACE") == "ns1"
