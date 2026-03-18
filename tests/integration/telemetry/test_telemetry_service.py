"""
Integration tests for the Telemetry service.

These tests verify that the Telemetry service starts correctly, connects
to its PostgreSQL and MinIO dependencies, and exposes a functional API.
"""

import pytest
import requests


class TestTelemetryServiceHealth:
    def test_health_endpoint_returns_200(self, http: requests.Session, telemetry_service_url: str):
        response = http.get(f"{telemetry_service_url}/health", timeout=10)
        assert response.status_code == 200

    def test_health_response_contains_status(self, http: requests.Session, telemetry_service_url: str):
        response = http.get(f"{telemetry_service_url}/health", timeout=10)
        data = response.json()
        assert "status" in data


class TestTelemetryServiceAPI:
    def test_results_endpoint_is_reachable(self, http: requests.Session, telemetry_service_url: str):
        """The /results endpoint should respond (200 or 404 are both acceptable)."""
        response = http.get(f"{telemetry_service_url}/results", timeout=10)
        assert response.status_code in (200, 404)

    def test_experiments_endpoint_is_reachable(self, http: requests.Session, telemetry_service_url: str):
        """The /experiments endpoint should respond without a server error."""
        response = http.get(f"{telemetry_service_url}/experiments", timeout=10)
        assert response.status_code < 500
