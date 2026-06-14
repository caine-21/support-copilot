import sys
import os
import gradio as gr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent"))
from agent_loop import run_agent

SAMPLES = [
    "My bill last month was wrong — I was overcharged by $20.",
    "I can't log in. My password keeps failing.",
    "I want to cancel my subscription immediately and get a refund.",
    "Your product is terrible. I want to file a complaint!",
    "How do I add a new team member to my workspace?",
    "我上个月的账单金额不对，多收了200元",
    "账号登不进去了，密码一直报错",
    "我要立刻取消订阅并申请退款",
]

ACTION_LABEL = {
    "AUTO_REPLY":  "🟢 AUTO_REPLY — Automated response / 自动回复",
    "ESCALATE_L1": "🟡 ESCALATE_L1 — Human agent / 转人工一线",
    "ESCALATE_L2": "🔴 ESCALATE_L2 — Senior escalation + churn alert / 升级高级客服 + 流失预警",
}


def analyze(ticket_text, user_id):
    if not ticket_text.strip():
        return "Please enter a support ticket. / 请输入工单内容", "", ""
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

        routing_md = (
            f"**{ACTION_LABEL.get(action, action)}**\n\n"
            f"**Confidence / 置信度：** {confidence:.0%}　"
            f"**Intent / 意图：** `{intent}`"
        )
        if reason:
            routing_md += f"\n\n**Reason / 原因：** {reason}"

        missing_md = "\n".join(f"- {m}" for m in missing) if missing else "None / 无缺失信息"

        return routing_md, draft or "(No draft reply / 无草稿回复)", missing_md

    except Exception as e:
        return (
            f"❌ Error / 运行出错：{e}\n\n"
            "Please check that `DEEPSEEK_API_KEY` or `GROQ_API_KEY` is configured.",
            "", ""
        )


with gr.Blocks(title="AI Support Triage / 客服智能分诊", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# 🎯 AI Customer Support Triage &nbsp;·&nbsp; 客服智能分诊\n"
        "Enter a support ticket. The agent classifies intent, searches the knowledge base, "
        "drafts a reply, and routes the ticket — using **KB similarity score** (not LLM "
        "self-reported confidence) to decide between auto-reply, L1, or L2 escalation.\n\n"
        "输入用户工单，系统自动分诊（自动回复 / 转人工 / 升级），并生成草稿回复。"
        "路由基于 **知识库相似度分数**（非 LLM 置信度），可审计、可复现。"
    )
    with gr.Row():
        with gr.Column(scale=1):
            ticket  = gr.Textbox(
                label="Support Ticket / 工单内容",
                placeholder="Describe the customer's issue… / 输入用户投诉或咨询…",
                lines=5,
            )
            user_id = gr.Textbox(label="User ID (optional / 可选)", value="U-demo")
            btn     = gr.Button("Analyze / 分析", variant="primary", size="lg")
            gr.Examples(SAMPLES, inputs=ticket, label="Sample tickets / 示例工单")
        with gr.Column(scale=1):
            routing = gr.Markdown(label="Routing Decision / 路由决策")
            draft   = gr.Textbox(
                label="Draft Reply / 草稿回复",
                lines=6,
                interactive=False,
            )
            missing = gr.Markdown(label="Missing Info / 缺失信息")

    gr.Markdown(
        "---\n"
        "**How routing works / 路由逻辑：** "
        "KB similarity ≥ 0.60 → eligible for auto-reply · "
        "churn risk → L2 always · "
        "no grounding → L1. "
        "Eval: 35 cases (20 baseline + 15 adversarial) · L2 recall 100% · unsafe auto-reply 0%.\n\n"
        "📂 [GitHub](https://github.com/caine-21/support-copilot)"
    )

    btn.click(analyze, inputs=[ticket, user_id], outputs=[routing, draft, missing])

demo.launch()
