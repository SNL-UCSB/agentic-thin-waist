import base64
import json
import os
import uuid

from app.telemetry import db, s3

from flask import Blueprint, request, jsonify


routes_bp = Blueprint("routes", __name__)

@routes_bp.route("/health", methods=["GET"])
def healthcheck():
    return (jsonify({"message": "Success"}), 200)

@routes_bp.route("/results", methods=["POST"])
def add_results():
    # TODO
    return (jsonify({"message": "Success"}), 200)

@routes_bp.route("/results", methods=["GET"])
def get_results_by_filters():
    # TODO
    return (jsonify({"message": "Success"}), 200)

@routes_bp.route("/results/<id>", methods=["GET"])
def get_results_by_id(result_id):
    # TODO
    return (jsonify({"message": "Success"}), 200)

@routes_bp.route("/results/<id>/artifacts", methods=["GET"])
def get_results_artifacts_by_id(result_id):
    # TODO
    return (jsonify({"message": "Success"}), 200)

@routes_bp.route("/results/<id>/tags", methods=["POST"])
def add_tags_to_results_by_id(result_id):
    # TODO
    return (jsonify({"message": "Success"}), 200)

@routes_bp.route("/results/export/csv", methods=["GET"])
def get_results_as_csv_by_filters():
    # TODO
    return (jsonify({"message": "Success"}), 200)

@routes_bp.route("/artifacts", methods=["POST"])
def add_artifacts():
    # TODO
    return (jsonify({"message": "Success"}), 200)

@routes_bp.route("/artifacts/<id>", methods=["GET"])
def get_artifacts_by_id(artifact_id):
    # TODO
    return (jsonify({"message": "Success"}), 200)
