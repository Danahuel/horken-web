"""Adaptadores RP1210 en Windows (Nexiq USB-Link, DG DPA5, Noregon DLA+,
Cat Comm Adapter, Cojali, Texa, clones de Nexiq...).

RP1210 es el estándar TMC/ATA para herramientas de diagnóstico de vehículos
pesados: cada fabricante instala una DLL y un .ini en C:\\Windows. Aquí se
envuelve esa DLL como un bus de python-can, así el resto del programa funciona
igual con cualquier adaptador.

Modo "CAN" (por defecto): recibimos las tramas en bruto y el programa hace el
Transport Protocol. Modo "J1939": el adaptador reensambla los mensajes largos
(usar si el adaptador no admite CAN en bruto).
"""
from __future__ import annotations

import configparser
import ctypes
import os
import struct
import sys
import time
from pathlib import Path
from typing import Optional

import can

from . import j1939

CMD_SET_ALL_FILTERS_PASS = 3
CMD_PROTECT_J1939_ADDRESS = 19
CMD_SET_ECHO = 16

# NAME J1939 de nuestra herramienta: "herramienta de servicio", autoconfigurable.
TOOL_NAME = bytes([0x00, 0x00, 0x60, 0x01, 0x00, 0x82, 0x00, 0xA0])


def windows_dir() -> Path:
    return Path(os.environ.get("WINDIR", r"C:\Windows"))


def list_adapters(win_dir: Optional[Path] = None) -> list[dict]:
    """Lee C:\\Windows\\RP121032.ini y el .ini de cada fabricante."""
    win_dir = win_dir or windows_dir()
    main = configparser.ConfigParser(strict=False, interpolation=None)
    main.read(win_dir / "RP121032.ini", encoding="latin-1")
    apis = [a.strip() for a in main.get("RP1210Support", "APIImplementations", fallback="").split(",") if a.strip()]
    out = []
    for api in apis:
        ini = configparser.ConfigParser(strict=False, interpolation=None)
        ini.read(win_dir / f"{api}.ini", encoding="latin-1")
        vendor = ini.get("VendorInformation", "Name", fallback=api)
        devices = []
        for sec in ini.sections():
            if sec.lower().startswith("deviceinformation"):
                devices.append({"id": ini.getint(sec, "DeviceID", fallback=1),
                                "description": ini.get(sec, "DeviceDescription", fallback=""),
                                "name": ini.get(sec, "DeviceName", fallback="")})
        protocols = sorted({ini.get(s, "ProtocolString", fallback="") for s in ini.sections()
                            if s.lower().startswith("protocolinformation")} - {""})
        out.append({"api": api, "vendor": vendor, "devices": devices, "protocols": protocols})
    return out


def _load_dll(api: str):
    if sys.platform != "win32":
        raise OSError("RP1210 solo funciona en Windows")
    bits = struct.calcsize("P") * 8
    try:
        return ctypes.WinDLL(f"{api}.dll")
    except OSError as e:
        if getattr(e, "winerror", None) == 193:
            raise OSError(f"La DLL {api}.dll no es de {bits} bits. Muchos adaptadores RP1210 solo traen DLL de "
                          f"32 bits: instala Python de 32 bits (Windows x86) y vuelve a probar.") from e
        raise OSError(f"No se pudo cargar {api}.dll: ¿está instalado el driver del adaptador? ({e})") from e


