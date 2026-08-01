from agent.multi_agent.shadow import MultiAgentShadowRunner
from conftest import manager, specialist


OBS = {"classification": {"intent": "billing", "confidence": 1}, "tone": {}, "kb_results": [{"doc_id": "FAQ-billing-01", "snippet": "invoice payment", "score": 1}], "history": {}}


def test_shadow_completed_and_serializable():
    packet = MultiAgentShadowRunner(manager(["billing"]), specialist).run("invoice", OBS)
    assert packet.status == "completed"
    assert MultiAgentShadowRunner.finalize(packet, "ESCALATE_L1")["baseline_action"] == "ESCALATE_L1"


def test_shadow_partial_failed_and_skipped():
    def fail_technical(name, context):
        if name == "technical": raise RuntimeError("down")
        return specialist(name, context)
    partial = MultiAgentShadowRunner(manager(["billing", "technical"]), fail_technical).run("invoice and error", OBS)
    failed = MultiAgentShadowRunner(manager(["billing"]), lambda n, c: (_ for _ in ()).throw(RuntimeError("down"))).run("invoice", OBS)
    assert partial.status == "partial" and failed.status == "failed"
    assert MultiAgentShadowRunner().skipped().skip_reason == "early_l2"
