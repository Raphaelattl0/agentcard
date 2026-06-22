"""
AgentCard.dev — multi-tenant A2A wrapper service.

Each tenant gets:
  - A unique subpath: /t/{tenant_slug}/.well-known/agent-card.json  (signed Agent Card)
  - A JSON-RPC endpoint: /t/{tenant_slug}/rpc  (message/send, tasks/get, tasks/cancel)
  - Their own signing keypair (provisioned at onboarding, persisted in SQLite)

Persistence: SQLite (app/storage.py). Survives restarts/redeploys.
"""
from __future__ import annotations
import json
import time
import uuid
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from app.models import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcError,
    ERR_METHOD_NOT_FOUND, ERR_INVALID_PARAMS, ERR_TASK_NOT_FOUND,
    TaskState, AgentCard,
)
from app.converter import openapi_to_agent_card, manual_skills_to_agent_card
from app.signing import generate_signing_key, sign_agent_card, public_key_jwk, private_key_to_pem
from app.executor import execute_skill
from app.mcp import handle_mcp
from app import storage

app = FastAPI(title="AgentCard.dev runtime")

SITE_DIR = Path(__file__).resolve().parent.parent / "site"


@app.get("/")
def landing():
    """Serve the marketing landing page at the root."""
    index = SITE_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(404, "Landing page not found")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProvisionRequest(BaseModel):
    tenant_slug: str
    name: str
    description: str
    organization: str | None = None
    upstream_base_url: str
    upstream_api_key: str | None = None
    openapi_spec: dict[str, Any] | None = None
    manual_endpoints: list[dict[str, Any]] | None = None
    public_base_url: str = "https://agentcard.dev"


class WaitlistRequest(BaseModel):
    email: EmailStr


def _load_tenant_for_runtime(slug: str) -> dict | None:
    raw = storage.load_tenant_raw(slug)
    if not raw:
        return None
    return {
        "card": AgentCard(**json.loads(raw["card_json"])),
        "operation_map": json.loads(raw["operation_map_json"]),
        "upstream_base_url": raw["upstream_base_url"],
        "upstream_auth_header": json.loads(raw["upstream_auth_header_json"]),
        "public_key_jwk": json.loads(raw["public_key_jwk_json"]),
        "key_id": raw["key_id"],
        "created_at": raw["created_at"],
        "call_count": raw["call_count"],
    }


@app.post("/provision")
def provision_tenant(req: ProvisionRequest):
    if storage.tenant_exists(req.tenant_slug):
        raise HTTPException(409, "Tenant slug already exists")

    agent_url = f"{req.public_base_url}/t/{req.tenant_slug}"

    if req.openapi_spec:
        card, op_map = openapi_to_agent_card(
            req.openapi_spec, agent_url=agent_url, organization=req.organization,
        )
        for op in op_map.values():
            op["base_url"] = req.upstream_base_url
    elif req.manual_endpoints:
        card, op_map = manual_skills_to_agent_card(
            name=req.name, description=req.description, agent_url=agent_url,
            upstream_base_url=req.upstream_base_url, endpoints=req.manual_endpoints,
            organization=req.organization,
        )
    else:
        raise HTTPException(400, "Must provide either openapi_spec or manual_endpoints")

    if not card.skills:
        raise HTTPException(400, "No skills could be derived — spec produced zero operations")

    priv_key = generate_signing_key()
    key_id = f"{req.tenant_slug}-{uuid.uuid4().hex[:8]}"
    signed_card = sign_agent_card(card, priv_key, key_id)

    tenant_data = {
        "card": signed_card,
        "operation_map": op_map,
        "upstream_base_url": req.upstream_base_url,
        "upstream_auth_header": {"Authorization": f"Bearer {req.upstream_api_key}"} if req.upstream_api_key else {},
        "public_key_jwk": public_key_jwk(priv_key),
        "key_id": key_id,
        "created_at": time.time(),
        "call_count": 0,
    }
    storage.save_tenant(req.tenant_slug, tenant_data, private_key_to_pem(priv_key))

    return {
        "status": "provisioned",
        "agent_card_url": f"{agent_url}/.well-known/agent-card.json",
        "rpc_url": f"{agent_url}/rpc",
        "mcp_url": f"{agent_url}/mcp",
        "skills": [s.id for s in card.skills],
        "public_key_jwk": public_key_jwk(priv_key),
    }


@app.get("/t/{tenant_slug}/.well-known/agent-card.json")
def get_agent_card(tenant_slug: str):
    tenant = _load_tenant_for_runtime(tenant_slug)
    if not tenant:
        raise HTTPException(404, "Unknown tenant")
    return JSONResponse(content=tenant["card"].model_dump(exclude_none=True))


