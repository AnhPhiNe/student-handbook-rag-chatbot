from __future__ import annotations

from typing import Any

import requests


DEFAULT_API_ERROR_ANSWER = (
    "Không kết nối được API backend. Bạn kiểm tra FastAPI server đã chạy chưa."
)


class ChatApiClient:
    """Small Streamlit-side client for the FastAPI chat endpoint."""

    def __init__(self, base_url: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.timeout_seconds = timeout_seconds

    def answer(self, query: str, include_debug: bool = False) -> dict[str, Any]:
        url = f"{self.base_url}/chat"
        payload = {"query": query, "include_debug": include_debug}

        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        except requests.exceptions.Timeout as exc:
            return self._error_result(
                query=query,
                error_type="api_timeout",
                error_message=str(exc),
                include_debug=include_debug,
            )
        except requests.exceptions.ConnectionError as exc:
            return self._error_result(
                query=query,
                error_type="api_connection_error",
                error_message=str(exc),
                include_debug=include_debug,
            )
        except requests.exceptions.RequestException as exc:
            return self._error_result(
                query=query,
                error_type="api_request_error",
                error_message=str(exc),
                include_debug=include_debug,
            )

        if response.status_code != 200:
            return self._error_result(
                query=query,
                error_type="api_http_error",
                error_message=f"HTTP {response.status_code}: {self._response_detail(response)}",
                include_debug=include_debug,
            )

        try:
            data = response.json()
        except ValueError as exc:
            return self._error_result(
                query=query,
                error_type="api_invalid_json",
                error_message=str(exc),
                include_debug=include_debug,
            )

        if not isinstance(data, dict):
            return self._error_result(
                query=query,
                error_type="api_invalid_json",
                error_message="API response JSON is not an object.",
                include_debug=include_debug,
            )

        data.setdefault("query", query)
        return data

    def _error_result(
        self,
        *,
        query: str,
        error_type: str,
        error_message: str,
        include_debug: bool,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "query": query,
            "answer": DEFAULT_API_ERROR_ANSWER,
            "status": error_type,
            "error_type": error_type,
            "error_message": error_message,
            "citations_used": [],
            "llm_called": False,
            "used_cache": False,
            "clarification_needed": False,
            "intent": None,
            "strategy": None,
        }
        if include_debug:
            result["debug"] = {
                "error_type": error_type,
                "error_message": error_message,
                "api_base_url": self.base_url,
            }
        return result

    @staticmethod
    def _response_detail(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text[:500].strip()

        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
        return str(body)[:500]
