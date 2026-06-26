import json

import os



from auth.user_context import get_current_user_id, get_user_data_dir





class FileHistoryStore:

    """按 user_id 存储 Agent 对话：user_dict/{user_id}/chat.json"""



    def __init__(self, user_id: str | None = None):

        if user_id is None:

            user_id = get_current_user_id()

        self.user_id = user_id

        self.chat_path = get_user_data_dir(user_id) / "chat.json"



    def get_history(self) -> list:

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

        history = self.get_history()

        history.append({"role": role, "content": content})

        with open(self.chat_path, "w", encoding="utf-8") as f:

            json.dump(history, f, ensure_ascii=False)


