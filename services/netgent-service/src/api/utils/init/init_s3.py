"""S3/MinIO initialization helpers for the NetGent API package."""

from __future__ import annotations

import os
from typing import Final

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

DEFAULT_S3_ENDPOINT_URL: Final[str] = "http://minio:9000"
DEFAULT_S3_BUCKET_NAME: Final[str] = "netgent"
DEFAULT_S3_CONNECTION_RETRIES: Final[int] = 3
DEFAULT_S3_CONNECTION_TIMEOUT_SECONDS: Final[int] = 60
DEFAULT_AWS_REGION: Final[str] = "us-east-1"


def build_s3_client():
    """Create a MinIO-compatible S3 client from environment settings."""

    endpoint_url = os.getenv("S3_ENDPOINT_URL", DEFAULT_S3_ENDPOINT_URL)
    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    retries = int(
        os.getenv("S3_CONNECTION_RETRIES", str(DEFAULT_S3_CONNECTION_RETRIES))
    )
    timeout_seconds = int(
        os.getenv(
            "S3_CONNECTION_TIMEOUT_SECONDS",
            str(DEFAULT_S3_CONNECTION_TIMEOUT_SECONDS),
        )
    )
    region_name = os.getenv("AWS_REGION", DEFAULT_AWS_REGION)

    client_config = Config(
        connect_timeout=timeout_seconds,
        read_timeout=timeout_seconds,
        retries={"max_attempts": retries, "mode": "standard"},
        s3={"addressing_style": "path"},
    )

    missing_credentials = [
        name
        for name, value in (
            ("S3_ACCESS_KEY", access_key),
            ("S3_SECRET_KEY", secret_key),
        )
        if not value
    ]
    if missing_credentials:
        missing = ", ".join(missing_credentials)
        raise ValueError(
            "Missing required S3 credentials for NetGent startup: "
            f"{missing}. Set S3_ACCESS_KEY/S3_SECRET_KEY or AWS_ACCESS_KEY_ID/"
            "AWS_SECRET_ACCESS_KEY."
        )

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region_name,
        config=client_config,
    )


def init_s3_bucket(bucket_name: str | None = None):
    """Ensure the configured S3 bucket exists and return the client."""

    resolved_bucket_name = (
        bucket_name
        or os.getenv("NETGENT_S3_BUCKET_NAME")
        or os.getenv("S3_BUCKET_NAME", DEFAULT_S3_BUCKET_NAME)
    ).strip()
    if not resolved_bucket_name:
        raise ValueError(
            "NETGENT_S3_BUCKET_NAME or S3_BUCKET_NAME must be configured before "
            "S3 initialization."
        )

    s3_client = build_s3_client()

    try:
        s3_client.head_bucket(Bucket=resolved_bucket_name)
    except ClientError as exc:
        error_code = str(exc.response.get("Error", {}).get("Code", ""))
        if error_code not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        s3_client.create_bucket(Bucket=resolved_bucket_name)

    return s3_client
