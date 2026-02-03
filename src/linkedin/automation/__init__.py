"""LinkedIn automation module (optional).

Install with: pip install linkedin[automation]
"""

try:
    from .bot import *
    from .credentials import get_creds
except ImportError as e:
    raise ImportError(
        "Automation dependencies not installed. "
        "Install with: pip install linkedin[automation]"
    ) from e
