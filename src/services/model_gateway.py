"""Client HTTP gọi endpoint LLM từ backend (list model + Kaggle Ollama gateway).

Trình duyệt không gọi thẳng Kaggle: web -> FastAPI -> gateway, nên token của
gateway chỉ nằm ở server và không bị CORS chặn.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.services.llm_runtime import LLMEndpoint

# ngrok free hiển thị trang cảnh báo HTML nếu thiếu header này.
NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}
TIMEOUT = httpx.Timeout(15.0, connect=10.0)


class GatewayError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _headers(endpoint: LLMEndpoint) -> dict[str, str]:
    headers = dict(NGROK_HEADERS)
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    return headers


def gateway_root(endpoint: LLMEndpoint) -> str:
    return endpoint.base_url.removesuffix("/v1")


def _request(method: str, url: str, endpoint: LLMEndpoint, **kwargs: Any) -> Any:
    try:
        response = httpx.request(method, url, headers=_headers(endpoint), timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError as exc:
        raise GatewayError(f"không kết nối được endpoint ({type(exc).__name__})") from exc
    if response.status_code in {401, 403}:
        raise GatewayError("endpoint từ chối API key/token", 401)
    if response.status_code >= 400:
        detail = ""
        try:
            detail = str(response.json().get("detail") or "")
        except ValueError:
            pass
        raise GatewayError(detail or f"endpoint trả HTTP {response.status_code}", response.status_code)
    try:
        return response.json()
    except ValueError as exc:
        raise GatewayError("endpoint không trả JSON (sai URL hoặc trang cảnh báo ngrok?)") from exc


def list_model_ids(endpoint: LLMEndpoint) -> list[str]:
    data = _request("GET", f"{endpoint.base_url}/models", endpoint)
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise GatewayError("endpoint /models trả dữ liệu không đúng chuẩn OpenAI")
    return [str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")]


def gateway_info(endpoint: LLMEndpoint) -> dict[str, Any] | None:
    """Trả info nếu endpoint là RedLine Ollama gateway, None nếu không phải."""
    try:
        info = _request("GET", f"{gateway_root(endpoint)}/gateway/info", endpoint)
    except GatewayError as exc:
        if exc.status_code == 401:
            raise
        return None
    return info if isinstance(info, dict) and info.get("gateway") == "redline-ollama" else None


def call(endpoint: LLMEndpoint, method: str, path: str, **kwargs: Any) -> Any:
    return _request(method, f"{gateway_root(endpoint)}/gateway{path}", endpoint, **kwargs)
