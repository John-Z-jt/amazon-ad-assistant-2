from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from data_df_store.data_store import store
from diagnosis.config import DiagnosisConfig
from diagnosis.linkage import get_asins_for_campaign
from diagnosis.metrics import (
    build_asin_metrics,
    calc_campaign_acos,
    count_stat_days,
    get_campaign_date_range,
)


CONCLUSION_LABELS = {
    "INCREASE_BUDGET": "✅ 建议加预算",
    "HOLD_RESTOCK": "📦 暂不加预算（库存不足）",
    "HOLD_OPTIMIZE": "📉 暂不加预算（ACOS超标）",
    "UNABLE_TO_DIAGNOSE": "⚠️ 暂无法诊断",
}


@dataclass
class BudgetDiagnosisRow:
    广告活动名称: str
    连续超标天数: int
    最高使用率: float
    统计天数: int
    关联ASIN数: int
    最差ASIN: str | None
    可售数量: int | None
    日均订单: float | None
    库存可售天数: float | None
    活动ACOS: float | None
    诊断结论: str
    诊断结论码: str
    原因说明: str
    asin明细: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BudgetDiagnosisResult:
    rows: list[BudgetDiagnosisRow]
    config_snapshot: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [asdict(r) for r in self.rows],
            "config_snapshot": self.config_snapshot,
            "warnings": self.warnings,
            "generated_at": self.generated_at,
        }


