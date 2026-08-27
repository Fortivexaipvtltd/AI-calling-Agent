from __future__ import annotations

from app.agent_runtime.state_machine import StateMachine
from app.simulator.prospects import PROSPECTS
from app.simulator.run_sim import run


def test_state_machine_linear():
    sm = StateMachine()
    assert sm.state == "GREETING"
    sm.advance()
    assert sm.state == "IDENTITY_CHECK"
    sm.goto("CLOSE")
    assert sm.is_terminal()


def test_all_prospects_run_clean():
    from app.agent_runtime.state_machine import STATES
    for name in PROSPECTS:
        result = run(name)
        assert result["final_state"] in STATES, name
        assert 0 <= result["score"] <= 100


def test_disengagement_paths_close():
    for name in ("not_interested", "opt_out", "needs_decision_maker"):
        assert run(name)["final_state"] == "CLOSE", name


def test_opt_out_suppresses():
    result = run("opt_out")
    transcript = result["transcript"]
    assert any("removed you" in m["text"].lower() for m in transcript if m["role"] == "agent")


def test_hot_lead_handoff():
    result = run("hot_ready_to_buy")
    assert result["score"] >= 60


def test_one_question_per_turn():
    result = run("interested_price_objection")
    for m in result["transcript"]:
        if m["role"] == "agent":
            assert m["text"].count("?") <= 1


if __name__ == "__main__":
    test_state_machine_linear()
    test_all_prospects_run_clean()
    test_disengagement_paths_close()
    test_opt_out_suppresses()
    test_hot_lead_handoff()
    test_one_question_per_turn()
    print("all tests passed")
