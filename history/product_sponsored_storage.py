from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from ad_analyzers.product_sponserd_analyzer import clean_product_sponsored_report
from history.budget_storage import _date_range_list
from history.database import get_connection, init_db

REPORT_TYPE_PRODUCT_SPONSORED = "product_sponsored"


def _null_float(val) -> float | None:
    if val is None or pd.isna(val):
        return None
    return float(val)


def ingest_product_sponsored_upload(df: pd.DataFrame, source_filename: str) -> int:
    """上传即写库：写入 upload 批次与 product_sponsored_daily 行。"""
    init_db()
    cleaned = clean_product_sponsored_report(df)
    if "日期" not in cleaned.columns:
        raise ValueError("推广的商品报表缺少「日期」列，未入库")
    cleaned = cleaned.dropna(
        subset=["日期", "广告活动名称", "广告组名称", "广告ASIN", "广告SKU"]
    )
    if cleaned.empty:
        raise ValueError("推广的商品报表无有效数据，未入库")

    period_start = cleaned["日期"].min().strftime("%Y-%m-%d")
    period_end = cleaned["日期"].max().strftime("%Y-%m-%d")
    uploaded_at = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO uploads (report_type, uploaded_at, period_start, period_end, source_filename)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                REPORT_TYPE_PRODUCT_SPONSORED,
                uploaded_at,
                period_start,
                period_end,
                source_filename,
            ),
        )
        upload_id = int(cur.lastrowid)

        rows = []
        for _, row in cleaned.iterrows():
            rows.append(
                (
                    upload_id,
                    str(row["广告活动名称"]),
                    str(row["广告组名称"]),
                    str(row["广告ASIN"]),
                    str(row["广告SKU"]),
                    row["日期"].strftime("%Y-%m-%d"),
                    _null_float(row.get("展示量")),
                    _null_float(row.get("点击量")),
                    _null_float(row.get("点击率")),
                    _null_float(row.get("单次点击成本 (CPC)")),
                    _null_float(row.get("花费")),
                    _null_float(row.get("7天总销售额")),
                    _null_float(row.get("ACOS")),
                    _null_float(row.get("7天总订单数")),
                    _null_float(row.get("7天总销售量")),
                    _null_float(row.get("7天转化率")),
                    _null_float(row.get("ROAS")),
                )
            )

        conn.executemany(
            """
            INSERT INTO product_sponsored_daily (
                upload_id, campaign_name, ad_group_name, asin, sku, date,
                impressions, clicks, ctr, cpc, spend, sales, acos,
                orders, units, cvr, roas
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    return upload_id


def query_product_sponsored_dataframe(
    start_date: date, end_date: date
) -> tuple[pd.DataFrame, list[date]]:
    """
    按日期范围拼数：每个 (活动, 广告组, ASIN, SKU, 日期) 取 uploaded_at 最新一批。
    返回与 clean_product_sponsored_report 兼容的 DataFrame。
    """
    init_db()
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            """
            WITH ranked AS (
                SELECT
                    ps.campaign_name,
                    ps.ad_group_name,
                    ps.asin,
                    ps.sku,
                    ps.date,
                    ps.impressions,
                    ps.clicks,
                    ps.ctr,
                    ps.cpc,
                    ps.spend,
                    ps.sales,
                    ps.acos,
                    ps.orders,
                    ps.units,
                    ps.cvr,
                    ps.roas,
                    ROW_NUMBER() OVER (
                        PARTITION BY ps.campaign_name, ps.ad_group_name, ps.asin,
                                     ps.sku, ps.date
                        ORDER BY u.uploaded_at DESC, ps.upload_id DESC
                    ) AS rn
                FROM product_sponsored_daily ps
                JOIN uploads u ON u.upload_id = ps.upload_id
                WHERE ps.date >= ? AND ps.date <= ?
            )
            SELECT campaign_name, ad_group_name, asin, sku, date,
                   impressions, clicks, ctr, cpc, spend, sales, acos,
                   orders, units, cvr, roas
            FROM ranked
            WHERE rn = 1
            ORDER BY date, campaign_name, ad_group_name, asin, sku
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
                "广告ASIN": r["asin"],
                "广告SKU": r["sku"],
                "展示量": r["impressions"],
                "点击量": r["clicks"],
                "点击率": r["ctr"],
                "单次点击成本 (CPC)": r["cpc"],
                "花费": r["spend"],
                "7天总销售额": r["sales"],
                "ACOS": r["acos"],
                "7天总订单数": r["orders"],
                "7天总销售量": r["units"],
                "7天转化率": r["cvr"],
                "ROAS": r["roas"],
            }
            for r in rows
        ]
    )

    present_dates = set(pd.to_datetime(df["日期"]).dt.normalize().dt.date)
    missing = [d for d in _date_range_list(start_date, end_date) if d not in present_dates]
    return df, missing
