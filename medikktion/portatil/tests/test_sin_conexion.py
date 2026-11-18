"""Cortes de internet: no se pierde nada y todo se sube al volver."""
import json
import smtplib
import socket
import time

from medikktion.__main__ import is_network_error
from medikktion.sinks import ResilientSink


class FakeRemote:
    """Imita FirestoreSink; ``online`` decide si las llamadas fallan."""

    def __init__(self, online=True):
        self.online = online
        self.docs = {}
        self.uploads = 0

    def _check(self):
        if not self.online:
            raise ConnectionError("sin red")

    def open_session(self, sid, meta):
        self._check()
        self.sid = sid
        self.docs[sid] = {**meta, "status": "live"}

    def publish(self, snap):
        self._check()
        self.uploads += 1
        self.docs[self.sid].update(snap)

    def close(self, snap):
        self.publish({**snap, "status": "finished"})

    def upload_finished(self, sid, data):
        self._check()
        self.docs[sid] = {**data, "status": "finished"}


def _wait(cond, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_outage_then_recovery(tmp_path):
    remote = FakeRemote(online=True)
    rs = ResilientSink(remote, tmp_path, local_every=0)
    rs.BACKOFF = (0.1,)
    rs.open_session("s1", {"session_id": "s1"})
    rs.publish({"n": 1})
    assert _wait(lambda: remote.docs["s1"].get("n") == 1)

    remote.online = False                       # se corta internet
    for i in range(2, 30):
        rs.publish({"n": i, "trend": {"rpm": {"v": list(range(i))}}})
    assert _wait(lambda: not rs.online)
    local = json.loads((tmp_path / "s1.json").read_text())
    assert local["n"] == 29                     # copia en el portátil al día

    remote.online = True                        # vuelve
    assert _wait(lambda: rs.online and remote.docs["s1"].get("n") == 29)
    assert len(remote.docs["s1"]["trend"]["rpm"]["v"]) == 29   # historial completo
    assert remote.docs["s1"]["connection"]["last_outage_s"] is not None
    assert rs.close({"n": 30}) is True
    assert remote.docs["s1"]["status"] == "finished"


def test_session_started_and_ended_offline_is_uploaded_later(tmp_path):
    remote = FakeRemote(online=False)
    rs = ResilientSink(remote, tmp_path, local_every=0)
    rs.BACKOFF = (0.1,)
    rs.open_session("s2", {"session_id": "s2", "started_at": "2026-11-16T08:00:00+00:00"})
    rs.publish({"n": 5})
    assert rs.close({"n": 6}) is False          # termina sin conexión
    assert rs.pending_count() == 1 and "s2" not in remote.docs

    remote.online = True                        # al día siguiente, con red
    rs2 = ResilientSink(remote, tmp_path)
    assert rs2.flush_pending() == 1 and rs2.pending_count() == 0
    assert remote.docs["s2"]["n"] == 6 and remote.docs["s2"]["status"] == "finished"


def test_reading_never_blocks_on_network(tmp_path):
    class SlowRemote(FakeRemote):
        def publish(self, snap):
            time.sleep(3)                       # red lentísima
            raise TimeoutError()
    rs = ResilientSink(SlowRemote(), tmp_path)
    rs.open_session("s3", {"session_id": "s3"})
    t0 = time.time()
    for i in range(100):
        rs.publish({"n": i})
    assert time.time() - t0 < 0.5               # la lectura sigue a su ritmo


def test_network_vs_config_errors():
    assert is_network_error(socket.gaierror())
    assert is_network_error(smtplib.SMTPServerDisconnected())
    assert not is_network_error(smtplib.SMTPAuthenticationError(535, b"bad"))


def test_prune_keeps_pending_and_recent(tmp_path):
    import os
    from medikktion.sinks import prune_local
    old = tmp_path / "20240101-old.json"
    old.write_text("x" * 1000)
    os.utime(old, (time.time() - 400 * 86400,) * 2)        # más de un año
    new = tmp_path / "20261118-new.json"
    new.write_text("y" * 1000)
    pend = tmp_path / "pendientes"
    pend.mkdir()
    (pend / "s.json").write_text("z")
    os.utime(pend / "s.json", (time.time() - 900 * 86400,) * 2)
    n, _ = prune_local(tmp_path, max_days=365, max_mb=1000)
    assert n == 1 and not old.exists() and new.exists() and (pend / "s.json").exists()


def test_prune_by_size(tmp_path):
    import os
    from medikktion.sinks import prune_local
    for i in range(10):
        f = tmp_path / f"s{i}.pdf"
        f.write_bytes(b"0" * 200_000)
        os.utime(f, (time.time() - (10 - i) * 60,) * 2)
    n, _ = prune_local(tmp_path, max_days=365, max_mb=1)       # límite 1 MB
    left = sorted(p.name for p in tmp_path.iterdir())
    assert n == 5 and left == ["s5.pdf", "s6.pdf", "s7.pdf", "s8.pdf", "s9.pdf"]   # quedan las más nuevas (1,0 MB)
