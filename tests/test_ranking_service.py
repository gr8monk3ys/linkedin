"""Ranking: who gets the scarce invitations, and who is exempt."""

from linkedin.services.ranking_service import bottom, connection_bonus, rank_contacts, score_contact

PROFILE = {"target_role": "Solutions Engineer", "industries": "AI/ML, Backend, Data Infrastructure"}
COMPANIES = [{"id": 1, "name": "Acme", "priority": "high"}, {"id": 2, "name": "Beta", "priority": "low"}]


def c(**kw):
    base = {"id": 9, "name": "Someone", "title": "", "company": "", "status": "not_contacted"}
    base.update(kw)
    return base


def test_pinned_is_always_100_and_first():
    score, reasons = score_contact(c(pinned=True), PROFILE, COMPANIES)
    assert (score, reasons) == (100, ["pinned"])
    rows = rank_contacts(
        [
            c(id=1, name="Zed", pinned=True),
            c(id=2, name="Ann", title="Hiring Manager", company="Acme", status="responded"),
        ],
        PROFILE,
        COMPANIES,
    )
    assert [r["name"] for r in rows] == ["Zed", "Ann"]


def test_hiring_side_title_at_a_high_priority_company_outranks_a_peer():
    hm = score_contact(c(title="Engineering Manager", company="Acme"), PROFILE, COMPANIES)[0]
    peer = score_contact(c(title="Solutions Engineer", company="Nowhere"), PROFILE, COMPANIES)[0]
    stranger = score_contact(c(title="Credit Analyst II", company="Bank"), PROFILE, COMPANIES)[0]
    assert hm > peer > stranger


def test_reasons_name_every_signal():
    score, reasons = score_contact(
        c(title="Director of AI/ML Platform", company="Acme", status="responded", referral_contact_id=3),
        PROFILE,
        COMPANIES,
    )
    assert "decision-maker title" in reasons
    assert "high-priority company" in reasons
    assert any(r.startswith("industry overlap") for r in reasons)
    assert "replied" in reasons and "referred" in reasons
    assert score <= 100


def test_company_matches_by_id_or_name():
    by_id = score_contact(c(company="Other", company_id=1), PROFILE, COMPANIES)[0]
    by_name = score_contact(c(company="acme"), PROFILE, COMPANIES)[0]
    assert by_id == by_name == 30


def test_target_role_in_title_lifts_a_hiring_title():
    plain = score_contact(c(title="Recruiter"), PROFILE, COMPANIES)[0]
    targeted = score_contact(c(title="Recruiter, Solutions Engineer roles"), PROFILE, COMPANIES)[0]
    assert targeted == plain + 5


def test_bottom_never_contains_a_pinned_contact():
    rows = rank_contacts(
        [c(id=1, name="Pinned", pinned=True), c(id=2, name="Low"), c(id=3, name="Mid", title="Engineer")],
        PROFILE,
        COMPANIES,
    )
    assert [r["name"] for r in bottom(rows, 5)] == ["Low", "Mid"]


def test_connection_bonus_is_bounded():
    assert connection_bonus(0) == 0 and connection_bonus(100) == 25
