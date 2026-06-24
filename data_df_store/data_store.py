# data_store.py
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
