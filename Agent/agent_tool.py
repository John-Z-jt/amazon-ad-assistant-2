# agent_tool.py
import os
from data_df_store.data_store import store
from langchain_core.tools import tool
import pandas as pd
import streamlit as st
from Rag.rag_service import RagSummarizeService
from ad_analyzers.placement_analyzer import get_placement_analysis
from ad_analyzers.keyword_analyzer import get_keyword_analysis
from ad_analyzers.search_analyzer import get_search_analysis
from ad_analyzers.search_term_trend import get_search_term_trend
from diagnosis.budget_diagnosis import run_budget_diagnosis
from diagnosis.placement_diagnosis import run_placement_diagnosis
from diagnosis.keyword_diagnosis import run_keyword_diagnosis, KEYWORD_CONCLUSION_LABELS
from diagnosis.search_diagnosis import run_search_diagnosis, SEARCH_CONCLUSION_LABELS
from diagnosis.config import DiagnosisConfig

_rag_service = None


def _get_rag_service() -> RagSummarizeService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RagSummarizeService()
    return _rag_service


@tool(description = "从向量存储中检索参考资料。回答关于广告分析模块的功能、指标含义、设计原因等问题。")
def rag_summarize(query: str) -> str:
    """从向量库检索资料并生成 RAG 总结回复。

    Args:
        query (str): 用户查询问题。

    Returns:
        str: 模型生成的总结文本。

    Raises:
        Exception: 检索或模型调用失败。
    """
    return _get_rag_service().rag_summarize(query)


@tool(
    description="分析预算报表。如果不提供活动名称，返回所有异常活动的摘要；如果提供活动名称，返回该活动的详细信息。参数为广告活动名称（可选）。")
def analyze_budget_tool(activity_name: str = "") -> str:
    """分析预算报表，返回异常活动摘要或指定活动详情。

    Args:
        activity_name (str): 广告活动名称；为空时返回全部异常活动摘要。

    Returns:
        str: 格式化的预算分析结果文本。

    Raises:
        None
    """
    df = store.get("budget")
    if df is None:
        return "请先在左侧上传预算报表。"
    result = store.get("budget_analysis_result")
    if result is None:
        return "请先上传预算报表或刷新页面。"
    if result.get("error"):
        return f"分析出错：{result['error']}"

    cfg = DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    threshold = cfg.budget_usage_threshold
    consecutive_days = cfg.consecutive_days

    if not result["problem_activities"]:
        return (
            f"✅ 所有活动预算正常，未发现连续 ≥ {consecutive_days} 天"
            f"使用率超过 {threshold:.0%} 的情况。"
        )

    if activity_name and activity_name in result["problem_activities"]:
        summary_item = next((item for item in result["summary"] if item["广告活动名称"] == activity_name), None)
        if not summary_item:
            return f"未找到活动 '{activity_name}' 的预算数据。"
        msg = f"📊 活动「{activity_name}」预算详情：\n"
        msg += f"- 连续超标天数: {summary_item.get('连续超标天数', 0)}\n"
        msg += f"- 统计天数: {summary_item.get('统计天数', 0)}\n"
        msg += f"- 总预算: {summary_item['总预算']:.2f}\n"
        msg += f"- 总花费: {summary_item['总花费']:.2f}\n"
        msg += f"- 最高使用率: {summary_item['最高使用率']:.1%}\n"
        msg += f"- 平均使用率: {summary_item['平均使用率']:.1%}\n"
        msg += "\n💡 是否建议加码请调用 diagnose_budget_tool。"
        return msg

    sorted_summary = sorted(result["summary"], key=lambda x: x["最高使用率"], reverse=True)
    top5 = sorted_summary[:5]
    total = len(result["problem_activities"])
    msg = (
        f"⚠️ 发现 {total} 个活动连续 ≥ {consecutive_days} 天预算使用率超过 {threshold:.0%}，"
        f"其中最严重的 {len(top5)} 个：\n"
    )
    for item in top5:
        msg += (
            f"- {item['广告活动名称']}: 连续超标 {item.get('连续超标天数', 0)} 天, "
            f"最高使用率 {item['最高使用率']:.0%}\n"
        )
    if total > 5:
        msg += f"（其余 {total - 5} 个请指定活动名称查看详情）\n"
    msg += "\n💡 预算是否加码请调用 diagnose_budget_tool；每日明细见【手动分析】。"
    return msg


