"""
Converts an OpenAPI 3.x spec into an A2A Agent Card + skill->operation map.

This is the core "instant A2A-ification" logic: a customer gives us an
OpenAPI spec (or a handful of manually described endpoints), and we produce:
  1. A spec-compliant Agent Card (name, description, skills[])
  2. A mapping table: skill_id -> {method, path, base_url, param schema}
so the runtime wrapper knows which upstream REST call to make per skill.
"""
from __future__ import annotations
from typing import Any
from app.models import AgentSkill, AgentCapabilities, AgentCard, AgentProvider


def _operation_to_skill(path: str, http_method: str, op: dict[str, Any]) -> tuple[AgentSkill, dict]:
    op_id = op.get("operationId") or f"{http_method}_{path}".replace("/", "_").strip("_")
    summary = op.get("summary") or op.get("description") or f"{http_method.upper()} {path}"
    description = op.get("description") or summary

    # Build a richer description for LLM-based orchestrator routing —
    # vague descriptions make a skill undiscoverable in practice.
    params_desc = []
    for p in op.get("parameters", []):
        params_desc.append(f"{p.get('name')} ({p.get('in')}, {'required' if p.get('required') else 'optional'})")
    if params_desc:
        description += " Parameters: " + ", ".join(params_desc) + "."

    skill = AgentSkill(
        id=op_id,
        name=summary,
        description=description,
        tags=op.get("tags", []),
    )

    mapping = {
        "method": http_method.upper(),
        "path": path,
        "parameters": op.get("parameters", []),
        "requestBody": op.get("requestBody"),
    }
    return skill, mapping


def openapi_to_agent_card(
    openapi_spec: dict[str, Any],
    *,
    agent_url: str,
    organization: str | None = None,
    provider_url: str | None = None,
) -> tuple[AgentCard, dict[str, dict]]:
    """
    Returns (AgentCard, skill_id -> upstream operation mapping).
    The mapping is stored server-side and used by the runtime wrapper
    to translate an incoming A2A task into the correct upstream HTTP call.
    """
    info = openapi_spec.get("info", {})
    title = info.get("title", "Wrapped API Agent")
    description = info.get("description", f"A2A agent wrapping {title}")
    version = info.get("version", "1.0.0")

    skills: list[AgentSkill] = []
    operation_map: dict[str, dict] = {}

    for path, path_item in openapi_spec.get("paths", {}).items():
        for http_method, op in path_item.items():
            if http_method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            skill, mapping = _operation_to_skill(path, http_method, op)
            skills.append(skill)
            operation_map[skill.id] = mapping

    provider = None
    if organization:
        provider = AgentProvider(organization=organization, url=provider_url or agent_url)

    card = AgentCard(
        name=title,
        description=description,
        version=version,
        url=agent_url,
        provider=provider,
        capabilities=AgentCapabilities(streaming=True, pushNotifications=False, stateTransitionHistory=True),
        skills=skills,
        securitySchemes={
            "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
        },
        security=[{"ApiKeyAuth": []}],
    )
    return card, operation_map


def manual_skills_to_agent_card(
    *,
    name: str,
    description: str,
    agent_url: str,
    upstream_base_url: str,
    endpoints: list[dict[str, Any]],
    organization: str | None = None,
) -> tuple[AgentCard, dict[str, dict]]:
    """
    Fallback path for customers without an OpenAPI spec: they describe a
    handful of endpoints by hand (method, path, description, params) and we
    produce the same Agent Card + mapping output.

    endpoints: [{ "id": "...", "name": "...", "description": "...",
                  "method": "GET", "path": "/orders/{id}",
                  "parameters": [...] }]
    """
    skills = []
    operation_map = {}
    for ep in endpoints:
        skill = AgentSkill(
            id=ep["id"],
            name=ep["name"],
            description=ep["description"],
            tags=ep.get("tags", []),
        )
        skills.append(skill)
        operation_map[ep["id"]] = {
            "method": ep["method"].upper(),
            "path": ep["path"],
            "parameters": ep.get("parameters", []),
            "requestBody": ep.get("requestBody"),
            "base_url": upstream_base_url,
        }

    provider = AgentProvider(organization=organization, url=agent_url) if organization else None
    card = AgentCard(
        name=name,
        description=description,
        version="1.0.0",
        url=agent_url,
        provider=provider,
        capabilities=AgentCapabilities(streaming=True, stateTransitionHistory=True),
        skills=skills,
        securitySchemes={"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
        security=[{"ApiKeyAuth": []}],
    )
    return card, operation_map
