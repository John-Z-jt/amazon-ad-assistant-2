from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from data_df_store.data_store import store
from diagnosis.config import DiagnosisConfig

SEARCH_CONCLUSION_LABELS = {
    "NEGATIVE_CANDIDATE": "🔴 否定候选",
    "HIGH_ACOS_TERM": "🟠 高ACOS搜索词",
    "EXPANSION_CANDIDATE": "🟢 潜力拓词",
    "UNABLE_TO_DIAGNOSE": "⚠️ 暂无法诊断（数据不足）",
}

_AUTO_MATCH_TARGETS = frozenset(
    {
        "close match",
        "loose match",
        "substitutes",
        "complements",
    }
)

_KEYWORD_LINK_CODES = frozenset(
    {
        "REVIEW_SEARCH_ZERO_CONV",
        "REVIEW_SEARCH_HIGH_ACOS",
        "REVIEW_SEARCH_POTENTIAL",
    }
)

_LINKED_KEYWORD_HINT = "该搜索词来源于投放词诊断重点关注对象，建议优先排查。"

_SEARCH_CONCLUSION_SORT_ORDER = {
    "NEGATIVE_CANDIDATE": 0,
    "HIGH_ACOS_TERM": 1,
    "EXPANSION_CANDIDATE": 2,
}


@dataclass
class SearchDiagnosisRow:
    广告活动名称: str
    广告组名称: str
    投放: str
    匹配类型: str
    客户搜索词: str
    总花费: float
    总点击: float
    总订单: float
    总ACOS: float | None
    总转化率: float | None
    花费占比: float | None
    流量集中: bool
    重复触发: bool
    重复触发投放词数: int
    诊断结论: str
    诊断结论码: str
    原因说明: str


@dataclass
class SearchDiagnosisResult:
    rows: list[SearchDiagnosisRow]
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


def _normalize_match_target(text: str) -> str:
    normalized = str(text or "").strip().lower()
    normalized = normalized.replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def _is_auto_match_target(target: str) -> bool:
    return _normalize_match_target(target) in _AUTO_MATCH_TARGETS


def _build_linked_keyword_keys() -> set[tuple[str, str, str]]:
    linked: set[tuple[str, str, str]] = set()
    keyword_diag = store.get("keyword_diagnosis_result") or {}
    for row in keyword_diag.get("rows") or []:
        if row.get("诊断结论码") not in _KEYWORD_LINK_CODES:
            continue
        act = str(row.get("广告活动名称") or "")
        adg = str(row.get("广告组名称") or "")
        kw = str(row.get("投放") or "")
        if act and adg and kw:
            linked.add((act, adg, kw))
    return linked


