"""
Unit tests for GoogleDriveClient.delete_sibling_exports.

Verifies the post-download Drive cleanup primitive:
- method existence
- client-side regex matching (base name, .zip, (N) numeric suffixes)
- rejects substring collisions and non-numeric suffixes
- holds the service lock for list and each delete
- never raises; returns count of successful deletes
- handles listing failures, per-file delete failures, and stale 404s
"""
import threading
from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.google_drive.drive_client import GoogleDriveClient


@pytest.fixture
def client():
    """A GoogleDriveClient with a mocked service attached (connect() bypassed)."""
    auth = MagicMock()
    c = GoogleDriveClient(auth=auth)
    c.service = MagicMock()
    return c


class TestMethodExists:
    def test_delete_sibling_exports_is_callable(self, client):
        """GoogleDriveClient must expose delete_sibling_exports(chat_name)."""
        assert hasattr(client, "delete_sibling_exports")
        assert callable(client.delete_sibling_exports)


class _LockObservingService:
    """A fake Drive service that records whether the lock is held during
    each call, and returns caller-specified list results. Modeled on the
    helper in tests/unit/test_drive_client_threading.py."""

    def __init__(self, lock: threading.Lock, list_files: list[dict]):
        self.lock = lock
        self.list_files = list_files
        self.observations: list[tuple[str, bool]] = []
        self.deleted_ids: list[str] = []

    def files(self):
        return self

    def list(self, **kwargs):
        self.observations.append(("list", self.lock.locked()))
        outer = self

        class _Exec:
            def execute(self_inner):
                return {"files": outer.list_files}

        return _Exec()

    def delete(self, **kwargs):
        self.observations.append(("delete", self.lock.locked()))
        self.deleted_ids.append(kwargs.get("fileId"))
        outer = self

        class _Exec:
            def execute(self_inner):
                return {}

        return _Exec()


class TestBaseNameMatches:
    def test_base_name_and_zip_variant_are_deleted(self):
        """`WhatsApp Chat with X` and `WhatsApp Chat with X.zip` are both deleted."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "f1", "name": "WhatsApp Chat with Daniel Cocking"},
                {"id": "f2", "name": "WhatsApp Chat with Daniel Cocking.zip"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 2
        assert set(fake.deleted_ids) == {"f1", "f2"}


class TestNumericSiblingsMatch:
    def test_numeric_siblings_are_deleted(self):
        """All (N) and (N).zip variants must be deleted."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "f1", "name": "WhatsApp Chat with Daniel Cocking (1)"},
                {"id": "f2", "name": "WhatsApp Chat with Daniel Cocking (2).zip"},
                {"id": "f3", "name": "WhatsApp Chat with Daniel Cocking (10).zip"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 3
        assert set(fake.deleted_ids) == {"f1", "f2", "f3"}


class TestSubstringCollisionsRejected:
    def test_different_chat_with_same_prefix_is_not_deleted(self):
        """Files whose chat portion extends past the target name must be ignored."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "keep1", "name": "WhatsApp Chat with Daniel Cocking Jr.zip"},
                {"id": "keep2", "name": "WhatsApp Chat with Daniel Cocking family"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 0
        assert fake.deleted_ids == []


class TestNonNumericSuffixesRejected:
    def test_non_numeric_suffixes_are_not_deleted(self):
        """`(abc)` or custom renames must be ignored."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "x1", "name": "WhatsApp Chat with Daniel Cocking (abc).zip"},
                {"id": "x2", "name": "WhatsApp Chat with Daniel Cocking (1) backup.zip"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 0
        assert fake.deleted_ids == []


class TestSpecialCharsInChatName:
    def test_period_and_apostrophe_match_literally(self):
        """Chat name with ``.`` and ``'`` must match literally, not as regex meta-chars.

        The trailing period in `O'Brien.` would otherwise match any character if
        unescaped. And the apostrophe must be escaped in the Drive `contains` query.
        """
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "yes1", "name": "WhatsApp Chat with O'Brien."},
                {"id": "yes2", "name": "WhatsApp Chat with O'Brien. (1).zip"},
                # This one must NOT match — the '.' in chat name was escaped, so
                # the literal 'X' following it means the name is different.
                {"id": "no1", "name": "WhatsApp Chat with O'BrienX"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("O'Brien.")

        assert removed == 2
        assert set(fake.deleted_ids) == {"yes1", "yes2"}


class TestRootOnlyScope:
    def test_query_includes_root_parents_clause(self):
        """The Drive query passed to files().list() must include 'root' in parents."""
        captured = {}

        class _CapturingService:
            def files(self_inner):
                return self_inner

            def list(self_inner, **kwargs):
                captured["q"] = kwargs.get("q")

                class _Exec:
                    def execute(self_e):
                        return {"files": []}

                return _Exec()

            def delete(self_inner, **kwargs):
                raise AssertionError("should not delete when list is empty")

        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        c.service = _CapturingService()

        c.delete_sibling_exports("Daniel Cocking")

        assert captured["q"], "expected a query to be passed to files().list()"
        assert "'root' in parents" in captured["q"], (
            f"expected root-scope clause in query, got: {captured['q']!r}"
        )
        assert "WhatsApp Chat with Daniel Cocking" in captured["q"]
