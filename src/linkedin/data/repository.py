"""Abstract repository interfaces for data access."""

from abc import ABC, abstractmethod

from linkedin.types import CompanyDict, ContactDict, DraftDict, ProfileDict, ResearchDict


class ContactRepo(ABC):
    @abstractmethod
    def list_all(self) -> list[ContactDict]:
        ...

    @abstractmethod
    def get(self, contact_id: int) -> ContactDict | None:
        ...

    @abstractmethod
    def add(self, contact: ContactDict) -> ContactDict:
        ...

    @abstractmethod
    def update(self, contact: ContactDict) -> None:
        ...

    @abstractmethod
    def delete(self, contact_id: int) -> bool:
        ...

    @abstractmethod
    def next_id(self) -> int:
        ...

    @abstractmethod
    def save_all(self, contacts: list[ContactDict]) -> None:
        ...


class CompanyRepo(ABC):
    @abstractmethod
    def list_all(self) -> list[CompanyDict]:
        ...

    @abstractmethod
    def get(self, company_id: int) -> CompanyDict | None:
        ...

    @abstractmethod
    def add(self, company: CompanyDict) -> CompanyDict:
        ...

    @abstractmethod
    def update(self, company: CompanyDict) -> None:
        ...

    @abstractmethod
    def delete(self, company_id: int) -> bool:
        ...

    @abstractmethod
    def next_id(self) -> int:
        ...


class ProfileRepo(ABC):
    @abstractmethod
    def get(self) -> ProfileDict:
        ...

    @abstractmethod
    def save(self, profile: ProfileDict) -> None:
        ...


class DraftRepo(ABC):
    @abstractmethod
    def list_all(self) -> list[DraftDict]:
        ...

    @abstractmethod
    def get(self, draft_id: int) -> DraftDict | None:
        ...

    @abstractmethod
    def add(self, draft: DraftDict) -> DraftDict:
        ...

    @abstractmethod
    def next_id(self) -> int:
        ...


class ResearchRepo(ABC):
    @abstractmethod
    def get(self) -> ResearchDict:
        ...

    @abstractmethod
    def save(self, data: ResearchDict) -> None:
        ...
