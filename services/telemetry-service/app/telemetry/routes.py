import csv
import io
import uuid
from datetime import datetime

from app.telemetry import db, models, s3
from flask import Blueprint, request, jsonify, make_response

routes_bp = Blueprint("routes", __name__)


def _build_result_query(args):
    query = models.Result.query

    if experiment_id := args.get("experiment_id"):
        query = query.filter(models.Result.experiment_id == experiment_id)
    if application := args.get("application"):
        query = query.filter(models.Result.application == application)
    if capacity_min := args.get("capacity_min"):
        query = query.filter(models.Result.configured_capacity >= float(capacity_min))
    if capacity_max := args.get("capacity_max"):
        query = query.filter(models.Result.configured_capacity <= float(capacity_max))
    if latency_min := args.get("latency_min"):
        query = query.filter(models.Result.configured_latency >= float(latency_min))
    if latency_max := args.get("latency_max"):
        query = query.filter(models.Result.configured_latency <= float(latency_max))
    if congestion_control := args.get("congestion_control"):
        query = query.filter(
            models.Result.contextual_tree["c_trans"]["congestion_control"].astext
            == congestion_control
        )
    if created_after := args.get("created_after"):
        query = query.filter(
            models.Result.created_at >= datetime.fromisoformat(created_after)
        )
    if created_before := args.get("created_before"):
        query = query.filter(
            models.Result.created_at <= datetime.fromisoformat(created_before)
        )
    if tags := args.get("tags"):
        query = query.filter(models.Result.tags.contains(tags.split(",")))

    return query


@routes_bp.route("/health", methods=["GET"])
def healthcheck():
    return jsonify({"message": "Success"}), 200


@routes_bp.route("/results", methods=["POST"])
def add_results():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON payload, expected an object"}), 400

    # Basic validation for required fields
    errors = {}
    experiment_id = data.get("experiment_id")
    if experiment_id is None:
        errors["experiment_id"] = "experiment_id is required"
    status = data.get("status")
    if status is None:
        errors["status"] = "status is required"

    if errors:
        return jsonify({"error": "Invalid request", "details": errors}), 400

    bottleneck = data.get("bottleneck_state", {})
    contextual_tree = data.get("contextual_tree", {})
    c_app = contextual_tree.get("c_app", {})

    result = models.Result(
        result_id=str(uuid.uuid4()),
        experiment_id=experiment_id,
        trial_number=data.get("trial_number", 1),
        application=c_app.get("application"),
        status=status,
        configured_capacity=bottleneck.get("configured_capacity"),
        configured_latency=bottleneck.get("configured_latency"),
        measured_throughput=bottleneck.get("measured_throughput"),
        measured_rtt=bottleneck.get("measured_rtt"),
        qoe_metrics=data.get("qoe_metrics"),
        transport_state=data.get("transport_state"),
        contextual_tree=contextual_tree,
        pcap_path=data.get("pcap_path"),
        tags=None,
    )

    db.session.add(result)
    db.session.commit()

    return (
        jsonify(
            {
                "result_id": result.result_id,
                "experiment_id": result.experiment_id,
                "status": "stored",
                "created_at": result.created_at.isoformat() + "Z",
            }
        ),
        201,
    )


