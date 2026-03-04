# Storage Service

**Port**: 8004
**Deliverable**: D3 (Telemetry and Results Storage)
**Priority**: HIGH
**Status**: To be implemented

## Purpose

The Storage Service is the centralized data persistence layer for the Agentic Thin Waist. It provides:

1. **Experiment result storage** — Store ExperimentResult objects with full metadata
2. **Contextual tagging** — Attach ContextualTreeNode to all results
3. **Query interface** — Filter by experiment_id, application, capacity, latency, date
4. **Artifact management** — Store pcap files, workflow artifacts, logs
5. **Data analysis ready** — Export for downstream analysis and visualization

The Storage Service uses SQLAlchemy ORM (PostgreSQL in production, SQLite in development) and exposes a REST query API.

## Architecture

```
┌──────────────────────────────────────┐
│  Experiment API / NetGent / Substrate│
│         Results Input                │
└────────────┬────────────────────────┘
             │ POST /results
             │ POST /artifacts
             ▼
┌────────────────────────────────────┐
│   STORAGE SERVICE (8004)           │
│  ┌──────────────────────────────┐  │
│  │ SQLAlchemy ORM               │  │
│  │ - ExperimentResult table     │  │
│  │ - Artifact table             │  │
│  │ - ContextualTree table       │  │
│  └──────────────────────────────┘  │
└────────────┬──────────────────────┘
             │
      ┌──────┴───────┬──────────┐
      ▼              ▼          ▼
  ┌────────┐  ┌──────────┐  ┌────────────┐
  │SQLite  │  │PostgreSQL│  │File Storage│
  │:memory │  │:5432     │  │/data/      │
  └────────┘  └──────────┘  └────────────┘
```

## API Specification

### 1. Store Experiment Result

**Endpoint**: `POST /results`

**Request**:
```json
{
  "experiment_id": "youtube-10mbps-001",
  "trial_number": 1,
  "status": "success",
  "bottleneck_state": {
    "configured_capacity": 10.0,
    "configured_latency": 50,
    "measured_throughput": 9.8,
    "measured_rtt": 52,
    "verification_passed": true
  },
  "pcap_path": "s3://results/youtube-10mbps-001/trial-1.pcap",
  "qoe_metrics": {
    "video_startup_time_ms": 2500,
    "mean_bitrate_mbps": 8.5,
    "bitrate_changes": 3,
    "rebuffer_events": 1,
    "rebuffer_duration_ms": 2000
  },
  "transport_state": {
    "throughput_mbps": 9.8,
    "rtt_ms": 52,
    "packet_loss": 0.001,
    "retransmissions": 125
  },
  "contextual_tree": {
    "c_static": {
      "capacity_mbps": 10.0,
      "latency_ms": 50,
      "buffer_size": null,
      "aqm_policy": "fifo"
    },
    "c_dyn": {
      "ctp_cluster_id": "ctp-001",
      "measured_throughput": 9.8,
      "measured_rtt": 52
    },
    "c_app": {
      "application": "youtube",
      "workflow_spec": "watch-video-60s"
    },
    "c_trans": {
      "protocol": "tcp",
      "congestion_control": "cubic"
    }
  }
}
```

**Response** (201 Created):
```json
{
  "result_id": "result-abc123",
  "experiment_id": "youtube-10mbps-001",
  "status": "stored",
  "created_at": "2026-03-04T10:00:35Z"
}
```

---

### 2. Query Experiment Results

**Endpoint**: `GET /results`

**Query Parameters**:
- `experiment_id` — Filter by experiment ID (exact match)
- `application` — Filter by application (youtube, netflix, zoom)
- `capacity_min`, `capacity_max` — Filter by capacity range (Mbps)
- `latency_min`, `latency_max` — Filter by latency range (ms)
- `created_after`, `created_before` — Filter by date (ISO 8601)
- `tags` — Filter by comma-separated tags
- `limit` — Max results (default: 50, max: 500)
- `offset` — Pagination offset (default: 0)
- `sort_by` — Sort field (default: created_at)
- `sort_order` — asc or desc (default: desc)

**Example Request**:
```
GET /results?application=youtube&capacity_min=10&capacity_max=25&latency_max=100&limit=20
```

**Response** (200 OK):
```json
{
  "results": [
    {
      "result_id": "result-abc123",
      "experiment_id": "youtube-10mbps-001",
      "application": "youtube",
      "trial_number": 1,
      "created_at": "2026-03-04T10:00:35Z",
      "bottleneck_state": {
        "configured_capacity": 10.0,
        "configured_latency": 50,
        "measured_throughput": 9.8,
        "measured_rtt": 52
      },
      "qoe_metrics": {
        "video_startup_time_ms": 2500,
        "mean_bitrate_mbps": 8.5
      },
      "contextual_tree": {
        "c_static": {"capacity_mbps": 10.0, "latency_ms": 50}
      }
    }
  ],
  "total": 150,
  "limit": 20,
  "offset": 0,
  "returned": 20
}
```

