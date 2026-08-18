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

## Security and retention notes

- Uploaded names never become filesystem paths; opaque UUID-based keys are used.
- Document content is never logged.
- Access tokens are returned only at creation and stored only as hashes.
- Requests lazily mark due jobs expired, while the Compose `cleanup` service scans every minute
  and removes expired PDF, JSON, DOCX and preview files idempotently.
- Production hardening (sandboxed LibreOffice, worker resource limits, upload rate limiting,
  metrics, and staging verification) remains explicitly assigned to Milestone 5.
