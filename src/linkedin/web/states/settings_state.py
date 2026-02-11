"""Settings page state."""

import reflex as rx

from linkedin.data.factory import create_repos
from linkedin.services.profile_service import ProfileService


class SettingsState(rx.State):
    """State for the settings page."""

    profile_name: str = ""
    profile_headline: str = ""
    profile_target_role: str = ""
    profile_skills: str = ""
    profile_experience: str = ""
    profile_unique_value: str = ""
    profile_industries: str = ""
    profile_location: str = ""
    save_message: str = ""

    @rx.event
    def load_profile(self):
        """Load current profile data."""
        _, _, profile_repo, *_ = create_repos()
        svc = ProfileService(profile_repo)
        profile = svc.get_profile()
        if profile:
            self.profile_name = profile.get("name", "")
            self.profile_headline = profile.get("headline", "")
            self.profile_target_role = profile.get("target_role", "")
            self.profile_skills = profile.get("skills", "")
            self.profile_experience = profile.get("experience_summary", "")
            self.profile_unique_value = profile.get("unique_value", "")
            self.profile_industries = profile.get("industries", "")
            self.profile_location = profile.get("location", "")

    @rx.event
    def save_profile(self, form_data: dict):
        """Save profile data."""
        _, _, profile_repo, *_ = create_repos()
        svc = ProfileService(profile_repo)
        svc.save_profile(form_data)
        self.save_message = "Profile saved successfully!"
        self.load_profile()

    @rx.event
    def clear_message(self):
        self.save_message = ""