def _build_traffic_bucket_spend(summary: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    buckets: dict[tuple[str, str, str], float] = defaultdict(float)
    for row in summary:
        key = (
            str(row.get("广告活动名称") or ""),
            str(row.get("广告组名称") or ""),
            str(row.get("投放") or ""),
        )
        buckets[key] += float(row.get("总花费") or 0)
    return dict(buckets)


def _build_duplicate_trigger_counts(summary: list[dict[str, Any]]) -> dict[tuple[str, str, str], int]:
    by_term: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in summary:
        act = str(row.get("广告活动名称") or "")
        adg = str(row.get("广告组名称") or "")
        term = str(row.get("客户搜索词") or "")
        target = str(row.get("投放") or "")
        if act and adg and term and target:
            by_term[(act, adg, term)].add(target)
    return {key: len(targets) for key, targets in by_term.items()}


def _evaluate_row(
    row: dict[str, Any],
    config: DiagnosisConfig,
    bucket_spend: dict[tuple[str, str, str], float],
    dup_trigger_counts: dict[tuple[str, str, str], int],
    linked_keywords: set[tuple[str, str, str]],
) -> SearchDiagnosisRow | None:
    campaign = str(row.get("广告活动名称") or "")
    adgroup = str(row.get("广告组名称") or "")
    target = str(row.get("投放") or "")
    match_type = str(row.get("匹配类型") or "—")
    search_term = str(row.get("客户搜索词") or "")
    spend = float(row.get("总花费") or 0)
    clicks = float(row.get("总点击量") or 0)
    orders = float(row.get("总订单数") or 0)
    acos_raw = row.get("总ACOS")
    cvr_raw = row.get("总转化率")
    acos_val = None if acos_raw is None or (isinstance(acos_raw, float) and pd.isna(acos_raw)) else float(acos_raw)
    cvr_val = None if cvr_raw is None or (isinstance(cvr_raw, float) and pd.isna(cvr_raw)) else float(cvr_raw)

    reason_parts: list[str] = [
        f"花费 {spend:.2f}、点击 {int(clicks)}、订单 {int(orders)}",
    ]
    if acos_val is not None:
        reason_parts.append(f"ACOS {acos_val:.1%}")
    if cvr_val is not None:
        reason_parts.append(f"转化率 {cvr_val:.1%}")

    conclusion_code = ""
    if (
        orders == 0
        and clicks >= config.min_negative_clicks
        and spend >= config.min_negative_spend
    ):
        conclusion_code = "NEGATIVE_CANDIDATE"
        reason_parts.append("高花费高点击无转化，建议人工评估是否否定该搜索词")
    elif (
        orders >= config.min_high_acos_orders
        and acos_val is not None
        and acos_val > config.max_search_acos
    ):
        conclusion_code = "HIGH_ACOS_TERM"
        reason_parts.append("已有转化但广告效率偏低，建议人工评估是否降竞价或否词")
    elif (
        orders >= config.min_expansion_orders
        and acos_val is not None
        and acos_val <= config.max_expansion_acos
        and search_term.strip() != target.strip()
        and not _is_auto_match_target(target)
    ):
        conclusion_code = "EXPANSION_CANDIDATE"
        reason_parts.append("搜索词表现优秀，建议评估是否单独建立精准投放")
    else:
        return None

    bucket_key = (campaign, adgroup, target)
    term_key = (campaign, adgroup, search_term)
    bucket_total = bucket_spend.get(bucket_key, 0.0)
    spend_share = (spend / bucket_total) if bucket_total > 0 else None
    traffic_concentration = (
        spend_share is not None
        and bucket_total >= config.min_traffic_bucket_spend
        and spend_share >= config.traffic_concentration_ratio
    )
    if traffic_concentration and spend_share is not None:
        reason_parts.append(f"该搜索词占当前投放词花费 {spend_share:.1%}，存在流量集中风险")

    dup_count = dup_trigger_counts.get(term_key, 1)
    duplicate_trigger = dup_count >= config.min_duplicate_trigger_count
    if duplicate_trigger:
        reason_parts.append("该搜索词被多个投放词触发，存在内部竞争风险")

    if (campaign, adgroup, target) in linked_keywords:
        reason_parts.append(_LINKED_KEYWORD_HINT)

    return SearchDiagnosisRow(
        广告活动名称=campaign,
        广告组名称=adgroup,
        投放=target,
        匹配类型=match_type,
        客户搜索词=search_term,
        总花费=spend,
        总点击=clicks,
        总订单=orders,
        总ACOS=acos_val,
        总转化率=cvr_val,
        花费占比=spend_share,
        流量集中=traffic_concentration,
        重复触发=duplicate_trigger,
        重复触发投放词数=dup_count,
        诊断结论=SEARCH_CONCLUSION_LABELS.get(conclusion_code, conclusion_code),
        诊断结论码=conclusion_code,
        原因说明="；".join(reason_parts),
    )


def run_search_diagnosis(config: DiagnosisConfig | None = None) -> SearchDiagnosisResult:
    cfg = config or DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    search_result = store.get("search_analysis_result") or {}
    warnings: list[str] = []

    warnings.append("搜索词诊断为候选建议层，不做自动否定/降价/拓词操作，请人工确认后执行。")

    summary = search_result.get("summary") or []
    if search_result.get("error"):
        warnings.append(f"搜索词分析异常：{search_result['error']}")
        return SearchDiagnosisResult(
            rows=[],
            config_snapshot=cfg.to_dict(),
            warnings=warnings,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )

    if not summary:
        if store.get("search") is None:
            warnings.append("未上传搜索词报表")
        else:
            warnings.append("搜索词报表无有效汇总数据")
        return SearchDiagnosisResult(
            rows=[],
            config_snapshot=cfg.to_dict(),
            warnings=warnings,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )

    bucket_spend = _build_traffic_bucket_spend(summary)
    dup_trigger_counts = _build_duplicate_trigger_counts(summary)
    linked_keywords = _build_linked_keyword_keys()

    rows: list[SearchDiagnosisRow] = []
    for row in summary:
        evaluated = _evaluate_row(row, cfg, bucket_spend, dup_trigger_counts, linked_keywords)
        if evaluated is not None:
            rows.append(evaluated)

    rows.sort(
        key=lambda r: (
            _SEARCH_CONCLUSION_SORT_ORDER.get(r.诊断结论码, 99),
            -r.总花费,
        )
    )

    return SearchDiagnosisResult(
        rows=rows,
        config_snapshot=cfg.to_dict(),
        warnings=warnings,
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
