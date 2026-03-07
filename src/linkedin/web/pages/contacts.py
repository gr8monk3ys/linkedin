"""Contacts page — filterable table with add/edit modals."""

import reflex as rx

from linkedin.constants import CONTACT_SOURCES, CONTACT_STATUSES
from linkedin.web.layout import page_template
from linkedin.web.states.contacts_state import ContactsState


def status_badge(status: str) -> rx.Component:
    """Colored badge for contact status."""
    return rx.badge(
        status,
        variant="soft",
    )


def contact_row(contact: dict) -> rx.Component:
    """A single row in the contacts table."""
    return rx.table.row(
        rx.table.cell(rx.text(contact["name"], weight="medium")),
        rx.table.cell(contact.get("title", "")),
        rx.table.cell(contact.get("company", "")),
        rx.table.cell(status_badge(contact.get("status", "not_contacted"))),
        rx.table.cell(contact.get("source", "")),
        rx.table.cell(
            rx.button(
                rx.icon("eye", size=14),
                variant="ghost",
                size="1",
                on_click=ContactsState.select_contact(contact["id"]),
            ),
        ),
        style={"_hover": {"bg": rx.color("gray", 3)}, "cursor": "pointer"},
    )


def add_contact_modal() -> rx.Component:
    """Modal form to add a new contact."""
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=16), "Add Contact"),
        ),
        rx.dialog.content(
            rx.dialog.title("Add New Contact"),
            rx.form(
                rx.vstack(
                    rx.input(placeholder="Name *", name="name", required=True),
                    rx.input(placeholder="Title / Role", name="title"),
                    rx.input(placeholder="Company", name="company"),
                    rx.input(placeholder="LinkedIn URL", name="linkedin_url"),
                    rx.select(CONTACT_SOURCES, placeholder="Source", name="source", default_value="linkedin_search"),
                    rx.text_area(placeholder="Notes", name="notes"),
                    rx.hstack(
                        rx.dialog.close(rx.button("Cancel", variant="soft", color_scheme="gray")),
                        rx.dialog.close(rx.button("Add Contact", type="submit")),
                        spacing="3",
                        justify="end",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                on_submit=ContactsState.add_contact,
                reset_on_submit=True,
            ),
            max_width="500px",
        ),
    )


def contact_detail_panel() -> rx.Component:
    """Detail panel for selected contact."""
    c = ContactsState.selected_contact
    return rx.cond(
        ContactsState.show_detail,
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.heading(c["name"], size="5"),
                    rx.spacer(),
                    rx.button(
                        rx.icon("x", size=16),
                        variant="ghost",
                        on_click=ContactsState.close_detail,
                    ),
                    width="100%",
                ),
                rx.separator(),
                rx.text(c.get("title", ""), weight="medium"),
                rx.text(c.get("company", ""), color=rx.color("gray", 11)),
                rx.hstack(
                    rx.text("Status:", size="2"),
                    status_badge(c.get("status", "")),
                ),
                rx.cond(
                    c.get("email", "") != "",
                    rx.hstack(rx.icon("mail", size=14), rx.text(c.get("email", ""), size="2")),
                    rx.fragment(),
                ),
                rx.cond(
                    c.get("linkedin_url", "") != "",
                    rx.link("LinkedIn Profile", href=c.get("linkedin_url", ""), is_external=True, size="2"),
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
                rx.separator(),
                rx.text("Update Status", size="2", weight="bold"),
                rx.select(
                    CONTACT_STATUSES,
                    value=c.get("status", ""),
                    on_change=lambda val: ContactsState.update_status(c["id"], val),
                ),
                rx.hstack(
                    rx.button(
                        "Delete",
                        color_scheme="red",
                        variant="soft",
                        on_click=ContactsState.delete_contact(c["id"]),
                    ),
                    spacing="2",
                ),
                spacing="3",
                width="100%",
            ),
            width="350px",
            min_width="350px",
        ),
        rx.fragment(),
    )


def contacts_page() -> rx.Component:
    """Contacts page."""
    content = rx.vstack(
        # Toolbar
        rx.hstack(
            rx.input(
                placeholder="Search contacts...",
                on_change=ContactsState.search_contacts,
                width="300px",
            ),
            rx.select(
                [""] + CONTACT_STATUSES,
                placeholder="Filter by status",
                on_change=ContactsState.filter_by_status,
            ),
            rx.spacer(),
            add_contact_modal(),
            width="100%",
        ),
        # Table + detail panel
        rx.hstack(
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Name"),
                            rx.table.column_header_cell("Title"),
                            rx.table.column_header_cell("Company"),
                            rx.table.column_header_cell("Status"),
                            rx.table.column_header_cell("Source"),
                            rx.table.column_header_cell(""),
                        ),
                    ),
                    rx.table.body(
                        rx.foreach(ContactsState.contacts, contact_row),
                    ),
                    width="100%",
                ),
                flex="1",
                overflow_x="auto",
            ),
            contact_detail_panel(),
            spacing="4",
            width="100%",
            align="start",
        ),
        spacing="4",
        width="100%",
        on_mount=ContactsState.load_contacts,
    )
    return page_template(content, title="Contacts")
