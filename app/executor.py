"""
Runtime executor: takes an incoming A2A task (skill_id + structured params),
looks up the operation mapping produced by the converter, and makes the
actual upstream HTTP call against the customer's real API — then wraps the
result back into an A2A Task/Artifact.

This is the part that runs continuously, unattended, per tenant.
"""
from __future__ import annotations
import re
import httpx
from typing import Any
from app.models import Task, TaskStatus, TaskState, Artifact, MessagePart, Message


class UpstreamCallError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _fill_path_params(path: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Substitutes {param} placeholders in the path; returns (filled_path, remaining_params)."""
    remaining = dict(params)
    def repl(match):
        key = match.group(1)
        if key not in remaining:
            raise ValueError(f"Missing required path parameter: {key}")
        return str(remaining.pop(key))
    filled = re.sub(r"\{(\w+)\}", repl, path)
    return filled, remaining


def _split_params_by_location(
    op: dict[str, Any], filled_path_keys: set[str], all_params: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Splits the remaining (non-path) params into query vs body based on the
    operation's declared parameter locations (OpenAPI 'in' field). Falls back
    to query-string for everything if no schema info is available, since
    that's the safer default for GET-shaped wrapped APIs.
    """
    declared = {p["name"]: p.get("in", "query") for p in op.get("parameters", [])}
    query_params: dict[str, Any] = {}
    body_params: dict[str, Any] = {}

    for key, value in all_params.items():
        if key in filled_path_keys:
            continue
        location = declared.get(key, "query")
        if location == "query":
            query_params[key] = value
        else:  # 'body' or unspecified-but-has-requestBody
            body_params[key] = value

    # If the op declares a requestBody but params with in='query' weren't found
    # for some keys, anything not explicitly query-tagged falls back to body
    # when requestBody is present.
    if op.get("requestBody") and not declared:
        body_params, query_params = query_params, {}

    return query_params, body_params


async def execute_skill(
    *,
    skill_id: str,
    operation_map: dict[str, dict],
    base_url: str,
    upstream_auth_header: dict[str, str] | None,
    params: dict[str, Any],
) -> Task:
    """
    Executes one A2A skill invocation against the tenant's real upstream API.
    Returns a fully-populated Task in COMPLETED or FAILED state.
    """
    if skill_id not in operation_map:
        return Task(
            status=TaskStatus(
                state=TaskState.REJECTED,
                message=Message(role="agent", parts=[MessagePart(text=f"Unknown skill: {skill_id}")]),
            )
        )

    op = operation_map[skill_id]
    method = op["method"]
    raw_path = op.get("path", "/")
    upstream_base = op.get("base_url", base_url)

    path_keys = set(re.findall(r"\{(\w+)\}", raw_path))
    try:
        path, remaining = _fill_path_params(raw_path, params)
    except ValueError as e:
        return Task(status=TaskStatus(state=TaskState.REJECTED,
                    message=Message(role="agent", parts=[MessagePart(text=str(e))])))

    query_params, body_params = _split_params_by_location(op, path_keys, params)

    url = upstream_base.rstrip("/") + path
    headers = dict(upstream_auth_header or {})

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if method in ("GET", "DELETE"):
                resp = await client.request(method, url, params=query_params, headers=headers)
            else:
                resp = await client.request(method, url, params=query_params, json=body_params or None, headers=headers)
        except httpx.RequestError as e:
            return Task(
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(role="agent", parts=[MessagePart(text=f"Upstream request failed: {e}")]),
                )
            )

    if resp.status_code >= 400:
        return Task(
            status=TaskStatus(
                state=TaskState.FAILED,
                message=Message(role="agent", parts=[
                    MessagePart(text=f"Upstream returned {resp.status_code}: {resp.text[:500]}")
                ]),
            )
        )

    try:
        body: Any = resp.json()
    except ValueError:
        body = resp.text

    return Task(
        status=TaskStatus(state=TaskState.COMPLETED),
        artifacts=[
            Artifact(name=f"{skill_id}_result", parts=[MessagePart(kind="data", data=body)])
        ],
    )
