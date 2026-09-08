"""LinkedIn Job Hunt Assistant — the command line.

One module per command group. `_common` holds the root group, the console,
and the lazy `_app` handle; importing this package registers every group on
`cli` and touches nothing on disk.
"""

import click  # noqa: F401  (tests patch linkedin.cli.click.confirm)

from linkedin.cli import (  # noqa: F401  registration side effects
    analytics,
    applications,
    automate,
    automation,
    companies,
    contacts,
    daily,
    data,
    drafts,
    inbox,
    metrics,
    postings,
    posts,
    profile,
    settings,
)
from linkedin.cli._common import _app, _app_version, cli, console
from linkedin.cli.automate import _open_session, _report_selector_health, _review_feed_comment
from linkedin.cli.inbox import load_inbox_proposals, save_inbox_proposals

__all__ = [
    "_app",
    "_app_version",
    "_open_session",
    "_report_selector_health",
    "_review_feed_comment",
    "cli",
    "console",
    "load_inbox_proposals",
    "save_inbox_proposals",
]
