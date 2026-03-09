"""Tests for linkedin-cli."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from linkedin.cli import cli
from linkedin.data.json_store import ensure_dirs, load_json, save_json


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_data_dir(tmp_path, monkeypatch):
    """Use a temporary directory for data storage."""
    test_data_dir = tmp_path / ".linkedin-cli"
    monkeypatch.setattr("linkedin.data.json_store.DATA_DIR", test_data_dir)
    monkeypatch.setattr("linkedin.data.json_store.PROFILE_FILE", test_data_dir / "my_profile.json")
    monkeypatch.setattr("linkedin.data.json_store.CONTACTS_FILE", test_data_dir / "contacts.json")
    monkeypatch.setattr("linkedin.data.json_store.COMPANIES_FILE", test_data_dir / "companies.json")
    monkeypatch.setattr("linkedin.data.json_store.DRAFTS_FILE", test_data_dir / "drafts.json")
    monkeypatch.setattr("linkedin.data.json_store.TEMPLATES_FILE", test_data_dir / "templates.json")
    monkeypatch.setattr("linkedin.data.json_store.RESEARCH_FILE", test_data_dir / "research.json")
    monkeypatch.setattr("linkedin.data.json_store.BACKUPS_DIR", test_data_dir / "backups")
    # Also patch the data_service module which imports these directly
    monkeypatch.setattr("linkedin.services.data_service.CONTACTS_FILE", test_data_dir / "contacts.json")
    monkeypatch.setattr("linkedin.services.data_service.COMPANIES_FILE", test_data_dir / "companies.json")
    monkeypatch.setattr("linkedin.services.data_service.DRAFTS_FILE", test_data_dir / "drafts.json")
    monkeypatch.setattr("linkedin.services.data_service.TEMPLATES_FILE", test_data_dir / "templates.json")
    monkeypatch.setattr("linkedin.services.data_service.PROFILE_FILE", test_data_dir / "my_profile.json")
    monkeypatch.setattr("linkedin.services.data_service.RESEARCH_FILE", test_data_dir / "research.json")
    monkeypatch.setattr("linkedin.services.data_service.BACKUPS_DIR", test_data_dir / "backups")
    return test_data_dir


class TestDataStorage:
    """Tests for data storage functions."""

    def test_ensure_dirs_creates_directory(self, temp_data_dir):
        """ensure_dirs should create the data directory."""
        assert not temp_data_dir.exists()
        ensure_dirs()
        assert temp_data_dir.exists()

    def test_load_json_returns_default_when_file_missing(self, temp_data_dir):
        """load_json should return default when file doesn't exist."""
        result = load_json(temp_data_dir / "nonexistent.json", [])
        assert result == []

        result = load_json(temp_data_dir / "nonexistent.json", {})
        assert result == {}

    def test_save_and_load_json(self, temp_data_dir):
        """save_json and load_json should round-trip data."""
        test_data = {"name": "Test", "value": 123}
        test_file = temp_data_dir / "test.json"

        save_json(test_file, test_data)
        loaded = load_json(test_file, {})

        assert loaded == test_data


class TestCLI:
    """Tests for CLI commands."""

    def test_cli_help(self, runner):
        """CLI should show help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "LinkedIn Job Hunt Assistant" in result.output

    def test_cli_version(self, runner):
        """CLI should show version."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "3.0.0" in result.output


class TestProfile:
    """Tests for profile commands."""

    def test_profile_show_empty(self, runner, temp_data_dir):
        """profile show should indicate no profile when empty."""
        result = runner.invoke(cli, ["profile", "show"])
        assert result.exit_code == 0
        assert "No profile set up" in result.output

    def test_profile_setup_and_show(self, runner, temp_data_dir):
        """profile setup should save and show should display."""
        # Setup profile with input
        result = runner.invoke(
            cli,
            ["profile", "setup"],
            input="John Doe\nAI Engineer\nML Engineer\nPython, ML\nBuilt RAG systems\nUnique skills\nTech\nSF\n",
        )
        assert result.exit_code == 0
        assert "Profile saved" in result.output

        # Verify show displays it
        result = runner.invoke(cli, ["profile", "show"])
        assert result.exit_code == 0
        assert "John Doe" in result.output