---

### 3. Get Single Result

**Endpoint**: `GET /results/{result_id}`

**Response** (200 OK):
```json
{
  "result_id": "result-abc123",
  "experiment_id": "youtube-10mbps-001",
  "trial_number": 1,
  "status": "success",
  "created_at": "2026-03-04T10:00:35Z",
  "bottleneck_state": {...},
  "qoe_metrics": {...},
  "transport_state": {...},
  "contextual_tree": {...},
  "pcap_path": "s3://results/youtube-10mbps-001/trial-1.pcap"
}
```

---

### 4. Upload Artifact File

**Endpoint**: `POST /artifacts`

**Request** (multipart/form-data):
```
POST /artifacts
Content-Type: multipart/form-data

result_id: "result-abc123"
artifact_type: "pcap"  # or "har", "log", "screenshot"
file: <binary file>
```

**Response** (201 Created):
```json
{
  "artifact_id": "artifact-xyz789",
  "result_id": "result-abc123",
  "artifact_type": "pcap",
  "filename": "youtube-10mbps-001-trial-1.pcap",
  "size_bytes": 3567890,
  "storage_path": "s3://artifacts/result-abc123/pcap/file.pcap",
  "created_at": "2026-03-04T10:00:35Z"
}
```

---

### 5. Download Artifact

**Endpoint**: `GET /artifacts/{artifact_id}`

**Response** (200 OK):
- Binary file content with appropriate Content-Type header
- Supports Range requests for large files

---

### 6. List Artifacts for Result

**Endpoint**: `GET /results/{result_id}/artifacts`

**Response** (200 OK):
```json
{
  "result_id": "result-abc123",
  "artifacts": [
    {
      "artifact_id": "artifact-xyz789",
      "artifact_type": "pcap",
      "filename": "youtube-10mbps-001-trial-1.pcap",
      "size_bytes": 3567890,
      "storage_path": "s3://artifacts/result-abc123/pcap/file.pcap",
      "created_at": "2026-03-04T10:00:35Z"
    },
    {
      "artifact_id": "artifact-abc456",
      "artifact_type": "har",
      "filename": "youtube-workflow.har",
      "size_bytes": 125600,
      "created_at": "2026-03-04T10:00:35Z"
    }
  ]
}
```

---

### 7. Tag Results

**Endpoint**: `POST /results/{result_id}/tags`

**Request**:
```json
{
  "tags": ["high-quality", "production-run", "baseline"]
}
```

**Response** (200 OK):
```json
{
  "result_id": "result-abc123",
  "tags": ["high-quality", "production-run", "baseline"],
  "updated_at": "2026-03-04T10:01:00Z"
}
```

---

### 8. Export Results as CSV

**Endpoint**: `GET /results/export/csv`

**Query Parameters**: (same as /results query)

**Response** (200 OK):
- CSV file with columns: result_id, experiment_id, application, capacity, latency, startup_time, bitrate, ...

---

### 9. Health Check

**Endpoint**: `GET /health`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "database": {
    "type": "postgresql",
    "connected": true,
    "latency_ms": 2
  },
  "storage": {
    "type": "s3",
    "accessible": true
  }
}
```

## Dataclass Contracts

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime

@dataclass
class ExperimentResult:
    """Complete experiment result with all metadata."""
    result_id: str
    experiment_id: str
    trial_number: int
    status: str  # "success", "failure", "timeout"
    bottleneck_state: 'BottleneckState'
    qoe_metrics: Dict[str, Any]
    transport_state: Dict[str, Any]
    contextual_tree: 'ContextualTreeNode'
    pcap_path: Optional[str] = None
    created_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)

@dataclass
class ContextualTreeNode:
    """Rich metadata tagging results."""
    c_static: Dict[str, Any]  # capacity, latency, buffer, aqm
    c_dyn: Dict[str, Any]      # measured network state
    c_app: Dict[str, Any]      # application, workflow
    c_trans: Dict[str, Any]    # protocol, cc algorithm

@dataclass
class BottleneckState:
    """Measured network configuration."""
    configured_capacity: float
    configured_latency: float
    measured_throughput: float
    measured_rtt: float
    verification_passed: bool = True
    packet_loss_percent: float = 0.0

@dataclass
class Artifact:
    """Stored file metadata."""
    artifact_id: str
    result_id: str
    artifact_type: str  # "pcap", "har", "log", "screenshot"
    filename: str
    size_bytes: int
    storage_path: str
    created_at: str

@dataclass
class QueryFilter:
    """Query parameters for filtering results."""
    experiment_id: Optional[str] = None
    application: Optional[str] = None
    capacity_range: Optional[tuple] = None  # (min, max)
    latency_range: Optional[tuple] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    tags: Optional[List[str]] = None
    limit: int = 50
    offset: int = 0
```

## Service Dependencies

None - independent data layer service.

## Database Schema

