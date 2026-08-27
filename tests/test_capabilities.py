from __future__ import annotations

from app.capabilities import audit
from app.tools.registry import ToolRegistry


def test_all_capabilities_present():
    a = audit()
    missing = [r["capability"] for r in a["items"] if not r["present"]]
    assert not missing, missing
    assert a["coverage"] == 1.0


def test_new_tools_registered():
    r = ToolRegistry()
    for t in ("message.send_whatsapp", "telephony.start_recording",
              "telephony.warm_transfer", "telephony.cold_transfer",
              "telephony.conference", "telephony.drop_voicemail",
              "telephony.detect_machine", "rag.search", "mcp.call"):
        assert t in r.names(), t


def test_number_pool_rotation():
    from app.telephony.numbers import NumberService
    svc = NumberService()
    pool = svc.create_pool("p", strategy="round_robin")
    a = svc.provision("+911111111111")
    b = svc.provision("+912222222222")
    svc.add_to_pool(pool.id, a.id)
    svc.add_to_pool(pool.id, b.id)
    picks = {pool.pick("+919").e164 for _ in range(4)}
    assert picks == {a.e164, b.e164}


def test_amd_detects_machine_and_human():
    from app.telephony.amd import AnsweringMachineDetector
    d = AnsweringMachineDetector()
    assert d.detect(opening_transcript="please leave a message after the beep").label == "machine"
    assert d.detect(opening_transcript="hello?").label == "human"


def test_retry_policy_backoff():
    from app.telephony.retry import RetryPolicy
    p = RetryPolicy(max_retries=3, backoff_minutes=10)
    assert p.should_retry("no_answer", 0) is True
    assert p.should_retry("completed", 0) is False
    assert p.should_retry("busy", 3) is False


def test_model_router_falls_back_to_local():
    from app.providers.router import ModelRouter
    plan = ModelRouter().plan()
    assert plan["llm"] and plan["stt"] and plan["tts"]


def test_rag_retrieval_ranks_relevant():
    from app.ai.rag import VectorStore
    s = VectorStore()
    s.add("The 180-day better offer guarantee is continued support, not a job guarantee.")
    s.add("Classes run in the evening for working professionals.")
    hits = s.search("is there a job guarantee")
    assert hits and "guarantee" in hits[0]["text"].lower()


def test_structured_output_parse_and_validate():
    from app.ai.structured import LEAD_INSIGHT_SCHEMA, parse
    out = parse('noise {"sentiment": "positive", "score": "72", '
                '"next_action": "book_meeting"} trailing', LEAD_INSIGHT_SCHEMA)
    assert out["score"] == 72 and out["sentiment"] == "positive"


def test_workflow_runs_to_completion():
    from app.ai.workflows import sample_qualify_and_book
    res = sample_qualify_and_book().run({"lead_id": "lead_x"})
    assert any(s.get("tool") == "calendar.book" for s in res["trace"])


def test_multi_agent_handoff_chain():
    from app.ai.multi_agent import default_squad
    res = default_squad().run(["I'm interested and have budget", "I want to enroll"])
    roles = [t["role"] for t in res["transcript"]]
    assert "closer" in roles


def test_conversation_intelligence_next_best_action():
    from app.advanced.conversation_intelligence import ConversationIntelligence
    ci = ConversationIntelligence()
    ci.observe("this sounds great, how do I enroll and pay?")
    assert ci.next_best_action()["action"] == "move_to_close"


def test_autonomous_executor_completes_goal():
    from app.advanced.autonomous_executor import AutonomousExecutor
    res = AutonomousExecutor().run("book_meeting", "lead_y")
    assert res["status"] == "completed"


def test_memory_graph_relational_query():
    from app.advanced.memory_graph import MemoryGraph
    g = MemoryGraph()
    g.ingest_lead_memory("lead_1", "Rahul", {"goal": "AI job"}, ["price"])
    g.ingest_lead_memory("lead_2", "Anita", {"goal": "AI job"}, [])
    assert set(g.leads_with("raised", "objection", "price")) == {"lead_1"}


def test_optimizer_learns_best_arm():
    from app.advanced.optimizer import Optimizer
    rec = Optimizer().simulate(trials=300)
    assert rec["llm"]["best"] in ("anthropic", "byo", "local")


def test_redteam_guardrails_hold():
    from app.advanced.evaluation import evaluate
    assert evaluate()["guardrails"]["failed"] == 0


def test_workforce_routes_close_to_human():
    from app.advanced.workforce import Workforce
    w = Workforce()
    w.add_worker("ai", "ai", ["cold_call"], capacity=10)
    w.add_worker("human", "human", ["close"], capacity=2)
    rec = w.submit("close", "lead_z")
    assert rec["worker_kind"] == "human"


def test_business_optimizer_flags_and_recommends():
    from app.advanced.business_optimizer import BusinessOptimizer, KPIs
    out = BusinessOptimizer().optimize(KPIs(contact_rate=0.2, conversion_rate=0.1,
                                            opt_out_rate=0.2, avg_sentiment=-0.4))
    assert out["status"] == "action_required" and out["findings"]


def test_billing_invoice_math():
    from app.business.billing import BillingService
    b = BillingService()
    b.record("org_default", "call_minutes", 100)
    inv = b.invoice("org_default")
    assert inv["total_inr"] > inv["subtotal_inr"]


def test_rbac_permission_matrix():
    from app.business.teams import permitted
    assert permitted("agent", "calls:create")
    assert not permitted("viewer", "calls:create")
    assert permitted("owner", "anything:goes")


def test_audio_pipeline_suppresses_and_cancels():
    from app.realtime.audio import AudioPipeline
    p = AudioPipeline()
    quiet = p.process_frame(near_rms=0.005)
    assert quiet.suppressed_db > 0
    assert p.set_codec(["pcmu", "opus"]) == "opus"


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"all {len(fns)} capability tests passed")
    sys.exit(0)
