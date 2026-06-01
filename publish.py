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

import subprocess
import sys

import export_site

# The existing Vercel project this site lives in (see site/README.md).
SCOPE = "kamals-projects-ce7b0100"
ALIAS = "backtest-in-nf.vercel.app"


def deploy_command(site_dir=None):
    """Non-interactive prod deploy; prints the deployment URL as its sole stdout line."""
    site_dir = str(site_dir or export_site.SITE)
    return ["vercel", "deploy", "--prod", "--yes", "--scope", SCOPE, site_dir]


def alias_command(url):
    """Re-point the clean alias at a just-deployed immutable URL."""
    return ["vercel", "alias", "set", url, ALIAS, "--scope", SCOPE]


def _run(command):
    return subprocess.run(command, capture_output=True, text=True)


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

    url = deploy.stdout.strip().splitlines()[-1].strip()
    print(f"deployed: {url}")

    print(f"re-pointing alias {ALIAS} ...")
    alias = _run(alias_command(url))
    if alias.returncode != 0:
        sys.stderr.write(alias.stderr)
        return 1

    print(f"live: https://{ALIAS}")
    return 0


if __name__ == "__main__":
    sys.exit(publish())
