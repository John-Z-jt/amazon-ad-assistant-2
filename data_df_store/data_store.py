# data_store.py
"""进程内会话数据仓库（按登录 user_id 分桶）。

常用 key（手动分析 Tab）
-----------------------
- 原始报表：``budget`` / ``placement`` / ``keyword`` / ``search`` / ``search_share`` /
  ``product_sponsored`` / ``inventory`` / ``business``
- 分析结果：``*_analysis_result``（如 ``budget_analysis_result``）
- 诊断结果：``*_diagnosis_result``
- linkage：``campaign_asin_map``、``inventory_by_asin`` 等（见 diagnosis.linkage）

注意：刷新页面或换用户会清空；历史库数据在 SQLite/Turso，不在 store 里。
"""
import streamlit as st


class DataStore:
    """按 user_id 分桶的进程内数据存储（同一服务器多运营互不干扰）。"""

    def __init__(self):
        self._data: dict[str, dict] = {}

    def _bucket_key(self) -> str:
        from auth.user_context import get_current_user_id

        return get_current_user_id()

    def _bucket(self) -> dict:
        key = self._bucket_key()
        if key not in self._data:
            self._data[key] = {}
        return self._data[key]

    def set(self, key: str, value):
        self._bucket()[key] = value

    def get(self, key: str):
        return self._bucket().get(key, None)

    def clear(self):
        self._data.pop(self._bucket_key(), None)

    def clear_all(self):
        """切换登录用户时清空所有运营分桶（进程内内存）。"""
        self._data.clear()


store = DataStore()
