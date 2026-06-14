"""Quick spot-check on the 3 previously failing hidden_cancel cases."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import agent_loop
agent_loop.DEBUG = False
from agent_loop import run_agent
from memory import AgentMemory

CASES = [
    ("T-097", "U-900",
     "Can you also walk me through how to export all our data and transfer account"
     " ownership? I need to justify the renewal cost to my leadership, and I want"
     " to be prepared in case we decide to move on."),
    ("T-099", "U-901",
     "I need help filing a formal complaint about my subscription. Also, could you"
     " guide me on how to export all my data and transfer account ownership, as I"
     " need to justify the renewal cost to my team."),
    ("T-100", "U-902",
     "I paid $149 for my subscription. I need help getting a refund, and before"
     " that, I want to export all my data and transfer ownership to my colleague,"
     " as I'm evaluating whether the renewal cost is justified."),
]

mem = AgentMemory()
for tid, uid, text in CASES:
    r = run_agent(ticket_id=tid, ticket_text=text, user_id=uid, memory=mem)
    status = "PASS" if r["action"] == "ESCALATE_L2" else "FAIL"
    print(f"[{tid}] {status}  action={r['action']}  churn_risk={r['churn_risk']:.2f}")
