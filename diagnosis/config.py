from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from typing import Any

from auth.user_context import get_current_user_id, get_user_data_dir
@dataclass
class DiagnosisConfig:
    """预算与广告位诊断的共享阈值配置。"""

    budget_usage_threshold: float = 0.9
    consecutive_days: int = 3
    min_days_of_cover: float = 30.0
    max_campaign_acos: float = 0.20
    include_inbound_inventory: bool = False
    min_search_click_share: float = 0.20
    min_search_clicks: int = 20
    max_search_placement_acos: float = 0.20
    min_search_orders: int = 3
    min_search_cvr: float = 0.08
    max_pp_acos: float = 0.25
    min_pp_clicks: int = 10
    min_pp_orders: int = 2
    min_pp_cvr: float = 0.05
    pp_good_min_conditions: int = 2
    min_keyword_clicks: int = 10
    min_keyword_spend: float = 5.0
    max_keyword_acos: float = 0.30
    min_keyword_orders_potential: int = 2
    max_keyword_acos_potential: float = 0.20
    min_keyword_cvr_potential: float = 0.08
    min_duplicate_campaigns: int = 2
    min_zero_conv_clicks: int = 20
    min_keyword_orders_for_acos: int = 2
    min_negative_clicks: int = 20
    min_negative_spend: float = 5.0
    min_high_acos_orders: int = 2
    max_search_acos: float = 0.30
    min_expansion_orders: int = 2
    max_expansion_acos: float = 0.20
    traffic_concentration_ratio: float = 0.60
    min_traffic_bucket_spend: float = 10.0
    min_duplicate_trigger_count: int = 2
    version: str = "1.4"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DiagnosisConfig":
        if not data:
            return cls()
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def fingerprint(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)


def _config_path(user_id: str) -> str:
    return str(get_user_data_dir(user_id) / "diagnosis_config.json")


def load_diagnosis_config(user_id: str | None = None) -> DiagnosisConfig:
    if user_id is None:
        user_id = get_current_user_id()
    path = _config_path(user_id)
    if not os.path.isfile(path):
        return DiagnosisConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DiagnosisConfig.from_dict(data)
    except (json.JSONDecodeError, OSError, TypeError):
        return DiagnosisConfig()


def save_diagnosis_config(config: DiagnosisConfig, user_id: str | None = None) -> None:
    if user_id is None:
        user_id = get_current_user_id()
    path = _config_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)