@tool(
    description=(
        "预算诊断：结合库存、业务销量与活动ACOS，判断问题活动是否建议加预算。"
        "参数 activity_name 可选；为空返回全部问题活动的诊断结论。"
    )
)
def diagnose_budget_tool(activity_name: str = "") -> str:
    """运行预算诊断流水线，返回结构化建议。"""
    if store.get("budget") is None:
        return "请先在左侧上传预算报表。"

    cfg = DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    cached = store.get("budget_diagnosis_result")
    if cached is None:
        diag = run_budget_diagnosis(cfg)
        cached = diag.to_dict()
        store.set("budget_diagnosis_result", cached)

    warnings = cached.get("warnings") or []
    rows = cached.get("rows") or []

    if not rows:
        budget_result = store.get("budget_analysis_result") or {}
        if not budget_result.get("problem_activities"):
            return (
                f"✅ 无活动满足连续 ≥ {cfg.consecutive_days} 天"
                f"使用率 > {cfg.budget_usage_threshold:.0%}，无需预算诊断。"
            )
        msg = "⚠️ 有问题活动但暂无诊断结果，请确认已上传推广的商品、库存、业务报表。"
        if warnings:
            msg += "\n" + "\n".join(f"- {w}" for w in warnings)
        return msg

    if activity_name:
        target = next((r for r in rows if r.get("广告活动名称") == activity_name), None)
        if not target:
            return f"活动「{activity_name}」不在当前预算问题列表中，或名称不匹配。"
        rows = [target]

    msg_parts = [f"🩺 预算诊断（阈值：连续{cfg.consecutive_days}天>{cfg.budget_usage_threshold:.0%}，"
                 f"库存≥{cfg.min_days_of_cover:.0f}天，ACOS≤{cfg.max_campaign_acos:.0%}）\n"]
    if warnings:
        msg_parts.append("⚠️ " + "；".join(warnings) + "\n")

    for row in rows:
        acos = row.get("活动ACOS")
        cover = row.get("库存可售天数")
        acos_text = f"{acos:.1%}" if acos is not None else "—"
        cover_text = f"{cover:.1f}天" if cover is not None else "—"
        msg_parts.append(
            f"\n【{row.get('广告活动名称')}】\n"
            f"- 结论: {row.get('诊断结论')}\n"
            f"- 连续超标: {row.get('连续超标天数')} 天 | 最差ASIN: {row.get('最差ASIN') or '—'}\n"
            f"- 库存可售: {cover_text} | 活动ACOS: {acos_text}\n"
            f"- 原因: {row.get('原因说明')}\n"
        )

    msg_parts.append("\n💡 详细表格见【手动分析 → 预算诊断】。")
    return "".join(msg_parts)


@tool(
    description=(
        "广告位诊断（纯数据规则）：搜索位占比/ACOS/CVR/订单、库存，"
        "返回建议加/试加溢价、搜索侧竞争力偏弱等结论。"
        "Listing 仅作原因说明中的风险提示，不改变结论。"
        "用户问溢价/竞价/搜索侧竞争力时用此工具；看各放置 ACOS 用 analyze_placement_tool。"
        "参数 activity_name 可选，空=全部可诊断活动。"
    )
)
def diagnose_placement_tool(activity_name: str = "") -> str:
    """运行广告位诊断流水线。"""
    if store.get("placement") is None:
        return "请先在左侧上传广告位报表。"

    cfg = DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    cached = store.get("placement_diagnosis_result")
    if cached is None:
        diag = run_placement_diagnosis(cfg)
        cached = diag.to_dict()
        store.set("placement_diagnosis_result", cached)

    warnings = cached.get("warnings") or []
    rows = cached.get("rows") or []

    if not rows:
        msg = "⚠️ 暂无可诊断活动。请确认已上传广告位、预算、推广的商品及库存/业务报表。"
        if warnings:
            msg += "\n" + "\n".join(f"- {w}" for w in warnings)
        return msg

    if activity_name:
        target = next((r for r in rows if r.get("广告活动名称") == activity_name), None)
        if not target:
            return f"活动「{activity_name}」不在广告位诊断列表中（可能为预算异常活动或名称不匹配）。"
        rows = [target]

    msg_parts = [
        f"🩺 广告位诊断（搜索位点击占比阈值 {cfg.min_search_click_share:.0%}，"
        f"搜索位 ACOS≤{cfg.max_search_placement_acos:.0%}）\n"
    ]
    if warnings:
        msg_parts.append("⚠️ " + "；".join(warnings) + "\n")

    for row in rows:
        share = row.get("搜索位点击占比")
        spend_share = row.get("搜索位花费占比")
        acos = row.get("搜索位ACOS")
        cvr = row.get("搜索位转化率")
        share_text = f"{share:.1%}" if share is not None else "—"
        spend_text = f"{spend_share:.1%}" if spend_share is not None else "—"
        acos_text = f"{acos:.1%}" if acos is not None else "—"
        cvr_text = f"{cvr:.1%}" if cvr is not None else "—"
        msg_parts.append(
            f"\n【{row.get('广告活动名称')}】\n"
            f"- 结论: {row.get('诊断结论')}\n"
            f"- 搜索位点击占比: {share_text} | 花费占比: {spend_text}\n"
            f"- 搜索位 ACOS: {acos_text} | 转化率: {cvr_text}\n"
            f"- 最差ASIN: {row.get('最差ASIN') or '—'}\n"
            f"- 原因: {row.get('原因说明')}\n"
        )

    msg_parts.append(
        "\n💡 明细见【手动分析 → 广告位诊断】。"
        "结论仅由广告位数据决定；Listing 自评为可选参考，见各条原因说明末尾。"
        "「结构正常」须搜索位占比、ACOS、订单量同时达标。"
    )
    return "".join(msg_parts)


