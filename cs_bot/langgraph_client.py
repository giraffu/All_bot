import logging
import os
from dataclasses import dataclass
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from skill_manager import SkillManager

load_dotenv()


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


@dataclass(frozen=True)
class LangGraphRuntime:
    skill_manager: SkillManager
    llm: ChatOpenAI
    app: object


_runtime: LangGraphRuntime | None = None


def build_langgraph_app() -> LangGraphRuntime:
    skill_manager = SkillManager(
        skills_dir=os.path.join(os.path.dirname(__file__), "skills")
    )
    skill_manager.load_skills()

    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL", "gpt-oss-uncensored"),
        base_url=os.getenv("LLM_API_BASE", "http://localhost:1234/v1"),
        api_key="lm-studio",
        temperature=0.7,
        max_tokens=800,
    )
    tools = skill_manager.get_all_tools()
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    def chatbot_node(state: AgentState):
        base_prompt = os.getenv(
            "SYSTEM_PROMPT",
            "你是一个修仙世界合欢宗的热心大师姐。",
        )
        combined_prompt = f"{base_prompt}\n\n{skill_manager.get_combined_prompt()}"
        system_prompt = SystemMessage(content=combined_prompt)
        recent_messages = state["messages"][-5:]
        messages = [system_prompt] + recent_messages
        logging.info("LangGraph 思考中... 当前记忆长度: %s", len(state["messages"]))
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    workflow = StateGraph(AgentState)
    workflow.add_node("chatbot", chatbot_node)
    if tools:
        workflow.add_node("tools", ToolNode(tools))
        workflow.add_conditional_edges("chatbot", tools_condition)
        workflow.add_edge("tools", "chatbot")
    else:
        workflow.add_edge("chatbot", END)
    workflow.add_edge(START, "chatbot")

    # MemorySaver is process-local memory, not Redis or database persistence.
    app = workflow.compile(checkpointer=MemorySaver())
    return LangGraphRuntime(skill_manager=skill_manager, llm=llm, app=app)


def get_langgraph_runtime() -> LangGraphRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_langgraph_app()
    return _runtime


async def check_intent(user_text: str) -> bool:
    """
    使用轻量级的大模型调用进行意图识别，判断是否需要客服大师姐介入。
    返回 True 表示需要回复，False 表示不需要（用户只是闲聊）。
    """
    intent_prompt = f"""你是一个群聊意图分析器。判断以下用户的发言是否属于"求助"、"疑问"、"咨询客服"或"需要管理员介入"的范畴。
如果用户只是普通的闲聊、打招呼、吐槽、或者与其他群友的交流，请返回 0。
如果用户明确遇到了使用问题（如：充值、报错、不知道怎么用、排队等），或者直接向官方/客服提问，请返回 1。

用户发言：{user_text}

请只输出数字 0 或 1，不要输出任何其他内容。"""

    try:
        response = await get_langgraph_runtime().llm.ainvoke(intent_prompt)
        content = response.content.strip()
        return "1" in content
    except Exception as e:
        logging.error("意图识别失败: %s", e)
        return False


async def get_langgraph_reply(
    chat_id: int, username: str, user_text: str, base64_image: str = None
) -> str:
    """
    通过 LangGraph 获取大模型的回复，自动管理上下文记忆。
    """
    thread_id = f"{chat_id}_vision" if base64_image else str(chat_id)
    config = {"configurable": {"thread_id": thread_id}}

    if base64_image:
        input_message = HumanMessage(
            content=[
                {"type": "text", "text": f"【弟子 {username} 问】：{user_text}"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                },
            ]
        )
    else:
        input_message = HumanMessage(content=f"【弟子 {username} 问】：{user_text}")

    try:
        output_state = await get_langgraph_runtime().app.ainvoke(
            {"messages": [input_message]},
            config=config,
        )
        return output_state["messages"][-1].content
    except Exception as e:
        logging.error("LangGraph 执行失败: %s", e)
        return "（大师姐正在给宗主捶腿呢，现在有点忙不过来，晚点再理你哦~）"
