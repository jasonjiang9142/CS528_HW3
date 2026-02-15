
import os
import json
import logging
import functions_framework
from flask import Request
from google.cloud import storage, logging as cloud_logging
from google.cloud import pubsub_v1

# Config from environment (set in Cloud Function)
BUCKET_NAME = os.environ.get("GCS_BUCKET", "cs528-jx3onj-hw2")
PROJECT_ID = os.environ.get("GCP_PROJECT", "serious-music-485622-t8")
TOPIC_ID = os.environ.get("PUBSUB_TOPIC", "forbidden-requests")
GCS_PREFIX = "pages/"

# US export-restricted countries (sensitive cryptographic material)
FORBIDDEN_COUNTRIES = {
    "north korea", "iran", "cuba", "myanmar", "iraq", "libya",
    "sudan", "zimbabwe", "syria"
}

_client = None

def get_log_client():
    global _client
    if _client is None:
        _client = cloud_logging.Client(project=PROJECT_ID)
        _client.setup_logging()
    return _client


def log_structured(level: str, message: str, **kwargs):
    """Emit structured log and a simple print for Cloud Logging."""
    get_log_client()
    extra = {"json_fields": kwargs}
    if level == "error":
        logging.error(message, extra=extra)
    elif level == "warning":
        logging.warning(message, extra=extra)
    else:
        logging.info(message, extra=extra)
    print(message, flush=True)


def cors_headers():
    """Headers so browser fetch() from other origins can read the response."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, HEAD, OPTIONS, PATCH",
        "Access-Control-Allow-Headers": "Content-Type, X-country",
        "Access-Control-Max-Age": "3600",
    }


def object_name_from_path(path: str) -> str:
    """Map request path to GCS object name. Expects /pages/page_XXXXX.json or /page_XXXXX.json."""
    path = (path or "").strip().lstrip("/")
    if not path:
        return ""
    if path.startswith("pages/"):
        return path
    return f"{GCS_PREFIX}{path}"


def publish_forbidden(topic_path: str, country: str, path: str, project_id: str):
    """Publish a message to Pub/Sub for forbidden-country requests."""
    publisher = pubsub_v1.PublisherClient()
    payload = json.dumps({
        "country": country,
        "path": path,
        "message": f"Permission denied: request from forbidden country '{country}' for {path}",
    }).encode("utf-8")
    future = publisher.publish(topic_path, payload)
    future.result(timeout=10)


@functions_framework.http
def serve_file(request: Request):
    """
    Handle HTTP requests.
    - GET: serve file from bucket or 404; check X-country -> 400 if forbidden and publish to Pub/Sub.
    - Other methods: 501.
    """
    method = (request.method or "GET").upper()
    path = request.path or ""
    obj_name = object_name_from_path(path)
    headers = {"Content-Type": "text/plain; charset=utf-8", **cors_headers()}

    # --- OPTIONS: CORS preflight (so browser fetch() can reach us) ---
    if method == "OPTIONS":
        return ("", 204, {**cors_headers(), "Content-Length": "0"})

    # --- Non-GET: 501 Not Implemented ---
    if method != "GET":
        log_structured(
            "warning",
            f"501 Not Implemented: method={method} path={path}",
            status_code=501,
            http_method=method,
            path=path,
            error_type="method_not_allowed",
        )
        return ("Method Not Implemented", 501, headers)

    # --- GET: check X-country for export restriction ---
    country_header = (request.headers.get("X-country") or "").strip()
    if country_header:
        country_lower = country_header.lower()
        if country_lower in FORBIDDEN_COUNTRIES:
            log_structured(
                "warning",
                f"400 Permission denied: forbidden country X-country={country_header} path={path}",
                status_code=400,
                http_method=method,
                path=path,
                x_country=country_header,
                error_type="forbidden_country",
            )
            try:
                topic_path = pubsub_v1.PublisherClient.topic_path(PROJECT_ID, TOPIC_ID)
                publish_forbidden(topic_path, country_header, path, PROJECT_ID)
            except Exception as e:
                log_structured(
                    "error",
                    f"Failed to publish forbidden request to Pub/Sub: {e}",
                    error=str(e),
                )
            return (
                "Permission denied: export to this country is not allowed",
                400,
                headers,
            )

    # --- GET: resolve file and serve or 404 ---
    if not obj_name or not obj_name.endswith(".json"):
        log_structured(
            "warning",
            f"404 Not Found: path={path} (invalid or missing object name)",
            status_code=404,
            http_method=method,
            path=path,
            object_name=obj_name or "(empty)",
            error_type="not_found",
        )
        return ("Not Found", 404, headers)

    try:
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(obj_name)
        if not blob.exists():
            log_structured(
                "warning",
                f"404 Not Found: object gs://{BUCKET_NAME}/{obj_name} does not exist",
                status_code=404,
                http_method=method,
                path=path,
                object_name=obj_name,
                error_type="not_found",
            )
            return ("Not Found", 404, headers)
        content = blob.download_as_text()
        return (content, 200, {"Content-Type": "application/json; charset=utf-8", **cors_headers()})
    except Exception as e:
        log_structured(
            "error",
            f"404 Not Found or error reading object: {obj_name} error={e}",
            status_code=404,
            http_method=method,
            path=path,
            object_name=obj_name,
            error=str(e),
            error_type="not_found",
        )
        return ("Not Found", 404, headers)
