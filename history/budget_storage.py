from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from history.database import get_connection, init_db

REPORT_TYPE_BUDGET = "budget"


def _clean_budget_df(df: pd.DataFrame) -> pd.DataFrame:
    """与 get_budget_analysis 相同的预算清洗逻辑（仅清洗，不分析）。"""
    col_budget = "预算"
    col_spent = "花费"
    col_date = "日期"
    col_activity = "广告活动名称"

    needed = [col_budget, col_spent, col_date, col_activity]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"缺少列: {missing}")

    def clean_series(series):
        s = series.astype(str).str.strip()
        s = s.str.replace(r"[¥$€]", "", regex=True)
        s = s.str.replace(",", "", regex=False)
        s = s.str.replace(r"\s+", "", regex=True)
        s = s.replace("", pd.NA)
        return pd.to_numeric(s, errors="coerce")

    df_clean = df.copy()
    df_clean["预算"] = clean_series(df_clean[col_budget])
    df_clean["花费"] = clean_series(df_clean[col_spent])
    df_clean["日期"] = pd.to_datetime(df_clean[col_date], errors="coerce")
    df_clean = df_clean.dropna(subset=["日期", "预算", "花费"])
    if df_clean.empty:
        return df_clean

    df_clean["使用率"] = df_clean["花费"] / df_clean["预算"]
    return df_clean


def ingest_budget_upload(df: pd.DataFrame, source_filename: str) -> int:
    """上传即写库：写入 upload 批次与 budget_daily 行。"""
    init_db()
    cleaned = _clean_budget_df(df)
    if cleaned.empty:
        raise ValueError("预算报表无有效数据，未入库")

    period_start = cleaned["日期"].min().strftime("%Y-%m-%d")
    period_end = cleaned["日期"].max().strftime("%Y-%m-%d")
    uploaded_at = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO uploads (report_type, uploaded_at, period_start, period_end, source_filename)
            VALUES (?, ?, ?, ?, ?)
            """,
            (REPORT_TYPE_BUDGET, uploaded_at, period_start, period_end, source_filename),
        )
        upload_id = int(cur.lastrowid)

        rows = []
        for _, row in cleaned.iterrows():
            usage = row.get("使用率")
            usage_val = None if pd.isna(usage) else float(usage)
            rows.append(
                (
                    upload_id,
                    str(row["广告活动名称"]),
                    row["日期"].strftime("%Y-%m-%d"),
                    float(row["预算"]),
                    float(row["花费"]),
                    usage_val,
                )
            )

        conn.executemany(
            """
            INSERT INTO budget_daily (upload_id, campaign_name, date, budget, spend, usage_rate)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    return upload_id


def list_budget_uploads(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT upload_id, report_type, uploaded_at, period_start, period_end, source_filename
            FROM uploads
            WHERE report_type = ?
            ORDER BY uploaded_at DESC, upload_id DESC
            LIMIT ?
            """,
            (REPORT_TYPE_BUDGET, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def list_all_uploads(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT upload_id, report_type, uploaded_at, period_start, period_end, source_filename
            FROM uploads
            ORDER BY uploaded_at DESC, upload_id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_uploads_by_ids(upload_ids: list[int]) -> list[dict[str, Any]]:
    if not upload_ids:
        return []
    init_db()
    placeholders = ",".join("?" * len(upload_ids))
    with get_connection() as conn:
        cur = conn.execute(
            f"""
            SELECT upload_id, report_type, uploaded_at, period_start, period_end, source_filename
            FROM uploads
            WHERE upload_id IN ({placeholders})
            ORDER BY uploaded_at DESC
            """,
            upload_ids,
        )
        return [dict(row) for row in cur.fetchall()]


def delete_uploads(upload_ids: list[int]) -> None:
    if not upload_ids:
        return
    init_db()
    placeholders = ",".join("?" * len(upload_ids))
    with get_connection() as conn:
        conn.execute(
            f"DELETE FROM budget_daily WHERE upload_id IN ({placeholders})",
            upload_ids,
        )
        conn.execute(
            f"DELETE FROM placement_daily WHERE upload_id IN ({placeholders})",
            upload_ids,
        )
        conn.execute(
            f"DELETE FROM keyword_daily WHERE upload_id IN ({placeholders})",
            upload_ids,
        )
        conn.execute(
            f"DELETE FROM search_daily WHERE upload_id IN ({placeholders})",
            upload_ids,
        )
        conn.execute(
            f"DELETE FROM search_share_daily WHERE upload_id IN ({placeholders})",
            upload_ids,
        )
        conn.execute(
            f"DELETE FROM product_sponsored_daily WHERE upload_id IN ({placeholders})",
            upload_ids,
        )
        conn.execute(
            f"DELETE FROM uploads WHERE upload_id IN ({placeholders})",
            upload_ids,
        )


def _date_range_list(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def query_budget_dataframe(start_date: date, end_date: date) -> tuple[pd.DataFrame, list[date]]:
    """
    按日期范围拼数：每个 (活动, 日期) 取 uploaded_at 最新一批。
    返回与原始 CSV 兼容的 DataFrame 及范围内缺失的日历天。
    """
    init_db()
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            """
            WITH ranked AS (
                SELECT
                    bd.campaign_name,
                    bd.date,
                    bd.budget,
                    bd.spend,
                    ROW_NUMBER() OVER (
                        PARTITION BY bd.campaign_name, bd.date
                        ORDER BY u.uploaded_at DESC, bd.upload_id DESC
                    ) AS rn
                FROM budget_daily bd
                JOIN uploads u ON u.upload_id = bd.upload_id
                WHERE bd.date >= ? AND bd.date <= ?
            )
            SELECT campaign_name, date, budget, spend
            FROM ranked
            WHERE rn = 1
            ORDER BY date, campaign_name
            """,
            (start_str, end_str),
        )
        rows = cur.fetchall()

    if not rows:
        missing = _date_range_list(start_date, end_date)
        return pd.DataFrame(), missing

    df = pd.DataFrame(
        [
            {
                "广告活动名称": r["campaign_name"],
                "日期": pd.to_datetime(r["date"]),
                "预算": r["budget"],
                "花费": r["spend"],
            }
            for r in rows
        ]
    )

    present_dates = set(pd.to_datetime(df["日期"]).dt.normalize().dt.date)
    missing = [d for d in _date_range_list(start_date, end_date) if d not in present_dates]
    return df, missing
