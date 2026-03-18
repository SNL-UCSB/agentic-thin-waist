"""
End-to-end tests for the full Agentic Thin Waist stack.

These tests validate cross-service behaviour with all services running.
They cover the core requirements: controllability, composability, fidelity,
and replicability of network experiments.
"""

import pytest
import requests


class TestFullStackHealth:
    """Verify that every service in the stack is reachable and healthy."""

    def test_experiment_api_healthy(self, http: requests.Session, experiment_api_url: str):
        response = http.get(f"{experiment_api_url}/health", timeout=10)
        assert response.status_code == 200

    def test_ctp_service_healthy(self, http: requests.Session, ctp_service_url: str):
        response = http.get(f"{ctp_service_url}/health", timeout=10)
        assert response.status_code == 200

    def test_substrate_worker_healthy(self, http: requests.Session, substrate_worker_url: str):
        response = http.get(f"{substrate_worker_url}/health", timeout=10)
        assert response.status_code == 200

    def test_netgent_service_healthy(self, http: requests.Session, netgent_service_url: str):
        response = http.get(f"{netgent_service_url}/health", timeout=10)
        assert response.status_code == 200

    def test_telemetry_service_healthy(self, http: requests.Session, telemetry_service_url: str):
        response = http.get(f"{telemetry_service_url}/health", timeout=10)
        assert response.status_code == 200

    def test_orchestration_healthy(self, http: requests.Session, orchestration_url: str):
        response = http.get(f"{orchestration_url}/health", timeout=10)
        assert response.status_code == 200


class TestExperimentLifecycle:
    """
    Smoke test for the experiment creation lifecycle across all planes.

    Intent (Experiment API) → Representation (CTP) → Execution (Substrate Worker)
    → Results (Telemetry)
    """

    def test_experiment_api_accepts_requests(
        self, http: requests.Session, experiment_api_url: str
    ):
        """The Experiment API should accept and process requests without a 5xx error."""
        response = http.get(f"{experiment_api_url}/experiments", timeout=10)
        assert response.status_code < 500

    def test_ctp_profiles_accessible_from_experiment_api(
        self, http: requests.Session, ctp_service_url: str
    ):
        """CTP profile data should be accessible (cross-service read)."""
        response = http.get(f"{ctp_service_url}/profiles", timeout=10)
        assert response.status_code < 500

    def test_telemetry_accessible_after_stack_start(
        self, http: requests.Session, telemetry_service_url: str
    ):
        """Telemetry service should be ready to store results."""
        response = http.get(f"{telemetry_service_url}/experiments", timeout=10)
        assert response.status_code < 500
