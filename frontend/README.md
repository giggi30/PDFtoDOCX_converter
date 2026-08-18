# Frontend

React/Vite client for upload, conversion progress, side-by-side previews, quality metrics,
warnings and authenticated DOCX download.

Set `VITE_API_BASE_URL` when the backend is hosted on a different origin (for example
`https://your-backend.example.com`). If omitted, the client uses same-origin relative paths.

```bash
npm install
npm run dev
```

The Vite development server proxies `/api` and `/health` to `http://localhost:8000`.
