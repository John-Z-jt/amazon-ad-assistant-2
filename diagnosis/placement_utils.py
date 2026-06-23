from __future__ import annotations

from typing import Any

import numpy as np

from diagnosis.config import DiagnosisConfig

PLACEMENT_TYPE_TOS = "TOS"
PLACEMENT_TYPE_ROS = "ROS"
PLACEMENT_TYPE_PP = "PP"
PLACEMENT_TYPE_OTHER = "OTHER"


def normalize_placement_type(placement_name: str) -> str:
    name = str(placement_name or "").strip()
    if "搜索结果顶部" in name:
        return PLACEMENT_TYPE_TOS
    if "其余位置" in name or "其他位置" in name:
        return PLACEMENT_TYPE_ROS
    if "商品页面" in name:
        return PLACEMENT_TYPE_PP
    return PLACEMENT_TYPE_OTHER


def _sum_metrics(rows: list[dict], types: set[str]) -> dict[str, float]:
    clicks = 0.0
    spend = 0.0
    sales = 0.0
    orders = 0.0
    for row in rows:
        if normalize_placement_type(row.get("放置", "")) not in types:
            continue
        clicks += float(row.get("总点击量") or 0)
        spend += float(row.get("总花费") or 0)
        sales += float(row.get("总销售额") or 0)
        orders += float(row.get("总订单数") or 0)
    acos = spend / sales if sales > 0 else np.nan
    cvr = orders / clicks if clicks > 0 else np.nan
    return {
        "clicks": clicks,
        "spend": spend,
        "sales": sales,
        "orders": orders,
        "acos": acos,
        "cvr": cvr,
    }


def compute_campaign_placement_bundle(summary_rows: list[dict], campaign: str) -> dict[str, Any]:
    """汇总单个活动的搜索位 / 商品页 / 全量指标。"""
    rows = [r for r in summary_rows if r.get("广告活动名称") == campaign]
    total = _sum_metrics(rows, {PLACEMENT_TYPE_TOS, PLACEMENT_TYPE_ROS, PLACEMENT_TYPE_PP, PLACEMENT_TYPE_OTHER})
    search = _sum_metrics(rows, {PLACEMENT_TYPE_TOS, PLACEMENT_TYPE_ROS})
    pp = _sum_metrics(rows, {PLACEMENT_TYPE_PP})

    total_clicks = total["clicks"]
    search_click_share = search["clicks"] / total_clicks if total_clicks > 0 else 0.0
    search_spend_share = search["spend"] / total["spend"] if total["spend"] > 0 else 0.0

    return {
        "total_clicks": total_clicks,
        "total_spend": total["spend"],
        "search_click_share": search_click_share,
        "search_spend_share": search_spend_share,
        "search_clicks": search["clicks"],
        "search_spend": search["spend"],
        "search_orders": search["orders"],
        "search_acos": search["acos"],
        "search_cvr": search["cvr"],
        "pp_clicks": pp["clicks"],
        "pp_spend": pp["spend"],
        "pp_orders": pp["orders"],
        "pp_acos": pp["acos"],
        "pp_cvr": pp["cvr"],
    }


def is_search_performance_good(bundle: dict[str, Any], config: DiagnosisConfig) -> bool:
    acos = bundle.get("search_acos")
    if bundle.get("search_clicks", 0) < config.min_search_clicks:
        return False
    if acos is None or (isinstance(acos, float) and np.isnan(acos)):
        return False
    if float(acos) > config.max_search_placement_acos:
        return False
    if bundle.get("search_orders", 0) < config.min_search_orders:
        return False
    cvr = bundle.get("search_cvr")
    if cvr is None or (isinstance(cvr, float) and np.isnan(cvr)):
        return False
    return float(cvr) >= config.min_search_cvr


def is_pp_performance_good(bundle: dict[str, Any], config: DiagnosisConfig) -> bool:
    checks = 0
    pp_acos = bundle.get("pp_acos")
    if bundle.get("pp_clicks", 0) >= config.min_pp_clicks:
        checks += 1
    if pp_acos is not None and not (isinstance(pp_acos, float) and np.isnan(pp_acos)):
        if float(pp_acos) <= config.max_pp_acos:
            checks += 1
    if bundle.get("pp_orders", 0) >= config.min_pp_orders:
        checks += 1
    pp_cvr = bundle.get("pp_cvr")
    if pp_cvr is not None and not (isinstance(pp_cvr, float) and np.isnan(pp_cvr)):
        if float(pp_cvr) >= config.min_pp_cvr:
            checks += 1
    return checks >= config.pp_good_min_conditions


def search_metrics_unable(bundle: dict[str, Any], config: DiagnosisConfig) -> bool:
    acos = bundle.get("search_acos")
    if bundle.get("search_clicks", 0) < config.min_search_clicks:
        return True
    if acos is None or (isinstance(acos, float) and np.isnan(acos)):
        return True
    return False
