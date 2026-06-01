"""publish.py: export -> deploy -> re-alias orchestration (subprocess mocked)."""

import subprocess

import pytest

import export_site
import publish


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# Shape of recent `vercel deploy --prod` stdout: a JSON object, URL at deployment.url.
_DEPLOY_URL = "https://backtest-in-abc123-kamal.vercel.app"
_DEPLOY_JSON = (
    '{"status": "ok", "deployment": {"id": "dpl_x", "url": "%s", '
    '"readyState": "READY"}, "message": "ready."}' % _DEPLOY_URL
)


@pytest.fixture
def recorder(monkeypatch):
    """Record commands run and export() calls, in order, without touching network."""
    events = []

    def fake_export():
        events.append(("export",))

    def fake_run(command):
        events.append(("run", command))
        if command[:2] == ["vercel", "deploy"]:
            return _Result(stdout=_DEPLOY_JSON)
        return _Result()  # alias set -> success

    monkeypatch.setattr(publish.export_site, "export", fake_export)
    monkeypatch.setattr(publish, "_run", fake_run)
    return events


def test_deploy_command_uses_scope_and_site_dir():
    cmd = publish.deploy_command()
    assert cmd == ["vercel", "deploy", "--prod", "--yes", "--scope",
                   publish.SCOPE, str(export_site.SITE)]


def test_alias_command_targets_clean_alias():
    cmd = publish.alias_command("https://deploy-xyz.vercel.app")
    assert cmd == ["vercel", "alias", "set", "https://deploy-xyz.vercel.app",
                   publish.ALIAS, "--scope", publish.SCOPE]


def test_happy_path_exports_then_deploys_then_aliases(recorder):
    rc = publish.publish()
    assert rc == 0
    kinds = [e[0] for e in recorder]
    assert kinds == ["export", "run", "run"]  # export strictly before any deploy
    deploy_cmd, alias_cmd = recorder[1][1], recorder[2][1]
    assert deploy_cmd[:2] == ["vercel", "deploy"]
    assert deploy_cmd[-1] == str(export_site.SITE)  # deploy dir == export_site.SITE
    assert alias_cmd[:3] == ["vercel", "alias", "set"]


def test_parsed_deploy_url_is_aliased(recorder):
    publish.publish()
    alias_cmd = recorder[2][1]
    # the URL from the (mocked) deploy stdout is what gets aliased
    assert alias_cmd[3] == _DEPLOY_URL


def test_parse_deploy_url_handles_json_and_bare_and_missing():
    assert publish.parse_deploy_url(_DEPLOY_JSON) == _DEPLOY_URL
    # legacy bare-URL stdout still parses via the regex fallback
    assert publish.parse_deploy_url(
        "https://foo-xyz.vercel.app\n") == "https://foo-xyz.vercel.app"
    # no URL anywhere -> None (publish() turns this into a clean failure)
    assert publish.parse_deploy_url("nothing useful here") is None


def test_deploy_failure_skips_alias_and_surfaces_stderr(monkeypatch, capsys):
    events = []
    monkeypatch.setattr(publish.export_site, "export",
                        lambda: events.append("export"))

    def fake_run(command):
        events.append(command[:2])
        return _Result(returncode=1, stderr="Error: token expired\n")

    monkeypatch.setattr(publish, "_run", fake_run)

    rc = publish.publish()
    assert rc == 1
    assert events == ["export", ["vercel", "deploy"]]  # alias step NOT reached
    assert "token expired" in capsys.readouterr().err
