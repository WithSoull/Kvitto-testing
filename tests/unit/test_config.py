import pytest
from pydantic import ValidationError

from app.config import Settings

DATABASE_URL = "postgresql+asyncpg://kvitto:kvitto@localhost:5432/kvitto"


@pytest.mark.parametrize("secret", [None, ""])
def test_webhook_secret_is_required(monkeypatch: pytest.MonkeyPatch, secret: str | None) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    if secret is None:
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    else:
        monkeypatch.setenv("WEBHOOK_SECRET", secret)

    with pytest.raises(ValidationError, match="webhook_secret"):
        Settings(_env_file=None)


def test_webhook_secret_is_not_leaked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("WEBHOOK_SECRET", "top-secret")

    settings = Settings(_env_file=None)

    assert "top-secret" not in repr(settings)
    assert settings.webhook_secret.get_secret_value() == "top-secret"
