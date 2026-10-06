# Cloudflare Pages deployment

The repository is prepared so the frontend never uses `localhost` in production.

## Pages build settings

Use the repository root as the Pages project root.

- Build command: `npm run build`
- Build output directory: `dist`
- Node.js: 20 or newer

The root build installs the frontend dependencies, builds Vite, and copies the generated static files to `dist/`.

## API connection

The browser calls `/api` on the same Cloudflare Pages domain. The file
`functions/api/[[path]].js` proxies these requests to the FastAPI service.

Add this variable in **Workers & Pages → your Pages project → Settings → Variables and Secrets**:

```text
BACKEND_URL=https://your-fastapi-host.example.com
```

`BACKEND_URL` can be either the backend origin (`https://api.example.com`) or include
`/api` (`https://api.example.com/api`). Do not point it at `localhost`.

The existing Python FastAPI/PostgreSQL backend must be deployed to a host that can run
long-lived Python services and PostgreSQL. Cloudflare Pages serves the Vite frontend and
the small proxy Function; Pages does not run this FastAPI application itself.

## Local development

Start PostgreSQL/backend as before, then run the frontend. Vite proxies local `/api`
requests to `http://localhost:8000`:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Docker Compose continues to work with its explicit local `VITE_API_URL` override.

## Optional direct API mode

If you intentionally want the browser to call FastAPI directly, set `VITE_API_URL` at
build time. In that mode the FastAPI `CORS_ORIGINS` setting must include the Pages domain.
The default same-origin `/api` proxy mode does not require browser CORS configuration.

## Important

Pages Functions are deployed through Git integration or Wrangler. Cloudflare's dashboard
Direct Upload flow does not deploy a `/functions` directory. If this project was previously
uploaded only as static files, connect the repository to Pages or deploy with Wrangler.
