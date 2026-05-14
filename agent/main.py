"""
Entry point: python -m agent.main --ticket "..." [--user USER_ID] [--id TICKET_ID]

Example:
  python -m agent.main --ticket "我的发票上个月金额不对"
  python -m agent.main --ticket "I can't login" --id T-001 --user U-101
"""
import sys
import os
import json
import argparse
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import agent_loop
from agent_loop import run_agent


def main():
    parser = argparse.ArgumentParser(description="Support Copilot — SaaS ticket triage agent")
    parser.add_argument("--ticket", required=True, help="Customer ticket text")
    parser.add_argument("--id",   default="T-demo", help="Ticket ID")
    parser.add_argument("--user", default="U-demo", help="User ID")
    parser.add_argument("--debug", action="store_true", default=True)
    args = parser.parse_args()

    agent_loop.DEBUG = args.debug

    print("\n" + "=" * 70)
    print("SUPPORT COPILOT — ticket triage")
    print("=" * 70)
    print(f"Ticket ID : {args.id}")
    print(f"User ID   : {args.user}")
    print(f"Text      : {args.ticket}")
    print("=" * 70 + "\n")

    result = run_agent(
        ticket_text=args.ticket,
        ticket_id=args.id,
        user_id=args.user,
    )

    print("\n" + "=" * 70)
    print("FINAL RESULT")
    print("=" * 70)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 70)

    action = result.get("action", "ESCALATE_L1")
    conf = result.get("confidence", 0)
    print(f"\n→ ACTION: {action}  |  confidence: {conf}  |  intent: {result.get('intent')}")
    if action == "AUTO_REPLY":
        print(f"\nDraft reply:\n{result.get('draft_reply', '')}")
    elif action in ("ESCALATE_L1", "ESCALATE_L2"):
        tier = "L1 (first-line)" if action == "ESCALATE_L1" else "L2 (senior + churn review)"
        print(f"\nEscalate to: {tier}")
        print(f"Reason: {result.get('reason', '')}")
        if result.get("missing_info"):
            print(f"Missing info: {result['missing_info']}")
        if result.get("draft_reply"):
            print(f"\nSuggested draft for agent:\n{result['draft_reply']}")


if __name__ == "__main__":
    main()
