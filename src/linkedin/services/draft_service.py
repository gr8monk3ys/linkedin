"""Draft generation and management service."""

from datetime import datetime

from linkedin.ai.client import AIResult, ai_call
from linkedin.data.json_store import JsonContactRepo, JsonDraftRepo, JsonProfileRepo
from linkedin.services.planner import draft_spec_for
from linkedin.types import DraftDict, ProfileDict

FOLLOW_UP_GUIDANCE = {
    1: "This is a gentle first follow-up. Be casual and add value if possible.",
    2: "This is a second follow-up. Be shorter and offer an easy out.",
    3: "This is a final follow-up. Be very brief, suggest reconnecting in the future, and close the loop gracefully.",
}


class DraftService:
    def __init__(self, draft_repo: JsonDraftRepo, contact_repo: JsonContactRepo, profile_repo: JsonProfileRepo):
        self.drafts = draft_repo
        self.contacts = contact_repo
        self.profiles = profile_repo

    def delete_draft(self, draft_id: int) -> bool:
        """Remove a saved draft. Returns False if it was not there."""
        return self.drafts.delete(draft_id)

    def list_drafts(self) -> list[dict]:
        drafts = self.drafts.list_all()
        contacts = self.contacts.list_all()
        result = []
        for d in drafts:
            entry = dict(d)
            contact = next((c for c in contacts if c["id"] == d.get("contact_id")), None)
            entry["contact_name"] = contact.get("name", "Unknown") if contact else "Unknown"
            result.append(entry)
        return result

    def get_draft(self, draft_id: int) -> DraftDict | None:
        return self.drafts.get(draft_id)

    def generate_connection(self, contact_id: int) -> AIResult:
        """An `AIResult`: `.error` set when nothing could be drafted, `.was_fallback`
        when the text is an offline template rather than the model's."""
        profile = self.profiles.get()
        if not profile:
            return AIResult(error="Set up your profile first: linkedin profile setup")

        contact = self.contacts.get(contact_id)
        if not contact:
            return AIResult(error=f"Contact #{contact_id} not found")

        prompt = self._connection_prompt(profile, contact)
        return self._generate_with_fallback(
            prompt=prompt,
            max_tokens=200,
            fallback_text=self._fallback_connection(profile, contact),
        )

    def generate_message(self, contact_id: int, context: str = "") -> AIResult:
        profile = self.profiles.get()
        contact = self.contacts.get(contact_id)
        if not contact:
            return AIResult(error=f"Contact #{contact_id} not found")

        prompt = self._message_prompt(profile, contact, context)
        return self._generate_with_fallback(
            prompt=prompt,
            max_tokens=400,
            fallback_text=self._fallback_message(profile, contact, context),
        )

    def generate_intro_request(self, contact_id: int, target_id: int) -> AIResult:
        profile = self.profiles.get()
        if not profile:
            return AIResult(error="Set up your profile first: linkedin profile setup")

        contact = self.contacts.get(contact_id)
        if not contact:
            return AIResult(error=f"Contact #{contact_id} not found")

        target = self.contacts.get(target_id)
        if not target:
            return AIResult(error=f"Target contact #{target_id} not found")

        prompt = self._intro_request_prompt(profile, contact, target)
        return self._generate_with_fallback(
            prompt=prompt,
            max_tokens=400,
            fallback_text=self._fallback_intro_request(profile, contact, target),
        )

    def generate_thank_you(self, contact_id: int, context: str = "") -> AIResult:
        profile = self.profiles.get()
        if not profile:
            return AIResult(error="Set up your profile first: linkedin profile setup")

        contact = self.contacts.get(contact_id)
        if not contact:
            return AIResult(error=f"Contact #{contact_id} not found")

        prompt = self._thank_you_prompt(profile, contact, context)
        return self._generate_with_fallback(
            prompt=prompt,
            max_tokens=250,
            fallback_text=self._fallback_thank_you(profile, contact, context),
        )

    def generate_follow_up(self, contact_id: int, attempt: int = 1) -> AIResult:
        profile = self.profiles.get()
        if not profile:
            return AIResult(error="Set up your profile first: linkedin profile setup")

        contact = self.contacts.get(contact_id)
        if not contact:
            return AIResult(error=f"Contact #{contact_id} not found")

        prompt = self._follow_up_prompt(profile, contact, attempt)
        return self._generate_with_fallback(
            prompt=prompt,
            max_tokens=200,
            fallback_text=self._fallback_follow_up(profile, contact, attempt),
        )

    def generate_for_action(self, action: dict) -> tuple[str, AIResult] | None:
        """Draft for a planned action, as the planner's ACTIONS row says to.

        Returns (draft_type, result), or None for an action that has no draft
        (repairing dates, debriefing a call). The mapping lives in the planner
        so that an action with a rule and no draft cannot exist.
        """
        spec = draft_spec_for(action["action"])
        if spec is None:
            return None
        generator = getattr(self, spec["generator"])
        return spec["type"], generator(action["contact_id"], **spec["kwargs"])

    def generate_batch_connections(self, limit: int = 5) -> tuple[str | None, list[tuple[dict, str]]]:
        profile = self.profiles.get()
        if not profile:
            return "Set up your profile first: linkedin profile setup", []

        all_contacts = self.contacts.list_all()
        not_contacted = [c for c in all_contacts if c["status"] == "not_contacted"]
        if not not_contacted:
            return None, []

        results = []
        for contact in not_contacted[:limit]:
            prompt = self._connection_prompt(profile, contact)
            result = self._generate_with_fallback(
                prompt=prompt,
                max_tokens=200,
                fallback_text=self._fallback_connection(profile, contact),
            )
            if result.error and not result:
                return result.error, []
            results.append((contact, result))

        return None, results

    def save_draft(self, contact_id: int | None, draft_type: str, content: str, *, source: str, **extra) -> DraftDict:
        """Persist a draft with its provenance. `source` is `"ai"` or `"template"`;
        a row that lacks it is unknown and is treated like a template."""
        draft: DraftDict = {
            "id": self.drafts.next_id(),
            "contact_id": contact_id,
            "type": draft_type,
            "content": content,
            "source": source,
            "created_at": datetime.now().isoformat(),
        }
        draft.update(extra)
        return self.drafts.add(draft)

    def _generate_with_fallback(self, prompt: str, max_tokens: int, fallback_text: str) -> AIResult:
        """Generate a draft, falling back to an offline template.

        The template cannot use `context` and knows nothing about the
        conversation, so the result says which one it is. Persist `.source`
        with the draft; nothing downstream can tell them apart otherwise.
        """
        return ai_call(prompt, max_tokens=max_tokens, fallback=fallback_text)

    def _first_name(self, contact: dict) -> str:
        return str(contact.get("name", "")).strip().split(" ")[0] or "there"

    def _fallback_connection(self, profile: ProfileDict, contact: dict) -> str:
        first = self._first_name(contact)
        me = profile.get("name", "I")
        role = profile.get("target_role", "new opportunities")
        company = contact.get("company", "your team")
        msg = (
            f"Hi {first} — I’m {me}. I’ve been following the work at {company} and I’d value connecting "
            f"as I explore {role}. Thanks for considering."
        )
        return msg[:300]

    def _fallback_message(self, profile: ProfileDict, contact: dict, context: str) -> str:
        """Offline template. Deliberately ignores `context`.

        `context` is prompt input, not body text. Splicing it in verbatim turned
        a --context of instructions into the message itself — addressed to a
        real person, under the user's real name. A template cannot compose
        instructions into prose, so it does not try; the caller says the context
        was dropped instead.
        """
        first = self._first_name(contact)
        role = profile.get("target_role", "my next role")
        return (
            f"Hi {first}, thanks again for connecting. I’m currently focused on {role} and would appreciate any "
            f"advice on teams or opportunities that might be a fit. If helpful, I can send a concise summary."
        )

    def _fallback_intro_request(self, profile: ProfileDict, contact: dict, target: dict) -> str:
        first = self._first_name(contact)
        target_name = target.get("name", "this person")
        role = profile.get("target_role", "new opportunities")
        return (
            f"Hi {first}, would you be open to introducing me to {target_name}? I’m exploring {role} opportunities "
            f"and think a short conversation could be valuable. If useful, I can share a brief intro blurb to forward."
        )

    def _fallback_thank_you(self, profile: ProfileDict, contact: dict, context: str) -> str:
        """Offline template. Ignores `context` — see `_fallback_message`."""
        first = self._first_name(contact)
        return (
            f"Hi {first}, thank you again for your time. I appreciated your perspective and took away a few "
            f"clear next steps. I’ll keep you posted, and I’m happy to return the favor anytime."
        )

    def _fallback_follow_up(self, profile: ProfileDict, contact: dict, attempt: int) -> str:
        first = self._first_name(contact)
        role = profile.get("target_role", "my search")
        if attempt >= 3:
            return f"Hi {first}, closing the loop for now. If timing improves, I’d still value connecting around {role}."
        if attempt == 2:
            return (
                f"Hi {first}, quick follow-up in case my last note got buried. If there’s a better person to speak with "
                f"about {role}, I’d appreciate a pointer."
            )
        return (
            f"Hi {first}, following up in case this was missed. I’m still very interested in conversations around {role} "
            "and would appreciate any guidance."
        )

    def _connection_prompt(self, profile: ProfileDict, contact: dict) -> str:
        return f"""Write a LinkedIn connection request message (max 300 characters) from me to this person.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Current Role: {profile.get('headline', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Key Skills: {profile.get('skills', 'N/A')}
- What Makes Me Unique: {profile.get('unique_value', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Why I want to connect: {contact.get('notes', 'Interested in their work')}

Write a warm, personalized connection request that:
1. Shows I've looked at their profile
2. Mentions something specific about them or their company
3. Briefly explains why connecting would be mutually valuable
4. Is under 300 characters (LinkedIn limit)
5. Sounds natural, not salesy

Just write the message, no explanations."""

    def _message_prompt(self, profile: ProfileDict, contact: dict, context: str) -> str:
        return f"""Write a LinkedIn message from me to this person we're already connected with.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Experience: {profile.get('experience_summary', 'N/A')}
- Key Skills: {profile.get('skills', 'N/A')}
- Unique Value: {profile.get('unique_value', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Our history: {contact.get('notes', 'Just connected')}
- Current status: {contact['status']}

ADDITIONAL CONTEXT: {context if context else 'None provided'}

Write a professional but warm message that:
1. References our connection or something about them
2. Clearly states what I'm looking for (job opportunity, advice, referral)
3. Makes it easy for them to help (specific ask)
4. Is respectful of their time
5. Ends with a clear next step

Keep it under 500 words. Sound human, not like a template."""

    def _intro_request_prompt(self, profile: ProfileDict, contact: dict, target: dict) -> str:
        return f"""Write a LinkedIn message asking someone to introduce me to another person.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Key Skills: {profile.get('skills', 'N/A')}

ASKING (the person I'm messaging):
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Our relationship: {contact.get('notes', 'We are connected on LinkedIn')}

BEING INTRODUCED TO:
- Name: {target['name']}
- Title: {target['title']}
- Company: {target['company']}
- Why I want to meet them: {target.get('notes', 'Interested in their work')}

Write a message that:
1. Acknowledges my relationship with the person I'm asking
2. Explains who I want to be introduced to and why
3. Makes it easy for them to say yes (provides context they can forward)
4. Offers to provide more info or a brief intro paragraph
5. Is respectful and not pushy
6. Under 300 words

Just write the message, no explanations."""

    def _thank_you_prompt(self, profile: ProfileDict, contact: dict, context: str) -> str:
        return f"""Write a LinkedIn thank you message after a networking call or meeting.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Our history: {contact.get('notes', 'Had a call')}

CONTEXT: {context if context else 'A networking call to discuss career opportunities'}

Write a thank you message that:
1. Thanks them specifically for their time
2. References something specific from our conversation (make a reasonable assumption)
3. Mentions a key takeaway or insight I gained
4. Proposes a way to stay in touch or follow up
5. Offers to help them with something if possible
6. Is warm but professional
7. Under 150 words

Just write the message, no explanations."""

    def _follow_up_prompt(self, profile: ProfileDict, contact: dict, attempt: int) -> str:
        guidance = FOLLOW_UP_GUIDANCE.get(attempt, FOLLOW_UP_GUIDANCE[1])
        max_words = 150 if attempt == 1 else 100 if attempt == 2 else 50

        return f"""Write a LinkedIn follow-up message after not hearing back.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Our status: {contact['status'].replace('_', ' ')}
- Previous interaction: {contact.get('notes', 'Reached out previously')}

FOLLOW-UP CONTEXT:
{guidance}

Write a follow-up message that:
1. Acknowledges they're busy without being passive-aggressive
2. Adds new value or a fresh angle (not just "checking in")
3. Makes it easy to respond with a simple yes/no
4. Is under {max_words} words
5. Sounds confident but not desperate

Just write the message, no explanations."""
