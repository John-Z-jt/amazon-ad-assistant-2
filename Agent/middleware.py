from typing import Callable
from utils.prompt_loader import load_system_prompts, load_report_prompts
from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, before_model, dynamic_prompt, ModelRequest
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command
from auth.user_context import bind_user_id
from utils.logger_handler import logger

@wrap_tool_call
def monitor_tool(
        # # 请求的数据封装
        request: ToolCallRequest,
        # 执行的函数本身
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:             # 工具执行的监控
    """监控 Agent 工具调用并记录日志。

    Args:
        request (ToolCallRequest): 工具调用请求，含工具名与参数。
        handler (Callable): 实际执行工具的可调用对象。

    Returns:
        ToolMessage | Command: 工具执行结果。

    Raises:
        Exception: 工具执行失败时重新抛出原始异常。
    """
    logger.info(f"[tool monitor]执行工具：{request.tool_call['name']}")
    logger.info(f"[tool monitor]传入参数：{request.tool_call['args']}")

    user_id = request.runtime.context.get("user_id")
    if user_id:
        bind_user_id(str(user_id))

    try:
        result = handler(request)
        logger.info(f"[tool monitor]工具{request.tool_call['name']}调用成功")

        if request.tool_call['name'] == "fill_context_for_report":
            request.runtime.context["report"] = True

        return result
    except Exception as e:
        logger.error(f"工具{request.tool_call['name']}调用失败，原因：{str(e)}")
        raise e

@before_model
def log_before_model(
        state: AgentState,          # 整个Agent智能体中的状态记录
        runtime: Runtime,           # 记录了整个执行过程中的上下文信息
):         # 在模型执行前输出日志
    """在模型调用前记录当前 Agent 状态日志。

    Args:
        state (AgentState): Agent 当前状态，含消息列表。
        runtime (Runtime): 运行时上下文信息。

    Returns:
        None

    Raises:
        None
    """
    logger.info(f"[log_before_model]即将调用模型，带有{len(state['messages'])}条消息。")
    logger.debug(f"[log_before_model]{type(state['messages'][-1]).__name__} | {state['messages'][-1].content.strip()}")
    return None

@dynamic_prompt                 # 每一次在生成提示词之前，调用此函数
def report_prompt_switch(request: ModelRequest):     # 动态切换提示词
    """根据上下文动态切换系统提示词。

    Args:
        request (ModelRequest): 模型请求，含运行时上下文。

    Returns:
        str: 报告生成或默认系统提示词文本。

    Raises:
        KeyError: 配置中缺少提示词路径项。
        Exception: 提示词文件读取失败。
    """
    is_report = request.runtime.context.get("report", False)
    if is_report:               # 是报告生成场景，返回报告生成提示词内容
        return load_report_prompts()
    return load_system_prompts()

if __name__ == '__main__':
    print(load_report_prompts())

