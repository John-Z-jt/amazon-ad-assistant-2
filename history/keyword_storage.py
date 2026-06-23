from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from ad_analyzers.keyword_analyzer import clean_keyword_report
from history.budget_storage import _date_range_list
from history.database import get_connection, init_db

REPORT_TYPE_KEYWORD = "keyword"


def _null_float(val) -> float | None:
    if val is None or pd.isna(val):
        return None
    return float(val)


def ingest_keyword_upload(df: pd.DataFrame, source_filename: str) -> int:
    """上传即写库：写入 upload 批次与 keyword_daily 行。"""
    init_db()
    cleaned = clean_keyword_report(df)
    if "日期" not in cleaned.columns:
        raise ValueError("投放词报表缺少「日期」列，未入库")
    cleaned = cleaned.dropna(subset=["日期", "广告活动名称", "广告组名称", "投放"])
    if cleaned.empty:
        raise ValueError("投放词报表无有效数据，未入库")

    period_start = cleaned["日期"].min().strftime("%Y-%m-%d")
    period_end = cleaned["日期"].max().strftime("%Y-%m-%d")
    uploaded_at = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO uploads (report_type, uploaded_at, period_start, period_end, source_filename)
            VALUES (?, ?, ?, ?, ?)
            """,
            (REPORT_TYPE_KEYWORD, uploaded_at, period_start, period_end, source_filename),
        )
        upload_id = int(cur.lastrowid)

        rows = []
        for _, row in cleaned.iterrows():
            rows.append(
                (
                    upload_id,
                    str(row["广告活动名称"]),
                    str(row["广告组名称"]),
                    str(row["投放"]),
                    str(row["匹配类型"]),
                    row["日期"].strftime("%Y-%m-%d"),
                    _null_float(row.get("展示量")),
                    _null_float(row.get("点击量")),
                    _null_float(row.get("点击率")),
                    _null_float(row.get("7天总订单数(#)")),
                    _null_float(row.get("转化率")),
                    _null_float(row.get("单次点击成本 (CPC)_数值")),
                    _null_float(row.get("花费_数值")),
                    _null_float(row.get("7天总销售额_数值")),
                    _null_float(row.get("ACOS_数值")),
                )
            )

        conn.executemany(
            """
            INSERT INTO keyword_daily (
                upload_id, campaign_name, ad_group_name, keyword, match_type, date,
                impressions, clicks, ctr, orders, cvr, cpc, spend, sales, acos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    return upload_id


def query_keyword_dataframe(start_date: date, end_date: date) -> tuple[pd.DataFrame, list[date]]:
    """
    按日期范围拼数：每个 (活动, 广告组, 投放, 匹配类型, 日期) 取 uploaded_at 最新一批。
    返回与 clean_keyword_report 兼容的 DataFrame。
    """
    init_db()
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            """
            WITH ranked AS (
                SELECT
                    kd.campaign_name,
                    kd.ad_group_name,
                    kd.keyword,
                    kd.match_type,
                    kd.date,
                    kd.impressions,
                    kd.clicks,
                    kd.ctr,
                    kd.orders,
                    kd.cvr,
                    kd.cpc,
                    kd.spend,
                    kd.sales,
                    kd.acos,
                    ROW_NUMBER() OVER (
                        PARTITION BY kd.campaign_name, kd.ad_group_name, kd.keyword,
                                     kd.match_type, kd.date
                        ORDER BY u.uploaded_at DESC, kd.upload_id DESC
                    ) AS rn
                FROM keyword_daily kd
                JOIN uploads u ON u.upload_id = kd.upload_id
                WHERE kd.date >= ? AND kd.date <= ?
            )
            SELECT campaign_name, ad_group_name, keyword, match_type, date,
                   impressions, clicks, ctr, orders, cvr, cpc, spend, sales, acos
            FROM ranked
            WHERE rn = 1
            ORDER BY date, campaign_name, ad_group_name, keyword, match_type
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
                "日期": pd.to_datetime(r["date"]),
                "广告活动名称": r["campaign_name"],
                "广告组名称": r["ad_group_name"],
                "投放": r["keyword"],
                "匹配类型": r["match_type"],
                "展示量": r["impressions"],
                "点击量": r["clicks"],
                "点击率": r["ctr"],
                "7天总订单数(#)": r["orders"],
                "转化率": r["cvr"],
                "单次点击成本 (CPC)_数值": r["cpc"],
                "花费_数值": r["spend"],
                "7天总销售额_数值": r["sales"],
                "ACOS_数值": r["acos"],
            }
            for r in rows
        ]
    )

    present_dates = set(pd.to_datetime(df["日期"]).dt.normalize().dt.date)
    missing = [d for d in _date_range_list(start_date, end_date) if d not in present_dates]
    return df, missing
