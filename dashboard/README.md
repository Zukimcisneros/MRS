Dashboard deployment

This folder contains a minimal static dashboard to view and toggle `post_daily`, and to inspect the Moltbook queue.

How it works
- When deployed to Netlify, the dashboard uses `/.netlify/functions/proxy` to forward API calls to your backend. The proxy reads `BACKEND_URL` and `AGENT_TOKEN` from Netlify environment variables.
- Locally you can switch the environment dropdown to `Local Backend` which will call `http://127.0.0.1:8080` using the dev token `devtoken`.

Netlify setup
1. Add the site to Netlify and point to this repo (or deploy the `dashboard/` folder directly).
2. Add the following environment variables in Netlify Site settings → Build & deploy → Environment: `BACKEND_URL` (e.g. `https://example.com`) and `AGENT_TOKEN` (your agent token).
3. Build settings: none required; this is static HTML. Ensure Netlify Functions are enabled and the `netlify/functions` folder is included.

One-click deploy (GitHub + Netlify)

1. Push this repository to GitHub and ensure the default branch is `main`.
2. In Netlify, create a new site from Git and connect the GitHub repository.
3. In Netlify Site settings → Build & deploy → Environment, add two secrets:
	 - `NETLIFY_AUTH_TOKEN` — your Netlify personal access token (used by CI
		 action only if you want to trigger deploys from GitHub Actions).
	 - `NETLIFY_SITE_ID` — the site ID (optional if you have one site; used by the CLI).
	 - `BACKEND_URL` — public base URL of your API (e.g. `https://example.com`).
	 - `AGENT_TOKEN` — the API bearer token for server auth.

4. The included GitHub Actions workflow `.github/workflows/netlify-deploy.yml` will run on pushes to `main` and call the Netlify CLI to deploy the `dashboard` folder and functions. Ensure you set `NETLIFY_AUTH_TOKEN` and `NETLIFY_SITE_ID` as repository secrets if you want CI-driven deploys.

Notes
- Netlify's action uses the Netlify CLI; you can also use Netlify's UI to connect the repo and configure deploys without CI tokens.
- If your backend is local during development, keep the dashboard's env selector on `Local Backend`.

Local testing
1. Run your backend locally (e.g., `AGENT_TOKEN=devtoken python3 -m uvicorn agents.api:app --host 127.0.0.1 --port 8080`).
2. Serve the dashboard locally: `cd dashboard && python3 -m http.server 8000` then open `http://localhost:8000`.
