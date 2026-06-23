*亚马逊广告诊断助手（amazon_ad_assistant）项目上下文文档*  
*基于全量代码阅读整理，非 README 摘要*  
*最后更新：2026-06-11*



## **1. 项目目标**

**亚马逊广告诊断助手**是一个面向 Amazon PPC 运营的 **Streamlit Web 应用**，核心目标为：

1. 导入亚马逊广告后台导出的多类 CSV 报表；
2. 按固定诊断顺序（预算 → 广告位 → 投放词 → 搜索词 → 搜索词份额）进行 **规则化数据分析**；
3. 在「手动分析」页以表格、筛选、明细形式展示结果；
4. 在「AI 助手」页通过 **ReAct Agent + 工具调用 + RAG 知识库**，支持自然语言问答与综合诊断报告生成。

项目定位：**报表驱动的广告诊断工作台 + LLM 编排层**，不是完整的广告管理系统或自动化投放平台。

## **2. 用户是谁**


| **用户类型**          | **说明**                           |
| ----------------- | -------------------------------- |
| **亚马逊运营 / 广告优化师** | 日常复盘预算、广告位、关键词、搜索词表现             |
| **团队内部使用者**       | 会话 ID 硬编码、本地 JSON 存历史，偏内部工具形态    |
| **具备广告分析基础的人**    | 需理解 ACOS、否定词、展示量份额等概念；UI 不面向完全新手 |


当前 **无登录、无多租户**，所有使用者共享同一进程内的内存数据。

  


## **3. 解决什么问题**

### **3.1 业务痛点**

- 亚马逊广告报表分散（预算、广告位、投放词、搜索词、份额），人工串联分析成本高；
- 诊断有固定方法论（先预算、再广告位…），Excel 手工执行易漏步骤、标准不统一；
- 运营需要同时获得 **数据结论** 与 **分析原理 / 优化策略**。

### **3.2 项目提供的价值**


| **能力**      | **说明**                                            |
| ----------- | ------------------------------------------------- |
| **统一上传入口**  | 侧边栏一次上传 5 类 CSV                                   |
| **标准化分析逻辑** | 各 `ad_analyzers/`* 实现固定规则（预算使用率 >90%、否定词候选、象限分类等） |
| **双模式使用**   | 手动：可视化表格 + 筛选 + 明细；AI：对话查询 + Markdown 诊断报告        |
| **知识增强**    | RAG 从 `data/*_module.txt` 检索模块原理，解释「为什么这样分析」      |


## **4. 当前技术架构**

┌─────────────────────────────────────────────────────────────┐