def _pick_worst_asin(asin_metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not asin_metrics:
        return None

    def sort_key(item: dict[str, Any]) -> tuple:
        days = item.get("库存可售天数")
        if days is None:
            return (0, -1)
        return (1, float(days))

    return min(asin_metrics, key=sort_key)


def _evaluate_campaign_row(
    campaign: str,
    budget_summary: dict[str, Any],
    config: DiagnosisConfig,
    campaign_asin_map: dict[str, list[str]],
    inventory_by_asin: dict[str, dict[str, Any]],
    business_by_asin: dict[str, dict[str, Any]],
    asin_sku_map: dict[str, str],
    product_df: pd.DataFrame | None,
    budget_df: pd.DataFrame | None,
    global_warnings: list[str],
) -> BudgetDiagnosisRow:
    consecutive_days = int(budget_summary.get("连续超标天数", 0) or 0)
    max_usage = float(budget_summary.get("最高使用率", 0) or 0)
    stat_days = int(budget_summary.get("统计天数", 0) or 0)
    if stat_days <= 0 and budget_df is not None:
        stat_days = count_stat_days(budget_df, campaign)

    asins = get_asins_for_campaign(campaign, campaign_asin_map)
    date_start, date_end = get_campaign_date_range(budget_df, campaign) if budget_df is not None else (None, None)
    campaign_acos = calc_campaign_acos(product_df, campaign, date_start, date_end)

    asin_details: list[dict[str, Any]] = []
    for asin in asins:
        asin_details.append(
            build_asin_metrics(
                asin,
                stat_days,
                inventory_by_asin,
                business_by_asin,
                asin_sku_map,
                config,
            )
        )

    worst = _pick_worst_asin(asin_details)
    worst_asin = worst.get("广告ASIN") if worst else None
    worst_qty = worst.get("可售数量") if worst else None
    worst_daily = worst.get("日均订单") if worst else None
    worst_cover = worst.get("库存可售天数") if worst else None

    conclusion_code = "UNABLE_TO_DIAGNOSE"
    reason_parts: list[str] = [
        f"连续{consecutive_days}天使用率>{config.budget_usage_threshold:.0%}",
    ]

    if not asins:
        reason_parts.append("未在推广的商品报表中匹配到 ASIN")
    elif not inventory_by_asin or not business_by_asin:
        missing = []
        if not inventory_by_asin:
            missing.append("库存报表")
        if not business_by_asin:
            missing.append("业务报表")
        reason_parts.append(f"缺少{'、'.join(missing)}")
    else:
        any_insufficient = False
        any_unknown_stock = False
        for item in asin_details:
            daily = item.get("日均订单")
            cover = item.get("库存可售天数")
            if daily is None or daily <= 0:
                any_unknown_stock = True
            elif cover is not None and cover < config.min_days_of_cover:
                any_insufficient = True

        if any_unknown_stock and not any_insufficient:
            reason_parts.append("部分 ASIN 日均订单为 0，无法判断库存是否充足")
        elif any_insufficient:
            conclusion_code = "HOLD_RESTOCK"
            w_asin = worst_asin or "-"
            cover_text = f"{worst_cover:.1f}天" if worst_cover is not None else "—"
            reason_parts.append(
                f"最差 ASIN {w_asin} 库存可售{cover_text}<{config.min_days_of_cover:.0f}天"
            )
        elif campaign_acos is None:
            reason_parts.append("活动 ACOS 无法计算（销售额为 0 或缺少推广的商品数据）")
        elif campaign_acos > config.max_campaign_acos:
            conclusion_code = "HOLD_OPTIMIZE"
            reason_parts.append(
                f"活动 ACOS {campaign_acos:.1%}>{config.max_campaign_acos:.0%}，先优化再谈预算"
            )
        else:
            conclusion_code = "INCREASE_BUDGET"
            cover_text = f"{worst_cover:.1f}天" if worst_cover is not None else "—"
            reason_parts.append(
                f"库存可售{cover_text}≥{config.min_days_of_cover:.0f}天，"
                f"活动 ACOS {campaign_acos:.1%}≤{config.max_campaign_acos:.0%}"
            )

    if product_df is not None and date_start is not None and "日期" in product_df.columns:
        prod_dates = pd.to_datetime(product_df["日期"], errors="coerce").dropna()
        if not prod_dates.empty:
            if prod_dates.min().normalize() > date_start or prod_dates.max().normalize() < date_end:
                warn = f"活动「{campaign}」推广的商品日期范围与预算报表不完全一致"
                if warn not in global_warnings:
                    global_warnings.append(warn)

    return BudgetDiagnosisRow(
        广告活动名称=campaign,
        连续超标天数=consecutive_days,
        最高使用率=max_usage,
        统计天数=stat_days,
        关联ASIN数=len(asins),
        最差ASIN=worst_asin,
        可售数量=worst_qty,
        日均订单=worst_daily,
        库存可售天数=worst_cover,
        活动ACOS=campaign_acos,
        诊断结论=CONCLUSION_LABELS.get(conclusion_code, conclusion_code),
        诊断结论码=conclusion_code,
        原因说明="；".join(reason_parts),
        asin明细=asin_details,
    )


def run_budget_diagnosis(config: DiagnosisConfig | None = None) -> BudgetDiagnosisResult:
    cfg = config or DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    budget_result = store.get("budget_analysis_result") or {}
    budget_df = store.get("budget")
    product_df = store.get("product_sponsored")

    campaign_asin_map = store.get("campaign_asin_map") or {}
    inventory_by_asin = store.get("inventory_by_asin") or {}
    business_by_asin = store.get("business_by_asin") or {}
    asin_sku_map = store.get("asin_sku_map") or {}

    warnings: list[str] = []
    rows: list[BudgetDiagnosisRow] = []

    if budget_df is None:
        warnings.append("未上传预算报表")
        return BudgetDiagnosisResult(
            rows=[],
            config_snapshot=cfg.to_dict(),
            warnings=warnings,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )

    if not campaign_asin_map and product_df is None:
        warnings.append("未上传推广的商品报告，无法关联 ASIN")

    if not inventory_by_asin:
        warnings.append("未上传库存报表，库存相关诊断可能不完整")

    if not business_by_asin:
        warnings.append("未上传业务报表，日均订单无法计算")

    problem_activities = budget_result.get("problem_activities") or []
    summary_list = budget_result.get("summary") or []
    summary_by_campaign = {item["广告活动名称"]: item for item in summary_list}

    for campaign in problem_activities:
        summary_item = summary_by_campaign.get(campaign, {"广告活动名称": campaign})
        rows.append(
            _evaluate_campaign_row(
                campaign,
                summary_item,
                cfg,
                campaign_asin_map,
                inventory_by_asin,
                business_by_asin,
                asin_sku_map,
                product_df,
                budget_df,
                warnings,
            )
        )

    return BudgetDiagnosisResult(
        rows=rows,
        config_snapshot=cfg.to_dict(),
        warnings=warnings,
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
