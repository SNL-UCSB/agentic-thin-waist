import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import TypeDecorator, Text


class JsonEncodedList(TypeDecorator):
    impl = Text

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


@pytest.fixture(scope="session")
def app():
    with patch("shared.s3.client.S3Client") as mock_s3_class:
        mock_s3_class.return_value = MagicMock()

        from app.telemetry import db as _db

        from flask import Flask

        test_app = Flask(__name__)
        test_app.config["TESTING"] = True
        test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        test_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        _db.init_app(test_app)

        from app.telemetry import routes, commands

        test_app.register_blueprint(routes.routes_bp)
        test_app.register_blueprint(commands.commands_bp)

        with test_app.app_context():
            from app.telemetry import models
            from sqlalchemy import JSON

            models.Result.qoe_metrics.property.columns[0].type = JSON()
            models.Result.transport_state.property.columns[0].type = JSON()
            models.Result.contextual_tree.property.columns[0].type = JSON()
            models.Result.tags.property.columns[0].type = JsonEncodedList()
            models.Orchestration.payload.property.columns[0].type = JSON()

            _db.create_all()
            yield test_app
            _db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def db(app):
    from app.telemetry import db as _db

    with app.app_context():
        yield _db
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture
def mock_s3(app):
    with app.app_context():
        import app.telemetry.routes as r

        mock = MagicMock()
        r.s3 = mock
        yield mock


@pytest.fixture
def sample_result_payload():
    return {
        "experiment_id": "youtube-10mbps-001",
        "trial_number": 1,
        "status": "success",
        "bottleneck_state": {
            "configured_capacity": 10.0,
            "configured_latency": 50.0,
            "measured_throughput": 9.8,
            "measured_rtt": 52.0,
        },
        "pcap_path": "s3://bucket/trial-1.pcap",
        "qoe_metrics": {
            "video_startup_time_ms": 2500,
            "mean_bitrate_mbps": 8.5,
            "bitrate_changes": 3,
            "rebuffer_events": 1,
            "rebuffer_duration_ms": 2000,
        },
        "transport_state": {
            "throughput_mbps": 9.8,
            "rtt_ms": 52,
            "packet_loss": 0.001,
        },
        "contextual_tree": {
            "c_static": {"capacity_mbps": 10.0, "latency_ms": 50, "aqm_policy": "fifo"},
            "c_dyn": {"ctp_cluster_id": "ctp-001", "measured_throughput": 9.8},
            "c_app": {"application": "youtube", "workflow_spec": "watch-video-60s"},
            "c_trans": {"protocol": "tcp", "congestion_control": "cubic"},
        },
    }


@pytest.fixture
def persisted_result(client, db, sample_result_payload):
    resp = client.post("/results", json=sample_result_payload)
    assert resp.status_code == 201
    return resp.get_json()
