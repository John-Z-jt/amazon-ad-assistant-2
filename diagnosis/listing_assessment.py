import json
import os

from auth.user_context import get_current_user_id, get_user_data_dir

LISTING_FIELDS = ["五点", "A+", "价格竞争力", "评价评分"]
LISTING_LEVELS = ["良好", "一般", "差"]


def _listing_path(user_id: str) -> str:
    return str(get_user_data_dir(user_id) / "listing_by_asin.json")


def load_listing_by_asin(user_id: str | None = None) -> dict[str, dict[str, str]]:
    if user_id is None:
        user_id = get_current_user_id()
    path = _listing_path(user_id)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return {}


def save_listing_for_asin(
    asin: str,
    assessment: dict[str, str],
    user_id: str | None = None,
) -> None:
    if user_id is None:
        user_id = get_current_user_id()
    asin_key = str(asin).strip().upper()
    all_data = load_listing_by_asin(user_id)
    all_data[asin_key] = {field: assessment.get(field, "") for field in LISTING_FIELDS}
    path = _listing_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)


def evaluate_listing_assessment(assessment: dict[str, str] | None) -> str:
    """返回 missing / fail / pass。"""
    if not assessment:
        return "missing"
    for field in LISTING_FIELDS:
        if assessment.get(field) not in LISTING_LEVELS:
            return "missing"
    if any(assessment.get(field) == "差" for field in LISTING_FIELDS):
        return "fail"
    good_count = sum(1 for field in LISTING_FIELDS if assessment.get(field) == "良好")
    if good_count == 4:
        return "pass"
    if good_count >= 3:
        return "pass"
    return "fail"
