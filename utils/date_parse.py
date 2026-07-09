"""Amazon 报表日期列解析（文本 / Excel 序列号 / YYYYMMDD 整数）。

各 analyzer 的 clean_* 与历史库入库前应调用 coerce_report_dates，
解析失败的行不会进入按日明细。

美国站常见英文日期如 ``May 16, 2026`` / ``Jun 01, 2026`` 需显式格式解析，
不可仅依赖 pd.to_datetime 推断（跨月长 CSV 在 Cloud 上易整段失败）。
"""
from __future__ import annotations

import re

import pandas as pd

DATE_COLUMN_ALIASES = ("日期", "date", "Date", "DATE", "Day", "day", "时间")

# Excel 序列日：约 1954-01-01 .. 2120-01-01
_EXCEL_SERIAL_MIN = 20_000
_EXCEL_SERIAL_MAX = 80_000

# 美国站广告后台 CSV 常见英文日期
_EXPLICIT_DATE_FORMATS = (
    "%b %d, %Y",  # May 16, 2026 / Jun 01, 2026
    "%B %d, %Y",  # May 16, 2026（全称月份）
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y%m%d",
)


def _normalize_col_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name).strip().lower())


def resolve_date_column(df: pd.DataFrame, preferred: str = "日期") -> str | None:
    """在 DataFrame 中查找日期列名。"""
    if preferred in df.columns:
        return preferred
    for alias in DATE_COLUMN_ALIASES:
        if alias in df.columns:
            return alias
    norm_to_raw = {_normalize_col_name(c): c for c in df.columns}
    for alias in DATE_COLUMN_ALIASES:
        hit = norm_to_raw.get(_normalize_col_name(alias))
        if hit:
            return hit
    return None


def _non_empty_mask(series: pd.Series) -> pd.Series:
    as_str = series.astype(str).str.strip()
    return series.notna() & (as_str != "") & (~as_str.str.lower().isin({"nan", "none", "nat"}))


def _clean_date_text(value) -> str:
    """去掉首尾空白与 CSV 引号。"""
    s = str(value).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        s = s[1:-1].strip()
    return s


def _try_explicit_date_formats(texts: pd.Series) -> pd.Series:
    """对仍未解析的文本尝试常见显式格式（含美国站英文月份）。"""
    out = pd.Series(pd.NaT, index=texts.index, dtype="datetime64[ns]")
    cleaned = texts.map(_clean_date_text)
    pending = cleaned.ne("")
    if not pending.any():
        return out

    for fmt in _EXPLICIT_DATE_FORMATS:
        still = pending & out.isna()
        if not still.any():
            break
        parsed = pd.to_datetime(cleaned[still], format=fmt, errors="coerce")
        out.loc[parsed.index] = parsed
    return out


def parse_report_date_series(series: pd.Series) -> pd.Series:
    """
    解析报表日期列：支持 datetime、文本、Excel 序列号、YYYYMMDD 整数。
    返回 normalize 后的 datetime64（无时分秒）。
    """
    if series is None or len(series) == 0:
        return pd.Series(dtype="datetime64[ns]")

    if pd.api.types.is_datetime64_any_dtype(series):
        out = pd.to_datetime(series, errors="coerce")
    else:
        cleaned = series.map(_clean_date_text)
        out = pd.to_datetime(cleaned, errors="coerce")

        still_na = out.isna() & _non_empty_mask(series)
        if still_na.any():
            explicit = _try_explicit_date_formats(series[still_na])
            out.loc[explicit.index] = explicit

        still_na = out.isna() & _non_empty_mask(series)
        if still_na.any():
            nums = pd.to_numeric(series[still_na], errors="coerce")
            excel_ok = nums.notna() & (nums >= _EXCEL_SERIAL_MIN) & (nums <= _EXCEL_SERIAL_MAX)
            if excel_ok.any():
                excel_parsed = pd.to_datetime(
                    nums[excel_ok],
                    unit="D",
                    origin="1899-12-30",
                    errors="coerce",
                )
                out.loc[excel_parsed.index] = excel_parsed

            still_na = out.isna() & _non_empty_mask(series)
            if still_na.any():
                nums = pd.to_numeric(series[still_na], errors="coerce")
                for idx, val in nums.dropna().items():
                    iv = int(val)
                    if 19000101 <= iv <= 21001231:
                        text = f"{iv:08d}"
                        ts = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
                        if pd.notna(ts):
                            out.loc[idx] = ts

    if hasattr(out.dt, "tz") and out.dt.tz is not None:
        out = out.dt.tz_localize(None)
    return out.dt.normalize()


def _failed_date_samples(raw: pd.Series, parsed: pd.Series, *, limit: int = 3) -> list[str]:
    failed_mask = parsed.isna() & _non_empty_mask(raw)
    if not failed_mask.any():
        return []
    samples: list[str] = []
    for val in raw[failed_mask].head(limit * 3):
        text = _clean_date_text(val)
        if text and text not in samples:
            samples.append(text)
        if len(samples) >= limit:
            break
    return samples


def coerce_report_dates(
    df: pd.DataFrame,
    column: str = "日期",
    *,
    output_column: str | None = None,
) -> tuple[pd.DataFrame, int]:
    """
    解析并写回日期列。返回 (新 DataFrame, 解析失败行数, 失败样例列表)。
    """
    out_col = output_column or column
    src_col = resolve_date_column(df, column)
    if src_col is None:
        return df, 0

    df = df.copy()
    raw = df[src_col]
    parsed = parse_report_date_series(raw)
    failed = int((parsed.isna() & _non_empty_mask(raw)).sum())

    if src_col != out_col:
        df = df.drop(columns=[src_col])
    df[out_col] = parsed
    samples = _failed_date_samples(raw, parsed)
    return df, failed, samples


def maybe_warn_date_parse_failures(
    failed: int,
    report_label: str,
    *,
    samples: list[str] | None = None,
) -> None:
    if failed <= 0:
        return
    try:
        import streamlit as st

        msg = (
            f"**{report_label}**：有 {failed} 行「日期」无法识别，这些行不会出现在每日明细中。"
            "建议直接上传广告后台原始 CSV；若使用 Excel，请确保整列日期格式一致。"
        )
        if samples:
            msg += f" 失败样例：{', '.join(repr(s) for s in samples[:3])}。"
        st.warning(msg)
    except Exception:
        pass
