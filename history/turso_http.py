from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

from history.turso_config import turso_http_base_url

_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.4


def _encode_arg(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": str(value)}
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return {"type": "text", "value": str(value)}


def _decode_cell(cell: Any) -> Any:
    if cell is None:
        return None
    if not isinstance(cell, dict):
        return cell
    cell_type = cell.get("type")
    if cell_type == "null":
        return None
    if cell_type == "integer":
        return int(cell["value"])
    if cell_type == "float":
        return float(cell["value"])
    if cell_type == "text":
        return cell.get("value")
    if cell_type == "blob":
        return base64.b64decode(cell["base64"])
    return cell.get("value")


@dataclass
class HttpExecuteResult:
    columns: tuple[str, ...]
    rows: list[tuple[Any, ...]]
    last_insert_rowid: int | None


class TursoHttpClient:
    """Turso SQL over HTTP (/v2/pipeline)，适用于 Streamlit Cloud 等环境。"""

    def __init__(self, database_url: str, auth_token: str):
        self._base_url = turso_http_base_url(database_url).rstrip("/")
        self._token = auth_token.strip()
        self._pipeline_url = f"{self._base_url}/v2/pipeline"
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True

    def _is_transient_error(self, exc: BaseException) -> bool:
        if isinstance(exc, urllib.error.HTTPError) and exc.code in {408, 429, 500, 502, 503, 504}:
            return True
        msg = str(exc).lower()
        return "timeout" in msg or "temporarily" in msg

    def _post_pipeline(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        payload_bytes = json.dumps({"requests": requests}).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            req = urllib.request.Request(
                self._pipeline_url,
                data=payload_bytes,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = resp.read().decode("utf-8")
                return json.loads(body)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"Turso HTTP {exc.code}: {detail}")
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise last_error from exc
            except Exception as exc:
                last_error = exc
                if attempt >= _RETRY_ATTEMPTS - 1 or not self._is_transient_error(exc):
                    raise RuntimeError(f"Turso HTTP 请求失败: {exc}") from exc
            if attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_BASE_DELAY * (attempt + 1))
        if isinstance(last_error, RuntimeError):
            raise last_error
        if last_error is not None:
            raise RuntimeError(f"Turso HTTP 请求失败: {last_error}") from last_error
        raise RuntimeError("Turso HTTP 请求失败")

    def _parse_execute_result(self, result_item: dict[str, Any]) -> HttpExecuteResult:
        if result_item.get("type") == "error":
            raise RuntimeError(f"Turso SQL 错误: {result_item.get('error', result_item)}")

        response = result_item.get("response") or {}
        if response.get("type") != "execute":
            return HttpExecuteResult((), [], None)

        result = response.get("result") or {}
        columns = tuple(col.get("name", "") for col in result.get("cols", []))
        rows: list[tuple[Any, ...]] = []
        for raw_row in result.get("rows", []):
            if isinstance(raw_row, list):
                rows.append(tuple(_decode_cell(cell) for cell in raw_row))
            else:
                rows.append((_decode_cell(raw_row),))

        last_id = result.get("last_insert_rowid")
        last_insert_rowid = int(last_id) if last_id is not None else None
        return HttpExecuteResult(columns, rows, last_insert_rowid)

    def execute(self, sql: str, parameters: Iterable[Any] | None = None) -> HttpExecuteResult:
        if self._closed:
            raise RuntimeError("Turso HTTP 连接已关闭")

        stmt: dict[str, Any] = {"sql": sql}
        if parameters is not None:
            stmt["args"] = [_encode_arg(value) for value in parameters]

        payload = self._post_pipeline(
            [
                {"type": "execute", "stmt": stmt},
                {"type": "close"},
            ]
        )
        results = payload.get("results") or []
        if not results:
            return HttpExecuteResult((), [], None)
        return self._parse_execute_result(results[0])

    def execute_many(self, sql: str, seq_of_parameters: Iterable[Iterable[Any]]) -> HttpExecuteResult | None:
        last_result: HttpExecuteResult | None = None
        for params in seq_of_parameters:
            last_result = self.execute(sql, params)
        return last_result

    def execute_batch(self, statements: list[str]) -> None:
        if not statements:
            return
        requests = [{"type": "execute", "stmt": {"sql": sql}} for sql in statements]
        requests.append({"type": "close"})
        payload = self._post_pipeline(requests)
        for item in payload.get("results") or []:
            if item.get("type") == "error":
                raise RuntimeError(f"Turso SQL 错误: {item.get('error', item)}")
            if item.get("response", {}).get("type") == "execute":
                continue
            if item.get("response", {}).get("type") == "close":
                break
