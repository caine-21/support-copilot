from concurrent.futures import ThreadPoolExecutor, as_completed
from .context import build_manager_context, build_billing_context, build_technical_context
from .contracts import MultiAgentShadowPacket
from .manager import decide_manager
from .merger import merge_specialist_results
from .specialists import run_specialist
class MultiAgentShadowRunner:
    """Bounded analysis only; never receives or mutates the formal action."""
    def __init__(self, manager_runner=None, specialist_runner=None): self.manager_runner, self.specialist_runner = manager_runner, specialist_runner
    def skipped(self, baseline_action=""):
        return MultiAgentShadowPacket(status="skipped", baseline_action=baseline_action, baseline_action_unchanged=True, skip_reason="early_l2")
    def run(self, ticket_text, obs, customer_context=None, baseline_action=""):
        manager_context = build_manager_context(ticket_text, obs["classification"], obs["tone"], obs["kb_results"])
        decision, errors = decide_manager(manager_context, self.manager_runner)
        slices = {item.specialist: item.model_dump() for item in decision.domain_slices}
        contexts = {"billing": build_billing_context(classification=obs["classification"], kb_results=obs["kb_results"], customer_context=customer_context, domain_slice=slices.get("billing"), tone=obs["tone"]), "technical": build_technical_context(classification=obs["classification"], kb_results=obs["kb_results"], history=obs.get("history"), domain_slice=slices.get("technical"), tone=obs["tone"])}
        results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_specialist, name, contexts[name], self.specialist_runner) for name in decision.selected_specialists]
            for future in as_completed(futures): results.append(future.result())
        merged = merge_specialist_results(results); failures = sum(result.error is not None for result in results)
        status = "completed" if not failures else ("failed" if failures == len(results) and results else "partial")
        return MultiAgentShadowPacket(status=status, manager_decision=decision, specialist_results=results, baseline_action=baseline_action, baseline_action_unchanged=True, errors=errors + [result.error for result in results if result.error], **merged)
    @staticmethod
    def finalize(packet, baseline_action): return packet.model_copy(update={"baseline_action": baseline_action, "baseline_action_unchanged": True}).model_dump()
