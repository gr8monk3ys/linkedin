"""Smart templates + A/B testing service."""

import math
from datetime import datetime

from linkedin.data.repository import ContactRepo, DraftRepo


class TemplateService:
    def __init__(self, contact_repo: ContactRepo, draft_repo: DraftRepo):
        self.contacts = contact_repo
        self.drafts = draft_repo
        self._templates: list[dict] = []

    def list_templates(self) -> list[dict]:
        """List all templates with stats."""
        for t in self._templates:
            t["response_rate"] = self._calc_response_rate(t)
        return self._templates

    def get_template(self, template_id: int) -> dict | None:
        """Get a template by ID."""
        for t in self._templates:
            if t.get("id") == template_id:
                t["response_rate"] = self._calc_response_rate(t)
                return t
        return None

    def save_template(self, name: str, template_type: str, content: str, variant: str = "A") -> dict:
        """Save a draft as a reusable template."""
        template = {
            "id": len(self._templates) + 1,
            "name": name,
            "template_type": template_type,
            "content": content,
            "variant": variant,
            "usage_count": 0,
            "response_count": 0,
            "created_at": datetime.now().isoformat(),
        }
        self._templates.append(template)
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
        return content

    def record_response(self, template_id: int) -> None:
        """Record that a template got a response."""
        template = self.get_template(template_id)
        if template:
            template["response_count"] = template.get("response_count", 0) + 1

    def get_ab_results(self) -> list[dict]:
        """Get A/B test results comparing variants."""
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
        matching = [t for t in self._templates if t.get("template_type") == template_type and t.get("usage_count", 0) > 0]
        if not matching:
            return None
        return max(matching, key=lambda t: self._response_rate_float(t))

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
