"""
VCP trading skills — each module is a single-responsibility LLM skill node.

Skills are the atomic units of the VCP Pure workflow.
Each skill owns one analytical domain, takes focused inputs, and returns a typed dict.

Usage (from workflow nodes):
    from app.services.skills import vcp_stage2_qualifier, vcp_contraction_analyst, vcp_execution_planner
    result = await vcp_stage2_qualifier.execute(...)
"""
