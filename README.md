# AgentCard.dev

Turn an OpenAPI spec into a signed, hosted A2A (Agent2Agent) agent in one API call.

## What this is

- `app/models.py` — A2A data models (Agent Card, Task lifecycle, JSON-RPC envelope)
- `app/converter.py` — OpenAPI spec → Agent Card + skill mapping
- `app/signing.py` — JCS canonicalization + ES256 JWS signing of Agent Cards
- `app/executor.py` — runtime: executes a skill call against the tenant's real upstream API
- `app/storage.py` — SQLite persistence (tenants, tasks, waitlist)
- `app/main.py` — FastAPI app tying it together (multi-tenant)
- `examples/` — a mock upstream API + OpenAPI spec to test against
- `site/index.html` — marketing landing page

## Run locally

```bash
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

Provision a test tenant:

```bash
curl -X POST http://localhost:8000/provision -H "Content-Type: application/json" -d '{
  "tenant_slug": "petstore",
  "name": "PetStore Orders Agent",
  "description": "Order and inventory management",
  "upstream_base_url": "https://your-real-api.com",
  "openapi_spec": { ... your OpenAPI spec ... },
  "public_base_url": "https://your-deployed-url.onrender.com"
}'
```

Then fetch the signed Agent Card at:
`https://your-deployed-url.onrender.com/t/petstore/.well-known/agent-card.json`

And call a skill via JSON-RPC:

```bash
curl -X POST https://your-deployed-url.onrender.com/t/petstore/rpc -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0", "id": "1", "method": "message/send",
  "params": {"skillId": "your_skill_id", "parameters": {...}}
}'
```

## Deploy to Render.com (free tier, no credit card)

1. Push this repo to GitHub.
2. Go to https://render.com → sign up (free, no card required for the free tier).
3. Click "New +" → "Blueprint" → connect this GitHub repo.
4. Render reads `render.yaml` automatically and provisions the service + a persistent disk for SQLite.
5. Once deployed, your service is live at `https://agentcard-dev-XXXX.onrender.com`.
6. Update `public_base_url` in your `/provision` calls to match your real Render URL.

Note: Render's free tier spins the service down after ~15 min of inactivity and takes
~30-50s to wake back up on the next request. Fine for testing/demoing; upgrade to a
paid instance ($7/mo+) once you have real traffic that can't tolerate cold starts.

## What's NOT done yet

- No auth on `/provision` — anyone who finds the URL can create a tenant. Add an API key
  check before this is public.
- No Stripe billing — `call_count` is tracked per tenant but nothing charges for it yet.
- Private keys are stored as plaintext PEM in SQLite — fine for a prototype, not for
  production. Move to a real KMS (AWS KMS, GCP Cloud KMS, or even encrypted-at-rest
  SQLite) before handling real customer secrets.
