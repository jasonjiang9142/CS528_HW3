

import os
import sys
import json
import time
from datetime import datetime

from google.cloud import pubsub_v1, storage

# Config
PROJECT_ID = os.environ.get("GCP_PROJECT", "serious-music-485622-t8")
BUCKET_NAME = os.environ.get("GCS_BUCKET", "cs528-jx3onj-hw2")
SUBSCRIPTION_ID = os.environ.get("PUBSUB_SUBSCRIPTION", "forbidden-requests-sub")
LOG_DIR = "forbidden_logs"
LOG_FILENAME = "forbidden_requests.log"


def get_credentials():
    """
    Use service account key file (GOOGLE_APPLICATION_CREDENTIALS) or
    impersonated credentials (USE_IMPERSONATION=1, IMPERSONATE_SA=...).
    """
    if os.environ.get("USE_IMPERSONATION", "").lower() in ("1", "true", "yes"):
        target_sa = os.environ.get("IMPERSONATE_SA")
        if not target_sa:
            print("USE_IMPERSONATION=1 requires IMPERSONATE_SA=service-account@project.iam.gserviceaccount.com", file=sys.stderr)
            sys.exit(1)
        try:
            from google.auth import default, impersonated_credentials
            source_credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            return impersonated_credentials.Credentials(
                source_credentials=source_credentials,
                target_principal=target_sa,
                target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
                lifetime=3600,
            )
        except Exception as e:
            print(f"Impersonation failed: {e}", file=sys.stderr)
            sys.exit(1)
    # Key file: load explicitly so we can error clearly if file is missing
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path:
        print(
            "Set GOOGLE_APPLICATION_CREDENTIALS to the path of your service account JSON key file.\n"
            "Example: export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json",
            file=sys.stderr,
        )
        sys.exit(1)
    if not os.path.isfile(key_path):
        print(f"Credentials file not found: {key_path}", file=sys.stderr)
        sys.exit(1)
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_file(key_path)


def append_to_gcs_log(bucket_name: str, blob_path: str, line: str, credentials=None):
    """Append a line to a blob in GCS (read-modify-write)."""
    client = storage.Client(project=PROJECT_ID, credentials=credentials) if credentials else storage.Client(project=PROJECT_ID)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    try:
        existing = blob.download_as_text()
    except Exception:
        existing = ""
    new_content = existing + line
    if not line.endswith("\n"):
        new_content += "\n"
    blob.upload_from_string(new_content, content_type="text/plain")


def run_subscriber(credentials=None):
    subscription_path = pubsub_v1.SubscriberClient.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)
    if credentials:
        subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
    else:
        subscriber = pubsub_v1.SubscriberClient()

    def callback(message):
        try:
            data = json.loads(message.data.decode("utf-8"))
            msg_text = data.get("message", message.data.decode("utf-8"))
            country = data.get("country", "?")
            path = data.get("path", "?")
        except Exception:
            msg_text = message.data.decode("utf-8", errors="replace")
            country = path = "?"

        timestamp = datetime.utcnow().isoformat() + "Z"
        line = f"[{timestamp}] {msg_text}\n"
        print(f"[Forbidden] {msg_text}", flush=True)

        blob_path = f"{LOG_DIR}/{LOG_FILENAME}"
        try:
            append_to_gcs_log(BUCKET_NAME, blob_path, line, credentials)
        except Exception as e:
            print(f"Failed to append to GCS: {e}", file=sys.stderr)
        message.ack()

    print(f"Subscribing to {subscription_path} (bucket log: gs://{BUCKET_NAME}/{LOG_DIR}/{LOG_FILENAME})", flush=True)
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
    subscriber.close()


if __name__ == "__main__":
    creds = get_credentials()
    run_subscriber(creds)
