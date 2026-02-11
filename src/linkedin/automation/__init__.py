"""LinkedIn automation module (optional).

Install with: pip install linkedin[automation]
"""

from .config import AutomationConfig
from .rate_limiter import RateLimiter
from .safety import SafetyLimits

__all__ = ["AutomationConfig", "RateLimiter", "SafetyLimits"]

try:
    from .browser import BrowserManager

    __all__.append("BrowserManager")
except ImportError:
    BrowserManager = None  # type: ignore[assignment,misc]
