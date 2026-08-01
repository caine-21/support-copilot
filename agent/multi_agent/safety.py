from .contracts import SafeAgentError

def safe_error(component: str, exc: Exception | None = None, code: str | None = None):
    if code is None:
        name = type(exc).__name__ if exc else "unknown"
        if "JSON" in name: code = f"{component}_json_invalid"
        elif "Validation" in name: code = f"{component}_schema_invalid"
        else: code = f"{component}_call_failed"
    return SafeAgentError(component=component, code=code)
