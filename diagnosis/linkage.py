from __future__ import annotations

from typing import Any

import pandas as pd


def _normalize_col_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "")


def pick_column(df: pd.DataFrame, *candidates: str) -> str | None:
    normalized = {_normalize_col_name(col): col for col in df.columns}
    for candidate in candidates:
        key = _normalize_col_name(candidate)
        if key in normalized:
            return normalized[key]
    return None


def build_campaign_asin_map(product_df: pd.DataFrame) -> dict[str, list[str]]:
    """广告活动名称 → 去重 ASIN 列表。"""
    if product_df is None or product_df.empty:
        return {}
    if "广告活动名称" not in product_df.columns or "广告ASIN" not in product_df.columns:
        return {}

    mapping: dict[str, set[str]] = {}
    for _, row in product_df[["广告活动名称", "广告ASIN"]].dropna(subset=["广告活动名称", "广告ASIN"]).iterrows():
        campaign = str(row["广告活动名称"]).strip()
        asin = str(row["广告ASIN"]).strip().upper()
        if not campaign or not asin:
            continue
        mapping.setdefault(campaign, set()).add(asin)
    return {k: sorted(v) for k, v in mapping.items()}


def build_campaign_adgroup_asin_map(product_df: pd.DataFrame) -> dict[tuple[str, str], list[str]]:
    """(广告活动名称, 广告组名称) → 去重 ASIN 列表。"""
    if product_df is None or product_df.empty:
        return {}
    required = ["广告活动名称", "广告组名称", "广告ASIN"]
    if any(col not in product_df.columns for col in required):
        return {}

    mapping: dict[tuple[str, str], set[str]] = {}
    subset = product_df[required].dropna()
    for _, row in subset.iterrows():
        campaign = str(row["广告活动名称"]).strip()
        adgroup = str(row["广告组名称"]).strip()
        asin = str(row["广告ASIN"]).strip().upper()
        if not campaign or not adgroup or not asin:
            continue
        mapping.setdefault((campaign, adgroup), set()).add(asin)
    return {k: sorted(v) for k, v in mapping.items()}


def build_asin_sku_map(product_df: pd.DataFrame) -> dict[str, str]:
    if product_df is None or product_df.empty:
        return {}
    if "广告ASIN" not in product_df.columns:
        return {}
    sku_col = "广告SKU" if "广告SKU" in product_df.columns else None
    result: dict[str, str] = {}
    for _, row in product_df.iterrows():
        asin = str(row.get("广告ASIN", "")).strip().upper()
        if not asin:
            continue
        sku = str(row.get(sku_col, "")).strip() if sku_col else ""
        if asin not in result and sku:
            result[asin] = sku
    return result


def build_inventory_by_asin(inventory_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if inventory_df is None or inventory_df.empty:
        return {}
    asin_col = pick_column(inventory_df, "ASIN", "asin")
    if asin_col is None:
        return {}

    fulfill_col = pick_column(inventory_df, "可售数量", "afn-fulfillable-quantity")
    inbound_col = pick_column(inventory_df, "在途库存数量", "afn-inbound-working-quantity")

    by_asin: dict[str, dict[str, Any]] = {}
    for _, row in inventory_df.iterrows():
        asin = str(row.get(asin_col, "")).strip().upper()
        if not asin:
            continue
        fulfillable = int(pd.to_numeric(row.get(fulfill_col, 0), errors="coerce") or 0) if fulfill_col else 0
        inbound = int(pd.to_numeric(row.get(inbound_col, 0), errors="coerce") or 0) if inbound_col else 0
        by_asin[asin] = {
            "可售数量": fulfillable,
            "在途库存数量": inbound,
        }
    return by_asin


def build_business_by_asin(business_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if business_df is None or business_df.empty:
        return {}

    asin_col = pick_column(business_df, "（子）ASIN", "(子)ASIN", "子ASIN", "ASIN", "asin")
    orders_col = pick_column(business_df, "已订购商品数量", "ordered-product-sales-units")
    if asin_col is None:
        return {}

    by_asin: dict[str, dict[str, Any]] = {}
    for _, row in business_df.iterrows():
        asin = str(row.get(asin_col, "")).strip().upper()
        if not asin:
            continue
        orders = 0
        if orders_col:
            orders = int(pd.to_numeric(row.get(orders_col, 0), errors="coerce") or 0)
        by_asin[asin] = {"已订购商品数量": orders}
    return by_asin


def get_asins_for_campaign(campaign: str, campaign_asin_map: dict[str, list[str]]) -> list[str]:
    return campaign_asin_map.get(campaign.strip(), [])


def refresh_linkage_indexes(
    product_df: pd.DataFrame | None = None,
    inventory_df: pd.DataFrame | None = None,
    business_df: pd.DataFrame | None = None,
    store=None,
) -> None:
    """根据已上传报表重建 linkage 索引并写入 store。"""
    from data_df_store.data_store import store as default_store

    s = store or default_store
    if product_df is None:
        product_df = s.get("product_sponsored")
    if inventory_df is None:
        inventory_df = s.get("inventory")
    if business_df is None:
        business_df = s.get("business")

    s.set("campaign_asin_map", build_campaign_asin_map(product_df))
    s.set("campaign_adgroup_asin_map", build_campaign_adgroup_asin_map(product_df))
    s.set("asin_sku_map", build_asin_sku_map(product_df))
    s.set("inventory_by_asin", build_inventory_by_asin(inventory_df))
    s.set("business_by_asin", build_business_by_asin(business_df))
