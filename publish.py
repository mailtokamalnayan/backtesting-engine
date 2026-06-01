"""Take the saved runs live in one command: export -> deploy -> re-alias.

    python publish.py        # or: make publish

Three steps that were previously remembered by hand:
  1. export_site.export()  -> regenerate site/data.json from the current runs
  2. vercel deploy --prod   -> push site/ to a fresh immutable production URL
  3. vercel alias set        -> re-point the clean alias at that URL

Step 3 is the un-forgettable bit: a ``*.vercel.app`` alias can't be a project
production domain, so it does NOT auto-follow a prod deploy and must be re-pointed
every time. Keeping all three in one place is the whole point of this script.

The Vercel calls are kept as pure command-string builders (``deploy_command`` /
``alias_command``) with a thin ``_run`` wrapper, so the commands are unit-testable
without touching the network.
"""

import json
import os
import re
import subprocess
import sys

import export_site

# Vercel target, from the environment so anyone can deploy to their own project:
#   VERCEL_SCOPE — your Vercel team/account slug (omitted if unset)
#   VERCEL_ALIAS — the clean *.vercel.app alias to re-point (alias step skipped if unset)
SCOPE = os.environ.get("VERCEL_SCOPE")
ALIAS = os.environ.get("VERCEL_ALIAS")


def deploy_command(site_dir=None):
    """Non-interactive prod deploy of the site dir; emits the deployment URL on stdout."""
    site_dir = str(site_dir or export_site.SITE)
    cmd = ["vercel", "deploy", "--prod", "--yes"]
    if SCOPE:
        cmd += ["--scope", SCOPE]
    return cmd + [site_dir]


def alias_command(url):
    """Re-point the clean alias at a just-deployed immutable URL."""
    cmd = ["vercel", "alias", "set", url, ALIAS]
    if SCOPE:
        cmd += ["--scope", SCOPE]
    return cmd


def _run(command):
    return subprocess.run(command, capture_output=True, text=True)


def parse_deploy_url(stdout):
    """Pull the production URL from `vercel deploy` stdout.

    Recent CLI versions print a JSON object (URL at ``.deployment.url``); older
    ones printed the bare URL as the sole line. Try JSON first, then fall back to
    the last ``*.vercel.app`` URL in the output. Returns None if none is found.
    """
    text = stdout.strip()
    try:
        url = json.loads(text).get("deployment", {}).get("url")
        if url:
            return url
    except (ValueError, AttributeError):
        pass
    matches = re.findall(r"https://[^\s\"']+\.vercel\.app", text)
    return matches[-1] if matches else None


def publish():
    print("exporting site/data.json from saved runs ...")
    export_site.export()

    print("deploying to Vercel production ...")
    deploy = _run(deploy_command())
    if deploy.returncode != 0:
        # Surface the CLI's own diagnostics (expired token, wrong scope, PATH) and
        # stop before aliasing — there's no good URL to point the alias at.
        sys.stderr.write(deploy.stderr)
        return 1

    url = parse_deploy_url(deploy.stdout)
    if not url:
        sys.stderr.write("could not parse a deployment URL from vercel output:\n")
        sys.stderr.write(deploy.stdout)
        return 1
    print(f"deployed: {url}")

    if not ALIAS:
        print("VERCEL_ALIAS not set — skipping alias step; the deploy URL above is live.")
        return 0

    print(f"re-pointing alias {ALIAS} ...")
    alias = _run(alias_command(url))
    if alias.returncode != 0:
        sys.stderr.write(alias.stderr)
        return 1

    print(f"live: https://{ALIAS}")
    return 0


if __name__ == "__main__":
    sys.exit(publish())
