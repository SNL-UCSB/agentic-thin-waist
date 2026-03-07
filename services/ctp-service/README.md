# CTP Service

**Port**: 8001
**Deliverable**: D1 (Network Virtualization Substrate - Representation Plane)
**Lead**: Jaber | **Supporting**: Satyam, Snithik
**PI**: Prof. Arpit Gupta
**Priority**: CRITICAL
**Status**: Active Development

## Purpose

The CTP (Cross-Traffic Profile) Service is the **Representation Plane** of the bottleneck in the Agentic Thin Waist architecture. It transforms passive packet traces from production networks into reusable, composable representations of dynamic congestion pressure—enabling systematic experimentation with realistic traffic conditions without binding to specific paths, applications, or users.

A CTP is a reusable representation of dynamic congestion pressure applied at a bottleneck, encoding temporal structure of aggregate demand (intensity, burstiness, heterogeneity, temporal correlations) without binding to particular paths, applications, or users that produced it.

## Input

CTP Service accepts:
- Packet traces (PCAP files) from production networks
- CTP selection queries by statistical descriptors (intensity, burstiness, temporal correlation, contributor structure)
- CTP transformation parameters (target capacity, scale factor)
- CTP merge specifications (weighted composition of multiple CTPs)

## Output

CTP Service produces:
- Cross-Traffic Profiles (CTPs) with statistical descriptors: intensity (packets/sec, bits/sec), burstiness (PMR, CoV), temporal correlation, structural properties
- Transformed CTPs adapted to target bottleneck capacity while preserving temporal structure
- Merged CTPs from weighted composition of multiple profiles
- Replay-ready packet data (PCAP format) for handoff to Substrate Worker

## Interfaces

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ctps/extract` | POST | Parse PCAP traces into CTP representations |
| `/ctps/select` | POST | Query corpus by statistical descriptors |
| `/ctps/transform` | POST | Rescale CTP amplitude to target capacity |
| `/ctps/merge` | POST | Compose multiple CTPs with weights |
| `/ctps/{id}/replay-data` | GET | Export CTP as replay-ready PCAP for Substrate Worker |
| `/ctps/{id}` | GET | Get full CTP details and descriptors |
| `/ctps` | GET | List CTPs with pagination |
| `/health` | GET | Service health and PostgreSQL connectivity |

## YouTube MVP Example

For YouTube at 10/25/50 Mbps:
- extract() processes campus trace to identify realistic background traffic CTPs
- select() retrieves CTPs matching intensity ranges for each capacity (low for 10Mbps, high for 50Mbps)
- transform() adapts selected CTP to each target capacity: scale factors 0.5×, 1.0×, 2.0× while preserving burst timing
- CTP Service prepares replay-ready PCAP data; Substrate Worker handles actual replay on the wire
- Success criteria: 3 transformed CTPs ready with replay-ready PCAP exports available for Substrate Worker

## Core Concepts

### Cross-Traffic Profile (CTP)

A CTP is an extracted, indexed representation of demand pressure that:
- **Captures temporal structure** of aggregate traffic (intensity, burstiness, heterogeneity, temporal correlation)
- **Encodes contributor composition** (host-level aggregates, prefix-based hierarchy, upload-download asymmetry)
- **Operates independently** of the specific paths, applications, or users that generated it
- **Enables systematic experimentation** with realistic, reproducible network conditions

### CTP Indexing

NetForge indexes CTPs using multi-dimensional statistical descriptors:

**Temporal Attributes**:
- Intensity: Mean traffic rate (packets/sec or bytes/sec)
- Burstiness: Peak-to-Mean Ratio (PMR) and Coefficient of Variation (CoV)
- Temporal Correlation: Autocorrelation at multiple lags

**Structural Attributes**:
- Contributor Count: Number of unique host pairs generating demand
- Upload-Download Asymmetry: Ratio of upstream to downstream traffic volume
- Prefix Diversity: Spatial heterogeneity via prefix-based aggregation trees

All CTPs are indexed in PostgreSQL to enable multi-dimensional queries for selection and retrieval.

### CTP Corpus

The NetForge prototype ingests packet traces from production vantage points. For the campus gateway (48k users, 8.2 Gbps peak), 15-minute intervals yielded approximately 230k CTPs after filtering. Each CTP groups packets into bidirectional host-level contributors, aggregated into prefix-based trees that preserve spatial locality, heterogeneity, asymmetry, and traffic composition.

## Architecture

```
┌────────────────────────────────────┐
│   Experiment Controller (Port 8000) │
│   or External Research Client       │
└────────────┬─────────────────────────┘
             │
             │ Orchestrates CTP operations
             │
             ▼
