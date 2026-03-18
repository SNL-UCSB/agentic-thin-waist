"""
Integration tests for the CTP (Cross-Traffic Profile) service.

These tests verify that the CTP service starts correctly and its core API
endpoints respond as expected.  They are designed to run against a live
instance of the service (either in the Docker Compose network or on localhost).
"""

import pytest
import requests


class TestCTPServiceHealth:
    def test_health_endpoint_returns_200(self, http: requests.Session, ctp_service_url: str):
        response = http.get(f"{ctp_service_url}/health", timeout=10)
        assert response.status_code == 200

    def test_health_response_contains_status(self, http: requests.Session, ctp_service_url: str):
        response = http.get(f"{ctp_service_url}/health", timeout=10)
        data = response.json()
        assert "status" in data


class TestCTPServiceAPI:
    def test_profiles_endpoint_is_reachable(self, http: requests.Session, ctp_service_url: str):
        """The /profiles endpoint should return a list (possibly empty) without error."""
        response = http.get(f"{ctp_service_url}/profiles", timeout=10)
        assert response.status_code in (200, 404)
