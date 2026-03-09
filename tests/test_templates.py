"""Tests for template service."""

from linkedin.data.json_store import JsonTemplateRepo
from linkedin.services.template_service import TemplateService
from tests.conftest import sample_contact


class TestTemplateService:
    def test_save_and_list(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())

        svc.save_template("Intro Template", "connection", "Hi {{name}}, I'd love to connect!")
        templates = svc.list_templates()
        assert len(templates) == 1
        assert templates[0]["name"] == "Intro Template"

    def test_use_template(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())

        contact_repo.add(sample_contact(name="Alice Smith", company="Acme", id=1))
        svc.save_template("Test", "connection", "Hi {{first_name}} from {{company}}!")

        rendered = svc.use_template(1, 1)
        assert rendered == "Hi Alice from Acme!"

    def test_use_template_increments_usage(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())

        contact_repo.add(sample_contact(name="Alice", id=1))
        svc.save_template("Test", "connection", "Hi {{name}}")

        svc.use_template(1, 1)
        svc.use_template(1, 1)
        template = svc.get_template(1)
        assert template["usage_count"] == 2

    def test_record_response(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())

        svc.save_template("Test", "connection", "Hi")
        svc.record_response(1)
        template = svc.get_template(1)
        assert template["response_count"] == 1

    def test_ab_results_no_variants(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())

        svc.save_template("Test", "connection", "Hi", variant="A")
        results = svc.get_ab_results()
        assert results == []  # Need at least 2 variants

    def test_ab_results_with_variants(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())

        t1 = svc.save_template("Intro", "connection", "Hi {{name}}", variant="A")
        t2 = svc.save_template("Intro", "connection", "Hello {{name}}!", variant="B")

        # Simulate usage
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

    def test_suggest_best(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())

        contact_repo.add(sample_contact(name="Alice", id=1))
        t1 = svc.save_template("Good", "connection", "Hi")
        t2 = svc.save_template("Better", "connection", "Hello!")

        # t1: 10 uses, 2 responses (20%)
        for _ in range(10):
            svc.use_template(t1["id"], 1)
        for _ in range(2):
            svc.record_response(t1["id"])

        # t2: 10 uses, 5 responses (50%)
        for _ in range(10):
            svc.use_template(t2["id"], 1)
        for _ in range(5):
            svc.record_response(t2["id"])

        best = svc.suggest_best("connection")
        assert best is not None
        assert best["name"] == "Better"

    def test_suggest_best_no_usage(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())
        svc.save_template("Unused", "connection", "Hi")
        assert svc.suggest_best("connection") is None

    def test_template_not_found(self, json_repos):
        contact_repo, *_ = json_repos
        svc = TemplateService(contact_repo, JsonTemplateRepo())
        assert svc.get_template(999) is None
        assert svc.use_template(999, 1) is None

    def test_templates_persist_across_service_instances(self, json_repos):
        contact_repo, *_ = json_repos
        first_service = TemplateService(contact_repo, JsonTemplateRepo())
        first_service.save_template("Persisted", "connection", "Hi {{name}}")

        second_service = TemplateService(contact_repo, JsonTemplateRepo())
        templates = second_service.list_templates()
        assert len(templates) == 1
        assert templates[0]["name"] == "Persisted"
