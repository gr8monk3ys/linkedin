"""Profile management service."""

from datetime import datetime

from linkedin.data.json_store import JsonProfileRepo
from linkedin.types import ProfileDict


class ProfileService:
    def __init__(self, repo: JsonProfileRepo):
        self.repo = repo

    def get_profile(self) -> ProfileDict:
        return self.repo.get()

    def save_profile(self, data: dict) -> ProfileDict:
        data["updated_at"] = datetime.now().isoformat()
        self.repo.save(data)
        return data
