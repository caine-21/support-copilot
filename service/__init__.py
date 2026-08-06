"""Service layer: auditable ticket workflow slice.

Turns the existing offline decision pipeline (agent_loop.run_agent) into a
run/query/review loop with persistence (SQLite), idempotent mock actions and
an audit trail. No real external system is called; MockTicketActionAdapter is
the only adapter wired by default.

Dependency note: this package only imports the heavy agent stack lazily inside
default_decision_fn, so unit tests can inject a fake decision port and stay
fully offline.
"""
