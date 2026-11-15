from fastapi.testclient import TestClient

from backend.app.api.v1 import auth
from backend.main import app


client = TestClient(app)


def test_google_auth_config_is_optional(monkeypatch):
    monkeypatch.setattr(auth, "_google_client_id", lambda: "")
    assert client.get("/api/auth/config").json() == {"google_client_id": None}
    response = client.post("/api/auth/google", json={"credential": "x" * 30})
    assert response.status_code == 503
    assert "GOOGLE_CLIENT_ID" in response.json()["detail"]


def test_google_sign_in_uses_verified_google_identity(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret-that-is-long-enough-for-hs256")
    monkeypatch.setattr(auth, "_google_client_id", lambda: "test-client.apps.googleusercontent.com")
    monkeypatch.setattr(auth, "verify_google_credential", lambda credential, client_id: {
        "email": "student@example.com", "name": "Test Student",
    })

    class Cursor:
        def __init__(self):
            self.lastrowid = 10
            self.executions = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=None):
            self.executions.append((query, params))
            if query.startswith("INSERT INTO user_accounts"):
                self.lastrowid = 11

        def fetchone(self):
            return None

    class Connection:
        def __init__(self):
            self.db_cursor = Cursor()

        def cursor(self):
            return self.db_cursor

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    connection = Connection()
    monkeypatch.setattr(auth, "connect_mysql", lambda: connection)
    response = client.post("/api/auth/google", json={"credential": "verified-token-value"})
    assert response.status_code == 200
    assert response.json()["profile"]["email"] == "student@example.com"
    assert response.json()["profile"]["display_name"] == "Test Student"
    profile_insert, account_insert = connection.db_cursor.executions[1:]
    assert profile_insert[0] == "INSERT INTO student_profiles (display_name, email) VALUES (%s,%s)"
    assert profile_insert[1] == ("Test Student", "student@example.com")
    assert account_insert[1][0] == "student@example.com"
    assert account_insert[1][1].startswith("pbkdf2_sha256$")
    assert account_insert[1][2] == 10
