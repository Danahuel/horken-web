"""Prueba del adaptador RP1210 con una DLL falsa que imita el comportamiento
de la especificación RP1210C, conectada a la máquina simulada."""
import ctypes
import time

import can
import pytest

from medikktion import collector, j1939, rp1210, simulator


class FakeRP1210Dll:
    """Imita la DLL del fabricante sobre un bus virtual."""

    def __init__(self, channel):
        self.bus = can.Bus(interface="virtual", channel=channel)
        self.protocol = None
        self.commands = []
        self.tp = j1939.TransportReassembler(our_address=0xF9)
        self.pending = []

    def RP1210_ClientConnect(self, hwnd, dev, proto, tx, rx, pkt):
        self.protocol = proto.decode().split(":")[0]
        return 1

    def RP1210_SendCommand(self, num, client, payload, size):
        self.commands.append((num, bytes(payload)))
        return 0

    def RP1210_ClientDisconnect(self, client):
        self.bus.shutdown()
        return 0

    def RP1210_GetErrorMsg(self, code, buf):
        buf.value = b"error simulado"
        return 0

    def RP1210_SendMessage(self, client, raw, size, notify, block):
        raw = bytes(raw[:size])
        if self.protocol == "CAN":
            arb, data = int.from_bytes(raw[1:5], "big"), raw[5:]
            self.bus.send(can.Message(arbitration_id=arb, data=data, is_extended_id=raw[0] == 1))
        else:
            pgn = raw[0] | raw[1] << 8 | raw[2] << 16
            arb = j1939.J1939Id(raw[3], pgn, raw[4], raw[5]).to_can_id()
            self.bus.send(can.Message(arbitration_id=arb, data=raw[6:], is_extended_id=True))
        return 0

    def RP1210_ReadMessage(self, client, buf, size, block):
        ts = (123456).to_bytes(4, "big")
        if self.protocol == "CAN":
            m = self.bus.recv(0)
            if m is None:
                return 0
            raw = ts + bytes([1]) + m.arbitration_id.to_bytes(4, "big") + bytes(m.data)
        else:
            raw = None
            while raw is None:
                m = self.bus.recv(0)
                if m is None:
                    return 0
                jid = j1939.J1939Id.parse(m.arbitration_id)
                if jid.pgn in (j1939.PGN_TP_CM, j1939.PGN_TP_DT):
                    done = self.tp.feed(jid, bytes(m.data))
                    if not done:
                        continue
                    pgn, sa, data = done
                    jid = j1939.J1939Id(7, pgn, sa, 0xFF)
                else:
                    data = bytes(m.data)
                raw = ts + bytes([jid.pgn & 0xFF, jid.pgn >> 8 & 0xFF, jid.pgn >> 16, jid.priority,
                                  jid.source, jid.destination]) + data
        ctypes.memmove(buf, raw, len(raw))
        return len(raw)


def test_list_adapters_reads_ini(tmp_path):
    (tmp_path / "RP121032.ini").write_text("[RP1210Support]\nAPIImplementations=NULN2R32\n")
    (tmp_path / "NULN2R32.ini").write_text(
        "[VendorInformation]\nName=NEXIQ Technologies USB-Link 2\n"
        "[DeviceInformation1]\nDeviceID=1\nDeviceDescription=USB-Link 2\n"
        "[ProtocolInformation1]\nProtocolString=J1939\n[ProtocolInformation2]\nProtocolString=CAN\n")
    a = rp1210.list_adapters(tmp_path)
    assert a[0]["api"] == "NULN2R32" and a[0]["devices"][0]["id"] == 1
    assert a[0]["protocols"] == ["CAN", "J1939"]


@pytest.mark.parametrize("protocol", ["CAN", "J1939"])
def test_rp1210_end_to_end(protocol):
    ch = f"rp-{protocol}"
    dll = FakeRP1210Dll(ch)
    bus = rp1210.RP1210Bus("NULN2R32", protocol=protocol, dll=dll)
    mbus = can.Bus(interface="virtual", channel=ch)
    sim = simulator.SimulatedMachine(mbus, "cat320")
    st = collector.MachineState("excavadora_20t")
    sess = collector.DiagnosticSession(bus, st)
    sim.start(); sess.start()
    try:
        time.sleep(1.3)
        sess.request_all()
        time.sleep(1.5)
        snap = st.snapshot()
    finally:
        sess.stop(); sim.stop(); bus.shutdown(); mbus.shutdown()
    assert (rp1210.CMD_SET_ALL_FILTERS_PASS, b"") in dll.commands
    if protocol == "J1939":
        assert any(c[0] == rp1210.CMD_PROTECT_J1939_ADDRESS for c in dll.commands)
    assert snap["summary"]["active_dtcs"] == 6
    assert snap["machine"]["serial"] == "SIM0001234"
    assert snap["tamper"]["verdict"] == "manipulado"