@tool(description="分析广告位报表。如果不提供活动名称，返回所有活动的异常摘要（最差广告位）；如果提供活动名称，返回该活动的广告位详情。参数为广告活动名称（可选）。")
def analyze_placement_tool(activity_name: str = "") -> str:
    """分析广告位报表，返回异常摘要或指定活动详情。

    Args:
        activity_name (str): 广告活动名称；为空时返回最差广告位摘要。

    Returns:
        str: 格式化的广告位分析结果文本。

    Raises:
        None
    """
    df = store.get("placement")
    if df is None:
        return "请先在左侧上传广告位报表。"
    result = store.get("placement_analysis_result")
    if result is None:
        return "请先上传广告位报表或刷新页面。"
    if result.get("error"):
        return f"分析出错：{result['error']}"
    if not result["summary"]:
        return "没有有效的广告位数据。"

    # 如果传入了活动名称
    if activity_name:
        # 查找该活动的汇总记录
        activity_summary = [item for item in result["summary"] if item['广告活动名称'] == activity_name]
        if not activity_summary:
            return f"未找到活动 '{activity_name}' 的广告位数据。"
        msg = f"📊 活动「{activity_name}」广告位详情：\n"
        for item in activity_summary:
            acos = item.get('整体ACOS', 0)
            msg += f"- {item['放置']}: ACOS {acos:.1%}\n"
        # 可选：附上每日明细的提示
        msg += "\n💡 详细每日明细请切换到【手动分析】标签页。"
        return msg

    # 无参：返回所有活动的异常摘要（只列出每个活动的**最差广告位**，且只展示前5个活动）
    # 按整体ACOS最高的广告位排序，但这里需要每个活动的最差广告位，可以从 `worst_placements_by_activity` 中获取
    worst_list = result.get("worst_placements_by_activity", [])
    if not worst_list:
        return "✅ 所有活动广告位表现正常。"
    # 去重活动（取每个活动的第一个最差广告位，因为可能有多个）
    unique_worst = {}
    for w in worst_list:
        act = w['广告活动名称']
        if act not in unique_worst:
            unique_worst[act] = w
    # 按ACOS降序排序，取前5个最差的活动
    sorted_worst = sorted(unique_worst.values(), key=lambda x: x.get('整体ACOS', 0), reverse=True)[:5]
    msg = "⚠️ 以下活动的广告位表现最差（ACOS最高）：\n"
    for w in sorted_worst:
        msg += f"- {w['广告活动名称']}: {w['放置']} ACOS {w['整体ACOS']:.1%}\n"
    if len(unique_worst) > 5:
        msg += f"（其余 {len(unique_worst) - 5} 个活动请指定名称查看详情）\n"
    msg += "\n💡 详细数据请切换到【手动分析】标签页。"
    return msg


@tool(description="分析投放词报表。支持参数：activity_name(活动名), adgroup_name(广告组名), keyword(关键词), match_type(匹配类型)。可任意组合。")
def analyze_keyword_tool(
    activity_name: str = "",
    adgroup_name: str = "",
    keyword: str = "",
    match_type: str = "",
) -> str:
    """分析投放词报表，支持按活动、广告组、关键词、匹配类型筛选。

    Args:
        activity_name (str): 广告活动名称，可选。
        adgroup_name (str): 广告组名称，可选。
        keyword (str): 投放关键词，可选。
        match_type (str): 匹配类型，可选。

    Returns:
        str: 格式化的投放词分析结果文本。

    Raises:
        None
    """
    df = store.get("keyword")
    if df is None:
        return "请先在左侧上传投放词报表。"
    result = store.get("keyword_analysis_result")
    if result is None:
        return "请先上传投放词报表或刷新页面。"
    if result.get("error"):
        return f"分析出错：{result['error']}"
    if not result["summary"]:
        return "没有有效的投放词数据。"

    matches = result["summary"]
    if activity_name:
        matches = [m for m in matches if m['广告活动名称'] == activity_name]
    if adgroup_name:
        matches = [m for m in matches if m['广告组名称'] == adgroup_name]
    if keyword:
        matches = [m for m in matches if m['投放'] == keyword]
    if match_type:
        matches = [m for m in matches if m.get('匹配类型') == match_type]

    if not matches:
        return "未找到匹配的数据。"
    if len(matches) == 1:
        m = matches[0]
        return (
            f"📊 投放词详情：\n活动: {m['广告活动名称']}\n广告组: {m['广告组名称']}\n"
            f"关键词: {m['投放']}\n匹配类型: {m.get('匹配类型', '—')}\n"
            f"总花费: {m['总花费']:.2f}\n总销售额: {m['总销售额']:.2f}\n订单数: {m['总订单数']}\n"
            f"平均CPC: {m['平均CPC']:.2f}\n点击率: {m['总点击率']:.1%}\n转化率: {m['总转化率']:.1%}\n"
            f"ACOS: {m['总ACOS']:.1%}\n"
            f"💡 需分诊信号（高ACOS/潜力/重复投放）请用 diagnose_keyword_tool。"
        )
    else:
        abnormal = [m for m in matches if m['总订单数'] == 0 and m['总花费'] > 0]
        if abnormal:
            top = sorted(abnormal, key=lambda x: x['总花费'], reverse=True)[:5]
            msg = f"⚠️ 发现 {len(abnormal)} 个高花费零订单的组合，最严重的{len(top)}个：\n"
            for m in top:
                msg += (
                    f"- {m['广告活动名称']}/{m['广告组名称']}/{m['投放']}/"
                    f"{m.get('匹配类型', '—')}: 花费 {m['总花费']:.2f}\n"
                )
            msg += "\n💡 需查搜索词或分诊结论请用 diagnose_keyword_tool。"
            return msg
        else:
            msg = f"✅ 指定范围内所有关键词都有订单，共 {len(matches)} 个组合。"
            msg += "\n💡 需分诊信号（高ACOS/潜力/重复投放）请用 diagnose_keyword_tool。"
            return msg