┌────────────────────────────────────┐
│   CTP SERVICE (Port 8001)           │
│  ┌──────────────────────────────┐  │
│  │ CTP Operations Engine        │  │
│  │                              │  │
│  │ • extract() — traces → CTPs  │  │
│  │ • select() — query by attrs  │  │
│  │ • transform() — adapt CTP    │  │
│  │ • merge() — compose CTPs     │  │
│  │                              │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ CTP Index & Storage          │  │
│  │ PostgreSQL with statistical  │  │
│  │ descriptors & metadata       │  │
│  └──────────────────────────────┘  │
└────────────┬─────────────────────────┘
             │
             │ Replay-ready PCAP data
             │ (handed to Substrate Worker
             │  for actual replay)
             │
             ▼
        ┌────────────────────┐
        │ Substrate Worker   │
        │ :8002              │
        │ Handles tcpreplay  │
        └────────────────────┘
```

## CTP Operations

The CTP Service provides four core operations (from NetForge paper):

### 1. extract() — Process Packet Traces into CTPs

Ingests raw PCAP/packet traces and extracts reusable CTP representations.

**Endpoint**: `POST /ctps/extract`

**Request**:
```json
{
  "trace_file": "gateway-2026-03-04-14h-15m.pcap",
  "interval_seconds": 60,
  "filter_min_packets": 100,
  "aggregation_level": "host"
}
```

**Response** (200 OK):
```json
{
  "ctp_count": 15,
  "extraction_status": "success",
  "ctps": [
    {
      "ctp_id": "ctp-20260304-001",
      "start_time": "2026-03-04T14:00:00Z",
      "duration_seconds": 60,
      "intensity": {
        "mean_pps": 45230,
        "mean_bps": 2.7e9
      },
      "burstiness": {
        "peak_to_mean_ratio": 3.2,
        "coefficient_of_variation": 0.84
      },
      "temporal_correlation": {
        "lag_1_autocorr": 0.62,
        "lag_5_autocorr": 0.41
      },
      "structure": {
        "contributor_count": 847,
        "upload_download_ratio": 0.23,
        "prefix_diversity": 0.78
      },
      "stored_at": "postgresql:ctp_corpus"
    }
  ],
  "filtering_notes": "Removed 3 intervals with < 100 packets"
}
```

### 2. select() — Query CTPs by Statistical Descriptors

Retrieve CTPs from the corpus matching specific congestion profiles.

**Endpoint**: `POST /ctps/select`

**Request**:
```json
{
  "query": {
    "intensity_range_mbps": [1000, 3000],
    "burstiness_pmr_range": [2.0, 4.0],
    "temporal_correlation_min": 0.4,
    "contributor_count_min": 500,
    "upload_download_ratio_max": 0.5
  },
  "limit": 10,
  "order_by": "intensity"
}
```

**Response** (200 OK):
```json
{
  "query_matched": 347,
  "results_returned": 10,
  "ctps": [
    {
      "ctp_id": "ctp-20260304-042",
      "intensity_mbps": 2150,
      "burstiness_pmr": 3.1,
      "temporal_correlation": 0.52,
      "contributor_count": 612,
      "upload_download_ratio": 0.31
    }
  ]
}
```

### 3. transform() — Rescale CTP to Target Bottleneck

Adapt a CTP's amplitude to match target capacity while preserving burst timing and structure.

**Endpoint**: `POST /ctps/transform`

**Request**:
```json
{
  "ctp_id": "ctp-20260304-042",
  "target_capacity_mbps": 1000,
  "preserve_structure": true
}
```

**Response** (200 OK):
```json
{
  "original_ctp_id": "ctp-20260304-042",
  "transformed_ctp_id": "ctp-transform-20260304-042-1000mbps",
  "original_intensity_mbps": 2150,
  "target_capacity_mbps": 1000,
  "scale_factor": 0.465,
  "preserved_attributes": {
    "burstiness_pmr": 3.1,
    "temporal_correlation": 0.52,
    "contributor_structure": "unchanged"
  },
  "notes": "Intensity rescaled; temporal structure and asymmetry preserved"
}
```

### 4. merge() — Compose Multiple CTPs

Systematically combine multiple CTPs to control dynamic pressure, creating synthetic workload compositions.

**Endpoint**: `POST /ctps/merge`

**Request**:
```json
{
  "ctp_ids": [
    "ctp-20260304-042",
    "ctp-20260304-127",
    "ctp-20260304-089"
  ],
  "weights": [0.5, 0.3, 0.2],
  "merge_strategy": "weighted_sum"
}
```

**Response** (200 OK):
```json
{
  "merged_ctp_id": "ctp-merge-20260304-composite-001",
  "source_ctps": 3,
  "weights": [0.5, 0.3, 0.2],
  "merged_properties": {
    "intensity_mbps": 1845,
    "burstiness_pmr": 3.0,
    "temporal_correlation": 0.48,
    "contributor_count_effective": 1120
  },
  "notes": "Merged CTP suitable for multi-tenant scenarios"
}
```

## API Reference

### General Health Check

**Endpoint**: `GET /health`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service_version": "1.0.0",
  "postgresql_connected": true,
  "kernel_version": "6.8.0-94-generic"
}
```

