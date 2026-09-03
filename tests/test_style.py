"""The voice rules reach every prompt that writes under the user's name."""

from unittest.mock import patch

from linkedin.ai.style import STYLE_RULES
from linkedin.app import App
from linkedin.data.paths import DataDir
from linkedin.services.content_service import build_prompt
from tests.conftest import sample_contact, sample_profile


def test_message_prompts_carry_the_rules(tmp_path):
    app = App(DataDir(tmp_path))
    app.profile_repo.save(sample_profile())
    app.contact_repo.add(sample_contact(id=1))
    with patch("linkedin.ai.client.generate_with_ai", return_value="ok") as gen:
        app.draft_svc.generate_connection(1)
        app.draft_svc.generate_message(1, context="c")
        app.draft_svc.generate_follow_up(1)
    for call in gen.call_args_list:
        prompt = call.args[0]
        assert "No em dashes" in prompt and "specific ask" in prompt


def test_post_prompts_carry_the_rules(tmp_path):
    assert STYLE_RULES.strip() in build_prompt({}, {"since": "a", "until": "b", "window_days": 7, "public_repos": 1, "merged_total": 0, "merged_by_human": 0, "merged_by_bots": 0, "repos_touched": 0, "top_repos": [], "recently_pushed": [], "sample_titles": []}, "story")
    app = App(DataDir(tmp_path))
    app.profile_repo.save(sample_profile())
    with patch("linkedin.ai.client.generate_with_ai", return_value="ok") as gen:
        app.research_svc.generate_post_draft("topic")
    assert "No emojis" in gen.call_args.args[0] and "emojis (not too many)" not in gen.call_args.args[0]
