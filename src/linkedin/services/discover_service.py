"""AI-powered networking discovery service."""

from linkedin.ai.client import generate_with_ai
from linkedin.data.repository import CompanyRepo, ContactRepo, ProfileRepo
from linkedin.services._helpers import get_ai_text_or_error
from linkedin.types import ProfileDict, Result


class DiscoverService:
    def __init__(self, profile_repo: ProfileRepo, company_repo: CompanyRepo, contact_repo: ContactRepo):
        self.profiles = profile_repo
        self.companies = company_repo
        self.contacts = contact_repo

    def discover_contacts(self, company: str | None = None, role: str | None = None) -> Result:
        """Returns Result(error, suggestions)."""
        profile = self.profiles.get()
        if not profile:
            return Result("Set up your profile first: linkedin profile setup")

        if not company and not role:
            return Result("Specify --company or --role to get suggestions")

        companies_list = self.companies.list_all()
        all_contacts = self.contacts.list_all()
        existing_titles = list(set([c["title"] for c in all_contacts]))[:10]

        if company:
            prompt = self._contact_by_company_prompt(profile, company, companies_list, existing_titles)
        else:
            prompt = self._contact_by_role_prompt(profile, role, companies_list)

        suggestions = generate_with_ai(prompt, max_tokens=800)
        suggestion_text, error = get_ai_text_or_error(suggestions)
        return Result(error, suggestion_text)

    def discover_companies(self) -> Result:
        profile = self.profiles.get()
        if not profile:
            return Result("Set up your profile first: linkedin profile setup")

        companies_list = self.companies.list_all()
        existing_companies = [c["name"] for c in companies_list]

        prompt = self._company_discovery_prompt(profile, existing_companies)
        suggestions = generate_with_ai(prompt, max_tokens=1000)
        suggestion_text, error = get_ai_text_or_error(suggestions)
        return Result(error, suggestion_text)

    def _contact_by_company_prompt(self, profile: ProfileDict, company: str, companies_list: list, existing_titles: list) -> str:
        tracked_company = next((c for c in companies_list if company.lower() in c["name"].lower()), None)
        company_context = ""
        if tracked_company:
            company_context = f"""
COMPANY WE'RE TRACKING:
- Name: {tracked_company['name']}
- Industry: {tracked_company.get('industry', 'Unknown')}
- Size: {tracked_company.get('size', 'Unknown')}
- Why targeting: {tracked_company.get('why_target', 'General interest')}
- Roles to find: {', '.join(tracked_company.get('key_people_to_find', [])) or 'Not specified'}
"""

        return f"""I'm job hunting and want to network at {company}. Suggest specific types of people I should find and connect with on LinkedIn.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Skills: {profile.get('skills', 'N/A')}
- Industries: {profile.get('industries', 'N/A')}
{company_context}
EXISTING CONTACTS I'VE FOUND (for reference):
{', '.join(existing_titles) if existing_titles else 'None yet'}

Provide a prioritized list of:
1. **Job titles to search for** (specific LinkedIn search terms)
2. **Why each is valuable** (what they can offer: referral, advice, intel)
3. **How to find them** (LinkedIn search tips, filters to use)
4. **What to look for in profiles** (signals they'd be receptive)
5. **Connection angle** (what to mention when reaching out)

Format as a clear, actionable list. Focus on 4-6 specific titles/roles."""

    def _contact_by_role_prompt(self, profile: ProfileDict, role: str, companies_list: list) -> str:
        return f"""I'm looking to connect with people in {role} positions for my job search. Suggest how to find and approach them.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Skills: {profile.get('skills', 'N/A')}
- Industries: {profile.get('industries', 'N/A')}

COMPANIES I'M TRACKING:
{', '.join([c['name'] for c in companies_list]) if companies_list else 'None yet'}

Provide:
1. **LinkedIn search strategy** - exact search terms and filters
2. **Profile signals** - what to look for that suggests they'd be receptive
3. **Connection angles** - different ways to approach based on their background
4. **Companies where this role has influence** - types of orgs where this role matters
5. **Related titles** - similar roles I should also search for
6. **Red flags** - profiles to avoid or approaches that won't work

Be specific and actionable."""

    def _company_discovery_prompt(self, profile: ProfileDict, existing_companies: list) -> str:
        return f"""Suggest companies I should target for networking based on my profile.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Skills: {profile.get('skills', 'N/A')}
- Experience: {profile.get('experience_summary', 'N/A')}
- Target Industries: {profile.get('industries', 'N/A')}
- Location: {profile.get('location', 'N/A')}

COMPANIES I'M ALREADY TRACKING:
{', '.join(existing_companies) if existing_companies else 'None yet'}

Suggest 8-10 companies I should consider, including:

1. **Company Name** and brief description
2. **Why it's a good fit** for my background
3. **What roles they likely have** matching my target
4. **How to research them** (what to look for)
5. **Networking angle** (why someone there would talk to me)

Include a mix of:
- Well-known companies in my target space
- Growing startups that might be hiring
- Companies using technologies I know
- Companies where my background would be valued

Don't just suggest FAANG - be specific to my skills and target role."""