│                    Streamlit UI (Agent/[app.py](http://app.py))               │

│  侧边栏 CSV 上传 │ Tab1 手动分析 │ Tab2 AI 助手 Chat        │

└────────────┬───────────────────────────────┬────────────────┘

             │                               │

             ▼                               ▼

┌────────────────────────┐    ┌──────────────────────────────┐

│  ad_analyzers/*        │    │  ReactAgent (react_[agent.py](http://agent.py)) │

│  clean_* + get_*       │    │  LangChain create_agent      │

│  analyze_* (UI)        │    │  + LangGraph middleware      │

└────────────┬───────────┘    └──────────┬───────────────────┘

             │                           │

             ▼                           ▼

┌────────────────────────┐    ┌──────────────────────────────┐

│  DataStore 单例        │◄───│  agent_[tool.py](http://tool.py) (7 tools)     │

│  (data_df_store/)      │    │  读取 store 中 DF + 预计算结果 │

└────────────────────────┘    └──────────┬───────────────────┘

                                         │

                    ┌────────────────────┼────────────────────┐

                    ▼                    ▼                    ▼

           ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐

           │ RagSummarize │   │ ChatTongyi   │   │ FileHistoryStore│

           │ Service      │   │ (DashScope)  │   │ (user_dict/*.json)│

           └──────┬───────┘   └──────────────┘   └─────────────────┘

                  │

                  ▼

           ┌──────────────┐

           │ FAISS 向量库  │  ← 配置名 chroma.yml，实际用 FAISS

           │ + DashScope   │

           │   Embedding   │

           └──────────────┘

### **4.1 技术栈**


| **层级**    | **技术**                                         |
| --------- | ---------------------------------------------- |
| UI        | Streamlit                                      |
| 数据处理      | pandas, numpy                                  |
| Agent     | LangChain `create_agent`, LangGraph middleware |
| LLM       | 阿里 DashScope `ChatTongyi`（`deepseek-v4-flash`） |
| Embedding | DashScope `text-embedding-v4`                  |
| 向量检索      | FAISS（`faiss-cpu`），非 ChromaDB                  |
| 配置        | YAML（`config/*.yml`）                           |
| 日志        | `logs/agent_YYYYMMDD.log`                      |
| 会话持久化     | JSON 文件（`user_dict/`）                          |


### **4.2 外部依赖**

- 需配置 DashScope API Key（`.env`，被 `.gitignore` 忽略）；
- 向量索引默认持久化到 `D:/faiss_index.bin` 和 `D:/doc_store.pkl`（硬编码绝对路径）。

## **5. 项目目录结构**

## **amazon_ad_assistant/**

**├── Agent/                      # 应用入口与 Agent 层**

**│   ├── [app.py](http://app.py)                  # Streamlit 主程序**

**│   ├── react_[agent.py](http://agent.py)          # ReAct Agent 封装**

**│   ├── agent_[tool.py](http://tool.py)           # LangChain Tools（7 个）**

**│   ├── [middleware.py](http://middleware.py)           # 工具监控、日志、动态 Prompt 切换**

**│   └── user_history_[store.py](http://store.py)   # 对话历史 JSON 持久化**

**├── ad_analyzers/               # 广告分析核心（清洗 + 计算 + UI）**

**│   ├── budget_[analyzer.py](http://analyzer.py)**

**│   ├── placement_[analyzer.py](http://analyzer.py)**

**│   ├── keyword_[analyzer.py](http://analyzer.py)**

**│   ├── search_[analyzer.py](http://analyzer.py)**

**│   └── search_term_[trend.py](http://trend.py)**

**├── data_df_store/**

**│   └── data_[store.py](http://store.py)           # 全局单例内存存储**

**├── Rag/**

**│   ├── Vector_[store.py](http://store.py)         # FAISS 向量库构建与检索**

**│   └── rag_[service.py](http://service.py)          # RAG 总结链**

**├── model/**

**│   └── [factory.py](http://factory.py)              # Chat / Embedding 模型工厂**

**├── utils/                      # 配置、路径、日志、文件加载**

**│   ├── config_[handler.py](http://handler.py)**

**│   ├── path_[tool.py](http://tool.py)**

**│   ├── prompt_[loader.py](http://loader.py)**

**│   ├── file_[handler.py](http://handler.py)**

**│   └── logger_[handler.py](http://handler.py)**

**├── config/                     # agent / rag / chroma / prompts 配置**

**├── Prompts/                    # Agent 系统提示词、报告提示词、RAG 提示词**

**├── data/                       # RAG 知识库原文（5 个模块 txt）**

**├── user_dict/                  # 用户会话历史 JSON**

**├── logs/                       # 运行日志**

**├── requirements.txt**

**└── .cursor/mcp.json            # Cursor MCP 配置（与主业务无关）**

**入口说明**：无 README；启动方式为从项目根目录运行 `streamlit run Agent/app.py`（需处理 `sys.path`）。

## **6. 数据流**

### **6.1 报表上传与预处理**

用户上传 CSV (sidebar)

    │

    ▼

load_csv() ── 尝试 gbk / utf-8 / gb2312 / gb18030 编码

    │

    ├── budget ──► store.set("budget", df)

    │              store.set("budget_analysis_result", get_budget_analysis(df))

    │

    ├── placement ──► clean_placement_data() ──► store + get_placement_analysis()

    │

    ├── keyword ──► clean_keyword_report() ──► store + get_keyword_analysis()

    │

    ├── search ──► clean_search_report() ──► store + get_search_analysis()

    │

    └── search_share ──► clean_search_share_report() ──► store + get_search_term_trend()

同时写入 st.session_state.df_* 供手动分析 Tab 使用

**特点**：

- 数据仅存 **进程内存**（`DataStore` 单例 + `session_state`）；
- **刷新页面需重新上传**（UI 已提示）；
- 上传时 **预计算分析结果**，Agent 工具读预计算结果，避免重复全量计算。

### **6.2 手动分析 Tab 数据流**

session_state.df_* 存在

    │

    ▼

analyze_*() UI 函数

    │

    ▼

优先读 store.get("*_analysis_result")

    │

    ▼

Streamlit 组件：multiselect / tabs / expander / dataframe / download_button

### **6.3 AI 助手 Tab 数据流**

用户输入 prompt

    │

    ▼

FileHistoryStore.get_history(session_id) + 新消息

    │

    ▼

ReactAgent.execute_stream()

    │

    ▼

create_agent + middleware:

  - log_before_model: 打日志

  - monitor_tool: 记录工具调用；fill_context_for_report 时设 [context.report](http://context.report)=True

  - report_prompt_switch: 动态切换 main_prompt / report_prompt

    │

    ▼

工具调用 (agent_[tool.py](http://tool.py)) ──► 读 store ──► 返回格式化文本

    │

    ▼

LLM 流式输出 ──► 写入 user_dict/{session_id}.json

### **6.4 RAG 数据流**

### **rag_summarize(query)**

    **│**

    **▼**

**VectorStoreService.get_retriever()(query)  ── FAISS 相似度检索 top-k**

    **│**

    **▼**

**拼接 context + PromptTemplate(rag_summarize.txt)**

    **│**

    **▼**

**ChatTongyi ──► 总结回答**

知识来源：`data/budget_module.txt` 等 5 个模块文档。若 `D:/faiss_index.bin` 已存在则直接加载；否则需运行 `Vector_store.load_documents()` 构建索引。

## **7. 核心模块说明**

### **7.1** `Agent/app.py` **— 应用入口**

- Streamlit 页面布局、5 个 CSV 上传器、双 Tab；
- 上传触发清洗 + 预计算 + 双写 `store` / `session_state`；
- AI Tab：`session_id = "user023"` 硬编码，聊天流式渲染。

### **7.2** `ad_analyzers/`* **— 分析引擎**


| **模块**               | **输入报表** | **核心逻辑**                | **输出结构**                                            |
| -------------------- | -------- | ----------------------- | --------------------------------------------------- |
| `budget_analyzer`    | 预算 CSV   | 使用率 = 花费/预算，>90% 为异常    | `problem_activities`, `summary`, `daily_details`    |
| `placement_analyzer` | 广告活动_广告位 | 按活动+放置聚合 ACOS，找最佳/最差广告位 | `summary`, `top/worst_by_activity`, `daily_details` |
| `keyword_analyzer`   | 投放词      | 按活动/组/关键词聚合；跨活动对比       | `summary`, `daily_details`                          |
| `search_analyzer`    | 搜索词      | 否定词候选（零订单+高点击花费）；高潜力拓词  | `summary`, `daily_details` + 双 Tab UI               |
| `search_term_trend`  | 搜索词份额    | 每日排名/份额/ACOS；四象限分类      | `search_terms`, `data[term].trend/attribution`      |


**设计模式**：`get_*_analysis()` 纯计算 + `analyze_*()` Streamlit UI，供手动页与 Agent 工具共用。

### **7.3** `Agent/agent_tool.py` **— Agent 工具层**


| **工具**                     | **功能**                     |
| -------------------------- | -------------------------- |
| `rag_summarize`            | RAG 知识问答                   |
| `analyze_budget_tool`      | 预算异常摘要 / 单活动详情             |
| `analyze_placement_tool`   | 最差广告位摘要 / 单活动详情            |
| `analyze_keyword_tool`     | 投放词筛选 / 高花费零订单             |
| `analyze_search_tool`      | 搜索词摘要 / 否定词 & 拓词计数         |
| `analyze_search_term_tool` | 搜索词份额趋势（需指定 `search_term`） |
| `fill_context_for_report`  | 触发报告 Prompt 切换             |


工具返回 **文本摘要**，详细表格引导用户前往「手动分析」Tab。

### **7.4** `Agent/middleware.py` **— Agent 中间件**

- `monitor_tool`：工具调用日志 + 报告模式标记；
- `log_before_model`：模型调用前日志；
- `report_prompt_switch`：`@dynamic_prompt`，根据 `context.report` 切换 `main_prompt.txt` / `report_prompt.txt`。

### **7.5** `Rag/Vector_store.py` **— 向量库**

- 读取 `data/` 下 txt/pdf；
- MD5 去重（`md5.text`）；
- `RecursiveCharacterTextSplitter` 分块；
- FAISS `IndexFlatL2` + `IndexIDMap` 持久化；
- **配置文件名** `chroma.yml` **具有误导性**，实际未使用 ChromaDB。

### **7.6** `data_df_store/data_store.py` **— 内存数据中心**

- 单例字典存储 DataFrame 与预计算 dict；
- Agent 工具与 UI 共享同一实例；
- 类型注解写 `pd.DataFrame`，实际也存 dict（类型不一致）。

### **7.7** `Prompts/` **— 提示词体系**


| **文件**              | **用途**                   |
| ------------------- | ------------------------ |
| `main_prompt.txt`   | ReAct 规则、工具调用格式、报告生成强制流程 |
| `report_prompt.txt` | 分步骤综合报告模板（RAG 原理 + 数据工具） |
| `rag_summarize.txt` | RAG 回答约束（仅基于参考资料）        |


---

## **8. 已实现功能**

### **8.1 数据导入**

- 5 类 CSV 上传（预算、广告位、投放词、搜索词、搜索词份额）
- 多编码自动识别（GBK / UTF-8 等）
- 上传时自动清洗与预计算

### **8.2 手动分析（Tab1）**

- 预算分析：异常活动汇总、活动筛选、每日明细高亮、CSV 导出
- 广告位分析：活动/广告位双筛选、最佳/最差广告位、每日明细
- 投放词分析：三级联动筛选、每日明细、跨活动关键词对比
- 搜索词分析：否定词候选 / 高潜力拓词双 Tab、两种分析模式、分页、每日明细
- 搜索词趋势：排名/份额/ACOS 趋势、四象限分类、归因明细

### **8.3 AI 助手（Tab2）**

- 流式对话 UI
- ReAct Agent + 7 工具
- 对话历史 JSON 持久化（按 session_id）
- 综合诊断报告生成（动态 Prompt 切换）
- RAG 模块原理问答
- 工具调用监控与日志

### **8.4 基础设施**

- YAML 配置管理
- 统一路径工具 `path_tool.py`
- 按日滚动日志
- FAISS 向量索引持久化与 MD5 去重

---

## **9. 未实现功能**


| **功能**             | **说明**                                                   |
| ------------------ | -------------------------------------------------------- |
| 推广的商品报告            | `app.py` 中 file_uploader 已注释                             |
| Excel 直接上传         | 仅支持 CSV                                                  |
| 用户登录 / 多用户隔离       | session_id 硬编码，内存数据全局共享                                  |
| 报表持久化存储            | 刷新丢失；无数据库                                                |
| 除预算外其他模块 CSV 导出    | 仅 `budget_analyzer` 有 download_button                    |
| REST API / 批处理 CLI | 仅 Streamlit 入口                                           |
| 自动化测试              | 无 tests 目录                                               |
| 向量库自动初始化           | `load_documents()` 仅在 `Vector_store.py` 的 `__main_`_ 中调用 |
| 报告 PDF/Word 导出     | 仅 Markdown 文本输出                                          |
| 阈值/规则可配置化          | 90%、0.4、象限阈值等写死在代码                                       |
| 多语言 / 多站点报表适配      | 列名强依赖中文亚马逊报表格式                                           |
| 项目文档               | 无 README、无部署说明                                           |


---

## **10. 当前存在的问题**

### **10.1 功能 / 体验**

1. **手动分析默认不显示数据**：预算/广告位/关键词等多处 `multiselect(default=[])`，用户需先选筛选条件才看到表格。
2. **刷新丢数据**：上传报表仅存内存，与 UI 提示一致但限制日常使用。
3. **session_id 硬编码**（`user023`）：无法区分真实用户，历史文件会混用。
4. **报告模式 context 不重置**：`fill_context_for_report` 将 `context.report=True` 后未见重置逻辑，后续对话可能一直用报告 Prompt。
5. **Agent 流式输出可能重复**：`execute_stream` 对 `stream_mode="values"` 每条消息的 content 都 yield，可能输出中间步骤文本。

### **10.2 稳定性**

1. **工具调用参数不一致**：日志显示 `analyze_budget_tool` 在参数 `{}` 时失败，空字符串 `''` 时成功。
2. **RAG 依赖外部索引**：若 `D:/faiss_index.bin` 不存在且未手动 build，首次 `rag_summarize` 抛「向量库为空」。
3. **import 路径脆弱**：`Agent/` 与项目根目录混用 `sys.path.insert`；`react_agent.py` 用 `from agent_tool import` 而非包路径。

### **10.3 数据正确性**

1. **预算「总预算」语义**：`groupby` 对预算求和，跨日重复活动可能语义不清。
2. `@st.cache_data` **缓存 DataFrame 参数**：hash 行为可能不符合预期。
3. `DataStore` **类型注解不准确**：实际存储 dict 与 DataFrame 混合。

### **10.4 配置 / 部署**

1. `requirements.txt` **不完整**：缺少 `pyyaml`（代码使用）、可能缺少 `langgraph` 等 Agent 依赖。
2. **FAISS 路径写死** `D:/`：换机器/用户无法直接运行。
3. **无** `.env` **示例**：新开发者不知需哪些环境变量。

---

## **11. 技术债**


| **类别**        | **具体项**                                              |
| ------------- | ---------------------------------------------------- |
| **代码重复**      | `to_float` / `to_percent_float` 在 4 个 analyzer 中重复实现 |
| **命名误导**      | `chroma.yml` 实际配置 FAISS；`chroma_db` 配置项未使用           |
| **分层不清**      | `agent_tool.py` 导入未使用的 `streamlit`；分析 UI 与计算同文件      |
| **硬编码**       | session_id、阈值、象限阈值(30%/排名3)、FAISS 绝对路径               |
| **Prompt 维护** | 超长 txt 提示词，与工具签名耦合，易 drift                           |
| **无测试**       | 分析规则、工具输出格式均无自动化保障                                   |
| **Git 忽略策略**  | `user_dict/*.json` 被 ignore，但仓库中仍有多份样例文件             |
| **日志无轮转策略**   | 仅按日文件名，无 size/retention 管理                           |


---

## **12. 后续可优化方向**

### **12.1 短期（体验与稳定性）**

1. 修复手动分析默认 UX：multiselect 默认选中全部或展示未筛选汇总表；
2. session_id 可配置：URL 参数 / 侧边栏输入 / 登录后绑定；
3. 报告模式 reset：对话轮次结束或新用户消息时重置 `context.report`；
4. 补全 `requirements.txt` 并添加 `.env.example`；
5. 向量库路径改为项目相对路径；应用启动时自动检测并 build 索引；
6. 统一 import 路径：将 `Agent` 改为正规 Python 包或使用 `python -m` 启动。

### **12.2 中期（功能完善）**

1. 报表持久化：上传 CSV 缓存到本地/session，刷新可恢复；
2. 各模块 CSV/Excel 导出：与预算导出一致；
3. 支持 Excel 上传：运营常从后台直接导出 xlsx；
4. 阈值配置化：`config/analysis.yml` 统一管理 90%、0.4、象限阈值等；
5. 推广的商品报告模块补齐；
6. Agent 输出优化：仅 stream 最终 assistant 消息，隐藏 ReAct 中间步骤。

### **12.3 长期（架构演进）**

1. 分析引擎与 UI 分离：`core/` 纯函数 + `ui/` Streamlit，便于 CLI/API 复用；
2. 多用户与权限：对接公司内部账号；
3. 自动化测试：针对 `get_*_analysis` 用 fixture CSV 做快照测试；
4. 批处理/定时诊断：对接网络盘报表路径自动跑诊断；
5. 评估 Agent 质量：对报告生成做 golden test 或 LLM-as-judge；
6. 替换/抽象 LLM 提供商：factory 已具备雏形，可扩展 OpenAI 等。

---

## **附录 A：诊断方法论**

项目内置 **五步诊断顺序**，与代码模块一一对应：


| **顺序** | **模块** | **目的**               |
| ------ | ------ | -------------------- |
| 1      | 预算     | 确保预算充足，避免后续分析失真      |
| 2      | 广告位    | 判断 Listing 在不同位置的竞争力 |
| 3      | 投放词    | 识别浪费与内部竞争            |
| 4      | 搜索词    | 否定词 / 拓词候选           |
| 5      | 搜索词份额  | 市场竞争视角（IS/IR 趋势）     |


该顺序在 Prompt、RAG 知识库、UI Tab 顺序中保持一致，是项目的核心业务约束。

---

## **附录 B：关键配置一览**


| **文件**               | **关键项**                                                                         |
| -------------------- | ------------------------------------------------------------------------------- |
| `config/rag.yml`     | `chat_model_name: deepseek-v4-flash`, `embedding_model_name: text-embedding-v4` |
| `config/chroma.yml`  | `vector_path: D:/faiss_index.bin`, `data_path: data`, `k: 3`                    |
| `config/agent.yml`   | `session_id_dir_path: user_dict`                                                |
| `config/prompts.yml` | 三类 Prompt 文件路径                                                                  |


---

## **附录 C：启动方式（参考）**

*# 1. 安装依赖*

pip install -r requirements.txt

*# 2. 配置环境变量（DashScope API Key）*

*# 创建 .env 并设置 DASHSCOPE_API_KEY=...*

*# 3. 首次使用 RAG 需构建向量索引（若 D:/faiss_index.bin 不存在）*

python Rag/Vector_store.py

*# 4. 启动应用*

streamlit run Agent/app.py



