from biznexa.config import Settings
from biznexa.db import is_valid_schema_identifier


def test_generic_postgresql_url_is_normalized_for_psycopg():
    settings = Settings(database_url="postgresql://user:password@example.test:5432/app")
    assert settings.sqlalchemy_database_url == "postgresql+psycopg://user:password@example.test:5432/app"


def test_explicit_psycopg_url_is_preserved():
    url = "postgresql+psycopg://user:password@example.test:5432/app"
    settings = Settings(database_url=url)
    assert settings.sqlalchemy_database_url == url


def test_schema_identifier_validation_rejects_sql_fragments():
    assert is_valid_schema_identifier("BizNexa_Analytics")
    assert not is_valid_schema_identifier("public; DROP SCHEMA public")
    assert not is_valid_schema_identifier("schema.name")
