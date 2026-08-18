# PDF to DOCX Platform

Milestone 4.2 of a CV-focused PDF-to-DOCX platform. The worker classifies PDFs, extracts content
and layout, generates an editable DOCX, renders both documents, and returns an interpretable
quality report with authenticated page previews. A React interface covers the complete flow.

## Requirements

- Docker with Compose, or Python 3.12+, PostgreSQL 16, and Redis 7
- Maximum upload: 10 MB and 5 pages
- Native PDF files only; one file per conversion

## Start locally with Docker Compose

```bash
cp .env.example .env
# Replace APP_TOKEN_PEPPER before exposing the service.
docker compose up --build
```

The web interface is available at `http://localhost:3000`. The API is available at
`http://localhost:8000`; interactive documentation is at `http://localhost:8000/docs`.
PostgreSQL and Redis are not exposed on host ports.

## API flow

Create a conversion:

```bash
curl -F 'file=@resume.pdf;type=application/pdf' -F 'mode=editable' \
  http://localhost:8000/api/v1/conversions
```

The response includes a `job_id` and a one-time `access_token`. Send that token on subsequent
requests; only its HMAC-SHA256 hash is persisted.

```bash
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/v1/conversions/<job_id>
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/v1/conversions/<job_id>/result
curl -OJ -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/v1/conversions/<job_id>/download
curl -X DELETE -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/v1/conversions/<job_id>
```

The worker emits a valid, editable DOCX containing the extracted text, mapped Word styles,
images and the detected document structure. Canva-like pages are split into local hero, main,
column and bottom-card zones so a header or contact panel cannot be mistaken for global columns.
Full-bleed colour bands and photos use page-relative anchors; body columns retain their local
boundaries, vector bullets, separator and source-relative spacing. Bottom cards can overlap the main
column without forcing an extra page. The `editable` mode preserves the same document geometry,
while `high_fidelity` additionally reproduces supported decorative accents. The worker also persists
the intermediate JSON model under an opaque storage key. LibreOffice renders the DOCX, and the quality engine reports text
accuracy, visual similarity, layout similarity, page-count agreement and the main differences.
Unsupported fonts, images or decorations are reported through aggregated conversion warnings.

## Conversion modules

- `app/conversion/models.py`: Pydantic domain model, with top-left PDF-point coordinates;
- `app/conversion/classifier.py`: native, scanned and hybrid classification from neutral signals;
- `app/conversion/extractor.py`: text blocks, styles, images and vector decorations;
- `app/conversion/layout_analyzer.py`: reading order, columns, sidebars, inferred lists and local
  hero/card zones;
- `app/conversion/pipeline.py`: PDF-to-`DocumentModel` orchestration.
- `app/conversion/docx_builder.py`: editable and high-fidelity DOCX generation, compatible
  compatible font mappings, page-anchored images and colour bands, local columns, accent lines,
  borderless layout tables and aggregated unsupported-element warnings.
- `app/quality/renderer.py`: PDF and DOCX rendering into temporary PNG previews;
- `app/quality/comparator.py`: visual, text, layout and page-count metrics with an overall score.

The test suite contains ten generated, anonymous CV fixtures covering single-column, sidebar and
two-column layouts. Each fixture is verified both as a `DocumentModel` and as a readable,
editable DOCX. `test-documents/private/` is ignored and must never be committed.

Milestone 4.2 adds a committed Canva-style regression fixture plus a private four-page CV check.
On the committed fixture, the `high_fidelity` score increased from 74.3 to 86.9 and layout
similarity from 51.9 to 76.5. The private Canva CV retains four pages and 100% text accuracy; its
measured score increased from 67.9 to 81.1. The private source remains outside the repository.

## Frontend development

```bash
cd frontend
npm install
npm run dev
```

The Vite development server proxies API calls to `http://localhost:8000`.

## Backend development

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
mypy app
pytest --cov=app
```

Apply database migrations with `alembic upgrade head`. Configuration uses the `APP_` prefix;
all supported variables and safe local defaults are documented in `.env.example`.

## Deploy notes (Vercel)

The defaults in `.env.example` are for local Docker Compose only (`postgres` and `redis`
hostnames). On Vercel you must set external service URLs:

- `APP_DATABASE_URL`: managed PostgreSQL URL (for example Neon/Supabase/RDS).
- `APP_REDIS_URL`: managed Redis URL (for example Upstash/Redis Cloud).
- `APP_TOKEN_PEPPER`: long random secret.

This backend also requires an RQ worker and LibreOffice for DOCX rendering. Vercel serverless
functions do not run a persistent worker process. For production, run the worker on a separate
runtime (VM/container) that shares the same `APP_DATABASE_URL`, `APP_REDIS_URL` and
`APP_STORAGE_PATH`.

## Quick deploy runbook (Railway + Vercel frontend)

Use this setup if you want to keep the frontend on Vercel and move backend processing to Railway.

1. Create a new Railway project from this repository.
2. Add a PostgreSQL service and a Redis service in the same Railway project.
3. Create three app services from `backend/Dockerfile`:
  - API service command: `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"`
  - Worker service command: `rq worker --url $APP_REDIS_URL $APP_RQ_QUEUE_NAME`
  - Cleanup service command: `python -m app.workers.cleanup_scheduler`
4. Set environment variables on all three backend services:
  - `APP_ENVIRONMENT=production`
  - `APP_DATABASE_URL=<Railway Postgres connection string>`
  - `APP_REDIS_URL=<Railway Redis connection string>`
  - `APP_TOKEN_PEPPER=<long random secret>`
  - `APP_RQ_QUEUE_NAME=conversions`
  - `APP_STORAGE_PATH=/data/conversions`
5. Add one persistent volume and mount it at `/data/conversions` on API, Worker and Cleanup
  so all services share uploaded PDFs, generated DOCX and previews.
6. Get the public Railway URL of the API service.
7. In Vercel (frontend project), set:
  - `VITE_API_BASE_URL=https://<your-railway-api-domain>`
8. In Railway API service, set CORS origins to the Vercel frontend domain:
  - `APP_CORS_ORIGINS=https://<your-vercel-frontend-domain>`

After deploy, validate this flow:

1. `GET /health` on Railway API returns `{"status":"ok"}`.
2. Upload from frontend returns `202` and job status `QUEUED`.
3. Worker logs show `process_conversion` jobs being consumed.
4. Poll endpoint progresses to `COMPLETED` and download works.

## Security and retention notes

- Uploaded names never become filesystem paths; opaque UUID-based keys are used.
- Document content is never logged.
- Access tokens are returned only at creation and stored only as hashes.
- Requests lazily mark due jobs expired, while the Compose `cleanup` service scans every minute
  and removes expired PDF, JSON, DOCX and preview files idempotently.
- Production hardening (sandboxed LibreOffice, worker resource limits, upload rate limiting,
  metrics, and staging verification) remains explicitly assigned to Milestone 5.