_KEYWORD_DIAGNOSIS_TYPE_ORDER = [
    "REVIEW_SEARCH_ZERO_CONV",
    "REVIEW_SEARCH_HIGH_ACOS",
    "REVIEW_SEARCH_POTENTIAL",
]
_KEYWORD_DIAGNOSIS_SAMPLES_PER_TYPE = 3
_DUPLICATE_RISK_LABEL = "⚠️ 重复投放风险（标签）"


def _format_keyword_diagnosis_row_brief(row: dict) -> str:
    acos = row.get("总ACOS")
    cvr = row.get("总转化率")
    acos_text = f"{acos:.1%}" if acos is not None else "—"
    cvr_text = f"{cvr:.1%}" if cvr is not None else "—"
    dup_part = ""
    if row.get("重复投放"):
        dup = int(row.get("重复活动数") or 0)
        dup_part = f" | ⚠️重复投放({dup}活动)"
    return (
        f"- {row.get('广告活动名称')}/{row.get('广告组名称')}/{row.get('投放')}/"
        f"{row.get('匹配类型', '—')} | "
        f"花费 {float(row.get('总花费') or 0):.2f} | 点击 {int(row.get('总点击') or 0)} | "
        f"订单 {int(row.get('总订单') or 0)} | ACOS {acos_text} | 转化率 {cvr_text}{dup_part}"
    )


def _format_keyword_diagnosis_grouped(rows: list[dict], cfg: DiagnosisConfig) -> str:
    """按结论类型分组输出摘要与样例。"""
    by_code: dict[str, list[dict]] = {code: [] for code in _KEYWORD_DIAGNOSIS_TYPE_ORDER}
    for row in rows:
        code = row.get("诊断结论码") or ""
        if code in by_code:
            by_code[code].append(row)

    scope = f"共 {len(rows)} 条异常"
    dup_count = sum(1 for r in rows if r.get("重复投放"))
    msg_parts = [
        f"🩺 投放词分诊摘要（{scope}）\n"
        f"阈值：点击≥{cfg.min_keyword_clicks}、花费≥{cfg.min_keyword_spend}、"
        f"无转化点击≥{cfg.min_zero_conv_clicks}、高ACOS>{cfg.max_keyword_acos:.0%}"
        f"且订单≥{cfg.min_keyword_orders_for_acos}、重复活动≥{cfg.min_duplicate_campaigns}\n",
    ]

    summary_lines = []
    for code in _KEYWORD_DIAGNOSIS_TYPE_ORDER:
        count = len(by_code[code])
        if count:
            summary_lines.append(f"- {KEYWORD_CONCLUSION_LABELS[code]}：{count} 条")
    if dup_count:
        summary_lines.append(f"- {_DUPLICATE_RISK_LABEL}：{dup_count} 条（叠加于主结论，非独立类型）")
    msg_parts.append("类型分布：\n" + "\n".join(summary_lines) + "\n")

    for code in _KEYWORD_DIAGNOSIS_TYPE_ORDER:
        type_rows = by_code[code]
        if not type_rows:
            continue
        type_rows = sorted(type_rows, key=lambda r: float(r.get("总花费") or 0), reverse=True)
        sample_n = min(_KEYWORD_DIAGNOSIS_SAMPLES_PER_TYPE, len(type_rows))
        msg_parts.append(f"\n{KEYWORD_CONCLUSION_LABELS[code]}（共 {len(type_rows)} 条，展示 {sample_n} 条）\n")
        for row in type_rows[:sample_n]:
            msg_parts.append(_format_keyword_diagnosis_row_brief(row) + "\n")
        if len(type_rows) > sample_n:
            msg_parts.append(f"  … 另有 {len(type_rows) - sample_n} 条，请至手动分析页查看\n")

    msg_parts.append(
        "\n💡 完整列表、筛选与导出请前往【手动分析 → 投放词分诊】。"
        "本层仅分诊信号；具体否定/降价/拓词请结合搜索词报表（下一阶段支持搜索词诊断）。"
    )
    return "".join(msg_parts)


