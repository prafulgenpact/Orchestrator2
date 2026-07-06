"""LLM client implementations and the record/replay layer.

The planner depends only on the `LLMClient` protocol in `base`; concrete clients
(Foundry for real calls, replay/record for tests) are selected by `get_client`.
"""

from __future__ import annotations
