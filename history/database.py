from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from auth.user_context import get_current_user_id, get_user_data_dir
from history.turso_config import get_turso_credentials, turso_configured, turso_url_candidates

INIT_DB_SCRIPT = """
CREATE TABLE IF NOT EXISTS uploads (
    upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    source_filename TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL,
    campaign_name TEXT NOT NULL,
    date TEXT NOT NULL,
    budget REAL NOT NULL,
    spend REAL NOT NULL,
    usage_rate REAL,
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_budget_daily_cell
    ON budget_daily(campaign_name, date, upload_id);
CREATE INDEX IF NOT EXISTS idx_uploads_type_time
    ON uploads(report_type, uploaded_at);

CREATE TABLE IF NOT EXISTS placement_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL,
    campaign_name TEXT NOT NULL,
    placement TEXT NOT NULL,
    date TEXT NOT NULL,
    impressions REAL,
    clicks REAL,
    ctr REAL,
    orders REAL,
    cvr REAL,
    cpc REAL,
    spend REAL,
    sales REAL,
    acos REAL,
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_placement_daily_cell
    ON placement_daily(campaign_name, placement, date, upload_id);

CREATE TABLE IF NOT EXISTS keyword_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    keyword TEXT NOT NULL,
    match_type TEXT NOT NULL,
    date TEXT NOT NULL,
    impressions REAL,
    clicks REAL,
    ctr REAL,
    orders REAL,
    cvr REAL,
    cpc REAL,
    spend REAL,
    sales REAL,
    acos REAL,
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_keyword_daily_cell
    ON keyword_daily(campaign_name, ad_group_name, keyword, match_type, date, upload_id);

CREATE TABLE IF NOT EXISTS search_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    target_keyword TEXT NOT NULL,
    match_type TEXT NOT NULL,
    search_term TEXT NOT NULL,
    date TEXT NOT NULL,
    impressions REAL,
    clicks REAL,
    ctr REAL,
    orders REAL,
    cvr REAL,
    cpc REAL,
    spend REAL,
    sales REAL,
    acos REAL,
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_search_daily_cell
    ON search_daily(campaign_name, ad_group_name, target_keyword, match_type, search_term, date, upload_id);

CREATE TABLE IF NOT EXISTS search_share_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL,
    search_term TEXT NOT NULL,
    date TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    keyword TEXT NOT NULL,
    match_type TEXT NOT NULL,
    impression_rank REAL,
    impression_share REAL,
    clicks REAL,
    spend REAL,
    orders REAL,
    sales REAL,
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_search_share_daily_cell
    ON search_share_daily(
        search_term, date, campaign_name, ad_group_name, keyword, match_type, upload_id
    );

CREATE TABLE IF NOT EXISTS product_sponsored_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    asin TEXT NOT NULL,
    sku TEXT NOT NULL,
    date TEXT NOT NULL,
    impressions REAL,
    clicks REAL,
    ctr REAL,
    cpc REAL,
    spend REAL,
    sales REAL,
    acos REAL,
    orders REAL,
    units REAL,
    cvr REAL,
    roas REAL,
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_product_sponsored_daily_cell
    ON product_sponsored_daily(
        campaign_name, ad_group_name, asin, sku, date, upload_id
    );

CREATE TABLE IF NOT EXISTS ops_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date TEXT NOT NULL,
    asin TEXT,
    campaign_name TEXT,
    ad_group_name TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_journal_event_date
    ON ops_journal(event_date);
"""

_TURSO_RETRY_ATTEMPTS = 3
_TURSO_RETRY_BASE_DELAY = 0.4
_INIT_FLAGS: set[str] = set()


def get_db_path() -> Path:
    return get_user_data_dir() / "ad_history.db"


def _is_transient_turso_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if "Handshake" in name or "WSServerHandshakeError" in name:
        return True
    msg = str(exc).lower()
    return "handshake" in msg or "connection reset" in msg or "connection closed" in msg


class _DictRow(dict):
    """兼容 sqlite3.Row：支持 dict(row) 与 row['col']。"""


class _TursoCursor:
    def __init__(self, result, lastrowid):
        self._result = result
        self.lastrowid = lastrowid

    def fetchall(self) -> list[_DictRow]:
        if self._result is None or not getattr(self._result, "rows", None):
            return []
        columns = getattr(self._result, "columns", None) or []
        rows: list[_DictRow] = []
        for row in self._result.rows:
            if hasattr(row, "asdict"):
                rows.append(_DictRow(row.asdict()))
            elif isinstance(row, dict):
                rows.append(_DictRow(row))
            elif columns:
                rows.append(_DictRow(dict(zip(columns, row))))
            else:
                rows.append(_DictRow({"value": row}))
        return rows


