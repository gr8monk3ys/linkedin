"""LinkedIn automation (optional). Install with: uv sync --extra automation

Everything here imports without Playwright; only opening a session needs it.
"""

from .budget import Budget
from .session import ActionResult, LinkedInSession

__all__ = ["ActionResult", "Budget", "LinkedInSession"]
