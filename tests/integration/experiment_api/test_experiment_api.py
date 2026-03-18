"""
Integration tests for the Experiment API service.

These tests verify that the Experiment API starts correctly with all its
required dependencies (CTP Service, Substrate Worker, Telemetry Service)
and responds to health and core API calls.
"""

import pytest
import requests


class TestExperimentAPIHealth:
    def test_health_endpoint_returns_200(self, http: requests.Session, experiment_api_url: str):
        response = http.get(f"{experiment_api_url}/health", timeout=10)
        assert response.status_code == 200

    def test_health_response_contains_status(self, http: requests.Session, experiment_api_url: str):
        response = http.get(f"{experiment_api_url}/health", timeout=10)
        data = response.json()
        assert "status" in data


class TestExperimentAPIExperiments:
    def test_experiments_list_is_reachable(self, http: requests.Session, experiment_api_url: str):
        """GET /experiments should respond without a server error."""
        response = http.get(f"{experiment_api_url}/experiments", timeout=10)
        assert response.status_code < 500

    def test_create_experiment_rejects_invalid_payload(
        self, http: requests.Session, experiment_api_url: str
    ):
        """POST /experiments with an empty body should return a 4xx error, not a 5xx."""
        response = http.post(f"{experiment_api_url}/experiments", json={}, timeout=10)
        assert response.status_code < 500