@app.get("/t/{tenant_slug}/public-key")
def get_public_key(tenant_slug: str):
    tenant = _load_tenant_for_runtime(tenant_slug)
    if not tenant:
        raise HTTPException(404, "Unknown tenant")
    return {"kid": tenant["key_id"], "jwk": tenant["public_key_jwk"]}


@app.post("/t/{tenant_slug}/rpc")
async def rpc_endpoint(tenant_slug: str, request: Request):
    tenant = _load_tenant_for_runtime(tenant_slug)
    if not tenant:
        raise HTTPException(404, "Unknown tenant")

    body = await request.json()
    try:
        rpc_req = JsonRpcRequest(**body)
    except Exception:
        return JsonRpcResponse(id=body.get("id", "0"), error=JsonRpcError(code=-32600, message="Invalid Request"))

    if rpc_req.method == "message/send":
        return await _handle_message_send(tenant_slug, tenant, rpc_req)
    elif rpc_req.method == "tasks/get":
        return _handle_tasks_get(rpc_req)
    elif rpc_req.method == "tasks/cancel":
        return _handle_tasks_cancel(rpc_req)
    else:
        return JsonRpcResponse(id=rpc_req.id, error=JsonRpcError(code=ERR_METHOD_NOT_FOUND, message=f"Unknown method {rpc_req.method}"))


async def _handle_message_send(tenant_slug: str, tenant: dict, rpc_req: JsonRpcRequest) -> JsonRpcResponse:
    params = rpc_req.params
    skill_id = params.get("skillId")
    skill_params = params.get("parameters", {})

    if not skill_id:
        return JsonRpcResponse(id=rpc_req.id, error=JsonRpcError(code=ERR_INVALID_PARAMS, message="Missing skillId"))

    storage.increment_call_count(tenant_slug)

    task = await execute_skill(
        skill_id=skill_id,
        operation_map=tenant["operation_map"],
        base_url=tenant["upstream_base_url"],
        upstream_auth_header=tenant["upstream_auth_header"],
        params=skill_params,
    )
    task_dict = task.model_dump(exclude_none=True)
    storage.save_task(task.id, task_dict)
    return JsonRpcResponse(id=rpc_req.id, result=task_dict)


def _handle_tasks_get(rpc_req: JsonRpcRequest) -> JsonRpcResponse:
    task_id = rpc_req.params.get("taskId")
    task_dict = storage.load_task(task_id) if task_id else None
    if not task_dict:
        return JsonRpcResponse(id=rpc_req.id, error=JsonRpcError(code=ERR_TASK_NOT_FOUND, message="Task not found"))
    return JsonRpcResponse(id=rpc_req.id, result=task_dict)


def _handle_tasks_cancel(rpc_req: JsonRpcRequest) -> JsonRpcResponse:
    task_id = rpc_req.params.get("taskId")
    task_dict = storage.load_task(task_id) if task_id else None
    if not task_dict:
        return JsonRpcResponse(id=rpc_req.id, error=JsonRpcError(code=ERR_TASK_NOT_FOUND, message="Task not found"))
    task_dict["status"]["state"] = TaskState.CANCELED.value
    storage.save_task(task_id, task_dict)
    return JsonRpcResponse(id=rpc_req.id, result=task_dict)


@app.post("/t/{tenant_slug}/mcp")
async def mcp_endpoint(tenant_slug: str, request: Request):
    """MCP Streamable HTTP endpoint — same engine as /rpc, MCP-shaped."""
    tenant = _load_tenant_for_runtime(tenant_slug)
    if not tenant:
        raise HTTPException(404, "Unknown tenant")

    body = await request.json()
    response = await handle_mcp(
        body,
        card=tenant["card"],
        operation_map=tenant["operation_map"],
        upstream_base_url=tenant["upstream_base_url"],
        upstream_auth_header=tenant["upstream_auth_header"],
        on_call=lambda: storage.increment_call_count(tenant_slug),
    )
    if response is None:  # notification — no content
        return JSONResponse(content=None, status_code=202)
    return JSONResponse(content=response)


@app.post("/waitlist")
def join_waitlist(req: WaitlistRequest):
    is_new = storage.add_waitlist_email(req.email.lower())
    return {"status": "joined" if is_new else "already_joined", "email": req.email}


@app.get("/health")
def health():
    tenants = storage.list_all_tenants()
    return {"status": "ok", "tenants": len(tenants)}


@app.get("/admin/tenants")
def list_tenants():
    rows = storage.list_all_tenants()
    result = {}
    for r in rows:
        card = json.loads(r["card_json"])
        result[r["slug"]] = {
            "skills": len(card.get("skills", [])),
            "calls": r["call_count"],
            "created_at": r["created_at"],
        }
    return result
