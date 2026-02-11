"""Shared layout components — sidebar navigation and page template."""

import reflex as rx

from linkedin.web.styles import SIDEBAR_WIDTH, TOPBAR_HEIGHT


def sidebar_item(text: str, icon: str, href: str) -> rx.Component:
    """A single sidebar navigation item."""
    return rx.link(
        rx.hstack(
            rx.icon(icon, size=20),
            rx.text(text, size="3", weight="medium"),
            width="100%",
            padding_x="0.75rem",
            padding_y="0.6rem",
            align="center",
            style={
                "_hover": {
                    "bg": rx.color("accent", 4),
                    "color": rx.color("accent", 11),
                },
                "border_radius": "0.5em",
            },
        ),
        href=href,
        underline="none",
        width="100%",
    )


def sidebar() -> rx.Component:
    """Sidebar with navigation links."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("briefcase", size=24, color=rx.color("accent", 9)),
                rx.heading("LinkedIn", size="5", weight="bold"),
                align="center",
                padding="0.5rem",
            ),
            rx.separator(),
            sidebar_item("Dashboard", "layout-dashboard", "/"),
            sidebar_item("Contacts", "users", "/contacts"),
            sidebar_item("Companies", "building-2", "/companies"),
            sidebar_item("Drafts", "file-text", "/drafts"),
            sidebar_item("Discover", "search", "/discover"),
            sidebar_item("Research", "lightbulb", "/research"),
            rx.separator(),
            sidebar_item("Settings", "settings", "/settings"),
            spacing="1",
            width="100%",
            padding="1em",
        ),
        width=SIDEBAR_WIDTH,
        min_width=SIDEBAR_WIDTH,
        height="100vh",
        background=rx.color("gray", 2),
        border_right=f"1px solid {rx.color('gray', 5)}",
        position="fixed",
        left="0",
        top="0",
    )


def page_template(content: rx.Component, title: str = "") -> rx.Component:
    """Wrap page content with sidebar layout."""
    return rx.box(
        sidebar(),
        rx.box(
            rx.box(
                rx.hstack(
                    rx.heading(title, size="6") if title else rx.fragment(),
                    align="center",
                    height=TOPBAR_HEIGHT,
                    padding_x="2em",
                    border_bottom=f"1px solid {rx.color('gray', 5)}",
                ),
            ),
            rx.box(
                content,
                padding="2em",
                overflow_y="auto",
                height=f"calc(100vh - {TOPBAR_HEIGHT})",
            ),
            margin_left=SIDEBAR_WIDTH,
            width=f"calc(100% - {SIDEBAR_WIDTH})",
        ),
        width="100%",
        min_height="100vh",
    )
