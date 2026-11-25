from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


def setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    # Streamlit Cloud injects values into st.secrets, while GitHub Actions uses env vars.
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return default


@lru_cache(maxsize=1)
def db() -> Client:
    url = setting("SUPABASE_URL")
    key = setting("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the cloud secrets.")
    return create_client(url, key)


def fernet():
    from cryptography.fernet import Fernet
    key = setting("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("Set TOKEN_ENCRYPTION_KEY in Streamlit secrets.")
    return Fernet(key.encode("utf-8"))


def save_private_value(name: str, value: str) -> None:
    encrypted = fernet().encrypt(value.encode("utf-8")).decode("ascii")
    db().table("private_values").upsert({"name": name, "encrypted_value": encrypted}).execute()


def read_private_value(name: str) -> str | None:
    rows = db().table("private_values").select("encrypted_value").eq("name", name).limit(1).execute().data
    if not rows:
        return None
    try:
        return fernet().decrypt(rows[0]["encrypted_value"].encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise RuntimeError("Could not decrypt a saved LinkedIn token. Check TOKEN_ENCRYPTION_KEY.") from exc
