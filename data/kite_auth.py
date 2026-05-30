"""Interactive Kite Connect login -> save access token.

Run once per day you need fresh data:

    python -m data.kite_auth

Reads KITE_API_KEY and KITE_API_SECRET from the environment, prints the login
URL, you log in in the browser (redirect URL http://127.0.0.1), then paste the
``request_token`` from the redirected address bar. The resulting access token is
saved to .kite_token.json (gitignored) and reused by KiteIntradaySource until it
expires (~7:30 AM next day).
"""

import datetime as dt
import json
import os
import sys

from data.kite_source import TOKEN_PATH


def main():
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if not api_key or not api_secret:
        print("Set KITE_API_KEY and KITE_API_SECRET in your environment first.",
              file=sys.stderr)
        return 1

    try:
        from kiteconnect import KiteConnect
    except ImportError:
        print("kiteconnect is not installed. Run: pip install kiteconnect",
              file=sys.stderr)
        return 1

    kite = KiteConnect(api_key=api_key)
    print("\n1) Open this URL and log in:\n")
    print("   " + kite.login_url())
    print("\n2) After login your browser redirects to "
          "http://127.0.0.1/?request_token=XXXX&action=login&status=success")
    print("   Copy the request_token value from the address bar.\n")
    request_token = input("Paste request_token: ").strip()

    data = kite.generate_session(request_token, api_secret=api_secret)
    payload = {
        "access_token": data["access_token"],
        "user_id": data.get("user_id"),
        "generated_on": dt.date.today().isoformat(),
    }
    with open(TOKEN_PATH, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nSaved access token to {TOKEN_PATH} (valid until ~7:30 AM tomorrow).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
