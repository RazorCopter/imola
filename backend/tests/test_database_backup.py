import subprocess
import uuid

import psycopg
import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

from api.database_backup import (
    DatabaseBackupView,
    DatabaseRestoreView,
    create_dump,
    restore_dump,
    validate_dump,
)
from tests.factories import UserFactory


@pytest.mark.django_db(transaction=True)
def test_postgres_backup_restore_and_rollback(tmp_path, monkeypatch):
    name = "codex_restore_" + uuid.uuid4().hex[:12]
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE DATABASE "{name}"')
    db = settings.DATABASES["default"]

    def connect():
        return psycopg.connect(
            host=db["HOST"],
            port=db["PORT"] or 5432,
            user=db["USER"],
            password=db["PASSWORD"],
            dbname=name,
            autocommit=True,
        )

    try:
        with connect() as conn:
            conn.execute("CREATE TABLE demo (value text)")
            conn.execute("INSERT INTO demo VALUES ('original')")
            conn.execute("CREATE SCHEMA conflicts")
        backup = tmp_path / "backup.dump"
        create_dump(backup, name)
        validate_dump(backup)
        with connect() as conn:
            conn.execute("UPDATE demo SET value='changed'")
            conn.execute("CREATE TABLE extra (id int)")
            conn.execute("DROP SCHEMA conflicts")
        restore_dump(backup, name)
        with connect() as conn:
            assert conn.execute("SELECT value FROM demo").fetchone()[0] == "original"
            assert conn.execute("SELECT to_regclass('public.extra')").fetchone()[0] is None
            conn.execute("UPDATE demo SET value='preserved'")
        original_run = subprocess.run

        def inject_failure(args, **kwargs):
            result = original_run(args, **kwargs)
            if args[0] == "pg_restore" and "--clean" in args:
                kwargs["stdout"].write(b"\nSELECT * FROM nonexistent_table_for_rollback_test;\n")
            return result

        monkeypatch.setattr(subprocess, "run", inject_failure)
        with pytest.raises(subprocess.CalledProcessError):
            restore_dump(backup, name)
        with connect() as conn:
            assert conn.execute("SELECT value FROM demo").fetchone()[0] == "preserved"
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.mark.django_db
def test_backup_and_restore_require_admin():
    user = UserFactory()
    factory = APIRequestFactory()
    for view, request in (
        (DatabaseBackupView.as_view(), factory.get("/")),
        (DatabaseRestoreView.as_view(), factory.post("/", {}, format="multipart")),
    ):
        force_authenticate(request, user=user)
        assert view(request).status_code == 403
    group, _ = Group.objects.get_or_create(name="admin")
    user.groups.add(group)
    request = factory.post("/", {}, format="multipart")
    force_authenticate(request, user=user)
    assert DatabaseRestoreView.as_view()(request).status_code == 400
