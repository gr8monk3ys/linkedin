"""Companies page — card grid with detail view."""

import reflex as rx

from linkedin.constants import COMPANY_PRIORITIES, COMPANY_SIZES
from linkedin.web.layout import page_template
from linkedin.web.states.companies_state import CompaniesState


def company_card(company: dict) -> rx.Component:
    """A company card in the grid."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.heading(company["name"], size="4"),
                rx.spacer(),
                rx.badge(company.get("priority", "medium"), variant="soft"),
                width="100%",
            ),
            rx.text(company.get("industry", ""), size="2", color=rx.color("gray", 11)),
            rx.hstack(
                rx.icon("users", size=14),
                rx.text(company.get("size", ""), size="2"),
                spacing="1",
                align="center",
            ),
            rx.cond(
                company.get("why_target", "") != "",
                rx.text(company.get("why_target", ""), size="2", trim="both"),
                rx.fragment(),
            ),
            rx.button(
                "View Details",
                variant="soft",
                size="1",
                on_click=CompaniesState.select_company(company["id"]),
            ),
            spacing="2",
        ),
        style={"_hover": {"border_color": rx.color("accent", 7)}, "cursor": "pointer"},
        min_width="280px",
    )


def add_company_modal() -> rx.Component:
    """Modal form to add a new company."""
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=16), "Add Company"),
        ),
        rx.dialog.content(
            rx.dialog.title("Add New Company"),
            rx.form(
                rx.vstack(
                    rx.input(placeholder="Company Name *", name="name", required=True),
                    rx.input(placeholder="Industry", name="industry"),
                    rx.select(COMPANY_SIZES, placeholder="Company Size", name="size", default_value="51-200"),
                    rx.input(placeholder="LinkedIn URL", name="linkedin_url"),
                    rx.input(placeholder="Website", name="website"),
                    rx.text_area(placeholder="Why target this company?", name="why_target"),
                    rx.select(COMPANY_PRIORITIES, placeholder="Priority", name="priority", default_value="medium"),
                    rx.text_area(placeholder="Notes", name="notes"),
                    rx.hstack(
                        rx.dialog.close(rx.button("Cancel", variant="soft", color_scheme="gray")),
                        rx.dialog.close(rx.button("Add Company", type="submit")),
                        spacing="3",
                        justify="end",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                on_submit=CompaniesState.add_company,
                reset_on_submit=True,
            ),
            max_width="500px",
        ),
    )


def company_detail_dialog() -> rx.Component:
    """Detail dialog for selected company."""
    c = CompaniesState.selected_company
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(c.get("name", "")),
            rx.vstack(
                rx.hstack(
                    rx.badge(c.get("priority", "medium"), variant="soft"),
                    rx.text(c.get("industry", ""), size="2"),
                    rx.text("Size:", size="2"),
                    rx.text(c.get("size", ""), size="2"),
                    spacing="2",
                ),
                rx.cond(
                    c.get("website", "") != "",
                    rx.link("Website", href=c.get("website", ""), is_external=True, size="2"),
                    rx.fragment(),
                ),
                rx.cond(
                    c.get("why_target", "") != "",
                    rx.box(
                        rx.text("Why Target", size="2", weight="bold"),
                        rx.text(c.get("why_target", ""), size="2"),
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    c.get("notes", "") != "",
                    rx.box(
                        rx.text("Notes", size="2", weight="bold"),
                        rx.text(c.get("notes", ""), size="2"),
                    ),
                    rx.fragment(),
                ),
                # Linked contacts
                rx.cond(
                    CompaniesState.company_contacts.length() > 0,
                    rx.box(
                        rx.text("Linked Contacts", size="2", weight="bold"),
                        rx.foreach(
                            CompaniesState.company_contacts,
                            lambda ct: rx.hstack(
                                rx.icon("user", size=14),
                                rx.text(ct["name"], size="2"),
                                rx.badge(ct.get("status", ""), size="1"),
                                spacing="2",
                            ),
                        ),
                    ),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(rx.button("Close", variant="soft")),
                    rx.button(
                        "Delete",
                        color_scheme="red",
                        variant="soft",
                        on_click=CompaniesState.delete_company(c.get("id", 0)),
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="600px",
        ),
        open=CompaniesState.show_detail,
        on_open_change=lambda _: CompaniesState.close_detail(),
    )


def companies_page() -> rx.Component:
    """Companies page."""
    content = rx.vstack(
        # Toolbar
        rx.hstack(
            rx.hstack(
                rx.heading(CompaniesState.companies.length(), size="4"),
                rx.text("Companies", size="4"),
                spacing="2",
                align="center",
            ),
            rx.spacer(),
            add_company_modal(),
            width="100%",
        ),
        # Card grid
        rx.flex(
            rx.foreach(CompaniesState.companies, company_card),
            wrap="wrap",
            spacing="4",
            width="100%",
        ),
        company_detail_dialog(),
        spacing="4",
        width="100%",
        on_mount=CompaniesState.load_companies,
    )
    return page_template(content, title="Companies")
