"""Cover sheet QR payloads: a random token plus a checksum, never a database id (D-029).

Format: ``MA1-<16 base32 chars>-<4 base32 chars>``

- ``MA1`` identifies the format (Marking Assistant, version 1).
- The token is 80 random bits. It is stored in ``cover_sheet.token`` and looked up on upload.
- The checksum is the first 20 bits of SHA-256 over ``MA1-<token>``. It detects misreads and
  damaged or hand-copied codes. It is not a secret.

Uppercase base32 and ``-`` are all in the QR alphanumeric alphabet, which keeps the code small.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from enum import StrEnum

PREFIX = "MA1"
TOKEN_LENGTH = 16  # base32 chars = 80 bits
CHECK_LENGTH = 4  # base32 chars = 20 bits
_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


def new_token() -> str:
    return base64.b32encode(secrets.token_bytes(10)).decode("ascii")


def _checksum(token: str) -> str:
    digest = hashlib.sha256(f"{PREFIX}-{token}".encode("ascii")).digest()
    return base64.b32encode(digest[:5]).decode("ascii")[:CHECK_LENGTH]


def payload_for(token: str) -> str:
    return f"{PREFIX}-{token}-{_checksum(token)}"


class PayloadProblem(StrEnum):
    NOT_OURS = "not_ours"
    BAD_CHECKSUM = "bad_checksum"


@dataclass(frozen=True)
class ParsedPayload:
    token: str | None
    problem: PayloadProblem | None


def parse_payload(text: str) -> ParsedPayload:
    """Classify decoded QR text. Only a well-formed payload with a valid checksum gives a token."""
    parts = text.strip().split("-")
    if (
        len(parts) != 3
        or parts[0] != PREFIX
        or len(parts[1]) != TOKEN_LENGTH
        or len(parts[2]) != CHECK_LENGTH
        or not set(parts[1] + parts[2]) <= _ALPHABET
    ):
        return ParsedPayload(None, PayloadProblem.NOT_OURS)
    if not secrets.compare_digest(_checksum(parts[1]), parts[2]):
        return ParsedPayload(None, PayloadProblem.BAD_CHECKSUM)
    return ParsedPayload(parts[1], None)