@routes_bp.route("/results", methods=["GET"])
def get_results_by_filters():
    args = request.args
    query = _build_result_query(args)
    total = query.count()

    sort_by = args.get("sort_by", "created_at")
    sort_order = args.get("sort_order", "desc")
    sort_col = getattr(models.Result, sort_by, models.Result.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    limit_raw = args.get("limit", "50")
    offset_raw = args.get("offset", "0")
    try:
        limit = int(limit_raw)
        offset = int(offset_raw)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    if limit < 0 or offset < 0:
        return jsonify({"error": "limit and offset must be non-negative"}), 400

    limit = min(limit, 500)
    results = query.limit(limit).offset(offset).all()

    return (
        jsonify(
            {
                "results": [r.to_dict() for r in results],
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(results),
            }
        ),
        200,
    )


@routes_bp.route("/results/<result_id>", methods=["GET"])
def get_results_by_id(result_id):
    result = models.Result.query.get_or_404(result_id)
    return jsonify(result.to_dict()), 200


@routes_bp.route("/results/<result_id>/artifacts", methods=["GET"])
def get_results_artifacts_by_id(result_id):
    models.Result.query.get_or_404(result_id)
    artifacts = models.Artifact.query.filter_by(result_id=result_id).all()
    return jsonify({"artifacts": [a.to_dict() for a in artifacts]}), 200


@routes_bp.route("/results/<result_id>/tags", methods=["POST"])
def add_tags_to_results_by_id(result_id):
    result = models.Result.query.get_or_404(result_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    new_tags = data.get("tags", [])
    if not isinstance(new_tags, list):
        new_tags = []

    existing = result.tags or []
    seen = set()
    combined_tags = []
    for tag in existing + new_tags:
        if tag not in seen:
            seen.add(tag)
            combined_tags.append(tag)

    result.tags = combined_tags
    db.session.commit()

    return jsonify({"result_id": result_id, "tags": result.tags}), 200


@routes_bp.route("/results/export/csv", methods=["GET"])
def get_results_as_csv_by_filters():
    query = _build_result_query(request.args)
    total = query.count()

    if total > 10000:
        return (
            jsonify(
                {
                    "error": f"Query returned {total} results, exceeding the 10,000 row export limit. Use filters to narrow results."
                }
            ),
            400,
        )

    results = query.all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "result_id",
            "experiment_id",
            "trial_number",
            "application",
            "status",
            "created_at",
            "configured_capacity",
            "configured_latency",
            "measured_throughput",
            "measured_rtt",
            "video_startup_time_ms",
            "mean_bitrate_mbps",
            "bitrate_changes",
            "rebuffer_events",
            "rebuffer_duration_ms",
            "congestion_control",
            "protocol",
            "pcap_path",
            "tags",
        ]
    )

    for r in results:
        qoe = r.qoe_metrics or {}
        c_trans = (r.contextual_tree or {}).get("c_trans", {})
        writer.writerow(
            [
                r.result_id,
                r.experiment_id,
                r.trial_number,
                r.application,
                r.status,
                r.created_at.isoformat() + "Z" if r.created_at else None,
                r.configured_capacity,
                r.configured_latency,
                r.measured_throughput,
                r.measured_rtt,
                qoe.get("video_startup_time_ms"),
                qoe.get("mean_bitrate_mbps"),
                qoe.get("bitrate_changes"),
                qoe.get("rebuffer_events"),
                qoe.get("rebuffer_duration_ms"),
                c_trans.get("congestion_control"),
                c_trans.get("protocol"),
                r.pcap_path,
                ",".join(r.tags or []),
            ]
        )

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = "attachment; filename=results.csv"
    return response, 200


@routes_bp.route("/artifacts", methods=["POST"])
def add_artifacts():
    result_id = request.form.get("result_id")
    artifact_type = request.form.get("artifact_type", "log")
    file = request.files.get("file")

    if not file or not result_id:
        return jsonify({"error": "result_id and file are required"}), 400

    models.Result.query.get_or_404(result_id)

    artifact_id = str(uuid.uuid4())
    filename = file.filename
    storage_path = f"artifacts/{result_id}/{artifact_id}/{filename}"

    # get size before uploading
    file.seek(0, 2)
    size_bytes = file.tell()
    file.seek(0)

    s3.put_object(file, storage_path)

    artifact = models.Artifact(
        artifact_id=artifact_id,
        result_id=result_id,
        artifact_type=artifact_type,
        filename=filename,
        size_bytes=size_bytes,
        storage_path=storage_path,
    )

    db.session.add(artifact)
    db.session.commit()

    return jsonify(artifact.to_dict()), 201


@routes_bp.route("/artifacts/<artifact_id>", methods=["GET"])
def get_artifacts_by_id(artifact_id):
    artifact = models.Artifact.query.get_or_404(artifact_id)

    file_bytes = s3.get_object(artifact.storage_path)

    response = make_response(file_bytes)
    response.headers["Content-Type"] = "application/octet-stream"
    response.headers[
        "Content-Disposition"
    ] = f"attachment; filename={artifact.filename}"
    return response, 200
