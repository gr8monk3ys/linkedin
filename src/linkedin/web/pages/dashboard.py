"""Dashboard page — overview stats, pipeline chart, actions."""

import reflex as rx

from linkedin.web.layout import page_template
from linkedin.web.states.dashboard_state import DashboardState


def stat_card(label: str, value, color: str = "blue") -> rx.Component:
    """A stat card with label and value."""
    return rx.card(
        rx.vstack(
            rx.text(label, size="2", color=rx.color("gray", 11)),
            rx.heading(value, size="7", weight="bold"),
            spacing="1",
        ),
        style={
            "border_left": f"4px solid {rx.color(color, 9)}",
            "min_width": "200px",
        },
    )


def pipeline_chart() -> rx.Component:
    """Bar chart showing contact pipeline stages."""
    return rx.card(
        rx.vstack(
            rx.heading("Pipeline", size="4"),
            rx.recharts.bar_chart(
                rx.recharts.bar(data_key="count", fill=rx.color("accent", 8)),
                rx.recharts.x_axis(data_key="status", font_size=12),
                rx.recharts.y_axis(),
                rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
                data=DashboardState.pipeline_data,
                width="100%",
                height=250,
            ),
            width="100%",
        ),
    )


def overdue_followups() -> rx.Component:
    """List of overdue follow-ups."""
    return rx.card(
        rx.vstack(
            rx.heading("Overdue Follow-ups", size="4"),
            rx.cond(
                DashboardState.overdue_followups.length() > 0,
                rx.vstack(
                    rx.foreach(
                        DashboardState.overdue_followups,
                        lambda c: rx.hstack(
                            rx.icon("clock", size=16, color=rx.color("orange", 9)),
                            rx.text(c["name"], weight="medium"),
                            rx.text(c.get("follow_up_date", ""), size="2", color=rx.color("gray", 11)),
                            align="center",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.text("No overdue follow-ups", color=rx.color("gray", 11)),
            ),
            width="100%",
        ),
    )


def suggested_actions() -> rx.Component:
    """List of suggested next actions."""
    return rx.card(
        rx.vstack(
            rx.heading("Suggested Actions", size="4"),
            rx.foreach(
                DashboardState.suggested_actions,
                lambda action: rx.hstack(
                    rx.icon("arrow-right", size=16, color=rx.color("accent", 9)),
                    rx.text(action, size="2"),
                    align="center",
                ),
            ),
            spacing="2",
            width="100%",
        ),
    )


def dashboard_page() -> rx.Component:
    """Main dashboard page."""
    content = rx.vstack(
        # Stat cards row
        rx.hstack(
            stat_card("Total Contacts", DashboardState.total_contacts, "blue"),
            stat_card("Companies", DashboardState.total_companies, "purple"),
            stat_card("Drafts", DashboardState.total_drafts, "green"),
            stat_card("Response Rate", DashboardState.response_rate, "orange"),
            wrap="wrap",
            spacing="4",
            width="100%",
        ),
        # Charts and actions row
        rx.hstack(
            rx.box(pipeline_chart(), flex="2"),
            rx.vstack(
                overdue_followups(),
                suggested_actions(),
                flex="1",
                spacing="4",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        spacing="6",
        width="100%",
        on_mount=DashboardState.load_dashboard,
    )
    return page_template(content, title="Dashboard")
