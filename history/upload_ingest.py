"""入库公共逻辑：先写 uploads 批次，再批量写 daily 明细。

Turso 下若 executemany 失败，会尝试删除刚插入的 upload 行，避免孤儿批次。
"""
from __future__ import annotations

from collections.abc import Callable

from history.database import UPLOAD_INSERT_SQL, _TursoConnection

_DELETE_UPLOAD_SQL = "DELETE FROM uploads WHERE upload_id = ?"


def insert_upload_with_daily_rows(
    conn,
    *,
    report_type: str,
    uploaded_at: str,
    period_start: str,
    period_end: str,
    source_filename: str,
    daily_sql: str,
    build_rows: Callable[[int], list[tuple]],
) -> int:
    """
    写入 uploads 批次与明细行。
    Turso 下明细行通过单次 pipeline 批量提交；失败时删除孤儿 upload 行。
    """
    upload_params = (report_type, uploaded_at, period_start, period_end, source_filename)
    cur = conn.execute(UPLOAD_INSERT_SQL, upload_params)
    if cur.lastrowid is None:
        raise RuntimeError("入库失败：未获得 upload_id")
    upload_id = int(cur.lastrowid)

    rows = build_rows(upload_id)
    if not rows:
        return upload_id

    try:
        conn.executemany(daily_sql, rows)
    except Exception:
        if isinstance(conn, _TursoConnection):
            try:
                conn.execute(_DELETE_UPLOAD_SQL, (upload_id,))
            except Exception:
                pass
        raise

    return upload_id
