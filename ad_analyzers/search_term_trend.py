import pandas as pd
import numpy as np
import streamlit as st
from typing import Dict, Any
from data_df_store.data_store import store


# ---------- 通用清洗函数 ----------
def to_float(series):
    """将 Series 清洗并转换为浮点数。

    Args:
        series: 待转换的 pandas Series。

    Returns:
        pd.Series: 转换后的数值 Series。

    Raises:
        None
    """
    s = series.astype(str).str.strip()
    s = s.str.replace(r'[¥$€]', '', regex=True)
    s = s.str.replace(',', '', regex=False)
    s = s.str.replace(r'\s+', '', regex=True)
    s = s.replace('', pd.NA)
    return pd.to_numeric(s, errors='coerce')


def to_percent_float(series):
    """将百分比字符串 Series 转换为 0-1 范围的浮点数。

    Args:
        series: 含百分号的 pandas Series。

    Returns:
        pd.Series: 转换后的小数 Series。

    Raises:
        None
    """
    s = series.astype(str).str.replace('%', '', regex=False).str.strip()
    s = s.replace('', pd.NA)
    return pd.to_numeric(s, errors='coerce') / 100


def _ensure_share_optional_columns(df_clean: pd.DataFrame) -> pd.DataFrame:
    if "keyword" not in df_clean.columns:
        df_clean["keyword"] = "—"
    if "match_type" not in df_clean.columns:
        df_clean["match_type"] = "—"
    else:
        df_clean["match_type"] = (
            df_clean["match_type"].astype(str).str.strip().replace({"": "—", "nan": "—", "None": "—"})
        )
    return df_clean


def _normalize_share_col_name(name: str) -> str:
    return " ".join(str(name).strip().replace("\u3000", " ").split()).lower()


# 每条规则：标准列名 -> 候选列名（越长越靠前，优先精确/完整匹配）
_SEARCH_SHARE_COLUMN_RULES: list[tuple[str, list[str]]] = [
    ("date", ["日期", "date"]),
    ("search_term", ["客户搜索词"]),
    ("impression_rank", ["搜索词展示量排名", "展示量排名"]),
    ("impression_share", ["搜索词展示量份额", "展示量份额"]),
    ("campaign", ["广告活动名称", "活动名称"]),
    ("ad_group", ["广告组名称"]),
    ("keyword", ["投放", "关键词"]),
    ("match_type", ["匹配类型"]),
    ("clicks", ["点击量"]),
    ("spend", ["花费", "消耗"]),
    (
        "orders",
        [
            "7 天内的总订单量 (#)",
            "7 天内的总订单量",
            "7天内的总订单量 (#)",
            "7天内的总订单量",
            "7天总订单数(#)",
            "7天总订单数",
            "总订单量",
            "订单量",
            "订单数",
        ],
    ),
    (
        "sales",
        [
            "7 天内的总销售额",
            "7天内的总销售额",
            "7 天总销售额",
            "7天总销售额",
            "总销售额",
            "销售额",
        ],
    ),
]

# 含这些子串的列名不参与对应标准列的模糊匹配（避免误抢列）
_SHARE_COLUMN_BLOCKLIST: dict[str, tuple[str, ...]] = {
    "search_term": ("展示量排名", "展示量份额", "广告组合"),
    "ad_group": ("广告组合",),
    "campaign": ("广告活动类型", "广告组合"),
    "orders": ("预计错失", "去年"),
    "sales": ("预计错失", "去年"),
    "clicks": ("预计错失", "去年"),
    "spend": ("预计错失", "去年"),
}


def _map_search_share_columns(columns: list) -> dict[str, str]:
    """将报表列名映射为标准列名；每列最多使用一次，优先更长、更精确的别名。"""
    rename_map: dict[str, str] = {}
    used: set[str] = set()

    for std, aliases in _SEARCH_SHARE_COLUMN_RULES:
        blocklist = _SHARE_COLUMN_BLOCKLIST.get(std, ())
        sorted_aliases = sorted(aliases, key=len, reverse=True)
        best_col: str | None = None
        best_score = -1

        for col in columns:
            if col in used:
                continue
            col_norm = _normalize_share_col_name(col)
            if any(token in col for token in blocklist):
                continue

            for alias in sorted_aliases:
                alias_norm = _normalize_share_col_name(alias)
                if col_norm == alias_norm:
                    best_col = col
                    best_score = 10_000 + len(alias_norm)
                    break
                if alias_norm in col_norm:
                    score = len(alias_norm)
                    if score > best_score:
                        best_score = score
                        best_col = col
            if best_score >= 10_000:
                break

        if best_col is not None:
            rename_map[best_col] = std
            used.add(best_col)

    return rename_map


