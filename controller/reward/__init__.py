# controller/reward/__init__.py
"""
Unified reward computation.

Combines:
- Plan progress reward (completion, step success)
- Test result reward (pass/fail delta)
"""
from .combine import combined_reward

__all__ = ["combined_reward"]
