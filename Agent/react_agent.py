from langchain.agents import create_agent
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent_tool import (
    rag_summarize,
    analyze_budget_tool,
    diagnose_budget_tool,
    analyze_placement_tool,
    diagnose_placement_tool,
    analyze_keyword_tool,
    diagnose_keyword_tool,
    analyze_product_sponsored_tool,
    analyze_search_tool,
    diagnose_search_tool,
    analyze_search_term_tool,
    fill_context_for_report,
)
from Agent.middleware import monitor_tool, log_before_model, report_prompt_switch



class ReactAgent:
    def __init__(self):
        """初始化 ReAct Agent，绑定模型、工具与中间件。

        Returns:
            None

        Raises:
            None
        """
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[
                rag_summarize,
                analyze_budget_tool,
                diagnose_budget_tool,
                analyze_placement_tool,
                diagnose_placement_tool,
                analyze_keyword_tool,
                diagnose_keyword_tool,
                analyze_product_sponsored_tool,
                analyze_search_tool,
                diagnose_search_tool,
                analyze_search_term_tool,
                fill_context_for_report,
            ],
            middleware=[monitor_tool, log_before_model, report_prompt_switch]
        )


    def execute_stream(self, message: list, *, user_id: str | None = None):
        """以流式方式执行 Agent 并逐块返回模型输出。

        Args:
            message: 对话消息列表。
            user_id: 当前登录用户，供工具线程内访问 store 分桶。
        """
        input_dict = {
            "messages": message
        }
        context: dict = {"report": False}
        if user_id:
            context["user_id"] = user_id
        for chunk in self.agent.stream(input_dict, stream_mode="values", context=context):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"