class RP1210Bus(can.BusABC):
    def __init__(self, channel: str, device_id: int = 1, protocol: str = "CAN", bitrate: int = 250000,
                 tool_address: int = 0xF9, dll=None, **kwargs):
        self.api = channel
        self.rp_protocol = protocol.upper()
        self.channel_info = f"RP1210 {channel} dispositivo {device_id} ({self.rp_protocol})"
        self.dll = dll or _load_dll(channel)
        baud = "Auto" if bitrate in (0, None) else str(bitrate // 1000)
        proto = f"{self.rp_protocol}:Baud={baud}".encode()
        cid = self.dll.RP1210_ClientConnect(0, device_id, proto, 0, 0, 0)
        if cid > 127 and baud == "Auto":
            cid = self.dll.RP1210_ClientConnect(0, device_id, self.rp_protocol.encode(), 0, 0, 0)
        if cid > 127:
            raise can.CanInitializationError(f"RP1210_ClientConnect falló: {self._err(cid)}")
        self.client = cid
        self._buf = ctypes.create_string_buffer(2048)
        if self.rp_protocol == "J1939":
            claim = bytes([tool_address]) + TOOL_NAME + bytes([0])  # 0 = bloquear hasta reclamar
            self._cmd(CMD_PROTECT_J1939_ADDRESS, claim)
        self._cmd(CMD_SET_ALL_FILTERS_PASS, b"")
        super().__init__(channel=channel, **kwargs)

    def _err(self, code: int) -> str:
        buf = ctypes.create_string_buffer(256)
        try:
            self.dll.RP1210_GetErrorMsg(code, buf)
            return f"{code} {buf.value.decode(errors='replace')}"
        except Exception:  # noqa: BLE001
            return str(code)

    def _cmd(self, number: int, payload: bytes) -> None:
        rc = self.dll.RP1210_SendCommand(number, self.client, payload, len(payload))
        if rc not in (0, None):
            raise can.CanOperationError(f"RP1210_SendCommand {number}: {self._err(rc)}")

    # --- recepción -------------------------------------------------------
    def _parse(self, raw: bytes) -> Optional[can.Message]:
        ts = int.from_bytes(raw[0:4], "big") / 1e6
        if self.rp_protocol == "CAN":
            if len(raw) < 9:
                return None
            ext = raw[4] == 1
            arb = int.from_bytes(raw[5:9], "big")
            return can.Message(timestamp=ts, arbitration_id=arb, is_extended_id=ext, data=raw[9:],
                               channel=self.api)
        # J1939: PGN(3, LE) · prioridad(1) · origen(1) · destino(1) · datos (ya reensamblados)
        if len(raw) < 10:
            return None
        pgn = raw[4] | (raw[5] << 8) | (raw[6] << 16)
        prio = raw[7] & 0x7
        arb = j1939.J1939Id(prio, pgn, raw[8], raw[9]).to_can_id()
        data = raw[10:]
        return can.Message(timestamp=ts, arbitration_id=arb, is_extended_id=True, data=data,
                           dlc=min(len(data), 8), channel=self.api, check=False)

    def _recv_internal(self, timeout):
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            n = self.dll.RP1210_ReadMessage(self.client, self._buf, len(self._buf), 0)
            if n > 0:
                msg = self._parse(self._buf.raw[:n])
                if msg is not None:
                    return msg, False
            elif n < 0:
                raise can.CanOperationError(f"RP1210_ReadMessage: {self._err(-n)}")
            if end is not None and time.monotonic() >= end:
                return None, False
            time.sleep(0.002)

    # --- envío -----------------------------------------------------------
    def send(self, msg: can.Message, timeout=None) -> None:
        if self.rp_protocol == "CAN":
            raw = bytes([1 if msg.is_extended_id else 0]) + msg.arbitration_id.to_bytes(4, "big") + bytes(msg.data)
        else:
            jid = j1939.J1939Id.parse(msg.arbitration_id)
            if jid.pgn in (j1939.PGN_TP_CM, j1939.PGN_TP_DT):
                return  # en modo J1939 el adaptador gestiona el Transport Protocol
            raw = bytes([jid.pgn & 0xFF, (jid.pgn >> 8) & 0xFF, (jid.pgn >> 16) & 0xFF,
                         jid.priority, jid.source, jid.destination]) + bytes(msg.data)
        rc = self.dll.RP1210_SendMessage(self.client, raw, len(raw), 0, 1)
        if rc not in (0, None):
            raise can.CanOperationError(f"RP1210_SendMessage: {self._err(rc)}")

    def shutdown(self) -> None:
        try:
            self.dll.RP1210_ClientDisconnect(self.client)
        finally:
            super().shutdown()
