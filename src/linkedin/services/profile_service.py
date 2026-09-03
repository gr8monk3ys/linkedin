"""Profile management service."""

from datetime import datetime

from linkedin.data.json_store import JsonProfileRepo
from linkedin.types import ProfileDict


class ProfileService:
    def __init__(self, repo: JsonProfileRepo, copy_loader=None):
        self.repo = repo
        #: Returns {"headline", "about"} from the resume repo, or {}. The doc there
        #: is the single source; the copy saved here is what the AI prompts fall
        #: back to when the repo is not on this machine.
        self.copy_loader = copy_loader

    def get_profile(self) -> ProfileDict:
        profile = self.repo.get()
        copy = self.copy_loader() if self.copy_loader else {}
        if profile and copy:
            profile = dict(profile)
            for field in ("headline", "about"):
                if copy.get(field):
                    profile[field] = copy[field]
            profile["copy_source"] = "resume repo"
        return profile

    def save_profile(self, data: dict) -> ProfileDict:
        data["updated_at"] = datetime.now().isoformat()
        self.repo.save(data)
        return data