@tool(
    description=(
        "投放词分诊（纯数据规则）：识别高花费无转化、高 ACOS、潜力词、重复投放等信号，"
        "引导用户下钻搜索词报表；不给否定/降价/拓词最终结论。"
        "用户问投放词该否定吗、要不要降价、哪些词要查搜索词时用此工具；"
        "看花费/ACOS/订单明细用 analyze_keyword_tool。"
        "参数 activity_name、adgroup_name、keyword、match_type 可选，可任意组合筛选。"
    )
)
def diagnose_keyword_tool(
    activity_name: str = "",
    adgroup_name: str = "",
    keyword: str = "",
    match_type: str = "",
) -> str:
    """运行投放词分诊流水线。"""
    if store.get("keyword") is None:
        return "请先在左侧上传投放词报表。"

    cfg = DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    cached = store.get("keyword_diagnosis_result")
    if cached is None:
        diag = run_keyword_diagnosis(cfg)
        cached = diag.to_dict()
        store.set("keyword_diagnosis_result", cached)

    warnings = cached.get("warnings") or []
    rows = cached.get("rows") or []

    if activity_name:
        rows = [r for r in rows if r.get("广告活动名称") == activity_name]
    if adgroup_name:
        rows = [r for r in rows if r.get("广告组名称") == adgroup_name]
    if keyword:
        rows = [r for r in rows if r.get("投放") == keyword]
    if match_type:
        rows = [r for r in rows if r.get("匹配类型") == match_type]

    if not rows:
        msg = "✅ 未发现需关注的投放词异常（或样本未达阈值）。"
        if activity_name or adgroup_name or keyword or match_type:
            msg = "未找到符合筛选条件的投放词分诊结果（可能表现正常或样本不足）。"
        if warnings:
            msg += "\n" + "\n".join(f"- {w}" for w in warnings)
        return msg

    msg_parts: list[str] = []
    if warnings:
        msg_parts.append("⚠️ " + "；".join(warnings) + "\n")

    has_filter = bool(activity_name or adgroup_name or keyword or match_type)
    if has_filter:
        filter_desc = []
        if activity_name:
            filter_desc.append(f"活动={activity_name}")
        if adgroup_name:
            filter_desc.append(f"广告组={adgroup_name}")
        if keyword:
            filter_desc.append(f"投放词={keyword}")
        if match_type:
            filter_desc.append(f"匹配类型={match_type}")
        msg_parts.append(f"当前筛选（{'，'.join(filter_desc)}）\n")

    grouped = _format_keyword_diagnosis_grouped(rows, cfg)
    if has_filter:
        grouped = grouped.replace("共 ", "筛选下共 ", 1)
    msg_parts.append(grouped)
    return "".join(msg_parts)


@tool(description="分析推广的商品报表。支持参数：activity_name(活动名), adgroup_name(广告组名), ad_asin(广告ASIN)。可任意组合。")
def analyze_product_sponsored_tool(activity_name: str = "", adgroup_name: str = "", ad_asin: str = "") -> str:
    """分析推广的商品报表，支持按活动、广告组、广告ASIN筛选。

    Args:
        activity_name (str): 广告活动名称，可选。
        adgroup_name (str): 广告组名称，可选。
        ad_asin (str): 广告ASIN，可选。

    Returns:
        str: 格式化的推广商品分析结果文本。

    Raises:
        None
    """
    df = store.get("product_sponsored")
    if df is None:
        return "请先在左侧上传推广的商品报告。"
    result = store.get("product_sponsored_analysis_result")
    if result is None:
        return "请先上传推广的商品报告或刷新页面。"
    if result.get("error"):
        return f"分析出错：{result['error']}"
    if not result["summary"]:
        return "没有有效的推广商品数据。"

    matches = result["summary"]
    if activity_name:
        matches = [m for m in matches if m["广告活动名称"] == activity_name]
    if adgroup_name:
        matches = [m for m in matches if m["广告组名称"] == adgroup_name]
    if ad_asin:
        matches = [m for m in matches if m["广告ASIN"] == ad_asin]

    if not matches:
        return "未找到匹配的数据。"
    if len(matches) == 1:
        m = matches[0]
        return (
            f"📊 推广商品详情：\n"
            f"活动: {m['广告活动名称']}\n"
            f"广告组: {m['广告组名称']}\n"
            f"广告ASIN: {m.get('广告ASIN', '-')}\n"
            f"广告SKU: {m.get('广告SKU', '-')}\n"
            f"总花费: {m['总花费']:.2f}\n"
            f"总销售额: {m['总销售额']:.2f}\n"
            f"订单数: {m['总订单数']}\n"
            f"销售量: {m['总销售量']}\n"
            f"平均CPC: {m['平均CPC']:.2f}\n"
            f"点击率: {m['总点击率']:.1%}\n"
            f"7天转化率: {m['7天转化率']:.1%}\n"
            f"ACOS: {m['总ACOS']:.1%}\n"
            f"ROAS: {m['总ROAS']:.2f}"
        )

    abnormal = [m for m in matches if m["总订单数"] == 0 and m["总花费"] > 0]
    if abnormal:
        top = sorted(abnormal, key=lambda x: x["总花费"], reverse=True)[:5]
        msg = f"⚠️ 发现 {len(abnormal)} 个高花费零订单的 ASIN，最严重的{len(top)}个：\n"
        for m in top:
            msg += f"- {m['广告活动名称']}/{m['广告组名称']}/{m['广告ASIN']}: 花费 {m['总花费']:.2f}\n"
        return msg
    return f"✅ 指定范围内所有 ASIN 都有订单，共 {len(matches)} 个组合。"


