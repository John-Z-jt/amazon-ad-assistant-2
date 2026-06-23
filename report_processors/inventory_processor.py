# report_processors/inventory_processor.py
import os
from typing import BinaryIO, Union

import pandas as pd

from report_processors._csv_loader import read_report_file

InventorySource = Union[str, os.PathLike, BinaryIO]

_QUANTITY_COLUMNS = ["现货数量", "可售数量", "运营中心转运数量", "在途库存数量"]
_TEXT_COLUMNS = ["SKU", "FNSKU", "ASIN", "商品名称", "店铺"]
_OUTPUT_COLUMNS = _TEXT_COLUMNS + _QUANTITY_COLUMNS


def to_numeric_quantity(series: pd.Series) -> pd.Series:
    """将库存数量列清洗为数值 Series。"""
    s = series.astype(str).str.strip()
    s = s.str.replace(",", "", regex=False)
    s = s.str.replace(r"\s+", "", regex=True)
    s = s.replace("", pd.NA)
    return pd.to_numeric(s, errors="coerce")


def _normalize_col_name(name: str) -> str:
    """标准化列名便于匹配。"""
    return str(name).strip().lower().replace("_", "-")


def _pick_source_column(df: pd.DataFrame, *candidates: str) -> str | None:
    """按候选原始列名在 DataFrame 中查找实际列名。"""
    normalized = {_normalize_col_name(col): col for col in df.columns}
    for candidate in candidates:
        key = _normalize_col_name(candidate)
        if key in normalized:
            return normalized[key]
    return None


def clean_inventory_data(df: pd.DataFrame) -> pd.DataFrame:
    """清洗库存报表，返回标准中文列名 inventory_df。

    Args:
        df (pd.DataFrame): 原始库存报表。

    Returns:
        pd.DataFrame: 清洗后的 inventory_df，数值列缺失值填 0。
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    df_clean = df.copy()
    inventory_df = pd.DataFrame()

    text_source_map = {
        "SKU": ("sku",),
        "FNSKU": ("fnsku",),
        "ASIN": ("asin",),
        "商品名称": ("product-name", "product_name"),
        "店铺": ("store",),
    }
    for target_col, sources in text_source_map.items():
        source_col = _pick_source_column(df_clean, *sources)
        if source_col is not None:
            inventory_df[target_col] = df_clean[source_col].astype(str).str.strip()
        else:
            inventory_df[target_col] = ""

    quantity_source_map = {
        "现货数量": ("afn-warehouse-quantity", "afn-total-quantity"),
        "可售数量": ("afn-fulfillable-quantity",),
        "运营中心转运数量": ("afn-reserved-quantity",),
        "在途库存数量": ("afn-inbound-working-quantity",),
    }
    for target_col, sources in quantity_source_map.items():
        source_col = _pick_source_column(df_clean, *sources)
        if source_col is not None:
            inventory_df[target_col] = to_numeric_quantity(df_clean[source_col]).fillna(0)
        else:
            inventory_df[target_col] = 0

    for col in _QUANTITY_COLUMNS:
        inventory_df[col] = pd.to_numeric(inventory_df[col], errors="coerce").fillna(0).astype(int)

    for col in _TEXT_COLUMNS:
        inventory_df[col] = inventory_df[col].replace({"nan": "", "None": ""}).fillna("")

    return inventory_df[_OUTPUT_COLUMNS]


def load_inventory_data(source: InventorySource, *, filename: str | None = None) -> pd.DataFrame:
    """读取库存报表（CSV / xlsx）并返回清洗后的 inventory_df。"""
    raw_df = read_report_file(source, "库存报表", filename=filename)
    return clean_inventory_data(raw_df)


# 兼容旧函数名
clean_inventory_report = clean_inventory_data
