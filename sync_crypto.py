"""End-to-end encryption of the WebDAV sync file.

The server only ever stores ciphertext. The key comes from a passphrase the
user enters on every device (DPAPI can't help here: it is bound to one
machine). AES-GCM also detects tampering, and the KDF cost is fixed in code so
a modified file can't talk a client into weaker or ruinously expensive
parameters.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import unicodedata

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = 3
_SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}
_AAD = b"ocrmath-sync-v3"


class SyncPassphraseError(RuntimeError):
    """Wrong passphrase or a damaged file; the two can't be told apart."""

    def __init__(self):
        super().__init__("无法解密远端数据：同步口令不正确，或远端文件已损坏")


def _key(passphrase: str, salt: bytes) -> bytes:
    # Normalized so the same characters typed on another machine match.
    secret = unicodedata.normalize("NFKC", passphrase).encode("utf-8")
    return hashlib.scrypt(secret, salt=salt, **_SCRYPT)


def encrypt(data: dict, passphrase: str) -> dict:
    salt, nonce = os.urandom(16), os.urandom(12)
    plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
    cipher = AESGCM(_key(passphrase, salt)).encrypt(nonce, plain, _AAD)
    encode = lambda raw: base64.b64encode(raw).decode("ascii")
    return {"version": VERSION, "salt": encode(salt), "nonce": encode(nonce),
            "ciphertext": encode(cipher)}


def decrypt(envelope: dict, passphrase: str) -> dict:
    try:
        salt = base64.b64decode(envelope["salt"], validate=True)
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        cipher = base64.b64decode(envelope["ciphertext"], validate=True)
        plain = AESGCM(_key(passphrase, salt)).decrypt(nonce, cipher, _AAD)
        data = json.loads(plain.decode("utf-8"))
    except (KeyError, TypeError, ValueError, binascii.Error, InvalidTag):
        raise SyncPassphraseError() from None
    if not isinstance(data, dict):
        raise SyncPassphraseError()
    return data
