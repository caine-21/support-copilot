import sys
import os
import gradio as gr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent"))
from agent_loop import run_agent

SAMPLES = [
    "我上个月的账单金额不对，多收了200元",
    "账号登不进去了，密码一直报错",
    "我要立刻取消订阅并申请退款",
    "你们的产品太差了，我要投诉！",
    "How do I reset my password?",
]

ACTION_LABEL = {
    "AUTO_REPLY":   "🟢 AUTO_REPLY — 自动回复",
    "ESCALATE_L1":  "🟡 ESCALATE_L1 — 转人工一线",
    "ESCALATE_L2":  "🔴 ESCALATE_L2 — 升级高级客服 + 流失预警",
}


def analyze(ticket_text, user_id):
    if not ticket_text.strip():
        return "请输入工单内容", "", ""
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
            f"**置信度：** {confidence:.0%}　**意图：** `{intent}`"
        )
        if reason:
            routing_md += f"\n\n**原因：** {reason}"

        missing_md = "\n".join(f"- {m}" for m in missing) if missing else "无缺失信息"

        return routing_md, draft or "（无草稿回复）", missing_md

    except Exception as e:
        return f"❌ 运行出错：{e}\n\n请确认已配置 `DEEPSEEK_API_KEY` 或 `GROQ_API_KEY`。", "", ""


with gr.Blocks(title="客服智能分诊", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# 🎯 客服智能分诊系统\n"
        "输入用户工单，自动判断路由策略：**自动回复 / 转人工 / 升级高级客服**，"
        "并生成草稿回复。"
    )
    with gr.Row():
        with gr.Column(scale=1):
            ticket  = gr.Textbox(label="工单内容", placeholder="输入用户投诉 / 咨询…", lines=5)
            user_id = gr.Textbox(label="用户 ID（可选）", value="U-demo")
            btn     = gr.Button("分析工单", variant="primary", size="lg")
            gr.Examples(SAMPLES, inputs=ticket, label="示例工单")
        with gr.Column(scale=1):
            routing = gr.Markdown(label="路由决策")
            draft   = gr.Textbox(label="草稿回复", lines=6, interactive=False)
            missing = gr.Markdown(label="缺失信息 / 置信度依据")

    btn.click(analyze, inputs=[ticket, user_id], outputs=[routing, draft, missing])

demo.launch()
