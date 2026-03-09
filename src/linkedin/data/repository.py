"""Abstract repository interfaces for data access."""

from abc import ABC, abstractmethod

from linkedin.types import (
    ApplicationDict,
    CompanyDict,
    ContactDict,
    ContentPostDict,
    ConversationDict,
    DraftDict,
    InterviewPrepDict,
    ProfileDict,
    ResearchDict,
    TemplateDict,
)


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


class TemplateRepo(ABC):
    @abstractmethod
    def list_all(self) -> list[TemplateDict]:
        ...

    @abstractmethod
    def get(self, template_id: int) -> TemplateDict | None:
        ...

    @abstractmethod
    def add(self, template: TemplateDict) -> TemplateDict:
        ...

    @abstractmethod
    def update(self, template: TemplateDict) -> None:
        ...

    @abstractmethod
    def next_id(self) -> int:
        ...


class ApplicationRepo(ABC):
    @abstractmethod
    def list_all(self) -> list[ApplicationDict]: ...

    @abstractmethod
    def get(self, application_id: int) -> ApplicationDict | None: ...

    @abstractmethod
    def add(self, application: ApplicationDict) -> ApplicationDict: ...

    @abstractmethod
    def update(self, application: ApplicationDict) -> None: ...

    @abstractmethod
    def delete(self, application_id: int) -> bool: ...

    @abstractmethod
    def next_id(self) -> int: ...


class ConversationRepo(ABC):
    @abstractmethod
    def get_by_contact(self, contact_id: int) -> ConversationDict | None: ...

    @abstractmethod
    def upsert(self, conversation: ConversationDict) -> None: ...

    @abstractmethod
    def list_all(self) -> list[ConversationDict]: ...


class CalendarRepo(ABC):
    @abstractmethod
    def list_all(self) -> list[ContentPostDict]: ...

    @abstractmethod
    def get(self, post_id: int) -> ContentPostDict | None: ...

    @abstractmethod
    def add(self, post: ContentPostDict) -> ContentPostDict: ...

    @abstractmethod
    def update(self, post: ContentPostDict) -> None: ...

    @abstractmethod
    def delete(self, post_id: int) -> bool: ...

    @abstractmethod
    def next_id(self) -> int: ...


class InterviewPrepRepo(ABC):
    @abstractmethod
    def get_by_application(self, application_id: int) -> InterviewPrepDict | None: ...

    @abstractmethod
    def upsert(self, prep: InterviewPrepDict) -> None: ...
