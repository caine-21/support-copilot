import sys
import os
import gradio as gr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent"))
from agent_loop import run_agent

SAMPLES = [
    "How do I download my invoice from last month?",
    "I want to cancel my subscription immediately and get a refund.",
    "Our SSO login has been broken since this morning and we may breach SLA.",
    "Can Team plan users set up SSO with Okta?",
    "I need help canceling the company newsletter subscription.",
]

ACTION_LABEL = {
    "AUTO_REPLY":  "AUTO_REPLY — safe automated response",
    "ESCALATE_L1": "ESCALATE_L1 — human review",
    "ESCALATE_L2": "ESCALATE_L2 — senior escalation / churn or risk review",
}


def _value(value, default="unavailable"):
    return default if value in (None, "", [], {}) else value


def _format_kb_docs(result):
    docs = result.get("kb_grounding") or []
    if not docs:
        return "unavailable"
    lines = []
    for item in docs[:3]:
        doc_id = item.get("doc_id", "unknown")
        snippet = (item.get("snippet") or "").replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:220] + "..."
        lines.append(f"- `{doc_id}`: {snippet}")
    return "\n".join(lines)


def _format_grounding(result):
    gc = result.get("grounding_check") or {}
    if not gc:
        return "unavailable"
    claims = gc.get("ungrounded_claims") or []
    lines = [
        f"- grounding level: `{_value(result.get('grounding'))}`",
        f"- claim support ratio: `{gc.get('grounding_ratio', 'unavailable')}`",
        f"- auto-reply safe by compiler: `{gc.get('auto_reply_safe', 'unavailable')}`",
    ]
    if claims:
        lines.append("- ungrounded claims:")
        lines.extend(f"  - {claim}" for claim in claims[:3])
    else:
        lines.append("- ungrounded claims: none")
    return "\n".join(lines)


def _format_trace(result):
    trace = result.get("assumption_trace") or {}
    replay = result.get("assumption_replay") or {}
    if not trace and not replay:
        return "unavailable"
    lines = [
        f"- assumption risk: `{_value(trace.get('max_assumption_risk'))}`",
        f"- replay verdict: `{_value(replay.get('verdict'))}`",
        f"- load-bearing assumptions: `{_value(replay.get('load_bearing_assumptions'))}`",
    ]
    return "\n".join(lines)


def analyze(ticket_text, user_id):
    if not ticket_text.strip():
        return "Please enter a support ticket.", "", "", "", ""
    try:
        result = run_agent(
            ticket_text.strip(),
            ticket_id="T-demo",
            user_id=(user_id.strip() or "U-demo"),
        )

        action     = result.get("action", "ESCALATE_L1")
        confidence = result.get("confidence", 0)
        intent     = result.get("intent", "unknown")
        draft      = result.get("draft_reply", "")
        reason     = result.get("reason", "")
        missing    = result.get("missing_info", [])
        routing_signals = result.get("routing_signals", [])

        routing_md = (
            f"**{ACTION_LABEL.get(action, action)}**\n\n"
            f"- confidence: `{confidence:.0%}`\n"
            f"- intent: `{intent}`\n"
            f"- intent set: `{_value(result.get('intent_set'))}`\n"
            f"- priority: `{_value(result.get('priority'))}`\n"
            f"- tone: `{_value(result.get('tone'))}`\n"
            f"- churn risk: `{_value(result.get('churn_risk'))}`\n"
            f"- routing signals: `{_value(routing_signals)}`"
        )
        if reason:
            routing_md += f"\n\n**Reason:** {reason}"

        missing_md = "\n".join(f"- {m}" for m in missing) if missing else "None"

        evidence_md = (
            "### Matched FAQ / KB evidence\n"
            f"{_format_kb_docs(result)}\n\n"
            "### Grounding check\n"
            f"{_format_grounding(result)}\n\n"
            "### Assumption trace / replay\n"
            f"{_format_trace(result)}"
        )

        return routing_md, draft or "(No draft reply)", missing_md, evidence_md, result

    except Exception as e:
        return (
            f"Error: {e}\n\n"
            "Please check that `DEEPSEEK_API_KEY` or `GROQ_API_KEY` is configured.",
            "", "", "", {}
        )


with gr.Blocks(title="AI Support Triage", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# AI Support Copilot: Ticket Routing Decision System\n"
        "Enter a support ticket. The agent classifies intent, searches the knowledge base, "
        "drafts a reply, and routes the ticket. The point is not chat; the point is "
        "whether there is enough evidence to allow autonomous reply.\n\n"
        "**Latest eval snapshot:** 100 cases, 95/100 pass, action accuracy 96%, "
        "L2 recall 100%, unsafe AUTO_REPLY rate 0%."
    )
    with gr.Row():
        with gr.Column(scale=1):
            ticket  = gr.Textbox(
                label="Support Ticket",
                placeholder="Describe the customer's issue...",
                lines=5,
            )
            user_id = gr.Textbox(label="User ID (optional)", value="U-demo")
            btn     = gr.Button("Analyze", variant="primary", size="lg")
            gr.Examples(SAMPLES, inputs=ticket, label="Sample tickets")
        with gr.Column(scale=1):
            routing = gr.Markdown(label="Routing Decision")
            draft   = gr.Textbox(
                label="Draft Reply",
                lines=6,
                interactive=False,
            )
            missing = gr.Markdown(label="Missing Info")
            evidence = gr.Markdown(label="Evidence")
            raw_json = gr.JSON(label="Raw result")

    gr.Markdown(
        "---\n"
        "**How routing works:** AUTO_REPLY requires strong KB grounding and compiler-safe claims. "
        "Weak/no grounding routes to L1. SLA, hidden cancellation, security, or churn-like risk routes to L2. "
        "Assumption replay marks whether a decision stands on verified facts or LLM-inferred assumptions.\n\n"
        "[GitHub](https://github.com/caine-21/support-copilot)"
    )

    btn.click(analyze, inputs=[ticket, user_id], outputs=[routing, draft, missing, evidence, raw_json])

if __name__ == "__main__":
    demo.launch()
