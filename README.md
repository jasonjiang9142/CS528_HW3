# CS528 HW3: Microservices (Service 1 + Service 2)

## Table of contents

1. [Overview](#overview)
2. [Prerequisites](#1-prerequisites)
3. [Setup](#2-setup)
4. [Deploy & run](#3-deploy--run)
5. [Demos](#4-demos)
6. [Cloud Logging & report](#5-cloud-logging--report)
7. [PDF report: steps to configure and run](#pdf-report-steps-to-configure-and-run)

---

## Overview

| Component | Description |
|-----------|-------------|
| **Service 1** | Cloud Function. Serves files from GCS via HTTP GET. Returns 200 / 404 / 501 / 400. Logs errors to Cloud Logging. Publishes "forbidden" (400) events to Pub/Sub. |
| **Service 2** | Local process. Subscribes to Pub/Sub, prints forbidden-request messages to stdout, appends to `gs://BUCKET/forbidden_logs/forbidden_requests.log`. |

**Base URL (replace in commands below):**
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
| **Key file** | `GOOGLE_APPLICATION_CREDENTIALS` points to a JSON key. Client libraries use it to get access tokens. Only that SA's permissions are used. | Simple; no user login; assignment allows it. |
| **Impersonation** | User credentials call IAM Credentials API to get short-lived tokens for the SA. User needs **Service Account Token Creator** on that SA. | No key file on disk; uses existing user auth. |


---

## PDF report: steps to configure and run

### 1. Prerequisites

- A GCP project with billing enabled.
- The following APIs enabled: Cloud Functions, Cloud Run, Cloud Build, Cloud Storage, Cloud Pub/Sub, Cloud Logging. (Enable from **APIs & Services → Library**, or run the deploy command and answer **yes** when prompted.)
- A GCS bucket from Homework 2 with JSON files under the `pages/` prefix (e.g. `gs://cs528-jx3onj-hw2/pages/page_*.json`).
- A dedicated service account (e.g. `hw3-service-account@serious-music-485622-t8.iam.gserviceaccount.com`) that will run the Cloud Function and (optionally) the local subscriber.

### 2. Create the service account and grant roles

- In **IAM & Admin → Service Accounts**, create a new service account (e.g. `hw3-service-account`).
- Grant it:
  - **Storage Object Viewer** on the bucket (so the Cloud Function can read objects).
  - **Pub/Sub Publisher** on the project or on the topic (so the Cloud Function can publish "forbidden" events).
  - For the local subscriber (Service 2): **Pub/Sub Subscriber** on the subscription, and **Storage Object Admin** (or create/read) on the bucket so it can write to `forbidden_logs/`.

### 3. Create the Pub/Sub topic and subscription

- In **Pub/Sub → Topics**, create a topic (e.g. `forbidden-requests`).
- In **Pub/Sub → Subscriptions**, create a subscription (e.g. `forbidden-requests-sub`) attached to that topic.
- Ensure the service account has **Pub/Sub Publisher** on the topic and **Pub/Sub Subscriber** on the subscription (see step 2).

From the Cloud Shell or a terminal with `gcloud` configured:

```bash
export PROJECT_ID=serious-music-485622-t8
export TOPIC_ID=forbidden-requests
export SUBSCRIPTION_ID=forbidden-requests-sub

gcloud pubsub topics create $TOPIC_ID --project=$PROJECT_ID
gcloud pubsub subscriptions create $SUBSCRIPTION_ID --topic=$TOPIC_ID --project=$PROJECT_ID
```

### 4. Deploy Service 1 (Cloud Function)

- From the machine where the code lives, open a terminal and go to the directory that contains the `service1_main` folder (e.g. the project root).
- Run:

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

- If prompted to enable APIs (e.g. Cloud Functions, Cloud Run, Cloud Build), answer **yes**.
- After a successful deploy, note the function URL (e.g. `https://us-central1-serious-music-485622-t8.cloudfunctions.net/serve-file`). This is the **base URL** used in the demos below.

### 5. Run Service 2 (local subscriber) on your laptop

- Service 2 must run on your local machine and use the **same service account** as the Cloud Function, via either a key file or impersonation (do **not** use `gcloud auth application-default login`).

**Option A — Using a service account key file**

1. In GCP Console, go to **IAM & Admin → Service Accounts**, select the service account, open the **Keys** tab, add a new key, choose **JSON**, and download the file.
2. Store the JSON file in a secure location (e.g. `~/sa-key.json`). Do not commit it to version control.
3. In a terminal on your laptop:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/full/path/to/sa-key.json
cd service2_subscriber
pip install -r requirements.txt
python main.py
```
- The process will subscribe to the Pub/Sub subscription, print each "forbidden" request message to stdout, and append lines to `gs://cs528-jx3onj-hw2/forbidden_logs/forbidden_requests.log`. Leave it running when testing 400 (forbidden country) requests.

### 6. Verify the setup

- **Service 1:** In a browser or with curl, open:  
  `https://us-central1-serious-music-485622-t8.cloudfunctions.net/serve-file/pages/page_00001.json`  
  You should see JSON content and a 200 OK response.
- **Service 2:** With Service 2 running, send a request with a forbidden-country header (e.g. `curl -H "X-country: Iran" "<BASE_URL>/pages/page_00001.json"`). You should get 400 from the function, a printed message in the Service 2 terminal, and a new line in `gs://cs528-jx3onj-hw2/forbidden_logs/forbidden_requests.log`.



