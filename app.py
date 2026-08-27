"""Vercel-compatible, request-scoped entrypoint for Lily's FastAPI bridge.

This is deliberately not the Telegram long-polling bot process. See
DEPLOYMENT.md before choosing a serverless host for a Lily deployment.
"""
from lily.web_media import create_app

app = create_app()
