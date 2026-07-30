# Deploy QR Chores to Google Cloud Run

This guide deploys the Docker image to **Cloud Run** with:

- **Cloud SQL** (Postgres) for durable data  
- **Cloud Storage** for chore photos  
- **Secret Manager** for `SECRET_KEY` and DB password  

Replace placeholders (`PROJECT_ID`, `REGION`, etc.) with your values.

## Prerequisites

- `gcloud` CLI authenticated (`gcloud auth login`)
- Billing enabled on the project
- APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com \
  --project=PROJECT_ID
```

## 1. Choose a stable public URL

QR stickers encode `BASE_URL`. Set this **before** printing codes.

Examples:

- Cloud Run default: `https://qr-chores-xxxxx-uc.a.run.app`
- Custom domain: `https://chores.example.com` (recommended)

## 2. Artifact Registry + image build

```bash
export PROJECT_ID=your-project
export REGION=us-central1
export REPO=qr-chores
export IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/qr-chores:latest

gcloud artifacts repositories create ${REPO} \
  --repository-format=docker \
  --location=${REGION} \
  --project=${PROJECT_ID} || true

gcloud builds submit --tag "${IMAGE}" --project=${PROJECT_ID}
```

Or build locally and push:

```bash
docker build -t "${IMAGE}" .
docker push "${IMAGE}"
```

## 3. Cloud SQL (Postgres)

```bash
export INSTANCE=qr-chores-db
export DB_NAME=qr_chores
export DB_USER=qr_chores
# Generate a strong password and keep it:
export DB_PASS='replace-with-strong-password'

gcloud sql instances create ${INSTANCE} \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=${REGION} \
  --project=${PROJECT_ID}

gcloud sql databases create ${DB_NAME} --instance=${INSTANCE} --project=${PROJECT_ID}
gcloud sql users create ${DB_USER} --instance=${INSTANCE} --password="${DB_PASS}" --project=${PROJECT_ID}
```

Connection name:

```bash
export INSTANCE_CONNECTION=$(gcloud sql instances describe ${INSTANCE} \
  --project=${PROJECT_ID} --format='value(connectionName)')
```

Async SQLAlchemy URL for Cloud Run (Unix socket via Cloud SQL connector is typical with the Cloud SQL Auth proxy sidecar). A common pattern:

```text
postgresql+asyncpg://DB_USER:DB_PASS@/DB_NAME?host=/cloudsql/INSTANCE_CONNECTION
```

Store secrets instead of baking passwords into the service YAML.

## 4. GCS bucket for photos

```bash
export BUCKET=${PROJECT_ID}-qr-chores-photos
gcloud storage buckets create gs://${BUCKET} --location=${REGION} --project=${PROJECT_ID}
```

Grant the Cloud Run service account object admin on the bucket (after the service exists, or create a dedicated SA first).

## 5. Secrets

```bash
echo -n "$(openssl rand -hex 32)" | gcloud secrets create qr-chores-secret-key \
  --data-file=- --project=${PROJECT_ID}

echo -n "${DB_PASS}" | gcloud secrets create qr-chores-db-pass \
  --data-file=- --project=${PROJECT_ID}
```

## 6. Deploy Cloud Run

```bash
export SERVICE=qr-chores
export BASE_URL=https://YOUR_STABLE_HOST

# Build DATABASE_URL carefully (URL-encode special chars in the password)
export DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@/${DB_NAME}?host=/cloudsql/${INSTANCE_CONNECTION}"

gcloud run deploy ${SERVICE} \
  --image="${IMAGE}" \
  --region=${REGION} \
  --project=${PROJECT_ID} \
  --platform=managed \
  --allow-unauthenticated \
  --add-cloudsql-instances="${INSTANCE_CONNECTION}" \
  --set-env-vars="ENVIRONMENT=production,APP_TIMEZONE=America/Chicago,BASE_URL=${BASE_URL},PHOTO_STORAGE=gcs,GCS_BUCKET=${BUCKET},RUN_MIGRATIONS=1,RUN_SEED=1" \
  --set-secrets="SECRET_KEY=qr-chores-secret-key:latest" \
  --set-env-vars="DATABASE_URL=${DATABASE_URL}" \
  --min-instances=0 \
  --max-instances=3 \
  --memory=512Mi \
  --cpu=1 \
  --port=8080
```

Notes:

| Env | Purpose |
|-----|---------|
| `ENVIRONMENT=production` | Disables OpenAPI docs; requires non-default `SECRET_KEY` |
| `RUN_MIGRATIONS=1` | Entrypoint runs `alembic upgrade head` on start |
| `RUN_SEED=1` | Creates dad/mom/daughter + default achievements (idempotent) |
| `PHOTO_STORAGE=gcs` | Store proof photos in GCS |
| `BASE_URL` | Must match the URL users (and QR codes) use (HTTPS) |
| `LOG_LEVEL` | App + MCP Python log level (default `INFO`) |
| `SYSLOG_SERVER` | Optional rsyslog host (`host` or `host:port`, UDP 514). Dual-writes nginx + app + MCP logs while keeping stdout/stderr for Cloud Logging |

### Logging & syslog

By default every process logs to **stdout/stderr** (Cloud Logging on Cloud Run).

Set `SYSLOG_SERVER` to an rsyslog/syslogd address to **also** ship:

| Source | Syslog tag / program | Notes |
|--------|----------------------|--------|
| nginx access | `qr-chores-nginx-access` | facility `local0` |
| nginx error | `qr-chores-nginx` | facility `local0` |
| FastAPI app | `qr-chores` | user actions (`qr_chores.actions`), errors (`qr_chores.errors`) |
| MCP server | `qr-chores-mcp` | same `SYSLOG_SERVER` / `LOG_LEVEL` |

App action logging covers mutations (POST/PUT/PATCH/DELETE), authenticated requests, login/logout, chore completions, and unhandled exceptions. No secrets/passwords are logged.

Example:

```bash
-e SYSLOG_SERVER=rsyslog.internal.example:514 \
-e LOG_LEVEL=INFO
```

### Nginx performance (Docker image)

The container reverse-proxy:

- Serves marketing + `/static/` **directly** (bypasses uvicorn). Marketing media under `marketing/assets/` are symlinks into `imgs/` (design library); the image copies both trees, and the entrypoint stages marketing onto tmpfs with symlink dereference (`cp -aL`).
- Stages those trees into **tmpfs** (`/dev/shm`) when free space allows
- Uses `open_file_cache`, `sendfile`, keepalive to app/MCP upstreams, and gzip
- Starts FastAPI and MCP **in parallel** for faster cold start

After first successful deploy, set `RUN_SEED=0` (and optionally run migrations as a one-off job instead of every instance start) to avoid multi-instance race noise:

```bash
gcloud run services update ${SERVICE} \
  --region=${REGION} \
  --project=${PROJECT_ID} \
  --update-env-vars=RUN_MIGRATIONS=0,RUN_SEED=0
```

Prefer a **release-step migration** (Cloud Run Job or Cloud Build step) for production:

```bash
gcloud run jobs create qr-chores-migrate \
  --image="${IMAGE}" \
  --region=${REGION} \
  --project=${PROJECT_ID} \
  --set-cloudsql-instances="${INSTANCE_CONNECTION}" \
  --set-env-vars="DATABASE_URL=${DATABASE_URL}" \
  --command=alembic \
  --args=upgrade,head \
  --execute-now
```

### Photo retention (`qr-chores-reap-photos`)

Proof photos are stored outside the DB (`PHOTO_STORAGE=local` or `gcs`). Completions keep history forever, but **blobs** should not. Configure:

| Env | Default | Meaning |
|-----|---------|---------|
| `PHOTO_RETENTION_DAYS` | `90` | Delete objects whose completion `local_date` is older than this many days. `0` disables the job. |

Run the reaper (idempotent) as a **Cloud Run Job** on a schedule (daily is fine):

```bash
# One-off dry-run
gcloud run jobs execute qr-chores-reap-photos --region=${REGION} --project=${PROJECT_ID}

# Create job (once)
gcloud run jobs create qr-chores-reap-photos \
  --image="${IMAGE}" \
  --region=${REGION} \
  --project=${PROJECT_ID} \
  --set-cloudsql-instances="${INSTANCE_CONNECTION}" \
  --set-secrets="DATABASE_URL=DATABASE_URL:latest,SECRET_KEY=SECRET_KEY:latest" \
  --set-env-vars="PHOTO_STORAGE=gcs,GCS_BUCKET=${BUCKET},PHOTO_RETENTION_DAYS=90,APP_TIMEZONE=America/Chicago" \
  --command=qr-chores-reap-photos \
  --args= \
  --max-retries=1 \
  --task-timeout=10m

# Optional: Cloud Scheduler → Job daily
# gcloud scheduler jobs create http ... targeting the Run Job execute API
```

