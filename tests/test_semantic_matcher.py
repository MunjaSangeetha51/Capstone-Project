from backend.app.services import semantic_matcher
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from backend.app.core.auth import hash_password, issue_token, verify_password
from backend.main import app

client = TestClient(app)


def test_semantic_ranker_combines_similarity_and_verified_skill_coverage(monkeypatch):
    monkeypatch.setattr(semantic_matcher, "rank", lambda query, docs: ([80.0, 25.0], "test-embedding"))
    results = semantic_matcher.match_profile_to_postings(
        {"Python": 85, "SQL": 55},
        [
            {"title": "Python intern", "skills": ["Python"], "description": "Build data tools"},
            {"title": "SQL intern", "skills": ["SQL"], "description": "Query reports"},
        ],
    )
    assert results[0]["readiness_bucket"] == "ready_now"
    assert results[0]["matched_skills"] == ["Python"]
    assert results[1]["missing_skills"] == ["SQL"]
    assert all(item["matching_engine"] == "test-embedding" for item in results)


def test_auth_password_hash_and_signed_token(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret-that-is-long-enough-for-hs256")
    encoded = hash_password("a-long-test-password")
    assert encoded != "a-long-test-password"
    assert verify_password("a-long-test-password", encoded)
    assert not verify_password("wrong-password", encoded)
    token = issue_token(11, 22)
    response = client.get("/api/profiles/22", headers={"Authorization": f"Bearer {token}"})
    # Auth succeeds; this test environment has no MySQL configured for profile reads.
    assert response.status_code == 503
    assert client.get("/api/profiles/23", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_semantic_match_route_requires_a_valid_account_token():
    response = client.post("/api/semantic-match", json={"skills": {"Python": 75}, "postings": []})
    assert response.status_code == 401


def test_semantic_match_route_ranks_postings_for_authenticated_profile(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret-that-is-long-enough-for-hs256")
    monkeypatch.setattr(semantic_matcher, "rank", lambda query, docs: ([82.0], "test-embedding"))
    token = issue_token(1, 2)
    response = client.post(
        "/api/semantic-match",
        headers={"Authorization": f"Bearer {token}"},
        json={"skills": {"Python": 80}, "postings": [{"title": "Python role", "skills": ["Python"]}]},
    )
    assert response.status_code == 200
    match = response.json()["matches"][0]
    assert match["readiness_bucket"] == "ready_now"
    assert match["semantic_similarity"] == 82
