from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from auth.user_context import get_current_user_id, get_user_data_dir
from history.turso_config import get_turso_credentials, turso_configured

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


def get_db_path() -> Path:
    return get_user_data_dir() / "ad_history.db"


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
    """libsql-client 远程连接的 sqlite3 风格包装。"""

    def __init__(self, url: str, token: str):
        import libsql_client

        self._client = libsql_client.create_client_sync(url=url, auth_token=token)
        self.row_factory = sqlite3.Row

    def _run(self, sql: str, parameters: Iterable[Any] | None = None):
        if parameters is None:
            return self._client.execute(sql)
        return self._client.execute(sql, list(parameters))

    def execute(self, sql: str, parameters: Iterable[Any] | None = None) -> _TursoCursor:
        result = self._run(sql, parameters)
        return _TursoCursor(result, result.last_insert_rowid)

    def executemany(self, sql: str, seq_of_parameters: Iterable[Iterable[Any]]) -> _TursoCursor:
        for params in seq_of_parameters:
            self.execute(sql, params)
        return _TursoCursor(None, None)

    def executescript(self, sql_script: str) -> None:
        for statement in _split_sql_script(sql_script):
            self.execute(statement)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self._client.close()


def _split_sql_script(sql_script: str) -> list[str]:
    statements: list[str] = []
    for part in sql_script.split(";"):
        stmt = part.strip()
        if stmt:
            statements.append(stmt)
    return statements


def _connect_turso(url: str, token: str) -> _TursoConnection:
    return _TursoConnection(url, token)


@contextmanager
def get_connection():
    if turso_configured():
        creds = get_turso_credentials()
        if creds is None:
            user_id = get_current_user_id()
            raise RuntimeError(f"未配置用户 {user_id} 的 Turso 连接（turso.databases / turso.tokens）")
        url, token = creds
        conn = _connect_turso(url, token)
    else:
        conn = sqlite3.connect(get_db_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(INIT_DB_SCRIPT)