class TestContacts:
    """Tests for contacts CRM commands."""

    def test_contacts_list_empty(self, runner, temp_data_dir):
        """contacts list should indicate no contacts when empty."""
        result = runner.invoke(cli, ["contacts", "list"])
        assert result.exit_code == 0
        assert "No contacts yet" in result.output

    def test_contacts_add_and_list(self, runner, temp_data_dir):
        """contacts add should add and list should show."""
        result = runner.invoke(
            cli,
            ["contacts", "add"],
            input="Jane Smith\nCTO\nAcme Corp\nhttps://linkedin.com/in/jane\nGreat connection\n",
        )
        assert result.exit_code == 0
        assert "Added: Jane Smith" in result.output

        result = runner.invoke(cli, ["contacts", "list"])
        assert result.exit_code == 0
        assert "Jane Smith" in result.output
        assert "CTO" in result.output
        assert "Acme Corp" in result.output

    def test_contacts_view(self, runner, temp_data_dir):
        """contacts view should show contact details."""
        # Add a contact first
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Bob Jones\nEngineer\nTech Inc\nhttps://linkedin.com/in/bob\nTest notes\n",
        )

        result = runner.invoke(cli, ["contacts", "view", "1"])
        assert result.exit_code == 0
        assert "Bob Jones" in result.output
        assert "Engineer" in result.output
        assert "Tech Inc" in result.output

    def test_contacts_view_not_found(self, runner, temp_data_dir):
        """contacts view should handle missing contact."""
        result = runner.invoke(cli, ["contacts", "view", "999"])
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_contacts_update_status(self, runner, temp_data_dir):
        """contacts update should change status."""
        # Add a contact
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Alice\nManager\nCorp\nhttps://linkedin.com/in/alice\nNotes\n",
        )

        # Update status
        result = runner.invoke(cli, ["contacts", "update", "1", "--status", "connected"])
        assert result.exit_code == 0
        assert "Updated" in result.output

        # Verify status changed
        result = runner.invoke(cli, ["contacts", "view", "1"])
        assert "connected" in result.output

    def test_contacts_stats(self, runner, temp_data_dir):
        """contacts stats should show pipeline stats."""
        # Add contacts
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Person1\nRole\nCo\nurl\nNotes\n",
        )
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Person2\nRole\nCo\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["contacts", "stats"])
        assert result.exit_code == 0
        assert "Outreach Pipeline" in result.output
        assert "Not Contacted" in result.output


class TestDrafts:
    """Tests for drafts commands."""

    def test_drafts_list_empty(self, runner, temp_data_dir):
        """drafts list should indicate no drafts when empty."""
        result = runner.invoke(cli, ["drafts", "list"])
        assert result.exit_code == 0
        assert "No drafts yet" in result.output

    def test_drafts_connection_no_profile(self, runner, temp_data_dir):
        """drafts connection should require profile setup."""
        # Add a contact without profile
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Test\nRole\nCo\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["drafts", "connection", "1"])
        assert result.exit_code == 0
        assert "Set up your profile" in result.output

    def test_drafts_connection_contact_not_found(self, runner, temp_data_dir):
        """drafts connection should handle missing contact."""
        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Name\nTitle\nRole\nSkills\nExp\nUnique\nIndustry\nLoc\n",
        )

        result = runner.invoke(cli, ["drafts", "connection", "999"])
        assert result.exit_code == 0
        assert "not found" in result.output

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_drafts_connection_generates(self, mock_ai, runner, temp_data_dir):
        """drafts connection should generate AI draft."""
        mock_ai.return_value = "Hi! I'd love to connect and discuss AI engineering."

        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\n",
        )

        # Add contact
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Harrison\nCEO\nLangChain\nurl\nRAG expert\n",
        )

        # Generate draft (decline save)
        result = runner.invoke(cli, ["drafts", "connection", "1"], input="n\n")
        assert result.exit_code == 0
        assert "I'd love to connect" in result.output
        mock_ai.assert_called_once()

    def test_drafts_view_not_found(self, runner, temp_data_dir):
        """drafts view should handle missing draft."""
        result = runner.invoke(cli, ["drafts", "view", "999"])
        assert result.exit_code == 0
        assert "not found" in result.output


class TestResearch:
    """Tests for research commands."""

    def test_research_engagement(self, runner, temp_data_dir):
        """research engagement should show strategies."""
        result = runner.invoke(cli, ["research", "engagement"])
        assert result.exit_code == 0
        assert "LinkedIn Engagement Strategies" in result.output
        assert "Post Formats" in result.output

    @patch("linkedin.services.research_service.generate_with_ai")
    def test_research_ideas(self, mock_ai, runner, temp_data_dir):
        """research ideas should generate post ideas."""
        mock_ai.return_value = "1. Post idea one\n2. Post idea two"

        result = runner.invoke(cli, ["research", "ideas", "--topic", "AI"], input="n\n")
        assert result.exit_code == 0
        assert "Post idea" in result.output

    @patch("linkedin.services.research_service.generate_with_ai")
    def test_research_hashtags(self, mock_ai, runner, temp_data_dir):
        """research hashtags should generate hashtag suggestions."""
        mock_ai.return_value = "#MachineLearning\n#AI\n#DataScience"

        result = runner.invoke(cli, ["research", "hashtags", "machine learning"])
        assert result.exit_code == 0
        assert "Hashtag Recommendations" in result.output


