# web — the Contour map app

Internal tool. Draw a red line, make the sheet, see the findings on the map.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api and /files to :8000
npm test           # vitest
npm run build      # into dist/, which `uvicorn sheet.api:app` then serves
```

The API must be running from the repo root: `uvicorn sheet.api:app --port 8000`.
See the main README.
