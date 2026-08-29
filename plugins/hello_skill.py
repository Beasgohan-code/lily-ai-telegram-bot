"""Example trusted Lily plugin. Copy this pattern for local custom skills."""

PLUGIN = {
    "name": "hello-lily",
    "version": "1.0.0",
    "description": "Replies when a user asks Lily to say hello.",
    "triggers": ["say hello", "hello lily"],
    "match": "contains",
    "action": "plugin_reply",
    "risk": "safe",
    "requires_confirmation": False,
}


def build_plan(context):
    return {
        "intent": "hello-lily",
        "summary": "Respond to a hello request",
        "action": "plugin_reply",
        "risk": "safe",
        "requires_confirmation": False,
        "args": {"text": f"Hello, I’m Lily. You said: {context.text[:300]}"},
        "confidence": 1.0,
    }
