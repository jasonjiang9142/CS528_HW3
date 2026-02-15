# CS528 HW3: Microservices (Service 1 + Service 2)

## Table of contents

1. [Overview](#overview)
2. [Prerequisites](#1-prerequisites)
3. [Setup](#2-setup)
4. [Deploy & run](#3-deploy--run)
5. [Demos](#4-demos)
6. [Cloud Logging & report](#5-cloud-logging--report)


---

## Overview

| Component | Description |
|-----------|-------------|
| **Service 1** | Cloud Function. Serves files from GCS via HTTP GET. Returns 200 / 404 / 501 / 400. Logs errors to Cloud Logging. Publishes “forbidden” (400) events to Pub/Sub. |
| **Service 2** | Local process. Subscribes to Pub/Sub, prints forbidden-request messages to stdout, appends to `gs://BUCKET/forbidden_logs/forbidden_requests.log`. |

**Base URL :**
```
https://us-central1-serious-music-485622-t8.cloudfunctions.net/serve-file
```

---

## 1. Prerequisites

- **GCP project** with Cloud Functions (2nd gen), Cloud Storage, Pub/Sub, and Cloud Logging enabled.
- **Bucket** from HW2 with files under `pages/` (e.g. `gs://cs528-jx3onj-hw2/pages/page_*.json`).
- **Service account** (e.g. `hw3-service-account@serious-music-485622-t8.iam.gserviceaccount.com`) with:
  - Storage Object Viewer on the bucket
  - Pub/Sub Publisher on the topic
  - (For Service 2) Pub/Sub Subscriber on the subscription; Storage Object Admin on the bucket for `forbidden_logs/`.

---

## 2. Setup

### 2.1 Pub/Sub topic and subscription

```bash
export PROJECT_ID=serious-music-485622-t8
export TOPIC_ID=forbidden-requests
export SUBSCRIPTION_ID=forbidden-requests-sub

gcloud pubsub topics create $TOPIC_ID --project=$PROJECT_ID
gcloud pubsub subscriptions create $SUBSCRIPTION_ID \
  --topic=$TOPIC_ID \
  --project=$PROJECT_ID
```

Grant the service account:
- `roles/pubsub.publisher` on the **topic**
- `roles/pubsub.subscriber` on the **subscription**

---

## 3. Deploy & run

### 3.1 Deploy Service 1 (Cloud Function)

From the **project root** (parent of `service1_main`):

```bash
cd service1_main
gcloud functions deploy serve-file \
  --gen2 \
  --runtime=python312 \
  --region=us-central1 \
  --project=serious-music-485622-t8 \
  --source=. \
  --entry-point=serve_file \
  --trigger-http \
  --allow-unauthenticated \
  --service-account=hw3-service-account@serious-music-485622-t8.iam.gserviceaccount.com \
  --set-env-vars "GCS_BUCKET=cs528-jx3onj-hw2,GCP_PROJECT=serious-music-485622-t8,PUBSUB_TOPIC=forbidden-requests"
```

Note the function URL; use it as **BASE_URL** in the demos below.

### 3.2 Run Service 2 (local)

Use the **same service account**. Do **not** use `gcloud auth application-default login`.

**Option A — Key file**

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/full/path/to/sa-key.json
cd service2_subscriber
pip install -r requirements.txt
python main.py
```

**Option B — Impersonation**

```bash
export USE_IMPERSONATION=1
export IMPERSONATE_SA=hw3-service-account@serious-music-485622-t8.iam.gserviceaccount.com
cd service2_subscriber
pip install -r requirements.txt
python main.py
```

Service 2 prints each forbidden request to stdout and appends to `gs://cs528-jx3onj-hw2/forbidden_logs/forbidden_requests.log`.

---

## 4. Demos

Use your Cloud Function **BASE_URL** (e.g. `https://us-central1-serious-music-485622-t8.cloudfunctions.net/serve-file`).

### 4.1 100 requests (HTTP client)

```bash
python http_client.py --url https://us-central1-serious-music-485622-t8.cloudfunctions.net/serve-file --num 100
```

### 4.2 Curl — 200, 404, 501, 400

| Status | Command |
|--------|--------|
| **200** | `curl -i "BASE_URL/pages/page_00001.json"` |
| **404** | `curl -i "BASE_URL/pages/nonexistent.json"` |
| **501** | `curl -i -X PUT "BASE_URL/pages/page_00001.json"` |
| **400** | `curl -i -H "X-country: Iran" "BASE_URL/pages/page_00001.json"` |

### 4.3 Browser — one request per status

- **200:** Open in address bar: `BASE_URL/pages/page_00001.json`
- **404:** Open: `BASE_URL/pages/does_not_exist.json`
- **501:** In DevTools → Console, run:
  ```javascript
  fetch("BASE_URL/pages/page_00001.json", { method: "PUT" })
    .then(r => { console.log("Status:", r.status); return r.text(); })
    .then(t => console.log("Body:", t));
  ```
- **404 (console):**
  ```javascript
  fetch("BASE_URL/pages/nonexistent.json")
    .then(r => { console.log("Status:", r.status); return r.text(); })
    .then(t => console.log("Body:", t));
  ```
- **400:** In Console:
  ```javascript
  fetch("BASE_URL/pages/page_00001.json", { headers: { "X-country": "Iran" } })
    .then(r => { console.log("Status:", r.status); return r.text(); })
    .then(t => console.log("Body:", t));
  ```

Take **screenshots** for the PDF (page for 200/404; console for 501/400).

### 4.4 Forbidden countries (400) and Service 2

Forbidden list: North Korea, Iran, Cuba, Myanmar, Iraq, Libya, Sudan, Zimbabwe, Syria.

With **Service 2 running**, trigger 400 (e.g. curl or HTTP client with `X-country: Iran`). You should see: (1) 400 response, (2) message in Service 2 terminal, (3) line appended to `gs://cs528-jx3onj-hw2/forbidden_logs/forbidden_requests.log`.

**HTTP client (single request):**
```bash
python http_client.py --url https://us-central1-serious-music-485622-t8.cloudfunctions.net/serve-file --file pages/page_00001.json --x-country Iran
```

---

## 5. Cloud Logging & report

- **Where:** GCP Console → **Logging** → **Logs Explorer**
- **Filter by:** Resource type = Cloud Function (or function name); Severity = Warning/Error; or search `status_code=404`, `status_code=501`, `error_type=forbidden_country`
- **Report:** Include screenshots or exported log contents for 404 and 501 (and optionally 400).

### Service account / impersonation (Step 8 answer)

| Mechanism | How it works | Why use it |
|-----------|--------------|------------|
| **Key file** | `GOOGLE_APPLICATION_CREDENTIALS` points to a JSON key. Client libraries use it to get access tokens. Only that SA’s permissions are used. | Simple; no user login; assignment allows it. |
| **Impersonation** | User credentials call IAM Credentials API to get short-lived tokens for the SA. User needs **Service Account Token Creator** on that SA. | No key file on disk; uses existing user auth. |
