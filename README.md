# 亚马逊广告诊断助手

面向 Amazon PPC 运营的 **Streamlit 诊断工作台**：上传广告后台 **每日明细** 报表，按固定顺序做规则化分析，并支持 AI 助手问答与综合诊断报告。

**在线体验：** https://amazon-ad-assistant-2.streamlit.app

**运营使用说明：** [docs/USAGE.md](docs/USAGE.md)

---

## 功能概览

| 模块 | 说明 |
|------|------|
| 手动分析 | 预算 → 广告位 → 投放词 → 搜索词 → 份额趋势；含规则诊断面板 |
| 历史查询 | Turso 云端 SQLite 持久化；按日期范围查询、双段对比 |
| 运营日志 | 记录调价、Listing、市场备注，供复盘联动 |
| AI 助手 | ReAct Agent + 工具调用 + RAG 知识库 |

---

## ⚠️ 报表要求（必读）

请从广告后台导出 **每日（Daily）明细报表**，**不要**使用「摘要 / Summary / 时间段合计」类报告。

工具依赖 **日期列** 及 **按天多行数据**（如连续 N 天预算超标、每日搜索词份额等）。摘要报表会导致分析错误或诊断「数据不足」。

详见 [使用说明书 · 第 3 节](docs/USAGE.md#3-️-最重要报表必须是每日明细不是摘要)。

---

## 本地运行

### 环境

- Python 3.11（见 `runtime.txt`）
- 依赖见 `requirements.txt`

### 步骤

```bash
git clone https://github.com/John-Z-jt/amazon-ad-assistant-2.git
cd amazon-ad-assistant-2
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

1. 复制 `config/credentials.yaml.example` → `config/credentials.yaml`，填写登录用户
2. （可选）复制 `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml`，配置 `DASHSCOPE_API_KEY`、Turso 等
3. 启动：

```bash
streamlit run Agent/app.py
```

本地未配置 Turso 时，历史库使用 `user_dict/` 下 SQLite 文件。

---

## 部署到 Streamlit Cloud

1. Fork 本仓库，在 [Streamlit Cloud](https://share.streamlit.io) 新建 App
2. **Main file path：** `Agent/app.py`
3. 在 **Secrets** 中配置（结构见 `.streamlit/secrets.toml.example`）：
   - `DASHSCOPE_API_KEY`
   - `[credentials.usernames.xxx]` 登录账号
   - `[turso.databases]` / `[turso.tokens]` 每用户独立库（可选，不配则本地 SQLite 逻辑）

---

## 项目结构（简要）

```
Agent/app.py          # Streamlit 主入口
ad_analyzers/         # 各报表清洗与分析
diagnosis/            # 预算/广告位/词/搜索词诊断规则
history/              # 历史入库、Turso、运营日志
Prompts/ + data/      # Agent 提示词与 RAG 知识库
```

更多架构说明见 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)。

---

## 许可证与说明

内部 / 培训用途工具。使用云端服务时请自行保管 API Key 与数据库 Token，勿提交到公开仓库。

**在线地址：** https://amazon-ad-assistant-2.streamlit.app
