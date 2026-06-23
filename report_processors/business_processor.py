# report_processors/business_processor.py
import os
from typing import BinaryIO, Union

import pandas as pd

from report_processors._csv_loader import read_report_file

BusinessSource = Union[str, os.PathLike, BinaryIO]

_INT_COLUMN_KEYS = {
    _key
    for _key in [
        "会话数-总计",
        "页面浏览量-总计",
        "已订购商品数量",
        "已订购商品数量-b2b",
        "订单商品总数",
        "订单商品总数-b2b",
    ]
}

_RATE_COLUMN_KEYS = {
    _key
    for _key in [
        "转化率-总计",
        "页面浏览量百分比-总计",
        "推荐报价（推荐报价展示位）百分比",
        "商品会话百分比",
        "商品会话百分比-b2b",
    ]
}

_SALES_COLUMN_KEYS = {
    _key
    for _key in [
        "已订购商品销售额",
        "已订购商品销售额-b2b",
    ]
}


def _normalize_col_name(name: str) -> str:
    """标准化列名便于匹配。"""
    return str(name).strip().lower().replace(" ", "")


def _pick_source_column(df: pd.DataFrame, *candidates: str) -> str | None:
    """按候选原始列名在 DataFrame 中查找实际列名。"""
    normalized = {_normalize_col_name(col): col for col in df.columns}
    for candidate in candidates:
        key = _normalize_col_name(candidate)
        if key in normalized:
            return normalized[key]
    return None


def to_int_quantity(series: pd.Series) -> pd.Series:
    """将整数型指标列清洗为数值 Series。"""
    s = series.astype(str).str.strip()
    s = s.str.replace(",", "", regex=False)
    s = s.str.replace(r"\s+", "", regex=True)
    s = s.replace("", pd.NA)
    return pd.to_numeric(s, errors="coerce")


def to_float_amount(series: pd.Series) -> pd.Series:
    """将金额列清洗为 float Series。"""
    s = series.astype(str).str.strip()
    s = s.str.replace(r"[¥$€]", "", regex=True)
    s = s.str.replace(",", "", regex=False)
    s = s.str.replace(r"\s+", "", regex=True)
    s = s.replace("", pd.NA)
    return pd.to_numeric(s, errors="coerce")


def to_rate_float(series: pd.Series) -> pd.Series:
    """去除百分号并转为 float。"""
    s = series.astype(str).str.replace("%", "", regex=False).str.strip()
    s = s.str.replace(",", "", regex=False)
    s = s.replace("", pd.NA)
    return pd.to_numeric(s, errors="coerce")


def _clean_asin_series(series: pd.Series) -> pd.Series:
    """去除首尾空格并统一 ASIN 为大写。"""
    return series.astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})


def _clean_text_series(series: pd.Series) -> pd.Series:
    """去除文本列首尾空格。"""
    return series.astype(str).str.strip().replace({"nan": "", "None": ""})


def clean_business_data(df: pd.DataFrame) -> pd.DataFrame:
    """清洗业务报表，保留全部原始列名，仅做字段标准化。

    Args:
        df (pd.DataFrame): 原始业务报表。

    Returns:
        pd.DataFrame: 清洗后的 business_df。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    business_df = df.copy()

    for col in business_df.columns:
        col_key = _normalize_col_name(col)

        if "asin" in col_key:
            business_df[col] = _clean_asin_series(business_df[col])
        elif col_key in _INT_COLUMN_KEYS:
            business_df[col] = to_int_quantity(business_df[col]).fillna(0).astype(int)
        elif col_key in _RATE_COLUMN_KEYS:
            business_df[col] = to_rate_float(business_df[col]).fillna(0.0).astype(float)
        elif col_key in _SALES_COLUMN_KEYS:
            business_df[col] = to_float_amount(business_df[col]).fillna(0.0).astype(float)
        elif business_df[col].dtype == object:
            business_df[col] = _clean_text_series(business_df[col])

    child_asin_col = _pick_source_column(
        business_df, "（子）ASIN", "(子)ASIN", "子ASIN"
    )
    if child_asin_col is not None:
        business_df = business_df[
            business_df[child_asin_col].astype(str).str.strip() != ""
        ]

    return business_df.reset_index(drop=True)


def load_business_data(source: BusinessSource, *, filename: str | None = None) -> pd.DataFrame:
    """读取业务报表（CSV / xlsx）并返回清洗后的 business_df。"""
    raw_df = read_report_file(source, "业务报表", filename=filename)
    return clean_business_data(raw_df)
