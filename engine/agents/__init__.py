"""ADK-based agents for the SolarPro engine."""
from .shading_agent import (
    run_shading_agent,
    SHADING_AGENT_SYSTEM_PROMPT,
    SHADING_AGENT_VERSION,
)

__all__ = [
    "run_shading_agent",
    "SHADING_AGENT_SYSTEM_PROMPT",
    "SHADING_AGENT_VERSION",
]
