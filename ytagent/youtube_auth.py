"""One-time OAuth consent to obtain a DURABLE YouTube upload refresh token.

Run ON THE MAC (needs a browser — never in the container):
    ./.venv/bin/python -m ytagent.youtube_auth

Opens a browser: Banks signs in with the Google account that owns the channel, SELECTS
"The Tales of Wildlife and Nature" at the chooser, and grants the single youtube.upload scope.
The refresh token is written to .env as YOUTUBE_REFRESH_TOKEN and NEVER printed. Then restart
the bot. Prerequisites (Banks, in Google Cloud Console): YouTube Data API v3 enabled; the OAuth
client is a "Desktop app" type; the consent screen is in "Production" (a "Testing" screen issues
tokens that expire in 7 days).
"""
from __future__ import annotations

from dotenv import find_dotenv, set_key
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import load_settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    settings = load_settings()
    if not (settings.youtube_client_id and settings.youtube_client_secret):
        raise SystemExit("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET missing in .env")

    client_config = {
        "installed": {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    print("A browser window will open.")
    print('Sign in with the Google account that owns "The Tales of Wildlife and Nature",')
    print("select THAT channel at the chooser, and grant upload access.")
    # access_type=offline + prompt=consent guarantees a refresh_token is returned.
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        raise SystemExit(
            "No refresh token returned. Ensure the OAuth consent screen is in 'Production' "
            "(not 'Testing'), revoke any prior access for this app, and retry."
        )

    env_path = find_dotenv(usecwd=True) or ".env"
    set_key(env_path, "YOUTUBE_REFRESH_TOKEN", creds.refresh_token)
    print(f"\nRefresh token stored in {env_path} (not printed).")
    print("Now restart the bot:  docker compose up -d --build telegram-bot")


if __name__ == "__main__":
    main()
