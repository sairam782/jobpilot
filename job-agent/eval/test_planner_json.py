import json

from agent.schemas import PlannerAction


def test_planner_json_matches_action_schema() -> None:
    raw = '{"action":"type","selector":"input[name=\\"email\\"]","value":"a@example.com","reason":"Fill required email."}'

    action = PlannerAction.model_validate(json.loads(raw))

    assert action.action == "type"
    assert action.selector == 'input[name="email"]'
    assert action.value == "a@example.com"
