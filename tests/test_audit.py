import app.core.audit as audit


class _Boom:
    """Supabase stand-in whose table access fails as if audit_events is absent."""

    def table(self, *a, **k):
        raise Exception("relation audit_events does not exist")


def test_write_audit_swallows_errors(monkeypatch):
    monkeypatch.setattr(audit, "service_client", lambda: _Boom())
    # auditing must never raise / break the action it logs
    audit.write_audit("o", "u", "suspend", "t", "detail")


def test_list_audit_degrades_when_missing(monkeypatch):
    monkeypatch.setattr(audit, "service_client", lambda: _Boom())
    assert audit.list_audit("o") == []