def clean_search_share_report(df: pd.DataFrame, *, for_storage: bool = False) -> pd.DataFrame:
    """清洗搜索词份额报告，通过列名规则映射为标准字段。"""
    df_clean = df.copy()

    rename_map = _map_search_share_columns(list(df_clean.columns))
    if rename_map:
        df_clean.rename(columns=rename_map, inplace=True)

    required = ['date', 'search_term', 'campaign', 'ad_group', 'clicks', 'spend', 'orders', 'sales']
    missing = [r for r in required if r not in df_clean.columns]
    if missing:
        msg = f"搜索词份额报告缺少必要列: {missing}。实际列名: {list(df_clean.columns)}"
        if for_storage:
            raise ValueError(msg)
        st.error(msg)
        return pd.DataFrame()

    df_clean['date'] = pd.to_datetime(df_clean['date'], errors='coerce')
    df_clean['spend'] = to_float(df_clean['spend'])
    df_clean['sales'] = to_float(df_clean['sales'])
    df_clean['clicks'] = pd.to_numeric(df_clean['clicks'], errors='coerce')
    df_clean['orders'] = pd.to_numeric(df_clean['orders'], errors='coerce')
    if 'impression_rank' in df_clean.columns:
        df_clean['impression_rank'] = pd.to_numeric(df_clean['impression_rank'], errors='coerce')
    if 'impression_share' in df_clean.columns:
        df_clean['impression_share'] = to_percent_float(df_clean['impression_share'])

    df_clean = _ensure_share_optional_columns(df_clean)
    df_clean = df_clean.dropna(subset=['date', 'search_term'])
    return df_clean


def get_search_term_trend(df_clean: pd.DataFrame) -> Dict[str, Any]:
    """计算各搜索词的每日趋势与归因明细。

    Args:
        df_clean (pd.DataFrame): 清洗后的搜索词份额报表。

    Returns:
        Dict[str, Any]: 含 search_terms 列表与 data 字典的分析结果。

    Raises:
        None
    """
    if df_clean.empty:
        return {"search_terms": [], "data": {}}

    df_clean = _ensure_share_optional_columns(df_clean.copy())

    # 每日整体趋势
    daily_trend = df_clean.groupby(['search_term', 'date']).agg(
        total_clicks=('clicks', 'sum'),
        total_spend=('spend', 'sum'),
        total_orders=('orders', 'sum'),
        total_sales=('sales', 'sum'),
        impression_rank=('impression_rank', 'first') if 'impression_rank' in df_clean.columns else None,
        impression_share=('impression_share', 'first') if 'impression_share' in df_clean.columns else None
    ).reset_index()
    daily_trend['acos'] = daily_trend['total_spend'] / daily_trend['total_sales']
    daily_trend['acos'] = daily_trend['acos'].replace([np.inf, -np.inf], np.nan)

    # 每日归因明细（按投放词/匹配类型等）
    attribution = df_clean.groupby(['search_term', 'date', 'campaign', 'ad_group', 'keyword', 'match_type']).agg(
        clicks=('clicks', 'sum'),
        spend=('spend', 'sum'),
        orders=('orders', 'sum'),
        sales=('sales', 'sum')
    ).reset_index()

    data = {}
    for term in daily_trend['search_term'].unique():
        term_trend = daily_trend[daily_trend['search_term'] == term].sort_values('date').to_dict(orient='records')
        term_attribution = attribution[attribution['search_term'] == term].sort_values('date').to_dict(orient='records')
        data[term] = {
            'trend': term_trend,
            'attribution': term_attribution
        }
    return {
        "search_terms": sorted(daily_trend['search_term'].unique()),
        "data": data
    }


