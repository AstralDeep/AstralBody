"""Scheduled autonomous work ("cron") for the agentic-soul-integration feature (025).

A durable job store, a pure-Python timezone-aware next-run evaluator, a single
in-process asyncio scheduler loop, and a runner that executes due jobs under a
fresh per-run delegated authorization (bounded by the user's current scopes),
delivering results in-app only.
"""
