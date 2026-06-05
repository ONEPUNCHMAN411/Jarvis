
import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_MAGIC = b"JVAULT1\n"
_SALT_LEN = 16
_ITERATIONS = 200_000


def _key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_file(path: str, password: str, out: str | None = None) -> dict:
    p = Path(path).expanduser()
    if not p.is_file():
        return {"ok": False, "error": f"File not found: {path}"}
    try:
        data = p.read_bytes()
        salt = os.urandom(_SALT_LEN)
        token = Fernet(_key(password, salt)).encrypt(data)
        out_path = Path(out).expanduser() if out else p.with_suffix(p.suffix + ".vault")
        out_path.write_bytes(_MAGIC + salt + token)
        return {"ok": True, "out": str(out_path), "size": out_path.stat().st_size}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def decrypt_file(path: str, password: str, out: str | None = None) -> dict:
    p = Path(path).expanduser()
    if not p.is_file():
        return {"ok": False, "error": f"File not found: {path}"}
    try:
        blob = p.read_bytes()
        if not blob.startswith(_MAGIC):
            return {"ok": False, "error": "Not a JARVIS vault file."}
        salt = blob[len(_MAGIC):len(_MAGIC) + _SALT_LEN]
        token = blob[len(_MAGIC) + _SALT_LEN:]
        try:
            data = Fernet(_key(password, salt)).decrypt(token)
        except Exception:
            return {"ok": False, "error": "Wrong password or corrupted file."}
        if out:
            out_path = Path(out).expanduser()
        elif p.name.endswith(".vault"):
            out_path = p.with_name(p.name[:-6])
        else:
            out_path = p.with_name(p.stem + ".decrypted" + p.suffix)
        out_path.write_bytes(data)
        return {"ok": True, "out": str(out_path), "size": out_path.stat().st_size}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def encrypt_text(text: str, password: str) -> str:
    salt = os.urandom(_SALT_LEN)
    token = Fernet(_key(password, salt)).encrypt(text.encode("utf-8"))
    return base64.urlsafe_b64encode(salt + token).decode("ascii")


def decrypt_text(token_b64: str, password: str) -> str:
    raw = base64.urlsafe_b64decode(token_b64.encode("ascii"))
    salt, token = raw[:_SALT_LEN], raw[_SALT_LEN:]
    return Fernet(_key(password, salt)).decrypt(token).decode("utf-8")