def render_search_term_trend_result(result: dict, *, key_prefix: str = "trend") -> None:
    """展示搜索词份额趋势与归因（可指定 widget key 前缀）。"""
    if not result.get("search_terms"):
        st.info("未找到搜索词")
        return

    selected_term = st.selectbox(
        "选择要分析的客户搜索词",
        result["search_terms"],
        key=f"{key_prefix}_trend_term",
    )
    if not selected_term:
        return

    data = result["data"][selected_term]
    trend = data["trend"]
    attribution = data["attribution"]

    if trend:
        trend_df = pd.DataFrame(trend)
        is_threshold = 0.30
        rank_threshold = 3

        def classify(row):
            share = row.get("impression_share", 0)
            rank = row.get("impression_rank", 999)
            if share >= is_threshold and rank <= rank_threshold:
                return "高份额高排名 (核心贡献)"
            if share >= is_threshold and rank > rank_threshold:
                return "高份额低排名 (竞争激烈)"
            if share < is_threshold and rank <= rank_threshold:
                return "低份额高排名 (曝光不足)"
            return "低份额低排名 (待优化)"

        trend_df["广告表现象限"] = trend_df.apply(classify, axis=1)
        trend_df["date"] = pd.to_datetime(trend_df["date"]).dt.strftime("%Y-%m-%d")
        if "impression_share" in trend_df.columns:
            trend_df["impression_share"] = trend_df["impression_share"].apply(
                lambda x: f"{x:.1%}" if pd.notna(x) else "-"
            )
        if "acos" in trend_df.columns:
            trend_df["acos"] = trend_df["acos"].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "-")
        if "total_spend" in trend_df.columns:
            trend_df["total_spend"] = trend_df["total_spend"].apply(lambda x: f"{x:.2f}")
        if "total_sales" in trend_df.columns:
            trend_df["total_sales"] = trend_df["total_sales"].apply(lambda x: f"{x:.2f}")
        trend_df.rename(
            columns={
                "date": "日期",
                "total_clicks": "总点击量",
                "total_spend": "总花费",
                "total_orders": "总订单数",
                "total_sales": "总销售额",
                "impression_rank": "展示量排名",
                "impression_share": "展示量份额",
                "acos": "ACOS",
                "search_term": "客户搜索词",
            },
            inplace=True,
        )
        cols_order = [
            "日期", "总点击量", "总花费", "总订单数", "总销售额",
            "展示量排名", "展示量份额", "ACOS", "广告表现象限",
        ]
        available_cols = [c for c in cols_order if c in trend_df.columns]
        st.markdown("### 每日整体趋势")
        styled = trend_df[available_cols].style.apply(
            lambda row: [
                "background-color: #d4efdf" if row["广告表现象限"] == "高份额高排名 (核心贡献)" else ""
                for _ in row
            ],
            axis=1,
        )
        st.dataframe(styled, use_container_width=True)
    else:
        st.info("无趋势数据")

    st.markdown("### 每日归因明细（哪些投放词触发了该搜索词）")
    if attribution:
        attr_df = pd.DataFrame(attribution)
        if "date" in attr_df.columns:
            attr_df["date"] = pd.to_datetime(attr_df["date"]).dt.strftime("%Y-%m-%d")
        if "spend" in attr_df.columns:
            attr_df["spend"] = attr_df["spend"].apply(lambda x: f"{x:.2f}")
        if "sales" in attr_df.columns:
            attr_df["sales"] = attr_df["sales"].apply(lambda x: f"{x:.2f}")
        attr_df.rename(
            columns={
                "date": "日期",
                "campaign": "广告活动名称",
                "ad_group": "广告组名称",
                "keyword": "投放词",
                "match_type": "匹配类型",
                "clicks": "点击量",
                "spend": "花费",
                "orders": "订单数",
                "sales": "销售额",
            },
            inplace=True,
        )
        cols_show = [
            "日期", "广告活动名称", "广告组名称", "投放词", "匹配类型",
            "点击量", "花费", "订单数", "销售额",
        ]
        available_attr = [c for c in cols_show if c in attr_df.columns]
        st.dataframe(attr_df[available_attr], use_container_width=True)
    else:
        st.info("无归因明细数据")


def analyze_search_term_trend(df_clean: pd.DataFrame) -> None:
    """在 Streamlit 界面展示搜索词趋势与归因分析。

    Args:
        df_clean (pd.DataFrame): 清洗后的搜索词份额报表。

    Returns:
        None

    Raises:
        None
    """
    if df_clean.empty:
        st.info("没有有效的搜索词份额数据")
        return

    result = store.get("search_term_trend_result")
    if result is None:
        result = get_search_term_trend(df_clean)
        store.set("search_term_trend_result", result)
    if not result["search_terms"]:
        st.info("未找到搜索词")
        return

    st.subheader("📈 搜索词趋势分析（每日排名与份额变化）")
    render_search_term_trend_result(result, key_prefix="trend")