"""Theme constants and shared styles for the web dashboard."""

# Color scheme
ACCENT_COLOR = "blue"
SIDEBAR_BG = "var(--gray-2)"
CARD_BG = "var(--gray-1)"
BORDER_COLOR = "var(--gray-6)"

# Layout dimensions
SIDEBAR_WIDTH = "250px"
TOPBAR_HEIGHT = "64px"
CONTENT_PADDING = "2em"

# Stat card colors by type
STAT_COLORS = {
    "total": "blue",
    "active": "green",
    "pending": "orange",
    "completed": "purple",
}

# Status badge colors
STATUS_COLORS = {
    "not_contacted": "gray",
    "connection_sent": "orange",
    "connected": "blue",
    "messaged": "cyan",
    "responded": "green",
    "call_scheduled": "purple",
    "hired": "green",
    "rejected": "red",
}

# Priority colors
PRIORITY_COLORS = {
    "high": "red",
    "medium": "orange",
    "low": "blue",
}