@tool(description="分析搜索词报表。支持按广告活动、广告组、客户搜索词、匹配类型查询。不传参数返回全局摘要（否定词候选和高潜力词候选的数量）。")
def analyze_search_tool(
    activity_name: str = "",
    adgroup_name: str = "",
    search_term: str = "",
    match_type: str = "",
) -> str:
    """分析搜索词报表，支持按活动、广告组、客户搜索词、匹配类型筛选。

    Args:
        activity_name (str): 广告活动名称，可选。
        adgroup_name (str): 广告组名称，可选。
        search_term (str): 客户搜索词，可选。
        match_type (str): 匹配类型，可选。

    Returns:
        str: 格式化的搜索词分析结果文本。

    Raises:
        None
    """
    df = store.get("search")
    if df is None:
        return "请先在左侧上传搜索词报表。"
    result = store.get("search_analysis_result")
    if result is None:
        return "请先上传搜索词报表或刷新页面。"
    if result.get("error"):
        return f"分析出错：{result['error']}"
    if not result["summary"]:
        return "没有有效的搜索词数据。"

    summary_list = result["summary"]

    # 按参数过滤
    matches = summary_list
    if activity_name:
        matches = [m for m in matches if m['广告活动名称'] == activity_name]
    if adgroup_name:
        matches = [m for m in matches if m['广告组名称'] == adgroup_name]
    if search_term:
        matches = [m for m in matches if m['客户搜索词'] == search_term]
    if match_type:
        matches = [m for m in matches if m.get('匹配类型') == match_type]

    if not matches:
        return "未找到匹配的数据。"

    # 如果只有一条，返回详情
    if len(matches) == 1:
        m = matches[0]
        msg = f"📊 搜索词详情：\n"
        msg += f"- 客户搜索词: {m['客户搜索词']}\n"
        msg += f"- 广告活动: {m['广告活动名称']}\n"
        msg += f"- 广告组: {m['广告组名称']}\n"
        msg += f"- 触发投放词: {m['投放']}\n"
        msg += f"- 匹配类型: {m.get('匹配类型', '—')}\n"
        msg += f"- 总花费: {m['总花费']:.2f}\n"
        msg += f"- 总点击量: {m['总点击量']}\n"
        msg += f"- 总订单数: {m['总订单数']}\n"
        msg += f"- 平均CPC: {m['平均CPC']:.2f}\n"
        msg += f"- ACOS: {m['总ACOS']:.1%}\n"
        msg += "\n💡 详细每日明细请切换到【手动分析】标签页。"
        msg += "\n💡 否定/拓词候选与风险标签请用 diagnose_search_tool。"
        return msg

    df_all = pd.DataFrame(matches)
    # 否定词候选：按活动分组阈值（类似手动分析逻辑）
    group_means = df_all.groupby('广告活动名称')[['总点击量', '总花费']].mean().rename(
        columns={'总点击量': 'mean_clicks', '总花费': 'mean_spend'})
    df_with_means = df_all.merge(group_means, left_on='广告活动名称', right_index=True)
    negation = df_with_means[
        (df_with_means['总订单数'] == 0) &
        (df_with_means['总点击量'] > 0.4 * df_with_means['mean_clicks']) &
        (df_with_means['总花费'] > 0.4 * df_with_means['mean_spend'])
        ]

    # 高潜力词候选
    potential = df_all[(df_all['总订单数'] > 0) & (df_all['客户搜索词'] != df_all['投放']) & (df_all['总点击量'] > 2)]
    msg = f"🔍 搜索词分析（共 {len(df_all)} 个组合）：\n"
    if not negation.empty:
        msg += f"🚫 否定词候选（高点击高花费零订单）: {len(negation)} 个\n"
    if not potential.empty:
        msg += f"🌟 高潜力拓词候选（有订单未投放）: {len(potential)} 个\n"
    if negation.empty and potential.empty:
        msg += "✅ 未发现明显异常的搜索词。"
    msg += "\n💡 候选与风险诊断请用 diagnose_search_tool；明细见【手动分析 → 搜索词诊断】。"
    return msg


