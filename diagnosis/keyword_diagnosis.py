from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from data_df_store.data_store import store
from diagnosis.config import DiagnosisConfig

KEYWORD_CONCLUSION_LABELS = {
    "REVIEW_SEARCH_ZERO_CONV": "🔍 高花费无转化，需查搜索词",
    "REVIEW_SEARCH_HIGH_ACOS": "🔍 高 ACOS 有转化，需查搜索词",
    "REVIEW_SEARCH_POTENTIAL": "🌟 表现优秀，需查搜索词拓词",
    "DUPLICATE_KEYWORD_LAYERING": "⚠️ 重复投放，注意竞价分层",
    "UNABLE_TO_DIAGNOSE": "⚠️ 暂无法诊断（数据不足）",
}

_DUPLICATE_RISK_HINT = "该投放词同时出现在多个广告活动，存在内部竞争风险，请关注竞价分层。"
_NEXT_STEP_HINT = "投放词层面仅发现信号；具体否定/降价/拓词候选见搜索词诊断（手动分析 → 搜索词诊断）。"

_KEYWORD_CONCLUSION_SORT_ORDER = {
    "REVIEW_SEARCH_ZERO_CONV": 0,
    "REVIEW_SEARCH_HIGH_ACOS": 1,
    "REVIEW_SEARCH_POTENTIAL": 2,
}


@dataclass
class KeywordDiagnosisRow:
    广告活动名称: str
    广告组名称: str
    投放: str
    匹配类型: str
    总花费: float
    总点击: float
    总订单: float
    总ACOS: float | None
    总转化率: float | None
    重复投放: bool
    重复活动数: int
    诊断结论: str
    诊断结论码: str
    原因说明: str


@dataclass
class KeywordDiagnosisResult:
    rows: list[KeywordDiagnosisRow]
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


def _has_sample(row: dict[str, Any], config: DiagnosisConfig) -> bool:
    clicks = float(row.get("总点击量") or 0)
    spend = float(row.get("总花费") or 0)
    return clicks >= config.min_keyword_clicks and spend >= config.min_keyword_spend


def _build_duplicate_campaign_counts(summary: list[dict[str, Any]]) -> dict[str, int]:
    by_keyword: dict[str, set[str]] = defaultdict(set)
    for row in summary:
        kw = row.get("投放")
        act = row.get("广告活动名称")
        if kw and act:
            by_keyword[str(kw)].add(str(act))
    return {kw: len(acts) for kw, acts in by_keyword.items()}


def _evaluate_row(
    row: dict[str, Any],
    config: DiagnosisConfig,
    dup_count: int,
) -> KeywordDiagnosisRow | None:
    campaign = str(row.get("广告活动名称") or "")
    adgroup = str(row.get("广告组名称") or "")
    keyword = str(row.get("投放") or "")
    match_type = str(row.get("匹配类型") or "—")
    spend = float(row.get("总花费") or 0)
    clicks = float(row.get("总点击量") or 0)
    orders = float(row.get("总订单数") or 0)
    acos_raw = row.get("总ACOS")
    cvr_raw = row.get("总转化率")
    acos_val = None if acos_raw is None or (isinstance(acos_raw, float) and pd.isna(acos_raw)) else float(acos_raw)
    cvr_val = None if cvr_raw is None or (isinstance(cvr_raw, float) and pd.isna(cvr_raw)) else float(cvr_raw)

    if not _has_sample(row, config):
        return None

    reason_parts: list[str] = [
        f"花费 {spend:.2f}、点击 {int(clicks)}、订单 {int(orders)}",
    ]
    if acos_val is not None:
        reason_parts.append(f"ACOS {acos_val:.1%}")
    if cvr_val is not None:
        reason_parts.append(f"转化率 {cvr_val:.1%}")

    conclusion_code = ""
    if orders == 0 and clicks >= config.min_zero_conv_clicks:
        conclusion_code = "REVIEW_SEARCH_ZERO_CONV"
        reason_parts.append("高花费无转化，需下钻搜索词报表确认无效流量")
    elif (
        acos_val is not None
        and acos_val > config.max_keyword_acos
        and orders >= config.min_keyword_orders_for_acos
    ):
        conclusion_code = "REVIEW_SEARCH_HIGH_ACOS"
        reason_parts.append(
            f"ACOS {acos_val:.1%} > {config.max_keyword_acos:.0%}，需查搜索词定位高花费来源"
        )
    elif (
        orders >= config.min_keyword_orders_potential
        and acos_val is not None
        and acos_val <= config.max_keyword_acos_potential
        and cvr_val is not None
        and cvr_val >= config.min_keyword_cvr_potential
    ):
        conclusion_code = "REVIEW_SEARCH_POTENTIAL"
        reason_parts.append("转化与 ACOS 表现优秀，需查搜索词是否有未投放的出单词可拓词")
    else:
        return None

    is_duplicate = dup_count >= config.min_duplicate_campaigns
    if is_duplicate:
        reason_parts.append(_DUPLICATE_RISK_HINT)

    reason_parts.append(_NEXT_STEP_HINT)

    return KeywordDiagnosisRow(
        广告活动名称=campaign,
        广告组名称=adgroup,
        投放=keyword,
        匹配类型=match_type,
        总花费=spend,
        总点击=clicks,
        总订单=orders,
        总ACOS=acos_val,
        总转化率=cvr_val,
        重复投放=is_duplicate,
        重复活动数=dup_count,
        诊断结论=KEYWORD_CONCLUSION_LABELS.get(conclusion_code, conclusion_code),
        诊断结论码=conclusion_code,
        原因说明="；".join(reason_parts),
    )


def run_keyword_diagnosis(config: DiagnosisConfig | None = None) -> KeywordDiagnosisResult:
    cfg = config or DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    keyword_result = store.get("keyword_analysis_result") or {}
    warnings: list[str] = []

    warnings.append("投放词分诊不给否定/降价最终结论；请结合搜索词报表做下一步。")

    summary = keyword_result.get("summary") or []
    if keyword_result.get("error"):
        warnings.append(f"投放词分析异常：{keyword_result['error']}")
        return KeywordDiagnosisResult(
            rows=[],
            config_snapshot=cfg.to_dict(),
            warnings=warnings,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )

    if not summary:
        if store.get("keyword") is None:
            warnings.append("未上传投放词报表")
        else:
            warnings.append("投放词报表无有效汇总数据")
        return KeywordDiagnosisResult(
            rows=[],
            config_snapshot=cfg.to_dict(),
            warnings=warnings,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )

    dup_counts = _build_duplicate_campaign_counts(summary)
    rows: list[KeywordDiagnosisRow] = []
    for row in summary:
        keyword = str(row.get("投放") or "")
        dup_count = dup_counts.get(keyword, 1)
        evaluated = _evaluate_row(row, cfg, dup_count)
        if evaluated is not None:
            rows.append(evaluated)

    rows.sort(
        key=lambda r: (
            _KEYWORD_CONCLUSION_SORT_ORDER.get(r.诊断结论码, 99),
            -r.总花费,
        )
    )

    return KeywordDiagnosisResult(
        rows=rows,
        config_snapshot=cfg.to_dict(),
        warnings=warnings,
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
