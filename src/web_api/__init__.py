"""User-facing Web BFF package.

Only HTTP/BFF endpoints for authenticated Web users belong here.
Worker protocol, execution-plane orchestration, and agent-only APIs must stay in
`backend/app` to avoid dual-entrypoint drift.
"""
