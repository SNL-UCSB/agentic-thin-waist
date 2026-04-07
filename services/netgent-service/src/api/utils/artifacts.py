from __future__ import annotations

import base64
import json
import os
from typing import Any
from urllib.parse import quote

from .init.init_s3 import (
    DEFAULT_S3_BUCKET_NAME,
    DEFAULT_S3_ENDPOINT_URL,
    init_s3_bucket,
)

DEFAULT_S3_PUBLIC_URL = "http://localhost:9000"


def _resolve_bucket_name() -> str:
    return (
        os.getenv("NETGENT_S3_BUCKET_NAME")
        or os.getenv("S3_BUCKET_NAME")
        or DEFAULT_S3_BUCKET_NAME
    ).strip()


def _build_artifact_url(bucket_name: str, key: str) -> str:
    endpoint_url = (
        os.getenv("NETGENT_S3_PUBLIC_URL")
        or os.getenv("S3_PUBLIC_URL")
        or os.getenv("S3_ENDPOINT_URL")
        or DEFAULT_S3_PUBLIC_URL
    ).rstrip("/")
    return f"{endpoint_url}/{bucket_name}/{quote(key, safe='/')}"


def _put_object(
    s3_client: Any,
    *,
    bucket_name: str,
    key: str,
    body: bytes,
    content_type: str,
) -> dict[str, str]:
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=body,
        ContentType=content_type,
    )
    return {
        "bucket": bucket_name,
        "key": key,
        "s3_uri": f"s3://{bucket_name}/{key}",
        "url": _build_artifact_url(bucket_name, key),
    }


def _iter_result_screenshots(value: object, path: tuple[object, ...] = ()):
    if isinstance(value, dict):
        screenshot = value.get("screenshot")
        if isinstance(screenshot, dict):
            b64 = screenshot.get("b64")
            image_format = screenshot.get("format")
            if isinstance(b64, str) and b64 and isinstance(image_format, str):
                yield path, b64, image_format

        for key, nested_value in value.items():
            yield from _iter_result_screenshots(nested_value, (*path, key))
        return

    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            yield from _iter_result_screenshots(nested_value, (*path, index))


def _find_har(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        har = value.get("har")
        if isinstance(har, dict) and har:
            return har

        for nested_value in value.values():
            found = _find_har(nested_value)
            if found is not None:
                return found
        return None

    if isinstance(value, list):
        for nested_value in value:
            found = _find_har(nested_value)
            if found is not None:
                return found

    return None


def upload_job_artifacts(
    *,
    job_id: str,
    workflow_type: str,
    result: Any,
) -> list[dict[str, str]]:
    bucket_name = _resolve_bucket_name()
    s3_client = init_s3_bucket(bucket_name)
    artifacts: list[dict[str, str]] = []

    try:
        if workflow_type == "browser":
            for index, (path_parts, b64, image_format) in enumerate(
                _iter_result_screenshots(result),
                start=1,
            ):
                safe_format = image_format.lower().strip(".") or "png"
                key = f"{job_id}/screenshots/screenshot_{index:03d}.{safe_format}"
                artifact = _put_object(
                    s3_client,
                    bucket_name=bucket_name,
                    key=key,
                    body=base64.b64decode(b64),
                    content_type=f"image/{safe_format}",
                )
                artifact["type"] = "screenshot"
                artifact["source"] = " -> ".join(str(part) for part in path_parts)
                artifacts.append(artifact)

            har = _find_har(result)
            if har is not None:
                artifact = _put_object(
                    s3_client,
                    bucket_name=bucket_name,
                    key=f"{job_id}/har/session.har",
                    body=json.dumps(har, indent=2, ensure_ascii=False).encode("utf-8"),
                    content_type="application/json",
                )
                artifact["type"] = "har"
                artifacts.append(artifact)

        elif workflow_type == "shell":
            shell_output = result
            if isinstance(result, dict) and "result" in result:
                shell_output = result["result"]

            artifact = _put_object(
                s3_client,
                bucket_name=bucket_name,
                key=f"{job_id}/shell/output.json",
                body=json.dumps(
                    shell_output,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ).encode("utf-8"),
                content_type="application/json",
            )
            artifact["type"] = "shell"
            artifacts.append(artifact)
        elif workflow_type == "hybrid":
            for index, (path_parts, b64, image_format) in enumerate(
                _iter_result_screenshots(result),
                start=1,
            ):
                safe_format = image_format.lower().strip(".") or "png"
                key = f"{job_id}/screenshots/screenshot_{index:03d}.{safe_format}"
                artifact = _put_object(
                    s3_client,
                    bucket_name=bucket_name,
                    key=key,
                    body=base64.b64decode(b64),
                    content_type=f"image/{safe_format}",
                )
                artifact["type"] = "screenshot"
                artifact["source"] = " -> ".join(str(part) for part in path_parts)
                artifacts.append(artifact)

            har = _find_har(result)
            if har is not None:
                artifact = _put_object(
                    s3_client,
                    bucket_name=bucket_name,
                    key=f"{job_id}/har/session.har",
                    body=json.dumps(har, indent=2, ensure_ascii=False).encode("utf-8"),
                    content_type="application/json",
                )
                artifact["type"] = "har"
                artifacts.append(artifact)

            hybrid_output = result
            if isinstance(result, dict) and "result" in result:
                hybrid_output = result["result"]

            artifact = _put_object(
                s3_client,
                bucket_name=bucket_name,
                key=f"{job_id}/hybrid/output.json",
                body=json.dumps(
                    hybrid_output,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ).encode("utf-8"),
                content_type="application/json",
            )
            artifact["type"] = "hybrid"
            artifacts.append(artifact)
    finally:
        close = getattr(s3_client, "close", None)
        if callable(close):
            close()

    return artifacts
