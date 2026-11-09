"""Broker passwords at rest: AES-256-GCM.

Blob layout: 1 byte key version | 12 byte nonce | ciphertext+tag.
The associated data binds a blob to its user and broker account, so a blob
copied into another row does not decrypt.
"""
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_config


class CryptoError(Exception):
    pass


def _aad(user_id, account_id):
    return ("mohz:broker-password:%d:%d" % (int(user_id), int(account_id))).encode()


def _current(keys):
    if not keys:
        raise CryptoError("MOHZ_BROKER_KEY is not set: make one with `python -m mohz.keygen` and put it in .env")
    v = max(keys)
    return v, keys[v]


def encrypt_password(plain, user_id, account_id, keys=None):
    keys = get_config().broker_keys if keys is None else keys
    version, key = _current(keys)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plain.encode("utf-8"), _aad(user_id, account_id))
    return bytes([version]) + nonce + ct


def decrypt_password(blob, user_id, account_id, keys=None):
    keys = get_config().broker_keys if keys is None else keys
    if not blob or len(blob) < 1 + 12 + 16:
        raise CryptoError("no stored password")
    version, nonce, ct = blob[0], blob[1:13], blob[13:]
    key = keys.get(version)
    if key is None:
        raise CryptoError("the key for this password (version %d) is not configured" % version)
    try:
        return AESGCM(key).decrypt(nonce, ct, _aad(user_id, account_id)).decode("utf-8")
    except InvalidTag:
        raise CryptoError("the stored password could not be decrypted") from None


def key_version(blob):
    return blob[0] if blob else None
