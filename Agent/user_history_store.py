"""AI 助手对话持久化：按用户写入 user_dict/{user_id}/chat.json。"""
import json
import os

from auth.user_context import get_current_user_id, get_user_data_dir


class FileHistoryStore:
    """基于本地 JSON 文件的对话历史存储。"""

    def __init__(self, user_id: str | None = None):
        """绑定 user_id 并确定 chat.json 路径。"""
        if user_id is None:
            user_id = get_current_user_id()
        self.user_id = user_id
        self.chat_path = get_user_data_dir(user_id) / "chat.json"

    def get_history(self) -> list:
        """读取对话列表，每项为 {"role": "user"|"assistant", "content": str}。"""
        if not os.path.exists(self.chat_path):
            return []
        with open(self.chat_path, "r", encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def add_message(self, role: str, content: str) -> None:
        """追加一条消息并写回 chat.json。"""
        history = self.get_history()
        history.append({"role": role, "content": content})
        with open(self.chat_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)
