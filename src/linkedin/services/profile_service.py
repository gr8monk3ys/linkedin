"""Profile management service."""

from datetime import datetime

from linkedin.data.repository import ProfileRepo
from linkedin.types import ProfileDict


class ProfileService:
    def __init__(self, repo: ProfileRepo):
        self.repo = repo

    def get_profile(self) -> ProfileDict:
        return self.repo.get()

    def save_profile(self, data: dict) -> ProfileDict:
        data["updated_at"] = datetime.now().isoformat()
        self.repo.save(data)
        return data