_SEARCH_DIAGNOSIS_TYPE_ORDER = [
    "NEGATIVE_CANDIDATE",
    "HIGH_ACOS_TERM",
    "EXPANSION_CANDIDATE",
]
_SEARCH_DIAGNOSIS_SAMPLES_PER_TYPE = 3
_SEARCH_RISK_TRAFFIC_LABEL = "⚠️ 流量集中风险（标签）"
_SEARCH_RISK_DUP_LABEL = "⚠️ 重复触发风险（标签）"


def _format_search_diagnosis_row_brief(row: dict) -> str:
    acos = row.get("总ACOS")
    acos_text = f"{acos:.1%}" if acos is not None else "—"
    share = row.get("花费占比")
    share_text = f"{share:.1%}" if share is not None else "—"
    tags = []
    if row.get("流量集中"):
        tags.append(f"流量集中{share_text}")
    if row.get("重复触发"):
        tags.append(f"重复触发{int(row.get('重复触发投放词数') or 0)}词")
    tag_part = f" | {'，'.join(tags)}" if tags else ""
    return (
        f"- {row.get('广告活动名称')}/{row.get('广告组名称')}/"
        f"触发:{row.get('投放')}/{row.get('匹配类型', '—')}/{row.get('客户搜索词')} | "
        f"花费 {float(row.get('总花费') or 0):.2f} | 点击 {int(row.get('总点击') or 0)} | "
        f"订单 {int(row.get('总订单') or 0)} | ACOS {acos_text}{tag_part}"
    )


def _format_search_diagnosis_grouped(rows: list[dict], cfg: DiagnosisConfig) -> str:
    by_code: dict[str, list[dict]] = {code: [] for code in _SEARCH_DIAGNOSIS_TYPE_ORDER}
    for row in rows:
        code = row.get("诊断结论码") or ""
        if code in by_code:
            by_code[code].append(row)

    traffic_count = sum(1 for r in rows if r.get("流量集中"))
    dup_count = sum(1 for r in rows if r.get("重复触发"))

    msg_parts = [
        f"🩺 搜索词诊断摘要（共 {len(rows)} 条候选）\n"
        f"阈值：否定点击≥{cfg.min_negative_clicks}、花费≥{cfg.min_negative_spend}、"
        f"高ACOS>{cfg.max_search_acos:.0%}且订单≥{cfg.min_high_acos_orders}、"
        f"流量集中≥{cfg.traffic_concentration_ratio:.0%}\n",
    ]

    summary_lines = []
    for code in _SEARCH_DIAGNOSIS_TYPE_ORDER:
        count = len(by_code[code])
        if count:
            summary_lines.append(f"- {SEARCH_CONCLUSION_LABELS[code]}：{count} 条")
    if traffic_count:
        summary_lines.append(f"- {_SEARCH_RISK_TRAFFIC_LABEL}：{traffic_count} 条（叠加于主结论）")
    if dup_count:
        summary_lines.append(f"- {_SEARCH_RISK_DUP_LABEL}：{dup_count} 条（叠加于主结论）")
    msg_parts.append("类型分布：\n" + "\n".join(summary_lines) + "\n")

    for code in _SEARCH_DIAGNOSIS_TYPE_ORDER:
        type_rows = by_code[code]
        if not type_rows:
            continue
        type_rows = sorted(type_rows, key=lambda r: float(r.get("总花费") or 0), reverse=True)
        sample_n = min(_SEARCH_DIAGNOSIS_SAMPLES_PER_TYPE, len(type_rows))
        msg_parts.append(f"\n{SEARCH_CONCLUSION_LABELS[code]}（共 {len(type_rows)} 条，展示 {sample_n} 条）\n")
        for row in type_rows[:sample_n]:
            msg_parts.append(_format_search_diagnosis_row_brief(row) + "\n")
        if len(type_rows) > sample_n:
            msg_parts.append(f"  … 另有 {len(type_rows) - sample_n} 条，请至手动分析页查看\n")

    msg_parts.append(
        "\n💡 完整列表、筛选与导出请前往【手动分析 → 搜索词诊断】。"
        "本层输出候选建议，不做自动否定/降价/拓词，请人工确认后执行。"
    )
    return "".join(msg_parts)