class TestDashboard:
    """Tests for dashboard command."""

    def test_dashboard_empty(self, runner, temp_data_dir):
        """dashboard should show empty state."""
        result = runner.invoke(cli, ["dashboard"])
        assert result.exit_code == 0
        assert "Job Hunt Dashboard" in result.output
        assert "Profile: Not set up" in result.output

    def test_dashboard_with_data(self, runner, temp_data_dir):
        """dashboard should show profile and contacts."""
        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\n",
        )

        # Add contact
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Jane\nCTO\nCorp\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["dashboard"])
        assert result.exit_code == 0
        assert "Lorenzo" in result.output
        assert "ML Role" in result.output
        assert "CONTACTS PIPELINE" in result.output
        assert "Not Contacted" in result.output


class TestCompanies:
    """Tests for companies commands."""

    def test_companies_list_empty(self, runner, temp_data_dir):
        """companies list should indicate no companies when empty."""
        result = runner.invoke(cli, ["companies", "list"])
        assert result.exit_code == 0
        assert "No companies yet" in result.output

    def test_companies_add_and_list(self, runner, temp_data_dir):
        """companies add should add and list should show."""
        result = runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200", "--priority", "high"],
            input="LangChain\nAI/ML\nBuilding RAG tools\n",
        )
        assert result.exit_code == 0
        assert "Added company: LangChain" in result.output

        result = runner.invoke(cli, ["companies", "list"])
        assert result.exit_code == 0
        assert "LangChain" in result.output
        assert "AI/ML" in result.output

    def test_companies_view(self, runner, temp_data_dir):
        """companies view should show company details."""
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        result = runner.invoke(cli, ["companies", "view", "1"])
        assert result.exit_code == 0
        assert "TestCo" in result.output
        assert "Tech" in result.output

    def test_companies_view_not_found(self, runner, temp_data_dir):
        """companies view should handle missing company."""
        result = runner.invoke(cli, ["companies", "view", "999"])
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_companies_update(self, runner, temp_data_dir):
        """companies update should change priority and add notes."""
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        result = runner.invoke(cli, ["companies", "update", "1", "--priority", "high", "--notes", "Very promising"])
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_companies_contacts(self, runner, temp_data_dir):
        """companies contacts should list contacts at a company."""
        # Add company
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        # No contacts yet
        result = runner.invoke(cli, ["companies", "contacts", "1"])
        assert result.exit_code == 0
        assert "No contacts" in result.output


class TestEnhancedContacts:
    """Tests for enhanced contacts features."""

    def test_contacts_add_with_company_id(self, runner, temp_data_dir):
        """contacts add should link to company when company-id provided."""
        # Add company first
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        # Add contact linked to company
        result = runner.invoke(
            cli,
            ["contacts", "add", "--company-id", "1"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )
        assert result.exit_code == 0
        assert "Added: John Doe" in result.output
        assert "Linked to company #1" in result.output

    def test_contacts_list_filter_by_company_id(self, runner, temp_data_dir):
        """contacts list should filter by company-id."""
        # Add company
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        # Add contact linked to company
        runner.invoke(
            cli,
            ["contacts", "add", "--company-id", "1"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        # Add contact not linked
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Jane Doe\nManager\nOtherCo\nurl2\nNotes\n",
        )

        # Filter by company ID
        result = runner.invoke(cli, ["contacts", "list", "--company-id", "1"])
        assert result.exit_code == 0
        assert "John Doe" in result.output
        assert "Jane Doe" not in result.output

    def test_contacts_link_company(self, runner, temp_data_dir):
        """contacts link-company should link contact to company."""
        # Add company
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        # Add contact without company link
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nSomeCo\nurl\nNotes\n",
        )

        # Link to company
        result = runner.invoke(cli, ["contacts", "link-company", "1", "1"])
        assert result.exit_code == 0
        assert "Linked" in result.output

    def test_contacts_due_empty(self, runner, temp_data_dir):
        """contacts due should handle no overdue contacts."""
        result = runner.invoke(cli, ["contacts", "due"])
        assert result.exit_code == 0
        assert "No contacts yet" in result.output or "No overdue" in result.output

    def test_contacts_remind(self, runner, temp_data_dir):
        """contacts remind should set follow-up date."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["contacts", "remind", "1", "--days", "7"])
        assert result.exit_code == 0
        assert "Reminder set" in result.output

    def test_contacts_activity_empty(self, runner, temp_data_dir):
        """contacts activity should show empty state."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["contacts", "activity", "1"])
        assert result.exit_code == 0
        assert "No activities" in result.output


class TestEnhancedDrafts:
    """Tests for enhanced drafts features."""

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_drafts_intro_request(self, mock_ai, runner, temp_data_dir):
        """drafts intro-request should generate intro request."""
        mock_ai.return_value = "Hi, could you introduce me to someone?"

        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\n",
        )

        # Add two contacts
        runner.invoke(cli, ["contacts", "add"], input="Person1\nRole1\nCo1\nurl1\nNotes1\n")
        runner.invoke(cli, ["contacts", "add"], input="Person2\nRole2\nCo2\nurl2\nNotes2\n")

        result = runner.invoke(cli, ["drafts", "intro-request", "1", "--to", "2"], input="n\n")
        assert result.exit_code == 0
        assert "Introduction Request" in result.output

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_drafts_thank_you(self, mock_ai, runner, temp_data_dir):
        """drafts thank-you should generate thank you note."""
        mock_ai.return_value = "Thank you for your time!"

        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\n",
        )

        runner.invoke(cli, ["contacts", "add"], input="Person\nRole\nCo\nurl\nNotes\n")

        result = runner.invoke(cli, ["drafts", "thank-you", "1"], input="n\n")
        assert result.exit_code == 0
        assert "Thank You" in result.output

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_drafts_follow_up(self, mock_ai, runner, temp_data_dir):
        """drafts follow-up should generate follow-up message."""
        mock_ai.return_value = "Just checking in..."

        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\n",
        )

        runner.invoke(cli, ["contacts", "add"], input="Person\nRole\nCo\nurl\nNotes\n")

        result = runner.invoke(cli, ["drafts", "follow-up", "1", "--attempt", "1"], input="n\n")
        assert result.exit_code == 0
        assert "Follow-up" in result.output


