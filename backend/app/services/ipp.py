"""Small IPP/1.1 transport, restricted to explicitly configured private IPv4 addresses.

No discovery broadcasts, DNS, redirects, environment proxies or external print service.
The printer must support PDF directly. IPP errors never imply physical completion.
"""

import http.client
import ipaddress
import struct
from urllib.parse import urlsplit


class PrinterError(Exception):
    pass


def validate_uri(uri: str) -> tuple[str, int, str]:
    try:
        parts = urlsplit(uri)
        address = ipaddress.IPv4Address(parts.hostname or "")
        allowed = any(
            address in ipaddress.ip_network(net)
            for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")
        )
        if (
            parts.scheme not in ("ipp", "ipps")
            or not allowed
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Private printer address required")
        return str(address), parts.port or 631, parts.path or "/ipp/print"
    except ValueError as exc:
        raise PrinterError("hardware.printer_address") from exc


def attribute(tag: int, name: str, value: str | int | bool) -> bytes:
    key = name.encode("ascii")
    if isinstance(value, bool):
        data = bytes([int(value)])
    elif isinstance(value, int):
        data = struct.pack(">i", value)
    else:
        data = value.encode("utf-8")
    return bytes([tag]) + struct.pack(">H", len(key)) + key + struct.pack(">H", len(data)) + data


def parse_response(data: bytes) -> dict[str, list[str | int]]:
    if len(data) < 9 or data[0] not in (1, 2) or int.from_bytes(data[2:4]) > 0x00FF:
        raise PrinterError("hardware.printer_rejected")
    result: dict[str, list[str | int]] = {}
    pos, name = 8, ""
    try:
        while pos < len(data):
            tag = data[pos]
            pos += 1
            if tag == 3:
                return result
            if tag < 0x10:
                name = ""
                continue
            size = int.from_bytes(data[pos : pos + 2])
            pos += 2
            if pos + size + 2 > len(data):
                raise ValueError
            if size:
                name = data[pos : pos + size].decode("utf-8")
            pos += size
            size = int.from_bytes(data[pos : pos + 2])
            pos += 2
            if pos + size > len(data) or not name:
                raise ValueError
            raw = data[pos : pos + size]
            pos += size
            value: str | int = (
                int.from_bytes(raw, signed=True)
                if tag in (0x21, 0x23)
                else raw.decode("utf-8", errors="replace")
            )
            result.setdefault(name, []).append(value)
    except (ValueError, UnicodeError) as exc:
        raise PrinterError("hardware.printer_response") from exc
    raise PrinterError("hardware.printer_response")


def request(
    uri: str, operation: int, *, extra: bytes = b"", document: bytes = b""
) -> dict[str, list[str | int]]:
    host, port, path = validate_uri(uri)
    body = (
        struct.pack(">BBHI", 1, 1, operation, 1)
        + b"\x01"
        + attribute(0x47, "attributes-charset", "utf-8")
        + attribute(0x48, "attributes-natural-language", "en")
        + attribute(0x45, "printer-uri", uri)
        + extra
        + b"\x03"
        + document
    )
    connection = (
        http.client.HTTPSConnection(host, port, timeout=15)
        if uri.startswith("ipps:")
        else http.client.HTTPConnection(host, port, timeout=15)
    )
    try:
        connection.request("POST", path, body=body, headers={"Content-Type": "application/ipp"})
        response = connection.getresponse()
        if response.status != 200:
            raise PrinterError("hardware.printer_rejected")
        data = response.read(1_048_577)
        if len(data) > 1_048_576:
            raise PrinterError("hardware.printer_response")
        return parse_response(data)
    except (OSError, http.client.HTTPException) as exc:
        raise PrinterError("hardware.printer_unreachable") from exc
    finally:
        connection.close()


def capabilities(uri: str) -> dict[str, list[str | int]]:
    found = request(uri, 0x000B)
    if "application/pdf" not in found.get("document-format-supported", []):
        raise PrinterError("hardware.printer_pdf")
    return found


def submit(uri: str, document: bytes, name: str, duplex: bool) -> int:
    found = request(
        uri,
        0x0002,
        document=document,
        extra=(
            attribute(0x42, "job-name", name)
            + attribute(0x49, "document-format", "application/pdf")
            + attribute(0x22, "ipp-attribute-fidelity", True)
            + b"\x02"
            + attribute(0x44, "media", "iso_a4_210x297mm")
            + attribute(0x44, "sides", "two-sided-long-edge" if duplex else "one-sided")
        ),
    )
    job_id = found.get("job-id", [None])[0]
    if not isinstance(job_id, int) or job_id <= 0:
        raise PrinterError("hardware.printer_response")
    return job_id


def job_state(uri: str, job_id: int) -> int:
    found = request(uri, 0x0009, extra=attribute(0x21, "job-id", job_id))
    state = found.get("job-state", [None])[0]
    if not isinstance(state, int):
        raise PrinterError("hardware.printer_response")
    return state
