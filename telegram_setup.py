from getpass import getpass
from time import sleep

import requests


def main():
    token = getpass("Paste the Telegram bot token (input hidden): ").strip()
    if not token:
        raise SystemExit("No token entered.")
    response = None
    for attempt in range(3):
        try:
            response = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=(10, 60))
            break
        except requests.Timeout:
            if attempt < 2:
                print(f"Telegram did not respond yet; retrying ({attempt + 1}/2)…")
                sleep(4)
            else:
                raise SystemExit("Telegram timed out three times. Check your internet connection, VPN, firewall, then try again. The token was not printed.") from None
        except requests.RequestException:
            raise SystemExit("Could not reach Telegram. Check your internet connection, VPN, or firewall. The token was not printed.") from None
    if not response.ok:
        # requests' default HTTPError includes the full URL, which contains the bot token.
        if response.status_code in (401, 404):
            raise SystemExit(f"Telegram rejected this bot token (HTTP {response.status_code}). In @BotFather use /token to generate a fresh token, then try again. The token was not printed.")
        if response.status_code == 429:
            try:
                retry_after = response.json().get("parameters", {}).get("retry_after")
            except ValueError:
                retry_after = None
            if retry_after:
                raise SystemExit(f"Telegram rate-limited the request. Wait at least {int(retry_after)} seconds, then run the script once. The token was not printed.")
            raise SystemExit("Telegram rate-limited the request. Wait 5 minutes, then run the script once. The token was not printed.")
        raise SystemExit(f"Telegram returned HTTP {response.status_code}. The token was not printed.")
    try:
        updates = response.json().get("result", [])
    except ValueError:
        raise SystemExit("Telegram returned an unreadable response. The token was not printed.") from None
    chats = {}
    for update in updates:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if chat.get("id") is not None:
            chats[str(chat["id"])] = chat.get("username") or chat.get("first_name") or "Telegram chat"
    if not chats:
        raise SystemExit("No chat found. Open your bot in Telegram, press Start, send /start, then run this script again.")
    print("Chat IDs found (put your private chat's id in TELEGRAM_CHAT_ID):")
    for chat_id, label in chats.items():
        print(f"{label}: {chat_id}")


if __name__ == "__main__":
    main()
