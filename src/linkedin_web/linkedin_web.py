"""Bridge module so Reflex can import the app from its expected location."""

from linkedin.web.app import app

__all__ = ["app"]