class _TursoConnection:
    """libsql-client 远程连接；支持 batch 与重试。"""

    def __init__(self, url: str, token: str):
        import libsql_client

        self._libsql_client = libsql_client
        self._url = url
        self._token = token
        self._client = self._create_client()
        self.row_factory = sqlite3.Row

    def _create_client(self):
        last_error: Exception | None = None
        for candidate in turso_url_candidates(self._url):
            try:
                return self._libsql_client.create_client_sync(
                    url=candidate,
                    auth_token=self._token,
                )
            except Exception as exc:
                last_error = exc
                if not _is_transient_turso_error(exc):
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("无法创建 Turso 客户端")

    def _recreate_client(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
        self._client = self._create_client()

    def _run(self, sql: str, parameters: Iterable[Any] | None = None):
        last_error: Exception | None = None
        for attempt in range(_TURSO_RETRY_ATTEMPTS):
            try:
                if parameters is None:
                    return self._client.execute(sql)
                return self._client.execute(sql, list(parameters))
            except Exception as exc:
                last_error = exc
                if attempt >= _TURSO_RETRY_ATTEMPTS - 1 or not _is_transient_turso_error(exc):
                    raise
                self._recreate_client()
                time.sleep(_TURSO_RETRY_BASE_DELAY * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError("Turso 执行失败")

    def execute(self, sql: str, parameters: Iterable[Any] | None = None) -> _TursoCursor:
        result = self._run(sql, parameters)
        return _TursoCursor(result, result.last_insert_rowid)

    def executemany(self, sql: str, seq_of_parameters: Iterable[Iterable[Any]]) -> _TursoCursor:
        for params in seq_of_parameters:
            self.execute(sql, params)
        return _TursoCursor(None, None)

    def executescript(self, sql_script: str) -> None:
        statements = _split_sql_script(sql_script)
        if not statements:
            return
        if len(statements) == 1:
            self.execute(statements[0])
            return

        last_error: Exception | None = None
        for attempt in range(_TURSO_RETRY_ATTEMPTS):
            try:
                self._client.batch(statements)
                return
            except Exception as exc:
                last_error = exc
                if attempt >= _TURSO_RETRY_ATTEMPTS - 1 or not _is_transient_turso_error(exc):
                    break
                self._recreate_client()
                time.sleep(_TURSO_RETRY_BASE_DELAY * (attempt + 1))

        for statement in statements:
            self.execute(statement)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


def _split_sql_script(sql_script: str) -> list[str]:
    statements: list[str] = []
    for part in sql_script.split(";"):
        stmt = part.strip()
        if stmt:
            statements.append(stmt)
    return statements


def _turso_session_cache_key(user_id: str, url: str) -> str:
    return f"_turso_conn_{user_id}_{hash(url)}"


def _get_cached_turso_connection(user_id: str, url: str) -> _TursoConnection | None:
    try:
        import streamlit as st

        conn = st.session_state.get(_turso_session_cache_key(user_id, url))
        if isinstance(conn, _TursoConnection):
            if getattr(conn._client, "closed", False):
                return None
            return conn
    except Exception:
        pass
    return None


def _set_cached_turso_connection(user_id: str, url: str, conn: _TursoConnection) -> None:
    try:
        import streamlit as st

        st.session_state[_turso_session_cache_key(user_id, url)] = conn
    except Exception:
        pass


def _invalidate_cached_turso_connection(user_id: str, url: str) -> None:
    try:
        import streamlit as st

        key = _turso_session_cache_key(user_id, url)
        conn = st.session_state.pop(key, None)
        if isinstance(conn, _TursoConnection):
            conn.close()
    except Exception:
        pass


def _connect_turso(url: str, token: str, *, user_id: str | None = None) -> _TursoConnection:
    if user_id is None:
        user_id = get_current_user_id()

    cached = _get_cached_turso_connection(user_id, url)
    if cached is not None:
        return cached

    conn = _TursoConnection(url, token)
    _set_cached_turso_connection(user_id, url, conn)
    return conn


def _init_flag_key() -> str:
    if turso_configured():
        return f"history_db_initialized_{get_current_user_id()}"
    return f"history_db_initialized_local_{get_user_data_dir()}"


def _is_db_initialized() -> bool:
    key = _init_flag_key()
    try:
        import streamlit as st

        if st.session_state.get(key):
            return True
    except Exception:
        pass
    return key in _INIT_FLAGS


def _mark_db_initialized() -> None:
    key = _init_flag_key()
    try:
        import streamlit as st

        st.session_state[key] = True
    except Exception:
        pass
    _INIT_FLAGS.add(key)


@contextmanager
def get_connection():
    if turso_configured():
        creds = get_turso_credentials()
        if creds is None:
            user_id = get_current_user_id()
            raise RuntimeError(f"未配置用户 {user_id} 的 Turso 连接（turso.databases / turso.tokens）")
        url, token = creds
        user_id = get_current_user_id()
        conn = _connect_turso(url, token, user_id=user_id)
        close_after = False
    else:
        conn = sqlite3.connect(get_db_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        close_after = True

    try:
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if turso_configured() and _is_transient_turso_error(exc):
            _invalidate_cached_turso_connection(get_current_user_id(), url)
        raise
    finally:
        if close_after:
            conn.close()


def init_db() -> None:
    if _is_db_initialized():
        return

    with get_connection() as conn:
        conn.executescript(INIT_DB_SCRIPT)

    _mark_db_initialized()
