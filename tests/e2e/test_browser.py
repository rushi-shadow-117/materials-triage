"""The three screens in a real browser over recorded data, with no model and no network."""

from __future__ import annotations

import re

import pytest

from tests.e2e.conftest import shot, sign_in

pytestmark = pytest.mark.e2e


def test_rank_my_list_runs_end_to_end(page, server: str) -> None:  # type: ignore[no-untyped-def]
    sign_in(page, server, "scientist")
    page.get_by_role("button", name="Rank my list").click()
    page.get_by_label("formulas").fill("HfO2\nZrO2\nAl2O3\nUnobtainium oxide")
    page.get_by_role("button", name="Review criteria").click()
    page.get_by_text("Not chemical formulas: Unobtainium oxide").wait_for()
    shot(page, "01-confirm")
    page.get_by_role("button", name="Confirm and run").click()
    page.wait_for_url(re.compile(r"/runs/[0-9a-f-]{36}$"))
    # progress, then results: SiO2 anchor, the not-found name, three ranked rows
    page.get_by_text("Shown for calibration").wait_for()
    shot(page, "02-results-pi")
    rows = page.locator("tbody tr[data-composition]")
    assert rows.count() == 4  # Al2O3, HfO2, ZrO2 and the SiO2 anchor row
    assert rows.nth(0).get_attribute("data-composition") == "Al2O3"
    page.get_by_text("Not found in any source: Unobtainium oxide").wait_for()
    body = page.inner_text("body")
    assert "mp-" not in body  # the PI view names no record ids
    page.get_by_role("button", name="Audit view").click()
    page.get_by_role("heading", name="Decision log").wait_for()
    page.locator("details summary", has_text="HfO2").click()  # expand HfO2's breakdown
    panel = page.locator("details[open]", has_text="HfO2")
    panel.wait_for()
    assert "mp-352" in panel.inner_text(), panel.inner_text()[:1500]  # the record, audit only
    shot(page, "03-results-audit")
    # drill-down from HfO2's band gap
    page.locator("details", has_text="HfO2").get_by_role("link", name="band gap").first.click()
    page.get_by_text("Where this value came from").wait_for()
    assert "sha256:" in page.inner_text("body")
    shot(page, "04-drill")


def test_reloading_a_result_and_run_history_shows_the_page(page, server: str) -> None:  # type: ignore[no-untyped-def]
    """Human test session, breaker 2: a reload or a shared link showed the API's JSON."""
    sign_in(page, server, "scientist")
    page.get_by_role("button", name="Rank my list").click()
    page.get_by_label("formulas").fill("HfO2\nZrO2")
    page.get_by_role("button", name="Review criteria").click()
    page.get_by_role("button", name="Confirm and run").click()
    page.wait_for_url(re.compile(r"/runs/[0-9a-f-]{36}$"))
    page.reload()  # mid-run or just finished: either way the page, never JSON
    page.get_by_text("Shown for calibration").wait_for()
    assert "bundle_version" not in page.inner_text("body")
    shared = page.url
    page.goto(server + "/runs")
    page.reload()
    page.get_by_role("heading", name="Run history").wait_for()
    page.goto(shared)  # a shared link opens the result
    page.get_by_text("Shown for calibration").wait_for()


def test_confirm_form_shows_the_clamp(page, server: str) -> None:  # type: ignore[no-untyped-def]
    sign_in(page, server, "scientist")
    page.get_by_role("button", name="Fill the criteria form by hand").click()
    page.get_by_label(re.compile("Energy above hull cutoff")).fill("2000")
    page.get_by_text("you asked for 2000").wait_for()
    assert "Using 94" in page.inner_text("body")
    shot(page, "05-clamp")


def test_console_by_role(page, server: str) -> None:  # type: ignore[no-untyped-def]
    sign_in(page, server, "scientist")
    page.goto(server + "/console")
    page.get_by_text("The console is for site admins").wait_for()
    sign_in_again(page, server, "fde")
    page.goto(server + "/console")
    page.get_by_text("Effective configuration").wait_for()
    page.get_by_role("button", name="Source health").click()
    page.get_by_text("materials_project").wait_for()
    assert "Refresh now" not in page.inner_text("body")  # admin only
    page.get_by_role("button", name="Profiles (YAML)").click()
    page.get_by_label("profile yaml").fill(
        "profile: broken_v1\nweights:\n  status: entered\n  values: {band_gap: 5.0}\n"
    )
    page.get_by_role("button", name="Validate").click()
    page.get_by_text(re.compile(r"\d+ errors?,")).wait_for()
    assert "outside the site bounds" in page.inner_text("body") or "error" in page.inner_text(
        "body"
    )
    shot(page, "06-console-validate")
    sign_in_again(page, server, "admin")
    page.goto(server + "/console")
    page.get_by_role("button", name="Source health").click()
    page.get_by_text("Refresh now").wait_for()
    shot(page, "07-console-admin")


def sign_in_again(page, server: str, role: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(server + "/")
    page.get_by_role("button", name="Sign out").click()
    sign_in(page, server, role)
