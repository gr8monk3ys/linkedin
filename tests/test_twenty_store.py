"""Tests for the Twenty CRM store implementation."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from linkedin.data.twenty_client import (
    TwentyAuthError,
    TwentyClient,
    TwentyConnectionError,
    TwentyQueryError,
)
from linkedin.data.twenty_store import (
    TwentyCompanyRepo,
    TwentyContactRepo,
    TwentyDraftRepo,
    _IdMapper,
    _join_name,
    _split_name,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(data: dict, status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _gql_success(data: dict) -> httpx.Response:
    return _mock_response({"data": data})


def _gql_error(message: str) -> httpx.Response:
    return _mock_response({"errors": [{"message": message}]})


# ---------------------------------------------------------------------------
# TwentyClient tests
# ---------------------------------------------------------------------------


class TestTwentyClient:
    def test_query_success(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        with patch.object(client._http, "post", return_value=_gql_success({"currentWorkspace": {"id": "ws1"}})):
            result = client.query("{ currentWorkspace { id } }")
            assert result == {"currentWorkspace": {"id": "ws1"}}

    def test_query_graphql_error(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        with patch.object(client._http, "post", return_value=_gql_error("Field not found")):
            with pytest.raises(TwentyQueryError, match="Field not found"):
                client.query("{ bad }")

    def test_connection_error(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        with patch.object(client._http, "post", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(TwentyConnectionError):
                client.query("{ test }")

    def test_auth_error_401(self):
        client = TwentyClient(base_url="http://test:3000", api_key="bad")
        resp = _mock_response({}, status_code=401)
        with patch.object(client._http, "post", return_value=resp):
            with pytest.raises(TwentyAuthError, match="Invalid or missing"):
                client.query("{ test }")

    def test_auth_error_403(self):
        client = TwentyClient(base_url="http://test:3000", api_key="bad")
        resp = _mock_response({}, status_code=403)
        with patch.object(client._http, "post", return_value=resp):
            with pytest.raises(TwentyAuthError, match="Forbidden"):
                client.query("{ test }")

    def test_health_check_success(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        with patch.object(client._http, "post", return_value=_gql_success({"currentWorkspace": {"id": "ws1"}})):
            assert client.health_check() is True

    def test_health_check_failure(self):
        client = TwentyClient(base_url="http://test:3000", api_key="bad")
        with patch.object(client._http, "post", side_effect=httpx.ConnectError("refused")):
            assert client.health_check() is False

    def test_pagination_single_page(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        resp_data = {
            "people": {
                "edges": [{"node": {"id": "u1", "name": "A"}}, {"node": {"id": "u2", "name": "B"}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
        with patch.object(client._http, "post", return_value=_gql_success(resp_data)):
            results = client.paginate("query { people { edges { node { id } } } }", {}, "people")
            assert len(results) == 2
            assert results[0]["id"] == "u1"

    def test_pagination_multiple_pages(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        page1 = _gql_success({
            "people": {
                "edges": [{"node": {"id": "u1"}}],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
            }
        })
        page2 = _gql_success({
            "people": {
                "edges": [{"node": {"id": "u2"}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        })
        with patch.object(client._http, "post", side_effect=[page1, page2]):
            results = client.paginate("query($after: String) { people { edges { node { id } } } }", {}, "people")
            assert len(results) == 2

    def test_metadata_query(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        resp = _gql_success({"objects": {"edges": []}})
        with patch.object(client._http, "post", return_value=resp) as mock_post:
            client.metadata_query("{ objects { edges { node { id } } } }")
            call_url = mock_post.call_args[0][0]
            assert call_url == "http://test:3000/metadata"

    def test_mutate_delegates_to_query(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        with patch.object(client._http, "post", return_value=_gql_success({"createPerson": {"id": "u1"}})):
            result = client.mutate("mutation { createPerson { id } }")
            assert result == {"createPerson": {"id": "u1"}}

    def test_timeout_raises_connection_error(self):
        client = TwentyClient(base_url="http://test:3000", api_key="key123")
        with patch.object(client._http, "post", side_effect=httpx.ReadTimeout("timed out")):
            with pytest.raises(TwentyConnectionError, match="Timeout"):
                client.query("{ test }")


# ---------------------------------------------------------------------------
# _IdMapper tests
# ---------------------------------------------------------------------------


class TestIdMapper:
    def test_register_and_lookup(self, tmp_path):
        mapper = _IdMapper(tmp_path / "map.json")
        mapper.register("contact", 1, "uuid-abc")
        assert mapper.get_uuid("contact", 1) == "uuid-abc"
        assert mapper.get_local_id("contact", "uuid-abc") == 1

    def test_lookup_missing(self, tmp_path):
        mapper = _IdMapper(tmp_path / "map.json")
        assert mapper.get_uuid("contact", 99) is None
        assert mapper.get_local_id("contact", "nonexistent") is None

    def test_persistence(self, tmp_path):
        path = tmp_path / "map.json"
        mapper1 = _IdMapper(path)
        mapper1.register("company", 1, "uuid-co1")

        mapper2 = _IdMapper(path)
        assert mapper2.get_uuid("company", 1) == "uuid-co1"

    def test_next_local_id(self, tmp_path):
        mapper = _IdMapper(tmp_path / "map.json")
        assert mapper.next_local_id("contact") == 1
        mapper.register("contact", 1, "uuid-1")
        assert mapper.next_local_id("contact") == 2
        mapper.register("contact", 5, "uuid-5")
        assert mapper.next_local_id("contact") == 6

    def test_remove(self, tmp_path):
        mapper = _IdMapper(tmp_path / "map.json")
        mapper.register("contact", 1, "uuid-1")
        mapper.remove("contact", 1)
        assert mapper.get_uuid("contact", 1) is None

    def test_rebuild_from_twenty(self, tmp_path):
        mapper = _IdMapper(tmp_path / "map.json")
        mapper.rebuild_from_twenty("contact", ["uuid-a", "uuid-b", "uuid-c"])
        assert mapper.get_local_id("contact", "uuid-a") == 1
        assert mapper.get_local_id("contact", "uuid-b") == 2
        assert mapper.get_local_id("contact", "uuid-c") == 3

    def test_all_mappings(self, tmp_path):
        mapper = _IdMapper(tmp_path / "map.json")
        mapper.register("contact", 1, "uuid-1")
        mapper.register("contact", 2, "uuid-2")
        mappings = mapper.all_mappings("contact")
        assert mappings == {1: "uuid-1", 2: "uuid-2"}

    def test_all_mappings_empty(self, tmp_path):
        mapper = _IdMapper(tmp_path / "map.json")
        assert mapper.all_mappings("contact") == {}


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestNameHelpers:
    def test_split_simple(self):
        assert _split_name("Alice Smith") == ("Alice", "Smith")

    def test_split_single(self):
        assert _split_name("Alice") == ("Alice", "")

    def test_split_multiple(self):
        assert _split_name("Mary Jane Watson") == ("Mary", "Jane Watson")

    def test_split_empty(self):
        assert _split_name("") == ("", "")

    def test_join(self):
        assert _join_name("Alice", "Smith") == "Alice Smith"

    def test_join_first_only(self):
        assert _join_name("Alice", "") == "Alice"


# ---------------------------------------------------------------------------
# TwentyContactRepo tests
# ---------------------------------------------------------------------------


@pytest.fixture
def twenty_contact_setup(tmp_path):
    client = TwentyClient(base_url="http://test:3000", api_key="key123")
    mapper = _IdMapper(tmp_path / "map.json")
    repo = TwentyContactRepo(client, mapper)
    return client, mapper, repo


class TestTwentyContactRepo:
    def test_add(self, twenty_contact_setup):
        client, mapper, repo = twenty_contact_setup
        person_node = {
            "id": "uuid-p1",
            "name": {"firstName": "Alice", "lastName": "Smith"},
            "emails": {"primaryEmail": "alice@test.com"},
            "linkedinLink": {"primaryLinkUrl": "https://linkedin.com/in/alice", "primaryLinkLabel": "LinkedIn"},
            "jobTitle": "Engineer",
            "city": None,
            "companyId": None,
            "createdAt": "2024-01-15T10:00:00Z",
            "contactStatus": "not_contacted",
            "followUpDate": None,
            "lastContactDate": None,
            "contactSource": "linkedin_search",
            "contactNotes": "Met at conference",
        }
        with patch.object(client._http, "post", return_value=_gql_success({"createPerson": person_node})):
            result = repo.add({
                "name": "Alice Smith",
                "title": "Engineer",
                "email": "alice@test.com",
                "linkedin_url": "https://linkedin.com/in/alice",
                "notes": "Met at conference",
                "status": "not_contacted",
                "source": "linkedin_search",
            })
            assert result["id"] == 1
            assert result["name"] == "Alice Smith"
            assert result["email"] == "alice@test.com"
            assert mapper.get_uuid("contact", 1) == "uuid-p1"

    def test_get(self, twenty_contact_setup):
        client, mapper, repo = twenty_contact_setup
        mapper.register("contact", 1, "uuid-p1")
        person_node = {
            "id": "uuid-p1",
            "name": {"firstName": "Alice", "lastName": "Smith"},
            "emails": {"primaryEmail": ""},
            "linkedinLink": {},
            "jobTitle": "",
            "city": None,
            "companyId": None,
            "createdAt": "2024-01-15T10:00:00Z",
            "contactStatus": "not_contacted",
            "followUpDate": None,
            "lastContactDate": None,
            "contactSource": "linkedin_search",
            "contactNotes": "",
        }
        with patch.object(client._http, "post", return_value=_gql_success({"person": person_node})):
            result = repo.get(1)
            assert result is not None
            assert result["name"] == "Alice Smith"

    def test_get_nonexistent(self, twenty_contact_setup):
        _, _, repo = twenty_contact_setup
        assert repo.get(99) is None

    def test_list_all(self, twenty_contact_setup):
        client, mapper, repo = twenty_contact_setup
        nodes = [
            {
                "id": "uuid-p1",
                "name": {"firstName": "Alice", "lastName": "Smith"},
                "emails": {"primaryEmail": ""},
                "linkedinLink": {},
                "jobTitle": "",
                "city": None,
                "companyId": None,
                "createdAt": "2024-01-15T10:00:00Z",
                "contactStatus": "not_contacted",
                "followUpDate": None,
                "lastContactDate": None,
                "contactSource": "linkedin_search",
                "contactNotes": "",
            },
            {
                "id": "uuid-p2",
                "name": {"firstName": "Bob", "lastName": "Jones"},
                "emails": {"primaryEmail": ""},
                "linkedinLink": {},
                "jobTitle": "",
                "city": None,
                "companyId": None,
                "createdAt": "2024-01-15T10:00:00Z",
                "contactStatus": "connected",
                "followUpDate": None,
                "lastContactDate": None,
                "contactSource": "referral",
                "contactNotes": "",
            },
        ]
        resp = _gql_success({
            "people": {
                "edges": [{"node": n} for n in nodes],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        })
        with patch.object(client._http, "post", return_value=resp):
            results = repo.list_all()
            assert len(results) == 2
            names = {c["name"] for c in results}
            assert names == {"Alice Smith", "Bob Jones"}

    def test_update(self, twenty_contact_setup):
        client, mapper, repo = twenty_contact_setup
        mapper.register("contact", 1, "uuid-p1")
        with patch.object(client._http, "post", return_value=_gql_success({"updatePerson": {"id": "uuid-p1"}})):
            repo.update({"id": 1, "title": "Senior Engineer", "status": "connected"})

    def test_update_nonexistent(self, twenty_contact_setup):
        _, _, repo = twenty_contact_setup
        repo.update({"id": 99, "title": "Ghost"})  # Should not raise

    def test_delete(self, twenty_contact_setup):
        client, mapper, repo = twenty_contact_setup
        mapper.register("contact", 1, "uuid-p1")
        with patch.object(client._http, "post", return_value=_gql_success({"deletePerson": {"id": "uuid-p1"}})):
            assert repo.delete(1) is True
            assert mapper.get_uuid("contact", 1) is None

    def test_delete_nonexistent(self, twenty_contact_setup):
        _, _, repo = twenty_contact_setup
        assert repo.delete(99) is False

    def test_next_id(self, twenty_contact_setup):
        _, mapper, repo = twenty_contact_setup
        assert repo.next_id() == 1
        mapper.register("contact", 1, "uuid-1")
        assert repo.next_id() == 2

    def test_name_splitting(self, twenty_contact_setup):
        client, mapper, repo = twenty_contact_setup
        person_node = {
            "id": "uuid-p1",
            "name": {"firstName": "Mary", "lastName": "Jane Watson"},
            "emails": {"primaryEmail": ""},
            "linkedinLink": {},
            "jobTitle": "",
            "city": None,
            "companyId": None,
            "createdAt": "2024-01-15T10:00:00Z",
            "contactStatus": "not_contacted",
            "followUpDate": None,
            "lastContactDate": None,
            "contactSource": "linkedin_search",
            "contactNotes": "",
        }
        with patch.object(client._http, "post", return_value=_gql_success({"createPerson": person_node})):
            repo.add({"name": "Mary Jane Watson"})
            # Verify the mutation was called with split name
            call_body = client._http.post.call_args[1]["json"]
            input_data = call_body["variables"]["input"]
            assert input_data["name"]["firstName"] == "Mary"
            assert input_data["name"]["lastName"] == "Jane Watson"

    def test_company_id_mapping(self, twenty_contact_setup):
        client, mapper, repo = twenty_contact_setup
        mapper.register("company", 1, "uuid-co1")
        person_node = {
            "id": "uuid-p1",
            "name": {"firstName": "Alice", "lastName": ""},
            "emails": {"primaryEmail": ""},
            "linkedinLink": {},
            "jobTitle": "",
            "city": None,
            "companyId": "uuid-co1",
            "createdAt": "2024-01-15T10:00:00Z",
            "contactStatus": "not_contacted",
            "followUpDate": None,
            "lastContactDate": None,
            "contactSource": "linkedin_search",
            "contactNotes": "",
        }
        with patch.object(client._http, "post", return_value=_gql_success({"createPerson": person_node})):
            result = repo.add({"name": "Alice", "company_id": 1})
            assert result["company_id"] == 1
            call_body = client._http.post.call_args[1]["json"]
            assert call_body["variables"]["input"]["companyId"] == "uuid-co1"

    def test_save_all_adds_new(self, twenty_contact_setup):
        client, mapper, repo = twenty_contact_setup
        person_node = {
            "id": "uuid-p1",
            "name": {"firstName": "Alice", "lastName": ""},
            "emails": {"primaryEmail": ""},
            "linkedinLink": {},
            "jobTitle": "",
            "city": None,
            "companyId": None,
            "createdAt": "2024-01-15T10:00:00Z",
            "contactStatus": "not_contacted",
            "followUpDate": None,
            "lastContactDate": None,
            "contactSource": "linkedin_search",
            "contactNotes": "",
        }
        with patch.object(client._http, "post", return_value=_gql_success({"createPerson": person_node})):
            repo.save_all([{"name": "Alice"}])
            assert mapper.get_uuid("contact", 1) == "uuid-p1"


# ---------------------------------------------------------------------------
# TwentyCompanyRepo tests
# ---------------------------------------------------------------------------


@pytest.fixture
def twenty_company_setup(tmp_path):
    client = TwentyClient(base_url="http://test:3000", api_key="key123")
    mapper = _IdMapper(tmp_path / "map.json")
    repo = TwentyCompanyRepo(client, mapper)
    return client, mapper, repo


def _company_node(uuid="uuid-co1", name="Acme Corp", **overrides):
    defaults = {
        "id": uuid,
        "name": name,
        "domainName": {"primaryLinkUrl": "acme.com", "primaryLinkLabel": "Website"},
        "linkedinLink": {"primaryLinkUrl": "", "primaryLinkLabel": ""},
        "employees": 200,
        "createdAt": "2024-01-15T10:00:00Z",
        "companyIndustry": "Tech",
        "whyTarget": "Great culture",
        "companyPriority": "high",
        "companyNotes": "",
    }
    defaults.update(overrides)
    return defaults


class TestTwentyCompanyRepo:
    def test_add(self, twenty_company_setup):
        client, mapper, repo = twenty_company_setup
        node = _company_node()
        with patch.object(client._http, "post", return_value=_gql_success({"createCompany": node})):
            result = repo.add({"name": "Acme Corp", "industry": "Tech", "size": "51-200", "priority": "high"})
            assert result["id"] == 1
            assert result["name"] == "Acme Corp"
            assert mapper.get_uuid("company", 1) == "uuid-co1"

    def test_get(self, twenty_company_setup):
        client, mapper, repo = twenty_company_setup
        mapper.register("company", 1, "uuid-co1")
        with patch.object(client._http, "post", return_value=_gql_success({"company": _company_node()})):
            result = repo.get(1)
            assert result is not None
            assert result["name"] == "Acme Corp"
            assert result["industry"] == "Tech"

    def test_get_nonexistent(self, twenty_company_setup):
        _, _, repo = twenty_company_setup
        assert repo.get(99) is None

    def test_list_all(self, twenty_company_setup):
        client, mapper, repo = twenty_company_setup
        nodes = [_company_node("uuid-1", "Acme"), _company_node("uuid-2", "Globex")]
        resp = _gql_success({
            "companies": {
                "edges": [{"node": n} for n in nodes],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        })
        with patch.object(client._http, "post", return_value=resp):
            results = repo.list_all()
            assert len(results) == 2

    def test_update(self, twenty_company_setup):
        client, mapper, repo = twenty_company_setup
        mapper.register("company", 1, "uuid-co1")
        with patch.object(client._http, "post", return_value=_gql_success({"updateCompany": {"id": "uuid-co1"}})):
            repo.update({"id": 1, "priority": "low"})

    def test_delete(self, twenty_company_setup):
        client, mapper, repo = twenty_company_setup
        mapper.register("company", 1, "uuid-co1")
        with patch.object(client._http, "post", return_value=_gql_success({"deleteCompany": {"id": "uuid-co1"}})):
            assert repo.delete(1) is True
            assert mapper.get_uuid("company", 1) is None

    def test_delete_nonexistent(self, twenty_company_setup):
        _, _, repo = twenty_company_setup
        assert repo.delete(99) is False

    def test_next_id(self, twenty_company_setup):
        _, mapper, repo = twenty_company_setup
        assert repo.next_id() == 1

    def test_size_parsing(self, twenty_company_setup):
        client, mapper, repo = twenty_company_setup
        node = _company_node()
        with patch.object(client._http, "post", return_value=_gql_success({"createCompany": node})):
            repo.add({"name": "Test", "size": "5000+"})
            call_body = client._http.post.call_args[1]["json"]
            assert call_body["variables"]["input"]["employees"] == 5000


# ---------------------------------------------------------------------------
# TwentyDraftRepo tests
# ---------------------------------------------------------------------------


@pytest.fixture
def twenty_draft_setup(tmp_path):
    client = TwentyClient(base_url="http://test:3000", api_key="key123")
    mapper = _IdMapper(tmp_path / "map.json")
    repo = TwentyDraftRepo(client, mapper)
    return client, mapper, repo


def _note_node(uuid="uuid-n1", draft_type="connection", topic="", body="Hello!", person_uuid=None):
    title = f"[Draft:{draft_type}]"
    if topic:
        title += f" - {topic}"

    targets = []
    if person_uuid:
        targets = [{"node": {"id": "nt-1", "personId": person_uuid, "companyId": None}}]

    return {
        "id": uuid,
        "title": title,
        "body": body,
        "createdAt": "2024-01-15T10:00:00Z",
        "noteTargets": {"edges": targets},
    }


class TestTwentyDraftRepo:
    def test_add(self, twenty_draft_setup):
        client, mapper, repo = twenty_draft_setup
        node = _note_node()
        with patch.object(client._http, "post", return_value=_gql_success({"createNote": node})):
            result = repo.add({"type": "connection", "content": "Hello!"})
            assert result["id"] == 1
            assert result["type"] == "connection"
            assert mapper.get_uuid("draft", 1) == "uuid-n1"

    def test_add_with_contact_link(self, twenty_draft_setup):
        client, mapper, repo = twenty_draft_setup
        mapper.register("contact", 1, "uuid-p1")
        node = _note_node(person_uuid="uuid-p1")

        # First call creates note, second creates noteTarget
        responses = [
            _gql_success({"createNote": node}),
            _gql_success({"createNoteTarget": {"id": "nt-1"}}),
        ]
        with patch.object(client._http, "post", side_effect=responses):
            result = repo.add({"type": "connection", "content": "Hello!", "contact_id": 1})
            assert result["contact_id"] == 1
            assert client._http.post.call_count == 2

    def test_get(self, twenty_draft_setup):
        client, mapper, repo = twenty_draft_setup
        mapper.register("draft", 1, "uuid-n1")
        node = _note_node(body="Draft content")
        with patch.object(client._http, "post", return_value=_gql_success({"note": node})):
            result = repo.get(1)
            assert result is not None
            assert result["content"] == "Draft content"
            assert result["type"] == "connection"

    def test_get_nonexistent(self, twenty_draft_setup):
        _, _, repo = twenty_draft_setup
        assert repo.get(99) is None

    def test_list_all(self, twenty_draft_setup):
        client, mapper, repo = twenty_draft_setup
        nodes = [_note_node("uuid-1", "connection"), _note_node("uuid-2", "message", body="Hey")]
        resp = _gql_success({
            "notes": {
                "edges": [{"node": n} for n in nodes],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        })
        with patch.object(client._http, "post", return_value=resp):
            results = repo.list_all()
            assert len(results) == 2

    def test_note_title_encoding(self, twenty_draft_setup):
        client, mapper, repo = twenty_draft_setup
        node = _note_node(draft_type="post", topic="AI Trends")
        with patch.object(client._http, "post", return_value=_gql_success({"createNote": node})):
            repo.add({"type": "post", "content": "Great article", "topic": "AI Trends"})
            call_body = client._http.post.call_args[1]["json"]
            assert call_body["variables"]["input"]["title"] == "[Draft:post] - AI Trends"

    def test_note_title_decoding_with_topic(self, twenty_draft_setup):
        client, mapper, repo = twenty_draft_setup
        mapper.register("draft", 1, "uuid-n1")
        node = _note_node(draft_type="post", topic="AI Trends", body="Content")
        with patch.object(client._http, "post", return_value=_gql_success({"note": node})):
            result = repo.get(1)
            assert result["type"] == "post"
            assert result["topic"] == "AI Trends"

    def test_next_id(self, twenty_draft_setup):
        _, mapper, repo = twenty_draft_setup
        assert repo.next_id() == 1
        mapper.register("draft", 1, "uuid-1")
        assert repo.next_id() == 2
