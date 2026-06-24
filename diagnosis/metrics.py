from __future__ import annotations

from typing import Any

import pandas as pd

from diagnosis.config import DiagnosisConfig
from utils.date_parse import parse_report_date_series


def count_stat_days(budget_df: pd.DataFrame, campaign: str, date_col: str = "日期") -> int:
    if budget_df is None or budget_df.empty or date_col not in budget_df.columns:
        return 0
    subset = budget_df[budget_df["广告活动名称"] == campaign].copy()
    if subset.empty:
        return 0
    dates = parse_report_date_series(subset[date_col]).dropna()
    return int(dates.dt.normalize().nunique())


def get_campaign_date_range(budget_df: pd.DataFrame, campaign: str, date_col: str = "日期") -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if budget_df is None or budget_df.empty:
        return None, None
    subset = budget_df[budget_df["广告活动名称"] == campaign].copy()
    if subset.empty or date_col not in subset.columns:
        return None, None
    dates = parse_report_date_series(subset[date_col]).dropna()
    if dates.empty:
        return None, None
    return dates.min().normalize(), dates.max().normalize()


def calc_daily_orders(total_orders: int | float | None, stat_days: int) -> float | None:
    if stat_days <= 0:
        return None
    orders = float(total_orders or 0)
    return round(orders / stat_days, 2)


def calc_days_of_cover(inventory_qty: int | float | None, daily_orders: float | None) -> float | None:
    if daily_orders is None or daily_orders <= 0:
        return None
    qty = float(inventory_qty or 0)
    return round(qty / daily_orders, 1)


def get_inventory_qty(
    inventory_record: dict[str, Any] | None,
    config: DiagnosisConfig,
) -> int:
    if not inventory_record:
        return 0
    fulfillable = int(inventory_record.get("可售数量", 0) or 0)
    if config.include_inbound_inventory:
        inbound = int(inventory_record.get("在途库存数量", 0) or 0)
        return fulfillable + inbound
    return fulfillable


def calc_campaign_acos(
    product_df: pd.DataFrame,
    campaign: str,
    date_start: pd.Timestamp | None,
    date_end: pd.Timestamp | None,
) -> float | None:
    if product_df is None or product_df.empty:
        return None
    subset = product_df[product_df["广告活动名称"] == campaign].copy()
    if subset.empty:
        return None

    if "日期" in subset.columns and date_start is not None and date_end is not None:
        subset["日期"] = parse_report_date_series(subset["日期"])
        subset = subset[(subset["日期"] >= date_start) & (subset["日期"] <= date_end)]

    if subset.empty:
        return None

    spend = pd.to_numeric(subset.get("花费"), errors="coerce").fillna(0).sum()
    sales_col = "7天总销售额" if "7天总销售额" in subset.columns else None
    if not sales_col:
        return None
    sales = pd.to_numeric(subset[sales_col], errors="coerce").fillna(0).sum()
    if sales <= 0:
        return None
    return round(float(spend / sales), 4)


def build_asin_metrics(
    asin: str,
    stat_days: int,
    inventory_by_asin: dict[str, dict[str, Any]],
    business_by_asin: dict[str, dict[str, Any]],
    asin_sku_map: dict[str, str],
    config: DiagnosisConfig,
) -> dict[str, Any]:
    inv = inventory_by_asin.get(asin, {})
    biz = business_by_asin.get(asin, {})
    fulfillable = int(inv.get("可售数量", 0) or 0)
    inbound = int(inv.get("在途库存数量", 0) or 0)
    inventory_qty = get_inventory_qty(inv, config)
    total_orders = int(biz.get("已订购商品数量", 0) or 0)
    daily_orders = calc_daily_orders(total_orders, stat_days)
    days_of_cover = calc_days_of_cover(inventory_qty, daily_orders)

    stock_sufficient = False
    if daily_orders is None or daily_orders <= 0:
        stock_sufficient = False
    elif days_of_cover is not None:
        stock_sufficient = days_of_cover >= config.min_days_of_cover

    return {
        "广告ASIN": asin,
        "广告SKU": asin_sku_map.get(asin, ""),
        "可售数量": fulfillable,
        "在途库存数量": inbound,
        "库存数量_用于计算": inventory_qty,
        "已订购商品数量": total_orders,
        "日均订单": daily_orders,
        "库存可售天数": days_of_cover,
        "库存是否充足": stock_sufficient,
    }


def pick_worst_asin_by_inventory(asin_metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    """库存可售天数最短者为最差 ASIN。"""
    if not asin_metrics:
        return None

    def sort_key(item: dict[str, Any]) -> tuple:
        days = item.get("库存可售天数")
        if days is None:
            return (0, -1)
        return (1, float(days))

    return min(asin_metrics, key=sort_key)


def is_campaign_stock_sufficient(asin_metrics: list[dict[str, Any]], config: DiagnosisConfig) -> bool:
    if not asin_metrics:
        return True
    for item in asin_metrics:
        daily = item.get("日均订单")
        cover = item.get("库存可售天数")
        if daily is None or daily <= 0:
            return False
        if cover is None or cover < config.min_days_of_cover:
            return False
    return True

