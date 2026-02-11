"""Discover page — AI-powered contact/company suggestions."""

import reflex as rx

from linkedin.web.layout import page_template
from linkedin.web.states.discover_state import DiscoverState


def discover_page() -> rx.Component:
    """Discover page."""
    content = rx.vstack(
        rx.hstack(
            rx.card(
                rx.vstack(
                    rx.heading("Discover", size="4"),
                    rx.select(
                        ["contacts", "companies"],
                        value=DiscoverState.discover_type,
                        on_change=DiscoverState.set_discover_type,
                    ),
                    rx.cond(
                        DiscoverState.discover_type == "contacts",
                        rx.vstack(
                            rx.input(placeholder="Role / Title", on_change=DiscoverState.set_role),
                            rx.input(placeholder="Company", on_change=DiscoverState.set_company),
                            rx.input(placeholder="Industry", on_change=DiscoverState.set_industry),
                            spacing="2",
                        ),
                        rx.input(placeholder="Industry", on_change=DiscoverState.set_industry),
                    ),
                    rx.button(
                        rx.cond(DiscoverState.loading, rx.spinner(size="1"), rx.icon("search", size=16)),
                        "Discover",
                        on_click=DiscoverState.discover,
                        disabled=DiscoverState.loading,
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="350px",
                min_width="300px",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("Suggestions", size="4"),
                    rx.cond(
                        DiscoverState.loading,
                        rx.center(rx.spinner(size="3"), min_height="200px"),
                        rx.cond(
                            DiscoverState.suggestions != "",
                            rx.box(
                                rx.markdown(DiscoverState.suggestions),
                                width="100%",
                            ),
                            rx.center(
                                rx.text(
                                    "Enter search criteria and click Discover for AI suggestions.",
                                    color=rx.color("gray", 11),
                                ),
                                min_height="200px",
                            ),
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                flex="1",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        spacing="4",
        width="100%",
    )
    return page_template(content, title="Discover")
