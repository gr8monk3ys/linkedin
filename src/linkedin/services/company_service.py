"""Company management service."""

from datetime import datetime

from linkedin.data.repository import CompanyRepo, ContactRepo
from linkedin.types import CompanyDict, Result


class CompanyService:
    def __init__(self, company_repo: CompanyRepo, contact_repo: ContactRepo):
        self.companies = company_repo
        self.contacts = contact_repo

    def list_companies(self, priority: str = "all", industry: str | None = None) -> list[dict]:
        companies = self.companies.list_all()
        if not companies:
            return []

        filtered = companies
        if priority != "all":
            filtered = [c for c in filtered if c.get("priority") == priority]
        if industry:
            filtered = [c for c in filtered if industry.lower() in c.get("industry", "").lower()]

        contact_counts = self._get_contact_counts()

        result = []
        for c in filtered:
            entry = dict(c)
            entry["contact_count"] = contact_counts.get(c["id"], 0)
            result.append(entry)

        return result

    def get_company(self, company_id: int) -> Result:
        company = self.companies.get(company_id)
        if not company:
            return Result("Company not found")

        contacts = [c for c in self.contacts.list_all() if c.get("company_id") == company_id]
        result = dict(company)
        result["contacts"] = contacts
        return Result(None, result)

    def add_company(
        self,
        name: str,
        industry: str,
        size: str = "51-200",
        linkedin: str = "",
        website: str = "",
        why: str = "",
        priority: str = "medium",
    ) -> CompanyDict:
        company: CompanyDict = {
            "id": self.companies.next_id(),
            "name": name,
            "industry": industry,
            "size": size,
            "linkedin_url": linkedin,
            "website": website,
            "why_target": why,
            "key_people_to_find": [],
            "priority": priority,
            "notes": "",
            "created_at": datetime.now().isoformat(),
        }
        return self.companies.add(company)

    def update_company(
        self,
        company_id: int,
        priority: str | None = None,
        notes: str | None = None,
        add_role: str | None = None,
        linkedin: str | None = None,
        website: str | None = None,
    ) -> Result:
        company = self.companies.get(company_id)
        if not company:
            return Result("Company not found")

        if priority:
            company["priority"] = priority
        if notes:
            company["notes"] = (company.get("notes", "") + f"\n[{datetime.now().strftime('%Y-%m-%d')}] {notes}").strip()
        if add_role:
            if "key_people_to_find" not in company:
                company["key_people_to_find"] = []
            company["key_people_to_find"].append(add_role)
        if linkedin:
            company["linkedin_url"] = linkedin
        if website:
            company["website"] = website

        self.companies.update(company)
        return Result(None, company)

    def delete_company(self, company_id: int) -> Result:
        company = self.companies.get(company_id)
        if not company:
            return Result("Company not found")
        self.companies.delete(company_id)
        return Result(None, company)

    def get_company_contacts(self, company_id: int) -> Result:
        company = self.companies.get(company_id)
        if not company:
            return Result("Company not found")
        contacts = [c for c in self.contacts.list_all() if c.get("company_id") == company_id]
        return Result(None, {"company": company, "contacts": contacts})

    def _get_contact_counts(self) -> dict[int, int]:
        contacts = self.contacts.list_all()
        counts: dict[int, int] = {}
        for contact in contacts:
            cid = contact.get("company_id")
            if cid:
                counts[cid] = counts.get(cid, 0) + 1
        return counts