### List CTPs (Query Corpus)

**Endpoint**: `GET /ctps`

**Query Parameters**:
- `limit`: Max results (default: 50)
- `offset`: Pagination offset (default: 0)
- `order_by`: intensity, burstiness, contributor_count (default: intensity)

**Response** (200 OK):
```json
{
  "total": 230000,
  "returned": 50,
  "ctps": [
    {
      "ctp_id": "ctp-20260304-001",
      "intensity_mbps": 2150,
      "burstiness_pmr": 3.1,
      "temporal_correlation": 0.52,
      "contributor_count": 612,
      "upload_download_ratio": 0.31,
      "created_at": "2026-03-04T14:00:00Z"
    }
  ]
}
```

### Get CTP Details

**Endpoint**: `GET /ctps/{ctp_id}`

**Response** (200 OK):
```json
{
  "ctp_id": "ctp-20260304-042",
  "metadata": {
    "extracted_from": "gateway-2026-03-04-14h-15m.pcap",
    "start_time": "2026-03-04T14:00:00Z",
    "duration_seconds": 60,
    "interval_index": 3
  },
  "intensity": {
    "mean_pps": 45230,
    "mean_bps": 2.7e9,
    "mean_mbps": 2150
  },
  "burstiness": {
    "peak_pps": 144380,
    "peak_to_mean_ratio": 3.2,
    "coefficient_of_variation": 0.84
  },
  "temporal_correlation": {
    "lag_1": 0.62,
    "lag_5": 0.41,
    "lag_10": 0.28
  },
  "structure": {
    "contributor_count": 847,
    "unique_src_ip": 412,
    "unique_dst_ip": 835,
    "upload_download_ratio": 0.23,
    "prefix_diversity": 0.78
  },
  "distribution": {
    "packet_size_mean": 612,
    "packet_size_stdev": 284
  }
}
```

## Data Models

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class CTPIntensity:
    """Traffic intensity metrics."""
    mean_pps: float          # packets per second
    mean_bps: float          # bits per second
    peak_pps: float          # peak rate
    peak_bps: float

@dataclass
class CTPBurstiness:
    """Burstiness metrics."""
    peak_to_mean_ratio: float      # PMR
    coefficient_of_variation: float # CoV
    max_burst_size_packets: int

@dataclass
class CTPTemporalCorrelation:
    """Temporal correlation at multiple lags."""
    lag_1: float
    lag_5: float
    lag_10: float
    lag_60: Optional[float] = None

@dataclass
class CTPStructure:
    """Structural properties of contributor composition."""
    contributor_count: int
    unique_source_ips: int
    unique_dest_ips: int
    upload_download_ratio: float    # asymmetry metric
    prefix_diversity: float         # spatial locality

@dataclass
class CrossTrafficProfile:
    """Complete CTP representation."""
    ctp_id: str
    extracted_from: str              # PCAP source
    start_time: datetime
    duration_seconds: int
    intensity: CTPIntensity
    burstiness: CTPBurstiness
    temporal_correlation: CTPTemporalCorrelation
    structure: CTPStructure
    created_at: datetime

    def to_pcap_export(self) -> bytes:
        """Generate replay-ready PCAP data for Substrate Worker."""
        pass
