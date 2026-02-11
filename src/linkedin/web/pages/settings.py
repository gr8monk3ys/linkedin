"""Settings page — profile form, configuration."""

import reflex as rx

from linkedin.web.layout import page_template
from linkedin.web.states.settings_state import SettingsState


def settings_page() -> rx.Component:
    """Settings page with profile form."""
    content = rx.vstack(
        rx.card(
            rx.vstack(
                rx.heading("Your Profile", size="4"),
                rx.text("This information is used for AI-generated drafts and suggestions.", size="2", color=rx.color("gray", 11)),
                rx.form(
                    rx.vstack(
                        rx.hstack(
                            rx.vstack(
                                rx.text("Name", size="2", weight="bold"),
                                rx.input(name="name", default_value=SettingsState.profile_name, placeholder="Your name"),
                                flex="1",
                            ),
                            rx.vstack(
                                rx.text("Location", size="2", weight="bold"),
                                rx.input(name="location", default_value=SettingsState.profile_location, placeholder="City, State"),
                                flex="1",
                            ),
                            spacing="4",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Headline", size="2", weight="bold"),
                            rx.input(name="headline", default_value=SettingsState.profile_headline, placeholder="Your current headline"),
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Target Role", size="2", weight="bold"),
                            rx.input(name="target_role", default_value=SettingsState.profile_target_role, placeholder="Role you're targeting"),
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Key Skills", size="2", weight="bold"),
                            rx.text_area(name="skills", default_value=SettingsState.profile_skills, placeholder="Your key skills (comma separated)"),
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Experience Summary", size="2", weight="bold"),
                            rx.text_area(name="experience_summary", default_value=SettingsState.profile_experience, placeholder="Brief summary of your experience"),
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Unique Value Proposition", size="2", weight="bold"),
                            rx.text_area(name="unique_value", default_value=SettingsState.profile_unique_value, placeholder="What makes you unique"),
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Target Industries", size="2", weight="bold"),
                            rx.input(name="industries", default_value=SettingsState.profile_industries, placeholder="Industries (comma separated)"),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.button("Save Profile", type="submit"),
                            rx.cond(
                                SettingsState.save_message != "",
                                rx.text(SettingsState.save_message, color=rx.color("green", 11), size="2"),
                                rx.fragment(),
                            ),
                            spacing="3",
                            align="center",
                        ),
                        spacing="4",
                        width="100%",
                    ),
                    on_submit=SettingsState.save_profile,
                ),
                spacing="4",
                width="100%",
            ),
            max_width="700px",
        ),
        spacing="4",
        width="100%",
        on_mount=SettingsState.load_profile,
    )
    return page_template(content, title="Settings")
