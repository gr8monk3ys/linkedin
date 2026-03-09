"""Content research and post generation service."""

from datetime import datetime

from linkedin.data.repository import DraftRepo, ProfileRepo, ResearchRepo
from linkedin.services._helpers import generate_ai_text
from linkedin.types import Result

ENGAGEMENT_CONTENT = """
# LinkedIn Engagement Strategies

## Post Formats That Work

### 1. Personal Stories (Highest Engagement)
- Share failures and lessons learned
- Career transition stories
- "What I learned from X years doing Y"
- Vulnerability + insight = engagement

### 2. Contrarian Takes
- "Unpopular opinion: [hot take on industry topic]"
- Challenge conventional wisdom
- Back up with experience/data

### 3. Listicles
- "5 things I wish I knew about X"
- "10 tools every [role] should use"
- Easy to read and share

### 4. Behind-the-Scenes
- Day in the life
- Project breakdowns
- Company culture insights

### 5. Carousels/Documents
- Step-by-step guides
- Visual frameworks
- Cheat sheets

## Optimal Posting

| Day | Best Time | Why |
|-----|-----------|-----|
| Tuesday | 10am-12pm | Peak professional browsing |
| Wednesday | 10am-12pm | Midweek engagement |
| Thursday | 10am, 2pm | Pre-weekend planning |

**Avoid**: Weekends, late evenings, early mornings

## Formatting Tips

- **First line is everything** (hook them!)
- Use line breaks liberally
- Emojis: 1-3 max, use strategically
- Hashtags: 3-5, mix popular + niche
- End with a question to drive comments

## Engagement Tactics

1. Reply to EVERY comment within 1 hour
2. Comment on others' posts before posting yours
3. Tag relevant people (sparingly)
4. Post consistently (2-3x per week minimum)
"""

STYLE_INSTRUCTIONS = {
    "story": "Write as a personal story with a lesson. Start with a hook, build tension, reveal insight.",
    "listicle": "Write as a numbered list (5-7 items). Each item should be actionable and valuable.",
    "contrarian": "Take an unpopular stance on the topic. Be bold but back it up with reasoning.",
    "how-to": "Write as a practical guide. Step-by-step, actionable, clear.",
}


class ResearchService:
    def __init__(self, profile_repo: ProfileRepo, research_repo: ResearchRepo, draft_repo: DraftRepo):
        self.profiles = profile_repo
        self.research = research_repo
        self.drafts = draft_repo

    def get_engagement_strategies(self) -> str:
        return ENGAGEMENT_CONTENT

    def generate_ideas(self, topic: str | None = None) -> Result:
        """Returns Result(error, (focus_topic, ideas_text))."""
        profile = self.profiles.get()

        if topic:
            focus = topic
        elif profile:
            focus = f"{profile.get('target_role', '')} in {profile.get('industries', 'tech')}"
        else:
            focus = "professional growth"

        prompt = f"""Generate 10 LinkedIn post ideas for someone looking for a job in: {focus}

Their background: {profile.get('experience_summary', 'Tech professional') if profile else 'Tech professional'}
Their skills: {profile.get('skills', 'Various technical skills') if profile else 'Various technical skills'}

For each idea, provide:
1. A catchy hook (first line of the post)
2. What the post is about (1 sentence)
3. Why it would get engagement

Focus on posts that:
- Showcase expertise without being salesy
- Tell stories or share insights
- Could go viral or get lots of engagement
- Position them as a thought leader

Format as a numbered list."""

        ideas_text, error = generate_ai_text(prompt, max_tokens=800)
        return Result(error, (focus, ideas_text) if ideas_text is not None else None)

    def save_ideas(self, topic: str, ideas: str) -> None:
        research_data = self.research.get()
        if "ideas" not in research_data:
            research_data["ideas"] = []
        research_data["ideas"].append({
            "topic": topic,
            "ideas": ideas,
            "created_at": datetime.now().isoformat(),
        })
        self.research.save(research_data)

    def generate_post_draft(self, topic: str, style: str = "story") -> Result:
        profile = self.profiles.get()
        instruction = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["story"])

        prompt = f"""Write a LinkedIn post about: {topic}

Style: {instruction}

Author background:
- Role: {profile.get('headline', 'Professional') if profile else 'Professional'}
- Experience: {profile.get('experience_summary', 'Years of experience') if profile else 'Years of experience'}
- Target audience: People in {profile.get('industries', 'tech') if profile else 'tech'}

Requirements:
- Start with a compelling hook (first 2 lines are crucial)
- Use short paragraphs and line breaks
- Include 1-2 relevant emojis (not too many)
- End with a question or call to action
- Keep it 150-250 words
- Sound authentic, not like ChatGPT
- Add 3-5 relevant hashtags at the end

Write the post now:"""

        draft_text, error = generate_ai_text(prompt, max_tokens=500)
        return Result(error, draft_text)

    def save_post_draft(self, topic: str, style: str, content: str) -> None:
        draft = {
            "id": self.drafts.next_id(),
            "contact_id": None,
            "type": f"post_{style}",
            "content": content,
            "topic": topic,
            "created_at": datetime.now().isoformat(),
        }
        self.drafts.add(draft)

    def generate_hashtags(self, topic: str) -> Result:
        prompt = f"""Suggest the best LinkedIn hashtags for a post about: {topic}

Provide:
1. 5 high-volume hashtags (popular, broad reach)
2. 5 niche hashtags (smaller but engaged audience)
3. 3 trending hashtags (if relevant)

For each, briefly explain why it's good.

Format as a clean list."""

        hashtag_text, error = generate_ai_text(prompt, max_tokens=300)
        return Result(error, hashtag_text)