```

## Service Dependencies

**External Dependencies**:
- **PostgreSQL**: CTP corpus storage and multi-dimensional indexing (must support JSON queries on statistical descriptors)
- **scapy** (optional): For generating replay-ready PCAP files from CTP descriptors

**Other Services**:
- Experiment Controller (Port 8000): Orchestrates CTP selections and replay sessions
- No internal dependencies on other D1 services (standalone representation plane)

## Testing Criteria

> **Unit tests for this service live in `services/ctp-service/tests/`.** Run them with `pytest services/ctp-service/tests/ -v`.

### Unit Tests
- **Extraction**: Verify PCAP parsing, packet aggregation into CTPs, statistical computation
- **Selection**: Query by all descriptor types (intensity, burstiness, temporal_correlation, structure)
- **Transform**: Validate amplitude scaling while preserving temporal structure and asymmetry
- **Merge**: Weighted CTP composition produces correct aggregate descriptors
- **Export**: Replay-ready PCAP generation from CTP descriptors for Substrate Worker handoff
- **Indexing**: PostgreSQL schema, multi-dimensional range queries, JSON descriptor storage

### Integration Tests
- **End-to-end extraction**: PCAP ingestion → CTP storage → query retrieval (realistic 48k-user traces)
- **Transform fidelity**: Scale CTP to different bottleneck capacities; verify burst timing preserved
- **PCAP export**: Generated replay-ready PCAP matches CTP intensity and temporal structure
- **Corpus scale**: Performance with 230k CTPs (campus gateway corpus size)

### Performance Tests
- CTP extraction: < 5 seconds per 15-minute interval (48k users)
- Selection query: < 100ms for range queries on 230k CTPs (PostgreSQL B-tree)
- Transform: < 50ms amplitude rescaling
- Merge: < 100ms for 3-CTP weighted composition
- PCAP export: < 2 seconds to generate replay-ready PCAP from CTP descriptors
- Corpus query: < 500ms for multi-dimensional descriptor queries

## Implementation Architecture

### Directory Structure
```bash
services/ctp-service/
├── Dockerfile
├── requirements.txt
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app + endpoints
│   ├── models/
│   │   ├── __init__.py
│   │   ├── ctp.py                 # CTP dataclasses
│   │   └── descriptors.py         # Statistical descriptors
│   ├── database/
│   │   ├── __init__.py
│   │   ├── postgres.py            # PostgreSQL connection
│   │   └── migrations/            # Alembic schema migrations
│   ├── operations/
│   │   ├── __init__.py
│   │   ├── extract.py             # PCAP → CTP extraction
│   │   ├── select.py              # Multi-dimensional query
│   │   ├── transform.py           # CTP amplitude scaling
│   │   ├── merge.py               # CTP composition
│   │   └── export.py              # Replay-ready PCAP generation
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py              # Endpoint handlers
│   └── utils/
│       ├── __init__.py
│       └── logging.py
└── tests/
    ├── __init__.py
    ├── conftest.py                # pytest fixtures
    ├── test_extract.py
    ├── test_select.py
    ├── test_transform.py
    ├── test_merge.py
    ├── test_replay.py
    └── data/                       # Test PCAP files
```

### Key Modules

#### 1. Extract Operation (app/operations/extract.py)
```python
class CTPExtractor:
    """Transform PCAP traces into CTP representations."""

    def extract_from_pcap(
        self,
        pcap_file: str,
        interval_seconds: int = 60,
        min_packets: int = 100
    ) -> List[CrossTrafficProfile]:
        """
        1. Read PCAP packets
        2. Aggregate into bidirectional host-level contributors
        3. Build prefix-based hierarchical trees
        4. Compute statistical descriptors:
           - Intensity: mean_pps, mean_bps, peak rates
           - Burstiness: PMR, CoV at multiple timescales
           - Temporal correlation: lag-1, lag-5, lag-10 autocorrelation
           - Structure: contributor count, asymmetry, prefix diversity
        5. Store in PostgreSQL
        6. Return CTP list
        """
        pass

    def _compute_intensity(self, packets: List[Packet]) -> CTPIntensity:
        """Calculate mean/peak packet and bit rates."""
        pass

    def _compute_burstiness(self, timeseries: np.ndarray) -> CTPBurstiness:
        """PMR and CoV at 10ms, 100ms, 1s windows."""
        pass

    def _compute_temporal_correlation(self, timeseries: np.ndarray) -> CTPTemporalCorrelation:
        """Autocorrelation at lags 1, 5, 10, 60."""
        pass

    def _compute_structure(self, contributors: Dict) -> CTPStructure:
        """Contributor composition metrics."""
        pass
