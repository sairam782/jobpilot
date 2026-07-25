from agent.schemas import ActionType, PlannerAction


def test_planner_action_accepts_done_string() -> None:
    action = PlannerAction(action="done", reason="ready")

    assert action.action == ActionType.DONE
    assert action.selector is None
    assert action.value is None
