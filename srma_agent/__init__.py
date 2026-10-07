"""SRMA Agent: automated systematic review and meta-analysis.

`adk web` and `adk run` discover the agent by importing this package and
looking for `root_agent`, so the agent module must be imported here. Without
this line the ADK reports "no root_agent found" even though agent.py is
correct.
"""

from . import agent
from .agent import root_agent

__all__ = ["agent", "root_agent"]
