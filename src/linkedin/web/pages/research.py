"""Research page — engagement strategies, post ideas, drafts, hashtags."""

import reflex as rx

from linkedin.web.layout import page_template
from linkedin.web.states.research_state import ResearchState

POST_STYLES = ["story", "listicle", "contrarian", "how-to"]


def tab_button(label: str, tab_id: str) -> rx.Component:
    """Tab button component."""
    return rx.button(
        label,
        variant=rx.cond(ResearchState.active_tab == tab_id, "solid", "soft"),
        on_click=ResearchState.set_active_tab(tab_id),
    )


def engagement_tab() -> rx.Component:
    """Engagement strategies tab content."""
    return rx.cond(
        ResearchState.active_tab == "engagement",
        rx.card(
            rx.vstack(
                rx.heading("Engagement Strategies", size="4"),
                rx.button("Load Strategies", on_click=ResearchState.load_engagement, variant="soft"),
                rx.cond(
                    ResearchState.engagement_content != "",
                    rx.markdown(ResearchState.engagement_content),
                    rx.text("Click Load Strategies to view.", color=rx.color("gray", 11)),
                ),
                spacing="3",
                width="100%",
            ),
        ),
        rx.fragment(),
    )


def ideas_tab() -> rx.Component:
    """Post ideas tab content."""
    return rx.cond(
        ResearchState.active_tab == "ideas",
        rx.card(
            rx.vstack(
                rx.heading("Post Ideas", size="4"),
                rx.button(
                    rx.cond(ResearchState.loading, rx.spinner(size="1"), rx.icon("lightbulb", size=16)),
                    "Generate Ideas",
                    on_click=ResearchState.generate_ideas,
                    disabled=ResearchState.loading,
                ),
                rx.cond(
                    ResearchState.post_ideas != "",
                    rx.markdown(ResearchState.post_ideas),
                    rx.text("Click Generate Ideas for AI-powered suggestions.", color=rx.color("gray", 11)),
                ),
                spacing="3",
                width="100%",
            ),
        ),
        rx.fragment(),
    )


def draft_post_tab() -> rx.Component:
    """Draft post tab content."""
    return rx.cond(
        ResearchState.active_tab == "draft",
        rx.card(
            rx.vstack(
                rx.heading("Draft Post", size="4"),
                rx.input(placeholder="Post topic", on_change=ResearchState.set_post_topic),
                rx.select(POST_STYLES, value=ResearchState.post_style, on_change=ResearchState.set_post_style),
                rx.button(
                    rx.cond(ResearchState.loading, rx.spinner(size="1"), rx.icon("pen-tool", size=16)),
                    "Generate Draft",
                    on_click=ResearchState.generate_draft_post,
                    disabled=ResearchState.loading,
                ),
                rx.cond(
                    ResearchState.post_draft != "",
                    rx.box(
                        rx.markdown(ResearchState.post_draft),
                        padding="1em",
                        border_radius="8px",
                        background=rx.color("gray", 2),
                        width="100%",
                    ),
                    rx.text("Enter a topic and style to generate a post.", color=rx.color("gray", 11)),
                ),
                spacing="3",
                width="100%",
            ),
        ),
        rx.fragment(),
    )


def hashtags_tab() -> rx.Component:
    """Hashtags tab content."""
    return rx.cond(
        ResearchState.active_tab == "hashtags",
        rx.card(
            rx.vstack(
                rx.heading("Hashtag Research", size="4"),
                rx.button(
                    rx.cond(ResearchState.loading, rx.spinner(size="1"), rx.icon("hash", size=16)),
                    "Generate Hashtags",
                    on_click=ResearchState.generate_hashtags,
                    disabled=ResearchState.loading,
                ),
                rx.cond(
                    ResearchState.hashtags != "",
                    rx.markdown(ResearchState.hashtags),
                    rx.text("Click Generate for relevant hashtag suggestions.", color=rx.color("gray", 11)),
                ),
                spacing="3",
                width="100%",
            ),
        ),
        rx.fragment(),
    )


def research_page() -> rx.Component:
    """Research page with tabs."""
    content = rx.vstack(
        # Tab bar
        rx.hstack(
            tab_button("Engagement", "engagement"),
            tab_button("Post Ideas", "ideas"),
            tab_button("Draft Post", "draft"),
            tab_button("Hashtags", "hashtags"),
            spacing="2",
        ),
        # Tab content
        engagement_tab(),
        ideas_tab(),
        draft_post_tab(),
        hashtags_tab(),
        spacing="4",
        width="100%",
    )
    return page_template(content, title="Research")
