"""ML Services agent — consolidates the CLASSify, Forecaster, and LLM-Factory agents.

Feature 029 merged the three external-ML wrapper agents into one agent
(`ml-services-1`) with a union tool registry. Per-service tool logic lives in
``classify_tools`` / ``forecaster_tools`` / ``llm_factory_tools``; the shared
HTTP/credential/error foundation lives in ``_wrapper``.
"""
