"""Conversation history service -- log and view LinkedIn message threads."""

from datetime import datetime

from linkedin.data.json_store import JsonContactRepo, JsonConversationRepo
from linkedin.types import ConversationDict, MessageDict

VALID_SENDERS = {"me", "them"}


class ConversationService:
    def __init__(self, conversation_repo: JsonConversationRepo, contact_repo: JsonContactRepo):
        self.conversations = conversation_repo
        self.contacts = contact_repo

    def log(
        self,
        contact_id: int,
        sender: str,
        text: str,
        timestamp: str = "",
    ) -> ConversationDict:
        if sender not in VALID_SENDERS:
            raise ValueError(f"Invalid sender '{sender}'. Must be 'me' or 'them'.")

        contact = self.contacts.get(contact_id)
        if not contact:
            raise ValueError(f"Contact #{contact_id} not found.")

        message: MessageDict = {
            "sender": sender,
            "text": text,
            "timestamp": timestamp or datetime.now().isoformat(),
        }

        existing = self.conversations.get_by_contact(contact_id)
        if existing:
            messages = list(existing.get("messages") or [])
            messages.append(message)
            conv: ConversationDict = {
                **existing,
                "messages": messages,
                "updated_at": datetime.now().isoformat(),
            }
        else:
            conv = {
                "contact_id": contact_id,
                "messages": [message],
                "updated_at": datetime.now().isoformat(),
            }

        self.conversations.upsert(conv)
        return conv

    def get_thread(self, contact_id: int) -> ConversationDict | None:
        return self.conversations.get_by_contact(contact_id)

    def export(self, contact_id: int) -> str:
        thread = self.get_thread(contact_id)
        if not thread:
            return ""
        lines = []
        for msg in thread.get("messages") or []:
            prefix = "[Me]" if msg["sender"] == "me" else "[Them]"
            ts = msg.get("timestamp", "")[:16]
            lines.append(f"{prefix} ({ts}): {msg['text']}")
        return chr(10).join(lines)