@tool(
    description=(
        "搜索词诊断（纯数据规则）：否定候选、高ACOS、拓词候选及流量集中/重复触发风险标签；"
        "定位具体问题来源，输出可执行候选与原因，不做自动否定/降价/拓词。"
        "用户问哪些搜索词该否定、高ACOS搜索词、拓词候选、流量是否集中时用此工具；"
        "看花费/订单明细用 analyze_search_tool。"
        "参数 activity_name、adgroup_name、search_term、match_type 可选，可任意组合筛选。"
    )
)
def diagnose_search_tool(
    activity_name: str = "",
    adgroup_name: str = "",
    search_term: str = "",
    match_type: str = "",
) -> str:
    """运行搜索词诊断流水线。"""
    if store.get("search") is None:
        return "请先在左侧上传搜索词报表。"

    cfg = DiagnosisConfig.from_dict(store.get("diagnosis_config"))
    cached = store.get("search_diagnosis_result")
    if cached is None:
        diag = run_search_diagnosis(cfg)
        cached = diag.to_dict()
        store.set("search_diagnosis_result", cached)

    warnings = cached.get("warnings") or []
    rows = cached.get("rows") or []

    if activity_name:
        rows = [r for r in rows if r.get("广告活动名称") == activity_name]
    if adgroup_name:
        rows = [r for r in rows if r.get("广告组名称") == adgroup_name]
    if search_term:
        rows = [r for r in rows if r.get("客户搜索词") == search_term]
    if match_type:
        rows = [r for r in rows if r.get("匹配类型") == match_type]

    if not rows:
        msg = "✅ 未发现需关注的搜索词候选（或样本未达阈值）。"
        if activity_name or adgroup_name or search_term or match_type:
            msg = "未找到符合筛选条件的搜索词诊断结果（可能表现正常或样本不足）。"
        if warnings:
            msg += "\n" + "\n".join(f"- {w}" for w in warnings)
        return msg

    msg_parts: list[str] = []
    if warnings:
        msg_parts.append("⚠️ " + "；".join(warnings) + "\n")

    has_filter = bool(activity_name or adgroup_name or search_term or match_type)
    if has_filter:
        filter_desc = []
        if activity_name:
            filter_desc.append(f"活动={activity_name}")
        if adgroup_name:
            filter_desc.append(f"广告组={adgroup_name}")
        if search_term:
            filter_desc.append(f"搜索词={search_term}")
        if match_type:
            filter_desc.append(f"匹配类型={match_type}")
        msg_parts.append(f"当前筛选（{'，'.join(filter_desc)}）\n")

    grouped = _format_search_diagnosis_grouped(rows, cfg)
    if has_filter:
        grouped = grouped.replace("共 ", "筛选下共 ", 1)
    msg_parts.append(grouped)
    return "".join(msg_parts)


@tool(
    description="分析搜索词的市场趋势（店铺级别）。参数：search_term（必填，客户搜索词），返回该词的每日排名、份额、ACOS 趋势及主要贡献广告活动。")
def analyze_search_term_tool(search_term: str) -> str:
    """分析指定搜索词的市场趋势与贡献活动。

    Args:
        search_term (str): 客户搜索词，必填。

    Returns:
        str: 格式化的搜索词趋势分析结果文本。

    Raises:
        None
    """
    df = store.get("search_share")
    if df is None:
        return "请先在左侧上传搜索词份额报告。"
    result = store.get("search_term_trend_result")
    if result is None:
        return "请先上传搜索词份额报告或刷新页面。"
    
    if not result["search_terms"]:
        return "没有有效的搜索词数据。"
    if search_term not in result["search_terms"]:
        return f"未找到搜索词 '{search_term}' 的数据。"

    data = result["data"][search_term]
    trend = data['trend']
    attribution = data['attribution']

    if not trend:
        return f"搜索词 '{search_term}' 无趋势数据。"

    # 获取最近7天的趋势（取最后7条）
    recent = trend[-7:] if len(trend) > 7 else trend
    msg = f"📊 搜索词「{search_term}」市场趋势（店铺级别）：\n"
    for day in recent:
        date = day['date'].strftime('%Y-%m-%d')
        rank = day.get('impression_rank', '-')
        share = day.get('impression_share', 0)
        acos = day.get('acos', 0)
        msg += f"- {date}: 排名 {rank}, 份额 {share:.1%}, ACOS {acos:.1%}\n"

    # 统计主要贡献的广告活动（按花费或点击量）
    if attribution:
        # 按广告活动聚合总花费
        from collections import defaultdict
        campaign_spend = defaultdict(float)
        for item in attribution:
            campaign_spend[item['campaign']] += item['spend']
        top_campaigns = sorted(campaign_spend.items(), key=lambda x: x[1], reverse=True)[:3]
        if top_campaigns:
            msg += "\n💰 主要贡献的广告活动（按花费）：\n"
            for camp, spend in top_campaigns:
                msg += f"- {camp}: {spend:.2f}\n"

    msg += "\n💡 详细每日明细请切换到【手动分析】标签页。"
    return msg

@tool(description="无入参，无返回值，调用后触发中间件自动为广告报告生成的场景动态注入上下文信息，为后续提示词切换提供上下文信息")
def fill_context_for_report():
    """触发中间件切换为报告生成提示词上下文。

    Returns:
        str: 调用确认消息。

    Raises:
        None
    """
    return "fill_context_for_report已调用"






