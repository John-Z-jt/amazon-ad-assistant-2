from __future__ import annotations

from datetime import date, datetime

from history.database import get_connection, init_db


def _norm_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def create_journal_entry(
    event_date: date,
    content: str,
    *,
    asin: str | None = None,
    campaign_name: str | None = None,
    ad_group_name: str | None = None,
) -> int:
    text = str(content).strip()
    if not text:
        raise ValueError("备注内容不能为空")

    init_db()
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO ops_journal (
                event_date, asin, campaign_name, ad_group_name, content, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_date.isoformat(),
                _norm_optional(asin),
                _norm_optional(campaign_name),
                _norm_optional(ad_group_name),
                text,
                created_at,
            ),
        )
        return int(cur.lastrowid)


def query_journal_entries(
    start_date: date,
    end_date: date,
    *,
    asin: str | None = None,
    campaign_name: str | None = None,
) -> list[dict]:
    init_db()
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    sql = """
        SELECT id, event_date, asin, campaign_name, ad_group_name, content, created_at
        FROM ops_journal
        WHERE event_date >= ? AND event_date <= ?
    """
    params: list = [start_str, end_str]

    asin_filter = _norm_optional(asin)
    if asin_filter:
        sql += " AND asin LIKE ?"
        params.append(f"%{asin_filter}%")

    campaign_filter = _norm_optional(campaign_name)
    if campaign_filter:
        sql += " AND campaign_name LIKE ?"
        params.append(f"%{campaign_filter}%")

    sql += " ORDER BY event_date DESC, id DESC"

    with get_connection() as conn:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def delete_journal_entries(entry_ids: list[int]) -> int:
    if not entry_ids:
        return 0
    init_db()
    placeholders = ",".join("?" * len(entry_ids))
    with get_connection() as conn:
        cur = conn.execute(
            f"DELETE FROM ops_journal WHERE id IN ({placeholders})",
            entry_ids,
        )
        return int(getattr(cur, "rowcount", 0) or len(entry_ids))
