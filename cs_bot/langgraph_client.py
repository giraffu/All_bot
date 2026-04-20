import os
import logging
from typing import Annotated, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv
from skill_manager import SkillManager

load_dotenv()

# 初始化技能管理器并加载 skills 目录下的 prompt 和 tools
skill_manager = SkillManager(skills_dir=os.path.join(os.path.dirname(__file__), "skills"))
skill_manager.load_skills()

# ==========================================
# 1. 定义状态 (State)
# ==========================================
# AgentState 继承自 TypedDict，这里定义了在图中流转的数据结构。
# `add_messages` reducer 会自动将新消息追加到现有消息列表中，而不是覆盖。
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# ==========================================
# 2. 初始化 LLM 模型
# ==========================================
# 指向本地的 LM Studio 实例
llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "gpt-oss-uncensored"),
    base_url=os.getenv("LLM_API_BASE", "http://localhost:1234/v1"),
    api_key="lm-studio", # 本地随便填
    temperature=0.7,
    max_tokens=800
)

# 获取并绑定 tools
tools = skill_manager.get_all_tools()
if tools:
    llm_with_tools = llm.bind_tools(tools)
else:
    llm_with_tools = llm

# ==========================================
# 3. 定义图的节点 (Nodes)
# ==========================================
def chatbot_node(state: AgentState):
    """
    核心思考节点：接收当前状态（包含历史消息），调用大模型，返回新的状态更新。
    """
    base_prompt = os.getenv("SYSTEM_PROMPT", "你是一个修仙世界合欢宗的热心大师姐。")
    # 合并 base_prompt 与所有 skill prompt
    combined_prompt = f"{base_prompt}\n\n{skill_manager.get_combined_prompt()}"
    system_prompt = SystemMessage(content=combined_prompt)
    
    # 截断历史记忆：保留最近的 5 条消息（避免视觉大模型被历史图片一直困住）
    recent_messages = state["messages"][-5:]
    
    # 组装完整的对话上下文：系统提示词 + 截断后的历史消息
    messages = [system_prompt] + recent_messages
    
    logging.info(f"LangGraph 思考中... 当前记忆长度: {len(state['messages'])}")
    
    # 调用大模型 (绑定了工具)
    response = llm_with_tools.invoke(messages)
    
    # 返回的字典会被 add_messages reducer 自动追加到 state["messages"] 中
    return {"messages": [response]}

# ==========================================
# 4. 编排图的边 (Edges) 与编译
# ==========================================
workflow = StateGraph(AgentState)

# 添加核心思考节点
workflow.add_node("chatbot", chatbot_node)

if tools:
    # 如果有工具，添加工具执行节点
    tool_node = ToolNode(tools)
    workflow.add_node("tools", tool_node)
    
    # 从 chatbot 出来的流转逻辑：根据是否有工具调用请求，决定去 tools 还是结束
    workflow.add_conditional_edges("chatbot", tools_condition)
    # 工具执行完毕后，回到 chatbot 继续思考
    workflow.add_edge("tools", "chatbot")
else:
    # 如果没有工具，直接结束
    workflow.add_edge("chatbot", END)

# 定义起点
workflow.add_edge(START, "chatbot")

# 添加记忆持久化组件 (Checkpointer)
# MemorySaver 是基于内存的。如果需要持久化到数据库，未来可替换为 PostgresSaver
memory = MemorySaver()

# 编译图为可执行应用
app = workflow.compile(checkpointer=memory)

# ==========================================
# 5. 对外暴露的异步接口
# ==========================================

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
        response = await llm.ainvoke(intent_prompt)
        content = response.content.strip()
        # 只要模型输出 1，就代表需要回复
        return "1" in content
    except Exception as e:
        logging.error(f"意图识别失败: {e}")
        # 如果意图识别失败，默认保守策略：不主动打扰
        return False

async def get_langgraph_reply(chat_id: int, username: str, user_text: str, base64_image: str = None) -> str:
    """
    通过 LangGraph 获取大模型的回复，自动管理上下文记忆。
    """
    # thread_id 是 LangGraph 区分不同会话（记忆）的关键 Key。
    # 这里我们用 Telegram 的群组 chat_id 作为 thread_id。
    # 如果用户发了图片，我们给他开一个独立的临时 thread，避免图片污染全局记忆
    thread_id = f"{chat_id}_vision" if base64_image else str(chat_id)
    config = {"configurable": {"thread_id": thread_id}}
    
    # 构造用户输入
    if base64_image:
        input_message = HumanMessage(
            content=[
                {"type": "text", "text": f"【弟子 {username} 问】：{user_text}"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        )
    else:
        input_message = HumanMessage(content=f"【弟子 {username} 问】：{user_text}")
    
    try:
        # ainvoke 是异步调用。如果有工具调用，图会在内部循环，直到得出最终结果。
        output_state = await app.ainvoke({"messages": [input_message]}, config=config)
        
        # 提取最后一条消息（即大模型的回复）
        final_reply = output_state["messages"][-1].content
        return final_reply
        
    except Exception as e:
        logging.error(f"LangGraph 执行失败: {e}")
        return "（大师姐正在给宗主捶腿呢，现在有点忙不过来，晚点再理你哦~）"
