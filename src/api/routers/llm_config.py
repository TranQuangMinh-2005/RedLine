"""Chọn endpoint + model LLM khi đang chạy, và quản lý model trên Kaggle gateway.

Luồng UI:
1. GET  /config/llm                  -> endpoint/model hiện hành + các endpoint khả dụng
2. POST /config/llm/discover         -> list model của một endpoint (lưu URL/key nếu custom)
3. POST /config/llm                  -> kích hoạt endpoint + model
4. /config/llm/gateway/*             -> catalog, tải model (có tiến trình), xóa model
                                        khi endpoint là RedLine Ollama gateway (Kaggle)
"""

from __future__ import annotations

from typing import Any, NoReturn
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from src.config import get_settings
from src.guardrails import state as defense_state
from src.logging_config import audit_event
from src.services import llm_runtime, model_gateway
from src.services.llm_runtime import LLMEndpoint
from src.services.model_catalog import (
    GROQ_FEATURED,
    OLLAMA_FEATURED,
    annotate,
    is_groq_chat_model,
)
from src.services.model_gateway import GatewayError

router = APIRouter(prefix="/config/llm", tags=["config"])

ENDPOINT_LABELS = {
    "env": "Docker environment (.env)",
    "groq": "Groq API",
    "custom": "Endpoint khác (Kaggle / URL)",
}


class DiscoverRequest(BaseModel):
    endpoint: str = "env"
    # Chỉ dùng với endpoint custom. api_key=None giữ key đã lưu cho cùng URL.
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)


class SelectRequest(DiscoverRequest):
    model: str = Field(min_length=1, max_length=200)


class PullRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._/:-]+$")


def _raise(exc: Exception) -> NoReturn:
    if isinstance(exc, GatewayError):
        raise HTTPException(status_code=502 if exc.status_code >= 500 else exc.status_code,
                            detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _resolve(req: DiscoverRequest, model: str | None = None) -> LLMEndpoint:
    try:
        if req.endpoint == "custom" and req.base_url:
            llm_runtime.set_custom_connection(req.base_url, req.api_key)
        return llm_runtime.preset(req.endpoint, model)
    except ValueError as exc:
        _raise(exc)


def _featured_for(endpoint: LLMEndpoint, gateway: bool) -> list[dict[str, Any]]:
    if endpoint.provider == "groq":
        return GROQ_FEATURED
    if gateway or endpoint.provider == "ollama":
        return OLLAMA_FEATURED
    return GROQ_FEATURED + OLLAMA_FEATURED


def _endpoint_options() -> list[dict[str, Any]]:
    options = []
    for kind in llm_runtime.ENDPOINT_KINDS:
        try:
            view = llm_runtime.public_view(llm_runtime.preset(kind))
            view["configured"] = kind != "groq" or view["has_api_key"]
        except ValueError:
            view = {"kind": kind, "base_url": "", "model": "", "provider": "",
                    "has_api_key": False, "configured": False}
        view["label"] = ENDPOINT_LABELS[kind]
        options.append(view)
    return options


def _state() -> dict[str, Any]:
    active = llm_runtime.get_active()
    return {
        "active": llm_runtime.public_view(active),
        "endpoints": _endpoint_options(),
        "target_config_hash": get_settings().target_config_hash_for(defense_state.get_active_name()),
    }


@router.get("")
def read_llm_config() -> dict[str, Any]:
    return _state()


@router.post("/discover")
def discover_models(req: DiscoverRequest) -> dict[str, Any]:
    endpoint = _resolve(req)
    try:
        gateway = model_gateway.gateway_info(endpoint) if endpoint.kind != "groq" else None
        ids = model_gateway.list_model_ids(endpoint)
    except GatewayError as exc:
        _raise(exc)
    if endpoint.provider == "groq":
        ids = [model_id for model_id in ids if is_groq_chat_model(model_id)]
    return {
        "endpoint": {**llm_runtime.public_view(endpoint), "label": ENDPOINT_LABELS[endpoint.kind]},
        "gateway": gateway,
        "models": annotate(ids, _featured_for(endpoint, gateway is not None)),
    }


@router.post("")
def select_model(req: SelectRequest) -> dict[str, Any]:
    endpoint = _resolve(req, req.model)
    try:
        available = model_gateway.list_model_ids(endpoint)
    except GatewayError as exc:
        _raise(exc)
    if req.model not in available:
        raise HTTPException(status_code=422, detail=f"model {req.model!r} không có trên endpoint")
    previous, active = llm_runtime.set_active(endpoint)
    audit_event(
        "llm_endpoint_changed",
        request_id=str(uuid4()),
        previous_endpoint=previous.kind,
        previous_model=previous.model,
        endpoint=active.kind,
        provider=active.provider,
        model=active.model,
    )
    return _state()


# ---------------- Kaggle / Ollama gateway ----------------

def _gateway_endpoint(kind: str) -> LLMEndpoint:
    try:
        endpoint = llm_runtime.preset(kind)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return endpoint


def _gateway_call(kind: str, method: str, path: str, **kwargs: Any) -> Any:
    try:
        return model_gateway.call(_gateway_endpoint(kind), method, path, **kwargs)
    except GatewayError as exc:
        _raise(exc)


EndpointQuery = Query(default="custom", pattern="^(env|custom)$")


@router.get("/gateway/catalog")
def gateway_catalog(endpoint: str = EndpointQuery) -> Any:
    return _gateway_call(endpoint, "GET", "/catalog")


@router.get("/gateway/models")
def gateway_models(endpoint: str = EndpointQuery) -> Any:
    return _gateway_call(endpoint, "GET", "/models")


@router.get("/gateway/pulls")
def gateway_pulls(endpoint: str = EndpointQuery) -> Any:
    return _gateway_call(endpoint, "GET", "/pulls")


@router.post("/gateway/pulls")
def gateway_start_pull(req: PullRequest, endpoint: str = EndpointQuery) -> Any:
    result = _gateway_call(endpoint, "POST", "/pulls", json={"model": req.model})
    audit_event("llm_model_pull_started", request_id=str(uuid4()), endpoint=endpoint, model=req.model)
    return result


@router.delete("/gateway/pulls/{job_id}")
def gateway_cancel_pull(job_id: str, endpoint: str = EndpointQuery) -> Any:
    return _gateway_call(endpoint, "DELETE", f"/pulls/{job_id}")


@router.delete("/gateway/models/{model:path}")
def gateway_delete_model(model: str, endpoint: str = EndpointQuery) -> Any:
    try:
        PullRequest(model=model)  # validate tên model
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="tên model không hợp lệ") from exc
    if llm_runtime.get_active().model == model:
        raise HTTPException(status_code=409, detail="không xóa model đang được sử dụng")
    result = _gateway_call(endpoint, "DELETE", f"/models/{model}")
    audit_event("llm_model_deleted", request_id=str(uuid4()), endpoint=endpoint, model=model)
    return result
