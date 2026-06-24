from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from ad_analyzers.search_term_trend import clean_search_share_report
from history.budget_storage import _date_range_list
from history.database import get_connection, init_db
from history.upload_ingest import insert_upload_with_daily_rows

REPORT_TYPE_SEARCH_SHARE = "search_share"


def _null_float(val) -> float | None:
    if val is None or pd.isna(val):
        return None
    return float(val)


def ingest_search_share_upload(df: pd.DataFrame, source_filename: str) -> int:
    """上传即写库：写入 upload 批次与 search_share_daily 行。"""
    init_db()
    cleaned = clean_search_share_report(df, for_storage=True)
    if cleaned.empty:
        raise ValueError("搜索词份额报表无有效数据，未入库")

    period_start = cleaned["date"].min().strftime("%Y-%m-%d")
    period_end = cleaned["date"].max().strftime("%Y-%m-%d")
    uploaded_at = datetime.now().isoformat(timespec="seconds")

    def build_rows(upload_id: int) -> list[tuple]:
        rows: list[tuple] = []
        for _, row in cleaned.iterrows():
            rows.append(
                (
                    upload_id,
                    str(row["search_term"]),
                    row["date"].strftime("%Y-%m-%d"),
                    str(row["campaign"]),
                    str(row["ad_group"]),
                    str(row["keyword"]),
                    str(row["match_type"]),
                    _null_float(row.get("impression_rank")),
                    _null_float(row.get("impression_share")),
                    _null_float(row.get("clicks")),
                    _null_float(row.get("spend")),
                    _null_float(row.get("orders")),
                    _null_float(row.get("sales")),
                )
            )
        return rows

    with get_connection() as conn:
        upload_id = insert_upload_with_daily_rows(
            conn,
            report_type=REPORT_TYPE_SEARCH_SHARE,
            uploaded_at=uploaded_at,
            period_start=period_start,
            period_end=period_end,
            source_filename=source_filename,
            daily_sql="""
            INSERT INTO search_share_daily (
                upload_id, search_term, date, campaign_name, ad_group_name, keyword,
                match_type, impression_rank, impression_share, clicks, spend, orders, sales
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            build_rows=build_rows,
        )

    return upload_id


def query_search_share_dataframe(start_date: date, end_date: date) -> tuple[pd.DataFrame, list[date]]:
    """
    按日期范围拼数：每个 (搜索词, 日期, 活动, 广告组, 投放, 匹配类型) 取 uploaded_at 最新一批。
    返回与 clean_search_share_report 兼容的 DataFrame（标准列名）。
    """
    init_db()
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            """
            WITH ranked AS (
                SELECT
                    sd.search_term,
                    sd.date,
                    sd.campaign_name,
                    sd.ad_group_name,
                    sd.keyword,
                    sd.match_type,
                    sd.impression_rank,
                    sd.impression_share,
                    sd.clicks,
                    sd.spend,
                    sd.orders,
                    sd.sales,
                    ROW_NUMBER() OVER (
                        PARTITION BY sd.search_term, sd.date, sd.campaign_name,
                                     sd.ad_group_name, sd.keyword, sd.match_type
                        ORDER BY u.uploaded_at DESC, sd.upload_id DESC
                    ) AS rn
                FROM search_share_daily sd
                JOIN uploads u ON u.upload_id = sd.upload_id
                WHERE sd.date >= ? AND sd.date <= ?
            )
            SELECT search_term, date, campaign_name, ad_group_name, keyword, match_type,
                   impression_rank, impression_share, clicks, spend, orders, sales
            FROM ranked
            WHERE rn = 1
            ORDER BY date, search_term, campaign_name, ad_group_name, keyword, match_type
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
                "date": pd.to_datetime(r["date"]),
                "search_term": r["search_term"],
                "campaign": r["campaign_name"],
                "ad_group": r["ad_group_name"],
                "keyword": r["keyword"],
                "match_type": r["match_type"],
                "impression_rank": r["impression_rank"],
                "impression_share": r["impression_share"],
                "clicks": r["clicks"],
                "spend": r["spend"],
                "orders": r["orders"],
                "sales": r["sales"],
            }
            for r in rows
        ]
    )

    present_dates = set(pd.to_datetime(df["date"]).dt.normalize().dt.date)
    missing = [d for d in _date_range_list(start_date, end_date) if d not in present_dates]
    return df, missing
