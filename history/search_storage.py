from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from ad_analyzers.search_analyzer import clean_search_report
from history.budget_storage import _date_range_list
from history.database import get_connection, init_db
from history.upload_ingest import insert_upload_with_daily_rows

REPORT_TYPE_SEARCH = "search"


def _null_float(val) -> float | None:
    if val is None or pd.isna(val):
        return None
    return float(val)


def ingest_search_upload(df: pd.DataFrame, source_filename: str) -> int:
    """上传即写库：写入 upload 批次与 search_daily 行。"""
    init_db()
    cleaned = clean_search_report(df)
    if "日期" not in cleaned.columns:
        raise ValueError("搜索词报表缺少「日期」列，未入库")
    cleaned = cleaned.dropna(
        subset=["日期", "广告活动名称", "广告组名称", "投放", "客户搜索词"]
    )
    if cleaned.empty:
        raise ValueError("搜索词报表无有效数据，未入库")

    period_start = cleaned["日期"].min().strftime("%Y-%m-%d")
    period_end = cleaned["日期"].max().strftime("%Y-%m-%d")
    uploaded_at = datetime.now().isoformat(timespec="seconds")

    def build_rows(upload_id: int) -> list[tuple]:
        rows: list[tuple] = []
        for _, row in cleaned.iterrows():
            rows.append(
                (
                    upload_id,
                    str(row["广告活动名称"]),
                    str(row["广告组名称"]),
                    str(row["投放"]),
                    str(row["匹配类型"]),
                    str(row["客户搜索词"]),
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
        return rows

    with get_connection() as conn:
        upload_id = insert_upload_with_daily_rows(
            conn,
            report_type=REPORT_TYPE_SEARCH,
            uploaded_at=uploaded_at,
            period_start=period_start,
            period_end=period_end,
            source_filename=source_filename,
            daily_sql="""
            INSERT INTO search_daily (
                upload_id, campaign_name, ad_group_name, target_keyword, match_type,
                search_term, date, impressions, clicks, ctr, orders, cvr, cpc, spend, sales, acos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            build_rows=build_rows,
        )

    return upload_id


def query_search_dataframe(start_date: date, end_date: date) -> tuple[pd.DataFrame, list[date]]:
    """
    按日期范围拼数：每个 (活动, 广告组, 投放, 匹配类型, 客户搜索词, 日期) 取 uploaded_at 最新一批。
    返回与 clean_search_report 兼容的 DataFrame。
    """
    init_db()
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            """
            WITH ranked AS (
                SELECT
                    sd.campaign_name,
                    sd.ad_group_name,
                    sd.target_keyword,
                    sd.match_type,
                    sd.search_term,
                    sd.date,
                    sd.impressions,
                    sd.clicks,
                    sd.ctr,
                    sd.orders,
                    sd.cvr,
                    sd.cpc,
                    sd.spend,
                    sd.sales,
                    sd.acos,
                    ROW_NUMBER() OVER (
                        PARTITION BY sd.campaign_name, sd.ad_group_name, sd.target_keyword,
                                     sd.match_type, sd.search_term, sd.date
                        ORDER BY u.uploaded_at DESC, sd.upload_id DESC
                    ) AS rn
                FROM search_daily sd
                JOIN uploads u ON u.upload_id = sd.upload_id
                WHERE sd.date >= ? AND sd.date <= ?
            )
            SELECT campaign_name, ad_group_name, target_keyword, match_type, search_term, date,
                   impressions, clicks, ctr, orders, cvr, cpc, spend, sales, acos
            FROM ranked
            WHERE rn = 1
            ORDER BY date, campaign_name, ad_group_name, target_keyword, match_type, search_term
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
                "投放": r["target_keyword"],
                "匹配类型": r["match_type"],
                "客户搜索词": r["search_term"],
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
