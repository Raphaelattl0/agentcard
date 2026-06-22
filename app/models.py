"""
Core A2A data models.
Implements the subset of the A2A v1.x spec needed to wrap an arbitrary REST API
as a spec-compliant A2A Server: Agent Card, Agent Skill, Task lifecycle, JSON-RPC envelope.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid
import time


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------

class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = True


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    inputModes: list[str] = Field(default_factory=lambda: ["application/json"])
    outputModes: list[str] = Field(default_factory=lambda: ["application/json"])
    # The underlying REST operation this skill wraps (not part of spec, internal mapping)
    tags: list[str] = Field(default_factory=list)


class AgentProvider(BaseModel):
    organization: str
    url: str


class AgentCardSignature(BaseModel):
    protected: str  # base64url JWS header
    signature: str  # base64url signature


class AgentCard(BaseModel):
    name: str
    description: str
    version: str
    url: str
    provider: Optional[AgentProvider] = None
    documentationUrl: Optional[str] = None
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    defaultInputModes: list[str] = Field(default_factory=lambda: ["application/json"])
    defaultOutputModes: list[str] = Field(default_factory=lambda: ["application/json"])
    skills: list[AgentSkill] = Field(default_factory=list)
    securitySchemes: dict[str, Any] = Field(default_factory=dict)
    security: list[dict[str, list[str]]] = Field(default_factory=list)
    signatures: list[AgentCardSignature] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Task lifecycle
# ---------------------------------------------------------------------------

class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"


class MessagePart(BaseModel):
    kind: str = "text"  # text | file | data
    text: Optional[str] = None
    data: Optional[Any] = None


class Message(BaseModel):
    role: str  # "user" | "agent"
    parts: list[MessagePart]
    messageId: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Artifact(BaseModel):
    artifactId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    parts: list[MessagePart]


class TaskStatus(BaseModel):
    state: TaskState
    message: Optional[Message] = None
    timestamp: float = Field(default_factory=time.time)


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    contextId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    history: list[TaskStatus] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None


# Standard A2A / JSON-RPC error codes
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_TASK_NOT_FOUND = -32001
ERR_UPSTREAM_FAILED = -32010
