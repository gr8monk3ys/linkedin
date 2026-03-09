"""AI profile optimizer service — headline, about, skills, experience improvements."""

from linkedin.data.repository import ProfileRepo
from linkedin.services._helpers import generate_ai_text
from linkedin.types import Result


class OptimizerService:
    def __init__(self, profile_repo: ProfileRepo):
        self.profiles = profile_repo

    def optimize_headline(self) -> Result:
        """Generate headline variants."""
        profile = self.profiles.get()
        if not profile or not profile.get("name"):
            return Result("Set up your profile first.")

        prompt = f"""Generate 5 LinkedIn headline variants for this professional:

NAME: {profile.get('name', '')}
CURRENT HEADLINE: {profile.get('headline', 'Not set')}
TARGET ROLE: {profile.get('target_role', 'Not specified')}
SKILLS: {profile.get('skills', 'Not specified')}
EXPERIENCE: {profile.get('experience_summary', 'Not specified')}

Requirements:
1. Each headline should be under 120 characters
2. Include relevant keywords for recruiter search
3. Vary the style: one value-focused, one achievement-focused, one skill-focused, one industry-focused, one creative
4. Number them 1-5

Format: Number. Headline text
Just the headlines, no explanations."""

        content, error = generate_ai_text(prompt, max_tokens=300)
        return Result(error, content)

    def optimize_about(self) -> Result:
        """Generate an optimized About section."""
        profile = self.profiles.get()
        if not profile or not profile.get("name"):
            return Result("Set up your profile first.")

        prompt = f"""Write an optimized LinkedIn About section for this professional:

NAME: {profile.get('name', '')}
HEADLINE: {profile.get('headline', 'Not set')}
TARGET ROLE: {profile.get('target_role', 'Not specified')}
SKILLS: {profile.get('skills', 'Not specified')}
EXPERIENCE: {profile.get('experience_summary', 'Not specified')}
UNIQUE VALUE: {profile.get('unique_value', 'Not specified')}
INDUSTRIES: {profile.get('industries', 'Not specified')}

Requirements:
1. Start with a hook that captures attention
2. Include key achievements and metrics where possible
3. Mention target role and what you bring to it
4. Include relevant keywords naturally
5. End with a call to action
6. Under 2000 characters
7. Use first person

Just write the About section, no explanations."""

        content, error = generate_ai_text(prompt, max_tokens=600)
        return Result(error, content)

    def optimize_skills(self) -> Result:
        """Analyze skills and suggest improvements."""
        profile = self.profiles.get()
        if not profile or not profile.get("name"):
            return Result("Set up your profile first.")

        prompt = f"""Analyze and optimize the LinkedIn skills for this professional:

CURRENT SKILLS: {profile.get('skills', 'Not specified')}
TARGET ROLE: {profile.get('target_role', 'Not specified')}
EXPERIENCE: {profile.get('experience_summary', 'Not specified')}
INDUSTRIES: {profile.get('industries', 'Not specified')}

Provide:
1. KEEP: Skills that are well-aligned with target role
2. ADD: Skills missing that are critical for the target role (list at least 5)
3. REORDER: Suggested priority order for maximum recruiter visibility
4. GAP ANALYSIS: Skills gap between current profile and target role requirements
5. TRENDING: Skills gaining demand in this field

Be specific and actionable. Under 400 words."""

        content, error = generate_ai_text(prompt, max_tokens=500)
        return Result(error, content)

    def optimize_full(self) -> Result:
        """Full profile optimization review."""
        profile = self.profiles.get()
        if not profile or not profile.get("name"):
            return Result("Set up your profile first.")

        prompt = f"""Provide a complete LinkedIn profile optimization review:

NAME: {profile.get('name', '')}
HEADLINE: {profile.get('headline', 'Not set')}
TARGET ROLE: {profile.get('target_role', 'Not specified')}
SKILLS: {profile.get('skills', 'Not specified')}
EXPERIENCE: {profile.get('experience_summary', 'Not specified')}
UNIQUE VALUE: {profile.get('unique_value', 'Not specified')}
LOCATION: {profile.get('location', 'Not specified')}

Score each section (1-10) and provide specific improvement suggestions:
1. HEADLINE (current score, suggested improvement)
2. ABOUT SECTION (recommendations)
3. SKILLS (what to add/remove)
4. EXPERIENCE BULLETS (how to improve)
5. KEYWORDS (missing keywords for recruiter search)
6. OVERALL PROFILE STRENGTH (score out of 100)

Be specific and actionable. Under 500 words."""

        content, error = generate_ai_text(prompt, max_tokens=700)
        return Result(error, content)
