"""Tests for template service."""

from linkedin.services.template_service import TemplateService
from tests.conftest import sample_contact


class TestTemplateService:
    def _svc(self, json_repos, json_template_repo):
        contact_repo, *_ = json_repos
        return TemplateService(contact_repo, json_template_repo)

    def test_save_and_list(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)

        svc.save_template("Intro Template", "connection", "Hi {{name}}, I'd love to connect!")
        templates = svc.list_templates()
        assert len(templates) == 1
        assert templates[0]["name"] == "Intro Template"

    def test_use_template(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)
        contact_repo = json_repos[0]

        contact_repo.add(sample_contact(name="Alice Smith", company="Acme", id=1))
        svc.save_template("Test", "connection", "Hi {{first_name}} from {{company}}!")

        rendered = svc.use_template(1, 1)
        assert rendered == "Hi Alice from Acme!"

    def test_use_template_increments_usage(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)
        contact_repo = json_repos[0]

        contact_repo.add(sample_contact(name="Alice", id=1))
        svc.save_template("Test", "connection", "Hi {{name}}")

        svc.use_template(1, 1)
        svc.use_template(1, 1)
        template = svc.get_template(1)
        assert template["usage_count"] == 2

    def test_record_response(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)

        svc.save_template("Test", "connection", "Hi")
        assert svc.record_response(1) is True
        template = svc.get_template(1)
        assert template["response_count"] == 1

    def test_record_response_missing_template(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)
        assert svc.record_response(999) is False

    def test_use_template_tracks_contact_usage_history(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)
        contact_repo = json_repos[0]

        contact_repo.add(sample_contact(name="Alice", id=1))
        svc.save_template("Conn", "connection", "Hi {{name}}")
        svc.use_template(1, 1)

        contact = contact_repo.get(1)
        history = contact.get("template_usage_history", [])
        assert len(history) == 1
        assert history[0]["template_id"] == 1
        assert history[0]["response_recorded"] is False

    def test_auto_record_outcome_credits_once(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)
        contact_repo = json_repos[0]

        contact_repo.add(sample_contact(name="Alice", id=1))
        svc.save_template("Conn", "connection", "Hi {{name}}")
        svc.use_template(1, 1)

        result = svc.auto_record_outcome(1, "connected")
        assert result["recorded"] is True

        template = svc.get_template(1)
        assert template["response_count"] == 1

        duplicate = svc.auto_record_outcome(1, "connected")
        assert duplicate["recorded"] is False
        assert svc.get_template(1)["response_count"] == 1

    def test_auto_record_outcome_uses_matching_template_type(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)
        contact_repo = json_repos[0]

        contact_repo.add(sample_contact(name="Alice", id=1))
        svc.save_template("Conn", "connection", "Hi {{name}}")
        svc.save_template("Msg", "message", "Hello {{name}}")
        svc.use_template(1, 1)
        svc.use_template(2, 1)

        result = svc.auto_record_outcome(1, "responded")
        assert result["recorded"] is True
        assert result["template_id"] == 2
        assert svc.get_template(1)["response_count"] == 0
        assert svc.get_template(2)["response_count"] == 1

    def test_ab_results_no_variants(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)

        svc.save_template("Test", "connection", "Hi", variant="A")
        assert svc.get_ab_results() == []

    def test_ab_results_with_variants(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)
        contact_repo = json_repos[0]

        t1 = svc.save_template("Intro", "connection", "Hi {{name}}", variant="A")
        t2 = svc.save_template("Intro", "connection", "Hello {{name}}!", variant="B")

        contact_repo.add(sample_contact(name="Alice", id=1))
        for _ in range(10):
            svc.use_template(t1["id"], 1)
        for _ in range(10):
            svc.use_template(t2["id"], 1)

        for _ in range(3):
            svc.record_response(t1["id"])
        for _ in range(6):
            svc.record_response(t2["id"])

        results = svc.get_ab_results()
        assert len(results) == 1
        assert results[0]["name"] == "Intro"
        assert results[0]["best_variant"] == "B"

    def test_suggest_best(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)
        contact_repo = json_repos[0]

        contact_repo.add(sample_contact(name="Alice", id=1))
        t1 = svc.save_template("Good", "connection", "Hi")
        t2 = svc.save_template("Better", "connection", "Hello!")

        for _ in range(10):
            svc.use_template(t1["id"], 1)
        for _ in range(2):
            svc.record_response(t1["id"])

        for _ in range(10):
            svc.use_template(t2["id"], 1)
        for _ in range(5):
            svc.record_response(t2["id"])

        best = svc.suggest_best("connection")
        assert best is not None
        assert best["name"] == "Better"

    def test_suggest_best_no_usage(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)

        svc.save_template("Unused", "connection", "Hi")
        assert svc.suggest_best("connection") is None

    def test_template_not_found(self, json_repos, json_template_repo):
        svc = self._svc(json_repos, json_template_repo)

        assert svc.get_template(999) is None
        assert svc.use_template(999, 1) is None

    def test_templates_persist_across_instances(self, json_repos, json_template_repo):
        contact_repo = json_repos[0]

        svc_one = TemplateService(contact_repo, json_template_repo)
        svc_one.save_template("Persistent", "connection", "Hi {{name}}")

        svc_two = TemplateService(contact_repo, json_template_repo)
        templates = svc_two.list_templates()
        assert len(templates) == 1
        assert templates[0]["name"] == "Persistent"
