"""Smart templates + A/B testing service."""

import math
from datetime import datetime

import linkedin.data.json_store as json_store
from linkedin.data.repository import ContactRepo, DraftRepo

OUTCOME_TEMPLATE_TYPES = {
    "connected": {"connection"},
    "responded": {"message", "follow_up"},
    "call_scheduled": {"message", "follow_up"},
    "hired": {"message", "follow_up"},
}


class TemplateService:
    def __init__(self, contact_repo: ContactRepo, draft_repo: DraftRepo):
        self.contacts = contact_repo
        self.drafts = draft_repo
        self._templates: list[dict] = self._load_templates()

    def list_templates(self) -> list[dict]:
        """List all templates with stats."""
        self._refresh_templates()
        for t in self._templates:
            t["response_rate"] = self._calc_response_rate(t)
        return self._templates

    def get_template(self, template_id: int) -> dict | None:
        """Get a template by ID."""
        self._refresh_templates()
        for t in self._templates:
            if t.get("id") == template_id:
                t["response_rate"] = self._calc_response_rate(t)
                return t
        return None

    def save_template(self, name: str, template_type: str, content: str, variant: str = "A") -> dict:
        """Save a draft as a reusable template."""
        self._refresh_templates()
        template = {
            "id": self._next_template_id(),
            "name": name,
            "template_type": template_type,
            "content": content,
            "variant": variant,
            "usage_count": 0,
            "response_count": 0,
            "created_at": datetime.now().isoformat(),
        }
        self._templates.append(template)
        self._save_templates()
        return template

    def use_template(self, template_id: int, contact_id: int) -> str | None:
        """Apply a template with contact-specific placeholders.

        Returns the rendered message or None if template not found.
        """
        template = self.get_template(template_id)
        if not template:
            return None

        contact = self.contacts.get(contact_id)
        if not contact:
            return None

        # Replace placeholders
        content = template["content"]
        placeholders = {
            "name": contact.get("name", ""),
            "first_name": contact.get("name", "").split()[0] if contact.get("name") else "",
            "title": contact.get("title", ""),
            "company": contact.get("company", ""),
        }

        for key, value in placeholders.items():
            content = content.replace(f"{{{{{key}}}}}", value)

        # Increment usage
        template["usage_count"] = template.get("usage_count", 0) + 1
        self._track_usage_for_contact(contact, template)
        self._save_templates()
        return content

    def auto_record_outcome(self, contact_id: int, outcome_status: str) -> dict:
        """Auto-credit template responses from positive contact outcomes."""
        normalized_status = str(outcome_status or "").strip().lower()
        allowed_types = OUTCOME_TEMPLATE_TYPES.get(normalized_status)
        if not allowed_types:
            return {"recorded": False, "reason": "Status does not map to template feedback."}

        contact = self.contacts.get(contact_id)
        if not contact:
            return {"recorded": False, "reason": f"Contact #{contact_id} not found."}

        history = contact.get("template_usage_history")
        if not isinstance(history, list):
            history = []

        if not history:
            fallback_id = self._normalize_template_id(contact.get("last_template_id"))
            if fallback_id is not None:
                history = [{
                    "template_id": fallback_id,
                    "template_type": contact.get("last_template_type", ""),
                    "used_at": datetime.now().isoformat(),
                    "response_recorded": False,
                }]

        self._refresh_templates()
        for usage in reversed(history):
            if usage.get("response_recorded"):
                continue

            template_id = self._normalize_template_id(usage.get("template_id"))
            if template_id is None:
                continue

            template_type = str(usage.get("template_type", "")).strip().lower()
            if template_type and template_type not in allowed_types:
                continue

            template = self._template_by_id(template_id)
            if not template:
                continue

            resolved_type = str(template.get("template_type", "")).strip().lower()
            if resolved_type not in allowed_types:
                continue

            template["response_count"] = template.get("response_count", 0) + 1
            usage["response_recorded"] = True
            usage["response_status"] = normalized_status
            usage["response_recorded_at"] = datetime.now().isoformat()
            contact["template_usage_history"] = history
            self.contacts.update(contact)
            self._save_templates()
            return {
                "recorded": True,
                "template_id": template_id,
                "template_name": template.get("name", ""),
                "status": normalized_status,
            }

        return {"recorded": False, "reason": "No eligible template usage found for this outcome."}

    def record_response(self, template_id: int, count: int = 1) -> bool:
        """Record that a template got one or more responses."""
        template = self.get_template(template_id)
        if template:
            template["response_count"] = template.get("response_count", 0) + max(1, count)
            self._save_templates()
            return True
        return False

    def get_ab_results(self) -> list[dict]:
        """Get A/B test results comparing variants."""
        self._refresh_templates()
        # Group templates by name
        groups: dict[str, list[dict]] = {}
        for t in self._templates:
            name = t["name"]
            if name not in groups:
                groups[name] = []
            groups[name].append(t)

        results = []
        for name, variants in groups.items():
            if len(variants) < 2:
                continue

            variant_results = []
            for v in variants:
                usage = v.get("usage_count", 0)
                responses = v.get("response_count", 0)
                rate = (responses / usage * 100) if usage > 0 else 0
                variant_results.append({
                    "variant": v.get("variant", "?"),
                    "usage_count": usage,
                    "response_count": responses,
                    "response_rate": f"{rate:.1f}%",
                })

            # Statistical significance (simple z-test)
            significant = self._is_significant(variants) if len(variants) == 2 else False
            best = max(variant_results, key=lambda x: float(x["response_rate"].rstrip("%")))

            results.append({
                "name": name,
                "variants": variant_results,
                "significant": significant,
                "best_variant": best["variant"],
            })

        return results

    def suggest_best(self, template_type: str) -> dict | None:
        """Suggest the best-performing template for a given type."""
        self._refresh_templates()
        matching = [t for t in self._templates if t.get("template_type") == template_type and t.get("usage_count", 0) > 0]
        if not matching:
            return None
        best = max(matching, key=lambda t: self._response_rate_float(t))
        best["response_rate"] = self._calc_response_rate(best)
        return best

    def _calc_response_rate(self, template: dict) -> str:
        usage = template.get("usage_count", 0)
        responses = template.get("response_count", 0)
        if usage == 0:
            return "0%"
        return f"{(responses / usage * 100):.1f}%"

    def _response_rate_float(self, template: dict) -> float:
        usage = template.get("usage_count", 0)
        responses = template.get("response_count", 0)
        return (responses / usage) if usage > 0 else 0.0

    def _is_significant(self, variants: list[dict]) -> bool:
        """Simple z-test for two proportions."""
        if len(variants) != 2:
            return False

        n1 = variants[0].get("usage_count", 0)
        n2 = variants[1].get("usage_count", 0)
        if n1 < 10 or n2 < 10:
            return False

        p1 = variants[0].get("response_count", 0) / n1
        p2 = variants[1].get("response_count", 0) / n2
        p_pool = (variants[0].get("response_count", 0) + variants[1].get("response_count", 0)) / (n1 + n2)

        if p_pool == 0 or p_pool == 1:
            return False

        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
        if se == 0:
            return False

        z = abs(p1 - p2) / se
        return z > 1.96  # 95% confidence

    def _next_template_id(self) -> int:
        max_id = 0
        for template in self._templates:
            raw_id = template.get("id")
            if isinstance(raw_id, int):
                max_id = max(max_id, raw_id)
            elif isinstance(raw_id, str) and raw_id.isdigit():
                max_id = max(max_id, int(raw_id))
        return max_id + 1

    def _load_templates(self) -> list[dict]:
        raw = json_store.load_json(json_store.TEMPLATES_FILE, [])
        return raw if isinstance(raw, list) else []

    def _save_templates(self) -> None:
        json_store.save_json(json_store.TEMPLATES_FILE, self._templates)

    def _refresh_templates(self) -> None:
        self._templates = self._load_templates()

    def _track_usage_for_contact(self, contact: dict, template: dict) -> None:
        history = contact.get("template_usage_history")
        if not isinstance(history, list):
            history = []

        history.append({
            "template_id": template.get("id"),
            "template_type": template.get("template_type", ""),
            "used_at": datetime.now().isoformat(),
            "response_recorded": False,
        })

        contact["template_usage_history"] = history[-50:]
        contact["last_template_id"] = template.get("id")
        contact["last_template_type"] = template.get("template_type", "")
        self.contacts.update(contact)

    def _template_by_id(self, template_id: int) -> dict | None:
        for template in self._templates:
            raw_id = self._normalize_template_id(template.get("id"))
            if raw_id == template_id:
                return template
        return None

    def _normalize_template_id(self, value) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None
