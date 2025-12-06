from typing import Annotated, Literal
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage

from tools import tools, tools_by_name

load_dotenv()


class State(TypedDict):
    """State schema for the chatbot graph."""
    messages: Annotated[list, add_messages]


# Initialize the LLM with tools bound
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)
llm_with_tools = llm.bind_tools(tools)


def chatbot(state: State):
    """LLM decides whether to call a tool or respond directly."""
    writer = get_stream_writer()
    writer({"type": "node_start", "node": "chatbot"})
    return {"messages": [llm_with_tools.invoke(state["messages"])]}


def tool_node(state: State):
    """Execute the tool calls made by the LLM."""
    writer = get_stream_writer()
    results = []
    
    for tool_call in state["messages"][-1].tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        writer({
            "type": "tool_call",
            "tool": tool_name,
            "args": tool_args,
        })
        
        tool_fn = tools_by_name[tool_name]
        result = tool_fn.invoke(tool_args)
        
        writer({
            "type": "tool_result",
            "tool": tool_name,
            "result": str(result),
        })
        
        results.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )
    
    return {"messages": results}


def should_continue(state: State) -> Literal["tool_node", "__end__"]:
    """Route to tool_node if LLM made tool calls, otherwise end."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return "__end__"


# Build the graph
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tool_node", tool_node)

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", should_continue, ["tool_node", "__end__"])
graph_builder.add_edge("tool_node", "chatbot")

graph = graph_builder.compile()

