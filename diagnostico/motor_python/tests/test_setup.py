import base64
import json

from horken_diag import setup_wizard


def test_app_code_roundtrip():
    gs = {"project_info": {"project_number": "123456789", "project_id": "horken-test", "storage_bucket": "b"},
          "client": [{"client_info": {"mobilesdk_app_id": "1:123456789:android:abc"},
                      "api_key": [{"current_key": "AIzaSyTEST"}]}]}
    code = setup_wizard.app_code_from_google_services(gs)
    assert code.startswith("HORKEN1:")
    raw = code.split(":", 1)[1]
    d = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    assert d == {"k": "AIzaSyTEST", "a": "1:123456789:android:abc", "p": "horken-test", "s": "123456789", "b": "b"}


def test_rules_contain_emails():
    r = setup_wizard.build_rules(["a@gmail.com", "b@gmail.com"])
    assert "'a@gmail.com'" in r and "'b@gmail.com'" in r and "TU_CORREO" not in r
    assert r.count("rules_version") == 1 and "match /sessions/{id}" in r
