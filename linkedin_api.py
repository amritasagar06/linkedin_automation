from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from cloud_common import db, read_private_value, save_private_value, setting

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"


def make_authorization_url() -> str:
    state = secrets.token_urlsafe(32)
    db().table("oauth_states").insert({"state": state}).execute()
    params = {
        "response_type": "code",
        "client_id": setting("LINKEDIN_CLIENT_ID"),
        "redirect_uri": setting("LINKEDIN_REDIRECT_URI"),
        "state": state,
        "scope": "openid profile w_member_social",
    }
    if not params["client_id"] or not params["redirect_uri"]:
        raise RuntimeError("Set LINKEDIN_CLIENT_ID and LINKEDIN_REDIRECT_URI in Streamlit secrets.")
    return AUTH_URL + "?" + urlencode(params)


def finish_authorization(code: str, state: str) -> None:
    saved = db().table("oauth_states").select("state,created_at").eq("state", state).limit(1).execute().data
    if not saved:
        raise RuntimeError("LinkedIn authorization state was missing or already used. Start Connect again.")
    created = datetime.fromisoformat(saved[0]["created_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - created > timedelta(minutes=10):
        db().table("oauth_states").delete().eq("state", state).execute()
        raise RuntimeError("LinkedIn authorization took too long. Start Connect again.")

    token_response = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": setting("LINKEDIN_REDIRECT_URI"),
        "client_id": setting("LINKEDIN_CLIENT_ID"),
        "client_secret": setting("LINKEDIN_CLIENT_SECRET"),
    }, timeout=30)
    token_response.raise_for_status()
    tokens = token_response.json()
    access_token = tokens["access_token"]
    profile_response = requests.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    profile_response.raise_for_status()
    member_id = profile_response.json().get("sub")
    if not member_id:
        raise RuntimeError("LinkedIn did not return a member id. Reconnect with the openid and profile scopes enabled.")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 5184000)))
    save_private_value("linkedin_access_token", access_token)
    save_private_value("linkedin_person_urn", f"urn:li:person:{member_id}")
    save_private_value("linkedin_expires_at", expires_at.isoformat())
    if tokens.get("refresh_token"):
        save_private_value("linkedin_refresh_token", tokens["refresh_token"])
    else:
        # Do not keep a refresh token from an older connection if LinkedIn did not issue a new one.
        db().table("private_values").delete().eq("name", "linkedin_refresh_token").execute()
    db().table("oauth_states").delete().eq("state", state).execute()


def access_token() -> str:
    token = read_private_value("linkedin_access_token")
    expiry = read_private_value("linkedin_expires_at")
    if not token or not expiry:
        raise RuntimeError("Connect your LinkedIn account from the app before posting.")
    expires = datetime.fromisoformat(expiry)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires - datetime.now(timezone.utc) > timedelta(days=7):
        return token

    refresh = read_private_value("linkedin_refresh_token")
    if not refresh:
        raise RuntimeError("LinkedIn access token is expiring or expired, and this app was not issued a refresh token. Reconnect LinkedIn in the app.")
    response = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": setting("LINKEDIN_CLIENT_ID"),
        "client_secret": setting("LINKEDIN_CLIENT_SECRET"),
    }, timeout=30)
    response.raise_for_status()
    data = response.json()
    token = data["access_token"]
    expires = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 5184000)))
    save_private_value("linkedin_access_token", token)
    save_private_value("linkedin_expires_at", expires.isoformat())
    if data.get("refresh_token"):
        save_private_value("linkedin_refresh_token", data["refresh_token"])
    return token


def create_post(text: str) -> str:
    token = access_token()
    person_urn = read_private_value("linkedin_person_urn")
    if not person_urn:
        raise RuntimeError("LinkedIn member URN is missing. Reconnect LinkedIn in the app.")
    headers = {
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": setting("LINKEDIN_VERSION", "202610"),
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    payload = {
        "author": person_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    response = requests.post(POSTS_URL, headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    return response.headers.get("x-restli-id", "")
