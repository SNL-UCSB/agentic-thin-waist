from app.telemetry import db

from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy import Index, String
from datetime import datetime


class Result(db.Model):
    __tablename__ = "results"

    result_id = db.Column(db.String(64), primary_key=True)
    experiment_id = db.Column(db.String(64), nullable=False)
    trial_number = db.Column(db.Integer, nullable=False)
    application = db.Column(db.String(32))
    status = db.Column(db.String(32))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    configured_capacity = db.Column(db.Float)
    configured_latency = db.Column(db.Float)
    measured_throughput = db.Column(db.Float)
    measured_rtt = db.Column(db.Float)

    qoe_metrics = db.Column(JSONB)
    transport_state = db.Column(JSONB)
    contextual_tree = db.Column(JSONB)

    pcap_path = db.Column(db.String(512))

    tags = db.Column(ARRAY(String))

    artifacts = db.relationship("Artifact", backref="result", lazy=True)

    __table_args__ = (
        Index("idx_exp_app_date", "experiment_id", "application", "created_at"),
    )

    def to_dict(self):
        return {
            "result_id": self.result_id,
            "experiment_id": self.experiment_id,
            "trial_number": self.trial_number,
            "application": self.application,
            "status": self.status,
            "created_at": (
                self.created_at.isoformat() + "Z" if self.created_at else None
            ),
            "configured_capacity": self.configured_capacity,
            "configured_latency": self.configured_latency,
            "measured_throughput": self.measured_throughput,
            "measured_rtt": self.measured_rtt,
            "qoe_metrics": self.qoe_metrics,
            "transport_state": self.transport_state,
            "contextual_tree": self.contextual_tree,
            "pcap_path": self.pcap_path,
            "tags": self.tags or [],
        }


class Orchestration(db.Model):
    __tablename__ = "orchestrations"

    orchestration_id = db.Column(db.String(64), primary_key=True)
    status = db.Column(db.String(32), nullable=False, default="pending")
    payload = db.Column(JSONB, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        data = dict(self.payload or {})
        data["orchestration_id"] = self.orchestration_id
        data["status"] = self.status
        return data


class Artifact(db.Model):
    __tablename__ = "artifacts"

    artifact_id = db.Column(db.String(64), primary_key=True)
    result_id = db.Column(
        db.String(64), db.ForeignKey("results.result_id"), nullable=False
    )
    artifact_type = db.Column(db.String(32))
    filename = db.Column(db.String(256))
    size_bytes = db.Column(db.BigInteger)
    storage_path = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_artifact_result_type", "result_id", "artifact_type"),)

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "result_id": self.result_id,
            "artifact_type": self.artifact_type,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "storage_path": self.storage_path,
            "created_at": (
                self.created_at.isoformat() + "Z" if self.created_at else None
            ),
        }