```

#### 2. Select Operation (app/operations/select.py)
```python
class CTPSelector:
    """Query CTP corpus by multi-dimensional descriptors."""

    def select(self, query: Dict) -> List[CrossTrafficProfile]:
        """
        Multi-dimensional range queries on:
        - intensity_range_mbps: [min, max]
        - burstiness_pmr_range: [min, max]
        - temporal_correlation_min: threshold
        - contributor_count_min/max: range
        - upload_download_ratio_max: threshold

        Uses PostgreSQL B-tree indexes on JSON descriptor columns.
        """
        sql = self._build_query(query)
        results = self.db.execute(sql)
        return [CrossTrafficProfile.from_db(row) for row in results]

    def _build_query(self, query: Dict) -> str:
        """Construct parameterized SQL with bounds checking."""
        pass
```

#### 3. Transform Operation (app/operations/transform.py)
```python
class CTPTransformer:
    """Rescale CTP amplitude while preserving temporal structure."""

    def transform(
        self,
        ctp_id: str,
        target_capacity_mbps: float
    ) -> CrossTrafficProfile:
        """
        1. Load original CTP
        2. Calculate scale factor: target / original intensity
        3. Rescale packet rates (intensity)
        4. Preserve:
           - Burst timing and shape (burstiness PMR, CoV)
           - Temporal correlations
           - Contributor structure and asymmetry
        5. Store transformed CTP
        6. Return new CTP
        """
        original = self.db.get_ctp(ctp_id)
        scale = target_capacity_mbps / original.intensity.mean_mbps

        transformed = CrossTrafficProfile(
            ctp_id=f"ctp-transform-{ctp_id}-{target_capacity_mbps}mbps",
            intensity=CTPIntensity(
                mean_pps=original.intensity.mean_pps * scale,
                mean_bps=original.intensity.mean_bps * scale,
                peak_pps=original.intensity.peak_pps * scale,
                peak_bps=original.intensity.peak_bps * scale
            ),
            # Preserve other attributes
            burstiness=original.burstiness,
            temporal_correlation=original.temporal_correlation,
            structure=original.structure
        )
        self.db.store_ctp(transformed)
        return transformed
```

#### 4. Merge Operation (app/operations/merge.py)
```python
class CTPMerger:
    """Compose multiple CTPs with weights."""

    def merge(
        self,
        ctp_ids: List[str],
        weights: List[float]
    ) -> CrossTrafficProfile:
        """
        Weighted CTP composition:
        1. Load all CTPs
        2. Normalize weights
        3. Compute weighted aggregate:
           - Intensity: sum(weight_i * intensity_i)
           - Burstiness: weighted blend (preserve shape)
           - Structure: effective contributor count
        4. Store merged CTP
        5. Return composite CTP
        """
        ctps = [self.db.get_ctp(cid) for cid in ctp_ids]
        assert len(weights) == len(ctps)
        assert abs(sum(weights) - 1.0) < 1e-6

        merged_intensity = sum(w * ctp.intensity.mean_mbps for w, ctp in zip(weights, ctps))
        # ... compute other attributes

        merged = CrossTrafficProfile(
            ctp_id=f"ctp-merge-{timestamp}-composite",
            intensity=CTPIntensity(mean_mbps=merged_intensity, ...),
            # ...
        )
        self.db.store_ctp(merged)
        return merged
