"""LangGraph state machine for the JobPilot application loop."""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from agent.nodes.executor import ExecutionAgent
from agent.nodes.memory import MemoryAgent
from agent.nodes.observer import ObserverAgent
from agent.nodes.planner import PlannerAgent
from agent.nodes.recovery import RecoveryEngine
from agent.nodes.validator import ValidatorAgent
from agent.schemas import AgentState
from services.browser_controller import BrowserController


class JobPilotGraphState(TypedDict, total=False):
    """TypedDict contract for core graph state fields."""

    current_url: str
    page_state: object
    last_action: object
    audit_entries: list[str]
    recovery_attempts: int


def build_graph(browser: BrowserController):
    """Build and compile the multi-agent application graph."""

    observer = ObserverAgent(browser)
    planner = PlannerAgent()
    executor = ExecutionAgent(browser)
    validator = ValidatorAgent()
    recovery = RecoveryEngine()
    memory = MemoryAgent()

    graph = StateGraph(AgentState)
    graph.add_node("observe", observer)
    graph.add_node("plan", planner)
    graph.add_node("execute", executor)
    graph.add_node("validate", validator)
    graph.add_node("recover", recovery)
    graph.add_node("remember", memory)

    graph.set_entry_point("observe")
    graph.add_edge("observe", "plan")
    graph.add_edge("plan", "execute")
    graph.add_conditional_edges(
        "execute",
        _route_after_execute,
        {"validate": "validate", "recover": "recover"},
    )
    graph.add_conditional_edges(
        "recover",
        _route_after_recovery,
        {"execute": "execute", "end": END},
    )
    graph.add_edge("validate", "remember")
    graph.add_conditional_edges(
        "remember",
        _route_after_memory,
        {"observe": "observe", "end": END},
    )
    return graph.compile()


def _route_after_execute(state: AgentState) -> str:
    if state.execution and state.execution.success:
        return "validate"
    if state.recovery_attempts < 2:
        return "recover"
    return "validate"


def _route_after_recovery(state: AgentState) -> str:
    if state.done or state.recovery_attempts >= 2:
        return "end"
    return "execute"


def _route_after_memory(state: AgentState) -> str:
    if state.done or state.iterations >= 25:
        return "end"
    if state.recovery_attempts >= 2:
        return "end"
    if state.validation and state.validation.status in {"blocked", "error", "ready"}:
        return "end"
    return "observe"
