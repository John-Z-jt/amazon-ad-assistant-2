"""广告位诊断：基于 placement 汇总 + 预算/库存/linking 规则输出结论。

Listing 自评仅作风险提示，不参与结论门禁（见 ``_append_listing_hint``）。
结论码见 PLACEMENT_CONCLUSION_LABELS。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from data_df_store.data_store import store
from diagnosis.config import DiagnosisConfig
from diagnosis.linkage import get_asins_for_campaign
from diagnosis.listing_assessment import evaluate_listing_assessment, load_listing_by_asin
from diagnosis.metrics import (
    build_asin_metrics,
    count_stat_days,
    is_campaign_stock_sufficient,
    pick_worst_asin_by_inventory,
)
from diagnosis.placement_utils import (
    compute_campaign_placement_bundle,
    is_pp_performance_good,
    is_search_performance_good,
    search_metrics_unable,
)
from utils.date_parse import parse_report_date_series


PLACEMENT_CONCLUSION_LABELS = {
    "INCREASE_SEARCH_PREMIUM": "✅ 建议加搜索位溢价",
    "INCREASE_SEARCH_PREMIUM_CAUTIOUS": "⚡ 谨慎加搜索位溢价（Listing 未达标）",
    "TRY_INCREASE_PREMIUM": "⚡ 可试加搜索位溢价",
    "REDUCE_SEARCH_BID_OR_PREMIUM": "🔽 建议降搜索词竞价/搜索位溢价",
    "SEARCH_COMPETITION_WEAK": "🔍 搜索侧竞争力偏弱",
    "OPTIMIZE_LISTING": "📋 先优化 Listing",
    "PENDING_LISTING": "📝 待补充 Listing 自评",
    "HOLD_RESTOCK": "📦 暂不加溢价（库存不足）",
    "NO_ACTION_NEEDED": "⏸ 搜索位流量结构正常",
    "UNABLE_TO_DIAGNOSE": "⚠️ 暂无法诊断（数据不足）",
}


def _listing_status_for_worst(
    worst_asin: str | None,
    listing_by_asin: dict[str, dict[str, str]],
) -> str:
    """返回 missing / pass / fail / no_asin。"""
    if not worst_asin:
        return "no_asin"
    return evaluate_listing_assessment(listing_by_asin.get(worst_asin))


def _is_search_traffic_structure_healthy(bundle: dict[str, Any], config: DiagnosisConfig) -> bool:
    """搜索位点击占比、ACOS、订单量均达标，才视为结构正常。"""
    search_share = float(bundle.get("search_click_share") or 0)
    if search_share < config.min_search_click_share:
        return False
    if float(bundle.get("search_orders") or 0) < config.min_search_orders:
        return False
    acos = bundle.get("search_acos")
    if acos is None or (isinstance(acos, float) and pd.isna(acos)):
        return False
    return float(acos) <= config.max_search_placement_acos


def _append_listing_hint(
    reason_parts: list[str],
    listing_status: str,
    worst_asin: str | None,
) -> None:
    """Listing 仅作风险提示，不参与结论门禁。"""
    if listing_status == "pass":
        reason_parts.append("Listing 自评良好")
    elif listing_status == "fail":
        reason_parts.append("风险提示：Listing 自评未过关，放量后需关注转化率")
    elif listing_status == "missing":
        reason_parts.append("提示：尚未填写 Listing 自评，可在手动分析页面补充")


@dataclass
class PlacementDiagnosisRow:
    广告活动名称: str
    搜索位点击占比: float
    搜索位花费占比: float
    搜索位点击: float
    搜索位ACOS: float | None
    搜索位转化率: float | None
    搜索位订单: float
    商品页ACOS: float | None
    商品页转化率: float | None
    最差ASIN: str | None
    库存可售天数: float | None
    诊断结论: str
    诊断结论码: str
    原因说明: str
    关联ASIN数: int = 0
    asin明细: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PlacementDiagnosisResult:
    rows: list[PlacementDiagnosisRow]
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


def _get_stat_days(campaign: str, budget_df: pd.DataFrame | None, placement_df: pd.DataFrame | None) -> int:
    days = count_stat_days(budget_df, campaign) if budget_df is not None else 0
    if days > 0:
        return days
    if placement_df is None or placement_df.empty:
        return 0
    subset = placement_df[placement_df["广告活动名称"] == campaign]
    if subset.empty or "日期" not in subset.columns:
        return 0
    dates = parse_report_date_series(subset["日期"]).dropna()
    return int(dates.dt.normalize().nunique())


def _build_asin_context(
    campaign: str,
    config: DiagnosisConfig,
    campaign_asin_map: dict[str, list[str]],
    inventory_by_asin: dict[str, dict[str, Any]],
    business_by_asin: dict[str, dict[str, Any]],
    asin_sku_map: dict[str, str],
    budget_df: pd.DataFrame | None,
    placement_df: pd.DataFrame | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    asins = get_asins_for_campaign(campaign, campaign_asin_map)
    stat_days = _get_stat_days(campaign, budget_df, placement_df)
    asin_details = [
        build_asin_metrics(
            asin,
            stat_days,
            inventory_by_asin,
            business_by_asin,
            asin_sku_map,
            config,
        )
        for asin in asins
    ]
    worst = pick_worst_asin_by_inventory(asin_details)
    return asin_details, worst


def _evaluate_campaign(
    campaign: str,
    bundle: dict[str, Any],
    config: DiagnosisConfig,
    asin_details: list[dict[str, Any]],
    worst_asin_row: dict[str, Any] | None,
    listing_by_asin: dict[str, dict[str, str]],
) -> PlacementDiagnosisRow:
    worst_asin = worst_asin_row.get("广告ASIN") if worst_asin_row else None
    worst_cover = worst_asin_row.get("库存可售天数") if worst_asin_row else None
    search_share = float(bundle.get("search_click_share") or 0)
    spend_share = float(bundle.get("search_spend_share") or 0)
    search_acos = bundle.get("search_acos")
    search_cvr = bundle.get("search_cvr")
    pp_acos = bundle.get("pp_acos")
    pp_cvr = bundle.get("pp_cvr")

    reason_parts: list[str] = [
        f"搜索位点击占比 {search_share:.1%}（花费占比 {spend_share:.1%}）",
    ]
    conclusion_code = "UNABLE_TO_DIAGNOSE"

    if _is_search_traffic_structure_healthy(bundle, config):
        conclusion_code = "NO_ACTION_NEEDED"
        acos_text = f"{float(search_acos):.1%}" if search_acos is not None and not pd.isna(search_acos) else "—"
        reason_parts.append(
            f"搜索位点击占比 ≥ {config.min_search_click_share:.0%}、"
            f"ACOS {acos_text} ≤ {config.max_search_placement_acos:.0%}、"
            f"订单 ≥ {config.min_search_orders}，流量与转化结构正常"
        )
    elif not asin_details:
        reason_parts.append("未在推广的商品报表中匹配到 ASIN，无法完成库存评估")
    elif not is_campaign_stock_sufficient(asin_details, config):
        conclusion_code = "HOLD_RESTOCK"
        cover_text = f"{worst_cover:.1f}天" if worst_cover is not None else "—"
        reason_parts.append(
            f"最差 ASIN {worst_asin or '-'} 库存可售 {cover_text} < {config.min_days_of_cover:.0f} 天"
        )
    elif search_metrics_unable(bundle, config):
        reason_parts.append(
            f"搜索位点击 {int(bundle.get('search_clicks', 0))} 不足或 ACOS 无法计算（数据不足，与 Listing 无关）"
        )
    elif is_search_performance_good(bundle, config):
        acos_text = f"{float(search_acos):.1%}" if search_acos is not None else "—"
        cvr_text = f"{float(search_cvr):.1%}" if search_cvr is not None else "—"
        reason_parts.append(f"搜索位 ACOS {acos_text}、转化率 {cvr_text} 达标")
        conclusion_code = "INCREASE_SEARCH_PREMIUM"
        reason_parts.append(
            "当前搜索位表现已达标，建议提高搜索位溢价测试放量；"
            "若放量后转化率下降，再进一步检查 Listing 质量。"
        )
    elif is_pp_performance_good(bundle, config):
        pp_acos_text = f"{float(pp_acos):.1%}" if pp_acos is not None and not pd.isna(pp_acos) else "—"
        reason_parts.append(f"搜索位表现偏弱，商品页相对更好（ACOS {pp_acos_text}）")
        conclusion_code = "SEARCH_COMPETITION_WEAK"
        reason_parts.append(
            "商品页表现优于搜索位，说明搜索侧竞争力偏弱。"
            "建议进一步检查：搜索词质量、竞价策略、搜索位溢价、Listing 质量。"
            "当前数据无法单独判断问题来源。"
        )
    else:
        reason_parts.append("搜索位与商品页表现均不突出")
        conclusion_code = "TRY_INCREASE_PREMIUM"
        reason_parts.append("可小幅试加搜索位溢价并观察")

    if conclusion_code != "UNABLE_TO_DIAGNOSE":
        _append_listing_hint(
            reason_parts,
            _listing_status_for_worst(worst_asin, listing_by_asin),
            worst_asin,
        )

    acos_val = None if search_acos is None or (isinstance(search_acos, float) and pd.isna(search_acos)) else float(search_acos)
    cvr_val = None if search_cvr is None or (isinstance(search_cvr, float) and pd.isna(search_cvr)) else float(search_cvr)
    pp_acos_val = None if pp_acos is None or (isinstance(pp_acos, float) and pd.isna(pp_acos)) else float(pp_acos)
    pp_cvr_val = None if pp_cvr is None or (isinstance(pp_cvr, float) and pd.isna(pp_cvr)) else float(pp_cvr)

    return PlacementDiagnosisRow(
        广告活动名称=campaign,
        搜索位点击占比=search_share,
        搜索位花费占比=spend_share,
        搜索位点击=float(bundle.get("search_clicks") or 0),
        搜索位ACOS=acos_val,
        搜索位转化率=cvr_val,
        搜索位订单=float(bundle.get("search_orders") or 0),
        商品页ACOS=pp_acos_val,
        商品页转化率=pp_cvr_val,
        最差ASIN=worst_asin,
        库存可售天数=worst_cover,
        诊断结论=PLACEMENT_CONCLUSION_LABELS.get(conclusion_code, conclusion_code),
        诊断结论码=conclusion_code,
        原因说明="；".join(reason_parts),
        关联ASIN数=len(asin_details),
        asin明细=asin_details,
    )


def run_placement_diagnosis(config: DiagnosisConfig | None = None, user_id: str | None = None) -> PlacementDiagnosisResult:
    """逐活动诊断搜索位占比/ACOS/CVR/库存，跳过预算异常活动。"""
    if user_id is None:
        from auth.user_context import get_current_user_id

        user_id = get_current_user_id()
    cfg = config or DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    placement_result = store.get("placement_analysis_result") or {}
    budget_result = store.get("budget_analysis_result") or {}
    budget_df = store.get("budget")
    placement_df = store.get("placement")

    campaign_asin_map = store.get("campaign_asin_map") or {}
    inventory_by_asin = store.get("inventory_by_asin") or {}
    business_by_asin = store.get("business_by_asin") or {}
    asin_sku_map = store.get("asin_sku_map") or {}
    listing_by_asin = load_listing_by_asin(user_id)

    warnings: list[str] = []
    rows: list[PlacementDiagnosisRow] = []

    if placement_df is None or not placement_result.get("summary"):
        warnings.append("未上传广告位报表或报表无有效数据")
        return PlacementDiagnosisResult(
            rows=[],
            config_snapshot=cfg.to_dict(),
            warnings=warnings,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )

    if not campaign_asin_map:
        warnings.append("未上传推广的商品报告，ASIN/库存联动可能不完整")

    if not inventory_by_asin or not business_by_asin:
        warnings.append("缺少库存或业务报表，库存门禁可能无法生效")

    warnings.append(
        "Listing 自评为可选参考，仅追加在原因说明中，不影响诊断结论。"
    )

    problem_budget = set(budget_result.get("problem_activities") or [])
    summary_rows = placement_result.get("summary") or []
    campaigns = sorted({r.get("广告活动名称") for r in summary_rows if r.get("广告活动名称")})
    eligible = [c for c in campaigns if c not in problem_budget]

    if problem_budget:
        warnings.append(f"已排除 {len(problem_budget)} 个预算异常活动，仅诊断预算正常活动")

    for campaign in eligible:
        bundle = compute_campaign_placement_bundle(summary_rows, campaign)
        asin_details, worst = _build_asin_context(
            campaign,
            cfg,
            campaign_asin_map,
            inventory_by_asin,
            business_by_asin,
            asin_sku_map,
            budget_df,
            placement_df,
        )
        rows.append(
            _evaluate_campaign(
                campaign,
                bundle,
                cfg,
                asin_details,
                worst,
                listing_by_asin,
            )
        )

    return PlacementDiagnosisResult(
        rows=rows,
        config_snapshot=cfg.to_dict(),
        warnings=warnings,
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