Locally:

```bash
uv run qr-chores-reap-photos --dry-run
uv run qr-chores-reap-photos
uv run qr-chores-reap-photos --retention-days 30
```

The job deletes aged objects, clears `photo_object_key`, and leaves `had_photo=true` so photo achievements still count. History shows “Photo no longer available” when the blob is gone.

**Defense in depth (optional):** add a GCS Object Lifecycle rule on the photos bucket (e.g. delete objects under `completions/` after 100 days). Keep the app job so DB keys stay accurate and the UI does not link missing files.

## 7. Service account permissions

The Cloud Run runtime SA needs:

- `roles/cloudsql.client` on the project (or instance)
- `roles/storage.objectAdmin` on the photos bucket
- `roles/secretmanager.secretAccessor` on the secrets

```bash
export PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')
export SA=${PROJECT_NUMBER}-compute@developer.gserviceaccount.com

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA}" \
  --role="roles/cloudsql.client"

gcloud storage buckets add-iam-policy-binding gs://${BUCKET} \
  --member="serviceAccount:${SA}" \
  --role="roles/storage.objectAdmin"

gcloud secrets add-iam-policy-binding qr-chores-secret-key \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project=${PROJECT_ID}
```

## 8. Verify

```bash
export URL=$(gcloud run services describe ${SERVICE} --region=${REGION} --project=${PROJECT_ID} --format='value(status.url)')
curl -sS "${URL}/health"
# → {"status":"ok"}
```

Open `${URL}/login` and sign in with seeded accounts (change passwords after first login in a real family deploy — seed passwords are for bootstrap only).

## 9. Custom domain (optional)

Map a domain in Cloud Run → update `BASE_URL` → **only then** print QR stickers.

## 10. Local Docker smoke test

```bash
docker build -t qr-chores:local .
docker run --rm -p 8080:8080 \
  -e SECRET_KEY=dev-secret \
  -e DATABASE_URL=sqlite+aiosqlite:////tmp/qr_chores.db \
  -e BASE_URL=http://127.0.0.1:8080 \
  -e PHOTO_STORAGE=local \
  -e PHOTO_LOCAL_DIR=/tmp/uploads \
  -e RUN_MIGRATIONS=0 \
  -e RUN_SEED=1 \
  qr-chores:local
```

Verify health, API, and MCP proxy:

```bash
curl -sS http://127.0.0.1:8080/health
# MCP streamable-HTTP endpoint should respond (not 404)
curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" -d '{}'
```

`qrc` CLI (installed in the image; always uses `http://127.0.0.1:8000`):

```bash
CID=$(docker ps -q --filter ancestor=qr-chores:local | head -1)
docker exec -it "$CID" qrc auth login -e dad@example.com -p parent-pass
docker exec -it "$CID" qrc todays-chores
```

Optional MCP auto-login (tools use these on first use / lifespan):

```bash
-e QR_CHORES_EMAIL=dad@example.com \
-e QR_CHORES_PASSWORD=parent-pass
```

| In-container process | Bind | Notes |
|----------------------|------|--------|
| FastAPI (uvicorn) | `127.0.0.1:8000` | Source of truth for `/api/v1` |
| FastMCP | `127.0.0.1:8001` path `/mcp` | Tools always call `http://127.0.0.1:8000` |
| Nginx | `0.0.0.0:$PORT` | Proxies `/api` → app, `/mcp` → MCP |

## Operational checklist

- [ ] Strong `SECRET_KEY` in Secret Manager (not the dev default)  
- [ ] `ENVIRONMENT=production`  
- [ ] Postgres not SQLite on Cloud Run  
- [ ] `BASE_URL` matches public HTTPS URL  
- [ ] `PHOTO_STORAGE=gcs` + bucket permissions  
- [ ] Migrations applied  
- [ ] Seed run once; default seed passwords rotated or users recreated  
- [ ] Print QRs only after URL is final  
- [ ] `/docs` returns 404 in production  

## Troubleshooting

| Symptom | Check |
|---------|--------|
| 500 on first request | Cloud SQL socket / `DATABASE_URL` / SA `cloudsql.client` |
| Photos fail to save | `GCS_BUCKET`, SA storage role, `PHOTO_STORAGE=gcs` |
| QR opens wrong host | `BASE_URL` mismatch |
| Login fails after redeploy | Different `SECRET_KEY` invalidates sessions |
| Empty tables | Run migrations / seed |
