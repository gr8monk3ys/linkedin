"""Drafts page — generate and manage AI-powered drafts."""

import reflex as rx

from linkedin.web.layout import page_template
from linkedin.web.states.drafts_state import DraftsState

DRAFT_TYPES = ["connection", "message", "intro", "thank_you", "follow_up"]


def draft_controls() -> rx.Component:
    """Controls panel for generating drafts."""
    return rx.card(
        rx.vstack(
            rx.heading("Generate Draft", size="4"),
            rx.select(
                DRAFT_TYPES,
                value=DraftsState.draft_type,
                on_change=DraftsState.set_draft_type,
                placeholder="Draft type",
            ),
            rx.select(
                DraftsState.contacts.to(list[str]),
                placeholder="Select contact",
                on_change=DraftsState.set_contact_id,
            ),
            # Show contact dropdown as ID selector
            rx.cond(
                DraftsState.contacts.length() > 0,
                rx.vstack(
                    rx.text("Contact ID", size="2"),
                    rx.input(
                        placeholder="Contact ID",
                        on_change=DraftsState.set_contact_id,
                        type="number",
                    ),
                    spacing="1",
                ),
                rx.text("No contacts found. Add contacts first.", size="2", color=rx.color("gray", 11)),
            ),
            rx.cond(
                DraftsState.draft_type == "intro",
                rx.vstack(
                    rx.text("Target Contact ID", size="2"),
                    rx.input(
                        placeholder="Target contact ID",
                        on_change=DraftsState.set_target_id,
                        type="number",
                    ),
                    spacing="1",
                ),
                rx.fragment(),
            ),
            rx.cond(
                (DraftsState.draft_type == "message") | (DraftsState.draft_type == "thank_you"),
                rx.text_area(
                    placeholder="Additional context...",
                    on_change=DraftsState.set_context,
                ),
                rx.fragment(),
            ),
            rx.button(
                rx.cond(DraftsState.loading, rx.spinner(size="1"), rx.icon("sparkles", size=16)),
                "Generate",
                on_click=DraftsState.generate_draft,
                disabled=DraftsState.loading,
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
        width="350px",
        min_width="300px",
    )


def draft_preview() -> rx.Component:
    """Preview panel for generated draft."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.heading("Preview", size="4"),
                rx.spacer(),
                rx.cond(
                    DraftsState.generated_draft != "",
                    rx.button(
                        rx.icon("save", size=16),
                        "Save Draft",
                        variant="soft",
                        on_click=DraftsState.save_current_draft,
                    ),
                    rx.fragment(),
                ),
                width="100%",
            ),
            rx.cond(
                DraftsState.loading,
                rx.center(rx.spinner(size="3"), min_height="200px"),
                rx.cond(
                    DraftsState.generated_draft != "",
                    rx.box(
                        rx.text(DraftsState.generated_draft, white_space="pre-wrap"),
                        padding="1em",
                        border_radius="8px",
                        background=rx.color("gray", 2),
                        width="100%",
                    ),
                    rx.center(
                        rx.text("Select a contact and draft type, then click Generate.", color=rx.color("gray", 11)),
                        min_height="200px",
                    ),
                ),
            ),
            spacing="3",
            width="100%",
        ),
        flex="1",
    )


def saved_drafts_list() -> rx.Component:
    """List of previously saved drafts."""
    return rx.card(
        rx.vstack(
            rx.heading("Saved Drafts", size="4"),
            rx.cond(
                DraftsState.drafts.length() > 0,
                rx.vstack(
                    rx.foreach(
                        DraftsState.drafts,
                        lambda d: rx.box(
                            rx.hstack(
                                rx.badge(d.get("type", ""), variant="soft", size="1"),
                                rx.text(d.get("contact_name", "Unknown"), size="2", weight="medium"),
                                rx.text(d.get("created_at", ""), size="1", color=rx.color("gray", 11)),
                                spacing="2",
                                align="center",
                            ),
                            rx.text(
                                d.get("content", "")[:100] + "...",
                                size="2",
                                color=rx.color("gray", 11),
                            ),
                            padding="0.5em",
                            border_bottom=f"1px solid {rx.color('gray', 4)}",
                            width="100%",
                        ),
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.text("No saved drafts yet.", size="2", color=rx.color("gray", 11)),
            ),
            spacing="3",
            width="100%",
        ),
    )


def drafts_page() -> rx.Component:
    """Drafts page."""
    content = rx.vstack(
        rx.hstack(
            draft_controls(),
            draft_preview(),
            spacing="4",
            width="100%",
            align="start",
        ),
        saved_drafts_list(),
        spacing="6",
        width="100%",
        on_mount=DraftsState.load_drafts,
    )
    return page_template(content, title="Drafts")
