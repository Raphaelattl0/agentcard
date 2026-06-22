"""
MCP façade — second output format over the SAME tenant engine as A2A.

A2A exposes a tenant's wrapped API as an Agent Card + JSON-RPC (message/send).
MCP exposes the exact same operations as an MCP server over Streamable HTTP,
so an MCP client (Claude Desktop, IDEs, etc.) can list and call the tools.

Both share one operation_map and one executor (app.executor.execute_skill).
Nothing about the upstream call logic is duplicated here — this module only
translates MCP's JSON-RPC shapes to/from that engine.

Spec: https://modelcontextprotocol.io  (JSON-RPC 2.0 methods:
initialize, tools/list, tools/call, plus the initialized notification).
"""
from __future__ import annotations

from typing import Any

from app.executor import execute_skill

SUPPORTED_PROTOCOL = "2025-06-18"
SERVER_VERSION = "1.0.0"


def _json_schema_for_op(op: dict[str, Any]) -> dict[str, Any]:
    """Builds an MCP tool inputSchema (JSON Schema) from an operation's params."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in op.get("parameters", []):
        name = p.get("name")
        if not name:
            continue
        properties[name] = {"type": p.get("type", "string")}
        if p.get("description"):
            properties[name]["description"] = p["description"]
        if p.get("required"):
            required.append(name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def build_tools(card: Any, operation_map: dict[str, dict]) -> list[dict[str, Any]]:
    """One MCP tool per skill, descriptions pulled from the signed Agent Card."""
    desc_by_id = {s.id: (s.description or s.name or s.id) for s in card.skills}
    tools = []
    for skill_id, op in operation_map.items():
        tools.append({
            "name": skill_id,
            "description": desc_by_id.get(skill_id, skill_id),
            "inputSchema": _json_schema_for_op(op),
        })
    return tools


def _result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def handle_mcp(
    body: dict[str, Any],
    *,
    card: Any,
    operation_map: dict[str, dict],
    upstream_base_url: str,
    upstream_auth_header: dict[str, str] | None,
    on_call=None,
) -> dict[str, Any] | None:
    """
    Handles one MCP JSON-RPC request. Returns a response dict, or None for
    notifications (which must not produce a response body).
    `on_call` is an optional callback invoked on each tools/call (for metering).
    """
    method = body.get("method")
    req_id = body.get("id")

    if method == "initialize":
        client_proto = (body.get("params") or {}).get("protocolVersion", SUPPORTED_PROTOCOL)
        return _result(req_id, {
            "protocolVersion": client_proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": card.name, "version": SERVER_VERSION},
        })

    # Notifications (no id) — e.g. notifications/initialized. No response body.
    if method and method.startswith("notifications/"):
        return None

    if method == "tools/list":
        return _result(req_id, {"tools": build_tools(card, operation_map)})

    if method == "tools/call":
        params = body.get("params") or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if tool_name not in operation_map:
            return _error(req_id, -32602, f"Unknown tool: {tool_name}")

        if on_call:
            on_call()

        task = await execute_skill(
            skill_id=tool_name,
            operation_map=operation_map,
            base_url=upstream_base_url,
            upstream_auth_header=upstream_auth_header,
            params=arguments,
        )
        task_dict = task.model_dump(exclude_none=True)
        state = task_dict.get("status", {}).get("state")
        is_error = state in ("failed", "rejected")

        # Flatten the A2A Task result into MCP content blocks.
        text = _task_to_text(task_dict)
        return _result(req_id, {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        })

    return _error(req_id, -32601, f"Method not found: {method}")


def _task_to_text(task_dict: dict[str, Any]) -> str:
    """Extracts a human/agent-readable string from an executor Task result."""
    import json

    artifacts = task_dict.get("artifacts") or []
    for art in artifacts:
        for part in art.get("parts", []):
            if part.get("kind") == "data" and "data" in part:
                data = part["data"]
                return data if isinstance(data, str) else json.dumps(data, indent=2)
            if part.get("text"):
                return part["text"]
    # Fall back to the status message (covers FAILED/REJECTED cases).
    msg = task_dict.get("status", {}).get("message", {})
    for part in msg.get("parts", []):
        if part.get("text"):
            return part["text"]
    return json.dumps(task_dict)
