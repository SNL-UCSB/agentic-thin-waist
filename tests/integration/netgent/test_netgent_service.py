"""
Integration tests for the NetGent service.

These tests verify that the NetGent service starts correctly with its
Substrate Worker and Telemetry Service dependencies available.
"""

import pytest
import requests


class TestNetgentServiceHealth:
    def test_health_endpoint_returns_200(self, http: requests.Session, netgent_service_url: str):
        response = http.get(f"{netgent_service_url}/health", timeout=10)
        assert response.status_code == 200

    def test_health_response_contains_status(self, http: requests.Session, netgent_service_url: str):
        response = http.get(f"{netgent_service_url}/health", timeout=10)
        data = response.json()
        assert "status" in data


class TestNetgentServiceAPI:
    def test_workflows_endpoint_is_reachable(self, http: requests.Session, netgent_service_url: str):
        """The /workflows endpoint should respond without a server error."""
        response = http.get(f"{netgent_service_url}/workflows", timeout=10)
        assert response.status_code < 500

    def test_agents_endpoint_is_reachable(self, http: requests.Session, netgent_service_url: str):
        """The /agents endpoint should respond without a server error."""
        response = http.get(f"{netgent_service_url}/agents", timeout=10)
        assert response.status_code < 500