```

#### 5. Export Operation (app/operations/export.py)
```python
class CTPExporter:
    """Generate replay-ready PCAP files from CTP descriptors for Substrate Worker."""

    def export_replay_pcap(
        self,
        ctp_id: str,
        target_rate_mbps: float = None
    ) -> str:
        """
        Generate a replay-ready PCAP file from CTP descriptors.

        1. Load CTP from corpus
        2. Reconstruct packet timing from temporal descriptors
        3. Generate synthetic packets matching CTP intensity and structure
        4. Write PCAP file suitable for tcpreplay by Substrate Worker
        5. Return file path

        The Substrate Worker uses this PCAP with tcpreplay
        to apply the CTP at the bottleneck interface.
        """
        pass
```

### PostgreSQL Schema (Simplified)
```sql
CREATE TABLE ctps (
    ctp_id TEXT PRIMARY KEY,
    extracted_from TEXT,
    start_time TIMESTAMP,
    duration_seconds INT,

    -- Statistical descriptors (JSON for flexibility)
    intensity JSONB,              -- {mean_pps, mean_bps, peak_pps, peak_bps}
    burstiness JSONB,             -- {pmr, cov, max_burst}
    temporal_correlation JSONB,   -- {lag_1, lag_5, lag_10, lag_60}
    structure JSONB,              -- {contributors, src_ips, dst_ips, asymmetry, diversity}

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient multi-dimensional queries
CREATE INDEX idx_ctps_intensity_mean ON ctps USING BTREE ((intensity->>'mean_mbps')::FLOAT);
CREATE INDEX idx_ctps_burstiness_pmr ON ctps USING BTREE ((burstiness->>'pmr')::FLOAT);
CREATE INDEX idx_ctps_contributors ON ctps USING BTREE ((structure->>'contributor_count')::INT);
CREATE INDEX idx_ctps_temporal_corr ON ctps USING BTREE ((temporal_correlation->>'lag_1')::FLOAT);
```

### Example Test: Transform Preserves Structure
```python
def test_transform_preserves_structure():
    """Verify amplitude scaling doesn't change temporal properties."""
    extractor = CTPExtractor()
    original = extractor.extract_from_pcap("test.pcap")[0]

    transformer = CTPTransformer()
    transformed = transformer.transform(original.ctp_id, 1000)

    # Intensity scales proportionally
    assert abs(transformed.intensity.mean_mbps / original.intensity.mean_mbps - 2.0) < 0.01

    # Burstiness metrics preserved
    assert transformed.burstiness.peak_to_mean_ratio == original.burstiness.peak_to_mean_ratio
    assert transformed.burstiness.coefficient_of_variation == original.burstiness.coefficient_of_variation

    # Structure unchanged
    assert transformed.structure.contributor_count == original.structure.contributor_count
    assert transformed.structure.upload_download_ratio == original.structure.upload_download_ratio
```

## Deployment & Operations

### Environment Variables
```bash
CTP_DATABASE_URL=postgresql://user:pass@localhost:5432/ctp_corpus
CTP_PORT=8001
CTP_HOST=0.0.0.0
CTP_LOG_LEVEL=INFO
CTP_CORPUS_SIZE=230000        # Expected corpus size (campus gateway)
CTP_EXTRACT_BATCH_SIZE=1000   # PCAP processing batch size
```

### Running the Service
```bash
# Start with dependencies
docker-compose up postgres ctp-service

# Manual startup
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# Load CTP corpus (one-time)
python scripts/ingest_corpus.py /path/to/pcap/traces/

# Query examples
curl -X POST http://localhost:8001/ctps/select \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "intensity_range_mbps": [1000, 3000],
      "burstiness_pmr_range": [2.0, 4.0]
    },
    "limit": 20
  }'
```

### Monitoring
- Prometheus metrics: `/metrics` (operation latencies, query counts, PostgreSQL connection pool)
- Structured logs: JSON format with trace IDs for correlating requests
- Health check: `GET /health` returns database connectivity, corpus stats

## References

**NetForge Paper** (Section 3.4 - TRACE–CONTEXT DISAGGREGATION):
- Describes CTP extraction, indexing, and composition model
- Campus gateway corpus: 48k users, 8.2 Gbps peak, 230k CTPs from 15-min intervals
- Hierarchical demand representation with prefix-based trees

**Related Systems**:
- NetReplica: Private SNL-UCSB repository
- Containernet: Network emulation with containers

---

**Last Updated**: 2026-03-04
**Status**: Active Development
**Team Lead**: Jaber
**PI**: Prof. Arpit Gupta
**Repository**: agentic-thin-waist/services/ctp-service