### results table
```sql
CREATE TABLE results (
    result_id VARCHAR(64) PRIMARY KEY,
    experiment_id VARCHAR(64) NOT NULL,
    trial_number INT NOT NULL,
    application VARCHAR(32),
    status VARCHAR(32),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Bottleneck state
    configured_capacity FLOAT,
    configured_latency FLOAT,
    measured_throughput FLOAT,
    measured_rtt FLOAT,

    -- Metrics (stored as JSON)
    qoe_metrics JSONB,
    transport_state JSONB,
    contextual_tree JSONB,
    pcap_path VARCHAR(512),

    -- Tagging
    tags TEXT[],

    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id),
    INDEX (experiment_id, application, created_at)
);
```

### artifacts table
```sql
CREATE TABLE artifacts (
    artifact_id VARCHAR(64) PRIMARY KEY,
    result_id VARCHAR(64) NOT NULL,
    artifact_type VARCHAR(32),
    filename VARCHAR(256),
    size_bytes BIGINT,
    storage_path VARCHAR(512),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (result_id) REFERENCES results(result_id),
    INDEX (result_id, artifact_type)
);
```

## Testing Criteria

### Unit Tests
- Result creation with valid dataclasses
- Query filter building (date ranges, capacity ranges)
- Result serialization/deserialization

### Integration Tests
- Results stored and retrieved correctly
- Query filters return correct subsets
- Artifacts uploaded and downloaded
- Tag operations work
- Concurrent result uploads don't cause conflicts
- CSV export produces valid files

### Performance Tests
- Store result < 100ms
- Query 1000 results with filters < 500ms
- List artifacts < 200ms
- Artifact upload < 5s (depends on file size)

## Implementation Guide

### Step 1: Database Setup
```bash
# For development (SQLite)
pip install flask-sqlalchemy

# For production (PostgreSQL)
pip install psycopg2-binary
```

### Step 2: SQLAlchemy Models
```python
# app/models.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, JSON

db = SQLAlchemy()

class Result(db.Model):
    __tablename__ = 'results'

    result_id = db.Column(db.String(64), primary_key=True)
    experiment_id = db.Column(db.String(64), nullable=False)
    trial_number = db.Column(db.Integer)
    application = db.Column(db.String(32))
    status = db.Column(db.String(32))

    configured_capacity = db.Column(db.Float)
    configured_latency = db.Column(db.Float)
    measured_throughput = db.Column(db.Float)
    measured_rtt = db.Column(db.Float)

    qoe_metrics = db.Column(JSON)
    transport_state = db.Column(JSON)
    contextual_tree = db.Column(JSON)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_exp_app_date', 'experiment_id', 'application', 'created_at'),
    )

class Artifact(db.Model):
    __tablename__ = 'artifacts'

    artifact_id = db.Column(db.String(64), primary_key=True)
    result_id = db.Column(db.String(64), db.ForeignKey('results.result_id'))
    artifact_type = db.Column(db.String(32))
    filename = db.Column(db.String(256))
    size_bytes = db.Column(db.BigInteger)
    storage_path = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### Step 3: Query Builder
```python
# app/services/query_builder.py
class QueryBuilder:
    def build(self, filters: QueryFilter) -> SQLAlchemy.Query:
        query = Result.query

        if filters.experiment_id:
            query = query.filter_by(experiment_id=filters.experiment_id)

        if filters.application:
            query = query.filter_by(application=filters.application)

        if filters.capacity_range:
            min_cap, max_cap = filters.capacity_range
            query = query.filter(
                Result.configured_capacity.between(min_cap, max_cap)
            )

        if filters.date_from:
            query = query.filter(Result.created_at >= filters.date_from)

        return query.limit(filters.limit).offset(filters.offset)
```

### Step 4: REST API
```python
# app/api/results.py
from flask import Blueprint, request, jsonify
from app.models import Result, db

results_bp = Blueprint('results', __name__)

@results_bp.route('/results', methods=['POST'])
def store_result():
    data = request.get_json()
    result = Result(
        result_id=data['result_id'],
        experiment_id=data['experiment_id'],
        qoe_metrics=data['qoe_metrics'],
        contextual_tree=data['contextual_tree']
    )
    db.session.add(result)
    db.session.commit()
    return jsonify({"result_id": result.result_id}), 201

@results_bp.route('/results', methods=['GET'])
def query_results():
    filters = QueryFilter(
        experiment_id=request.args.get('experiment_id'),
        application=request.args.get('application'),
        limit=int(request.args.get('limit', 50))
    )
    query = QueryBuilder().build(filters)
    results = query.all()
    return jsonify({"results": [r.to_dict() for r in results]}), 200
```

## References

- SQLAlchemy documentation: https://www.sqlalchemy.org/
- PostgreSQL JSON types: https://www.postgresql.org/docs/current/datatype-json.html
- Flask-SQLAlchemy: https://flask-sqlalchemy.palletsprojects.com/
- S3 for artifact storage: https://aws.amazon.com/s3/

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 4)
