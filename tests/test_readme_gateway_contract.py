"""Exercise README gateway guards with approved tags and hostile link changes."""
from __future__ import annotations

import pytest

import test_readme_visuals as checks


TAGS = "utm_source=github&utm_medium=readme&utm_campaign=smcub-harness"
TAGGED_HOME = f"https://alphatech.net.cn/?{TAGS}"


def _replace_readme(monkeypatch, path, transform):
    original_read = checks.read
    changed = transform(original_read(path))
    monkeypatch.setattr(checks, "read", lambda target: changed if target == path else original_read(target))


@pytest.mark.parametrize("path", [checks.README_EN, checks.README_ZH])
@pytest.mark.parametrize("query", [
    "", TAGS, "utm_campaign=smcub-harness&utm_source=github&utm_medium=readme",
])
def test_gateway_guards_accept_only_the_approved_campaign_or_no_query(monkeypatch, path, query):
    _replace_readme(monkeypatch, path, lambda text: text.replace("?" + TAGS, "?" + query if query else ""))
    checks.test_readme_gateway_mount_is_additive()
    checks.test_gateway_banner_is_clickable()


@pytest.mark.parametrize("path", [checks.README_EN, checks.README_ZH])
@pytest.mark.parametrize("bad_target", [
    "https://alphatech.net.cn.attacker.invalid/",
    "https://alphatech.net.cn@attacker.invalid/",
    "http://alphatech.net.cn/",
    "https://alphatech.net.cn:8443/",
    "https://alphatech.net.cn/sign-up",
    "https://alphatech.net.cn/#other",
    f"https://alphatech.net.cn/?{TAGS}&aff=referral",
    f"https://alphatech.net.cn/?{TAGS}&redirect=https%3A%2F%2Fattacker.invalid",
    f"https://alphatech.net.cn/?{TAGS}&utm_source=other",
    "https://alphatech.net.cn/?utm_source=other&utm_medium=readme&utm_campaign=smcub-harness",
    "https://alphatech.net.cn/?utm_source=github",
    f"https://alphatech.net.cn/?{TAGS}&",
])
def test_gateway_guards_reject_wrong_destinations_or_unapproved_parameters(monkeypatch, path, bad_target):
    _replace_readme(monkeypatch, path, lambda text: text.replace(TAGGED_HOME, bad_target))
    with pytest.raises(SystemExit):
        checks.test_gateway_banner_is_clickable()


@pytest.mark.parametrize("path,missing", [
    (checks.README_EN, "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"),
    (checks.README_ZH, "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"),
    (checks.README_EN, "assets/smartmoney-cub-harness-cover.png"),
    (checks.README_ZH, "assets/benchmark/benchmark-hero-1200x630.png"),
])
def test_approved_tracking_does_not_bypass_required_readme_content(monkeypatch, path, missing):
    _replace_readme(monkeypatch, path, lambda text: text.replace(missing, "REMOVED"))
    with pytest.raises(SystemExit):
        checks.test_readme_gateway_mount_is_additive()


@pytest.mark.parametrize("bad_url", [
    f"https://attacker.invalid/?{TAGS}",
    f"https://alphatech.net.cn/unapproved-path?{TAGS}",
    "https://alphatech.net.cn/?aff=referral",
    f"http://attacker.invalid/?next={TAGGED_HOME}",
    f"ftp://attacker.invalid/?next={TAGGED_HOME}",
    f"mailto:attacker@example.invalid?body={TAGGED_HOME}",
    f"http://attacker.invalid/?next=[nested]({TAGGED_HOME})",
])
def test_approved_gateway_tags_do_not_allow_other_tracking_links(monkeypatch, bad_url):
    _replace_readme(monkeypatch, checks.README_EN, lambda text: text + f"\n[unexpected]({bad_url})\n")
    with pytest.raises(SystemExit):
        checks.test_readme_gateway_mount_is_additive()
    with pytest.raises(SystemExit):
        checks.test_gateway_banner_is_clickable()
