"""
Integration tests for the Substrate Worker service.

These tests verify that the Substrate Worker starts correctly with its
Telemetry Service dependency available, and responds to health and API calls.
"""

import pytest
import requests


class TestSubstrateWorkerHealth:
    def test_health_endpoint_returns_200(self, http: requests.Session, substrate_worker_url: str):
        response = http.get(f"{substrate_worker_url}/health", timeout=10)
        assert response.status_code == 200

    def test_health_response_contains_status(self, http: requests.Session, substrate_worker_url: str):
        response = http.get(f"{substrate_worker_url}/health", timeout=10)
        data = response.json()
        assert "status" in data


class TestSubstrateWorkerAPI:
    def test_workers_endpoint_is_reachable(self, http: requests.Session, substrate_worker_url: str):
        """The /workers endpoint should respond without a server error."""
        response = http.get(f"{substrate_worker_url}/workers", timeout=10)
        assert response.status_code < 500

    def test_tasks_endpoint_is_reachable(self, http: requests.Session, substrate_worker_url: str):
        """The /tasks endpoint should respond without a server error."""
        response = http.get(f"{substrate_worker_url}/tasks", timeout=10)
        assert response.status_code < 500
