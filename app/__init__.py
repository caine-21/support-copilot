"""A1 unified request runtime (additive domain facade).

Calls the existing verified `agent.*` modules as the source of truth for
policy (routing, grounding, authorization). This layer owns contract,
coordination, projection, routing and trace — never business-rule rewrite.
"""
