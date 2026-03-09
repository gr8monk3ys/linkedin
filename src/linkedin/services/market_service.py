"""Market intelligence service — salary estimates, trends, skill demand."""

from datetime import datetime

from linkedin.ai.client import generate_with_ai
from linkedin.data.repository import ProfileRepo
from linkedin.services._helpers import get_ai_text_or_error
from linkedin.types import Result


class MarketService:
    def __init__(self, profile_repo: ProfileRepo):
        self.profiles = profile_repo
        self._postings: list[dict] = []
        self._insights: list[dict] = []

    def analyze_market(self, role: str = "", industry: str = "") -> Result:
        """Get AI market analysis for a role/industry."""
        profile = self.profiles.get()
        target_role = role or profile.get("target_role", "")
        target_industry = industry or profile.get("industries", "")

        if not target_role:
            return Result("Set a target role in your profile or provide one.")

        prompt = f"""Provide a concise job market analysis for the following:

ROLE: {target_role}
INDUSTRY: {target_industry or 'General'}

Include:
1. Current demand level (high/medium/low) and trend
2. Typical salary range (US market)
3. Top 5 most-requested skills for this role
4. Key industry trends affecting this role
5. Hiring outlook for the next 6 months
6. Tips for standing out as a candidate

Keep it actionable and under 400 words."""

        result = generate_with_ai(prompt, max_tokens=600)
        content, error = get_ai_text_or_error(result)
        return Result(error, content)

    def estimate_salary(self, role: str = "", location: str = "") -> Result:
        """Get AI salary estimate."""
        profile = self.profiles.get()
        target_role = role or profile.get("target_role", "")
        loc = location or profile.get("location", "US")

        if not target_role:
            return Result("Set a target role in your profile or provide one.")

        prompt = f"""Estimate the salary range for:

ROLE: {target_role}
LOCATION: {loc}
EXPERIENCE LEVEL: Mid-Senior

Provide:
1. Base salary range (low - median - high)
2. Total compensation range (including bonus/equity)
3. Factors that increase pay (certifications, skills, company size)
4. How remote vs on-site affects compensation
5. Negotiation tips for this role

Be specific with numbers. Keep under 300 words."""

        result = generate_with_ai(prompt, max_tokens=500)
        content, error = get_ai_text_or_error(result)
        return Result(error, content)

    def analyze_trends(self, industry: str = "") -> Result:
        """Get AI hiring trend analysis."""
        profile = self.profiles.get()
        target_industry = industry or profile.get("industries", "")

        if not target_industry:
            return Result("Set target industries in your profile or provide one.")

        prompt = f"""Analyze current hiring trends for:

INDUSTRY: {target_industry}

Include:
1. Which roles are in highest demand
2. Emerging roles and skills
3. Industries/sectors with most growth
4. Impact of AI/automation on hiring
5. Remote work trends in this industry
6. Best job search strategies for this industry

Keep it actionable and under 350 words."""

        result = generate_with_ai(prompt, max_tokens=500)
        content, error = get_ai_text_or_error(result)
        return Result(error, content)

    def add_posting(self, posting: dict) -> dict:
        """Add a manually tracked job posting."""
        posting["id"] = len(self._postings) + 1
        posting["created_at"] = datetime.now().isoformat()
        self._postings.append(posting)
        return posting

    def list_postings(self) -> list[dict]:
        """List all tracked job postings."""
        return self._postings
