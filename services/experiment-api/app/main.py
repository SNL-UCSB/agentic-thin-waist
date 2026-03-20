from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, request


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    experiments: dict[str, dict[str, Any]] = {}

    @app.get("/health")
    def health():
        return jsonify({"status": "healthy", "checks": {}})

    @app.get("/status")
    def status():
        return jsonify(
            {
                "status": "healthy",
                "services": {
                    "ctp_service": os.environ.get("CTP_SERVICE_URL"),
                    "substrate_worker": os.environ.get("SUBSTRATE_WORKER_URL"),
                    "netgent_service": os.environ.get("NETGENT_SERVICE_URL"),
                    "telemetry_service": os.environ.get("TELEMETRY_SERVICE_URL"),
                },
                "experiments_total": len(experiments),
            }
        )

    @app.get("/experiments")
    def list_experiments():
        return jsonify(list(experiments.values()))

    @app.post("/experiments")
    def create_experiment():
        payload = request.get_json(silent=True) or {}
        experiment_id = payload.get("experiment_id")
        if not experiment_id:
            return jsonify({"error": "experiment_id is required"}), 400
        if experiment_id in experiments:
            return jsonify({"error": "experiment_id already exists"}), 409

        record = {
            "experiment_id": experiment_id,
            "status": "pending",
            "spec": payload,
        }
        experiments[experiment_id] = record
        return jsonify(record), 201

    @app.get("/experiments/<experiment_id>")
    def get_experiment(experiment_id: str):
        record = experiments.get(experiment_id)
        if record is None:
            return jsonify({"error": "experiment not found"}), 404
        return jsonify(record)

    return app


app = create_app()
