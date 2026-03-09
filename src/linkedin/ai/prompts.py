"""Shared AI prompt templates."""

from linkedin.types import ProfileDict


def connection_request_prompt(profile: ProfileDict, person: dict) -> str:
    """Shared connection request prompt used by draft_service and automation_service."""
    title = person.get("title") or person.get("headline", "N/A")
    company = person.get("company", "")
    context = person.get("notes") or person.get("location") or "Interested in their work"

    return f"""Write a LinkedIn connection request message (max 300 characters) from me to this person.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Current Role: {profile.get('headline', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Key Skills: {profile.get('skills', 'N/A')}
- What Makes Me Unique: {profile.get('unique_value', 'N/A')}

THEIR PROFILE:
- Name: {person.get('name', 'Unknown')}
- Title: {title}
- Company: {company}
- Why I want to connect: {context}

Write a warm, personalized connection request that:
1. Shows I've looked at their profile
2. Mentions something specific about them or their company
3. Briefly explains why connecting would be mutually valuable
4. Is under 300 characters (LinkedIn limit)
5. Sounds natural, not salesy

Just write the message, no explanations."""