class TestDiscover:
    """Tests for discover commands."""

    def test_discover_contacts_no_args(self, runner, temp_data_dir):
        """discover contacts should require --company or --role."""
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\n",
        )

        result = runner.invoke(cli, ["discover", "contacts"])
        assert result.exit_code == 0
        assert "Specify --company or --role" in result.output

    @patch("linkedin.services.discover_service.generate_with_ai")
    def test_discover_contacts_with_company(self, mock_ai, runner, temp_data_dir):
        """discover contacts should generate suggestions for a company."""
        mock_ai.return_value = "1. Engineering Manager\n2. Developer Advocate"

        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\n",
        )

        result = runner.invoke(cli, ["discover", "contacts", "--company", "LangChain"])
        assert result.exit_code == 0
        assert "Contact Discovery" in result.output

    @patch("linkedin.services.discover_service.generate_with_ai")
    def test_discover_companies(self, mock_ai, runner, temp_data_dir):
        """discover companies should generate company suggestions."""
        mock_ai.return_value = "1. Company A\n2. Company B"

        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\n",
        )

        result = runner.invoke(cli, ["discover", "companies"], input="n\n")
        assert result.exit_code == 0
        assert "Company Discovery" in result.output


class TestDataManagement:
    """Tests for data management commands."""

    def test_data_export_contacts_csv(self, runner, temp_data_dir):
        """data export contacts should create CSV file."""
        # Add a contact
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        output_file = temp_data_dir / "contacts.csv"
        result = runner.invoke(cli, ["data", "export", "contacts", "--output", str(output_file)])
        assert result.exit_code == 0
        assert "Exported 1 contacts" in result.output
        assert output_file.exists()

    def test_data_export_companies_csv(self, runner, temp_data_dir):
        """data export companies should create CSV file."""
        # Add a company
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        output_file = temp_data_dir / "companies.csv"
        result = runner.invoke(cli, ["data", "export", "companies", "--output", str(output_file)])
        assert result.exit_code == 0
        assert "Exported 1 companies" in result.output
        assert output_file.exists()

    def test_data_backup_and_backups_list(self, runner, temp_data_dir):
        """data backup should create backup and backups should list it."""
        # Add some data first
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        # Create backup
        result = runner.invoke(cli, ["data", "backup"])
        assert result.exit_code == 0
        assert "Backup created" in result.output

        # List backups
        result = runner.invoke(cli, ["data", "backups"])
        assert result.exit_code == 0
        assert "linkedin_cli_backup" in result.output


class TestAIGeneration:
    """Tests for AI generation function."""

    @patch("anthropic.Anthropic")
    def test_generate_with_ai_success(self, mock_anthropic_class):
        """generate_with_ai should return AI response."""
        from linkedin.ai.client import generate_with_ai

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Generated text")]
        )

        result = generate_with_ai("Test prompt")
        assert result == "Generated text"

    @patch("anthropic.Anthropic")
    def test_generate_with_ai_failure(self, mock_anthropic_class):
        """generate_with_ai should handle errors gracefully."""
        from linkedin.ai.client import generate_with_ai

        mock_anthropic_class.side_effect = Exception("API Error")

        result = generate_with_ai("Test prompt")
        assert "AI generation failed" in result
