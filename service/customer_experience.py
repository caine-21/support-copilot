"""Customer-facing copy and safe demo-profile helpers.

The public web channel is deliberately smaller than the internal ticket API.
This module keeps customer wording and demo-only context projection out of the
workflow engine while preserving the existing deterministic decision contract.
"""
from __future__ import annotations

import re
from typing import Any


_HUMAN_HANDOFF_PATTERNS = (
    "转人工",
    "人工客服",
    "真人客服",
    "找人工",
    "联系人工",
    "希望人工",
    "talk to a human",
    "speak to a human",
    "human agent",
    "talk to an agent",
    "speak to an agent",
    "connect me to support",
)


def is_human_handoff_request(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(marker in normalized for marker in _HUMAN_HANDOFF_PATTERNS)


def is_chinese(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def demo_customer_context(profile: dict[str, str] | None) -> dict[str, Any] | None:
    """Build the complete context contract from non-sensitive demo selectors."""
    if not profile:
        return None
    plan = profile.get("plan", "team")
    region = profile.get("region", "US")
    role = profile.get("role", "member")
    permissions = ["manage_billing", "manage_members"] if role in {"admin", "owner"} else []
    source = "public_demo_profile"
    fields = {
        "plan": plan,
        "region": region,
        "role": role,
        "permissions": permissions,
        "contract_status": "active",
        "account_status": "active",
    }
    return {
        "fields": {
            name: {
                "value": value,
                "status": "known",
                "source": source,
                "updated_at": "session",
                "allowed_for_auto_reply": True,
            }
            for name, value in fields.items()
        }
    }


_ZH_REPLIES = {
    "FAQ-account-01": (
        "重置密码：打开 Acme Collab 登录页，点击“忘记密码”，输入注册邮箱并点击发送。"
        "通常会在 2 分钟内收到重置链接；如果没有收到，请检查垃圾邮件。"
        "重置链接 1 小时后过期。若你通过 SSO 登录，请联系 IT 管理员重置 SSO 凭据。"
    ),
    "FAQ-billing-01": (
        "查看或下载发票：进入“设置 → 账单 → 发票历史记录”，选择对应发票下载 PDF。"
        "帮助中心还说明，续费时发票会自动发送给账单联系人。"
    ),
    "FAQ-billing-03": (
        "退款政策：月付方案不提供退款。年付方案在购买后 14 天内、且工作区活跃会话少于 5 次时可以申请退款。"
        "超过 14 天不再退款；周期中降级会把未使用部分抵扣到下一张账单，不会退回原支付方式。"
    ),
    "FAQ-billing-06": (
        "支持的支付方式包括 Visa、Mastercard、American Express、Discover 信用卡/借记卡，以及美国账户的 ACH 转账。"
        "不支持 PayPal、电汇或加密货币；更新方式请进入“设置 → 账单 → 支付方式”。"
    ),
    "FAQ-billing-08": (
        "退款申请条件：年付方案购买后 14 天内，且工作区活跃会话少于 5 次，可申请全额退款；"
        "重复扣款或取消后仍扣款等账单错误不受时间限制。月付方案不符合退款条件，周期中降级会获得账单抵扣。"
    ),
    "FAQ-feature-04": (
        "导出文档：打开文档后点击右上角三点菜单 → 导出，可选择 PDF、Markdown、HTML 或 DOCX。"
        "导出整个 Space 时，进入 Space 设置 → 导出 Space；批量导出会以 ZIP 文件发送到注册邮箱。"
    ),
}


def customer_reply(
    ticket_text: str,
    decision: str | None,
    draft: str | None,
    evidence: list[dict[str, Any]] | None,
) -> str:
    """Return localized, source-bounded copy for the public channel."""
    if not is_chinese(ticket_text):
        return draft or ""
    if decision == "ESCALATE_L2":
        return "这个问题需要人工优先处理。当前公开演示通道不会执行外部操作，请等待人工客服进一步确认。"
    if is_human_handoff_request(ticket_text):
        return "已记录你的人工处理请求。当前公开演示通道暂未连接真人收件箱，不会假装已经完成转接。"
    if decision == "ESCALATE_L1":
        return (
            "我暂时没有找到足够可靠的帮助中心内容来直接回答。"
            "你可以补充具体功能、报错信息或所在页面，我会再尝试分流；也可以由人工客服继续处理。"
        )
    doc_ids = [str(item.get("doc_id")) for item in (evidence or [])]
    for doc_id in doc_ids:
        if doc_id in _ZH_REPLIES:
            return _ZH_REPLIES[doc_id]
    return "已找到相关帮助中心内容，但当前演示版还没有这条内容的中文回复。英文原文：\n" + (draft or "")
