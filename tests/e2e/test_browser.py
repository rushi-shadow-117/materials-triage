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
    page.get_by_test_id("unresolved").get_by_text("Unobtainium oxide").wait_for()
    shot(page, "01-confirm")
    page.get_by_role("button", name="Confirm and run").click()
    page.wait_for_url(re.compile(r"/runs/[0-9a-f-]{36}$"))
    # progress, then results: SiO2 anchor, the not-found name, three ranked rows
    page.get_by_text("Shown for calibration").wait_for()
    shot(page, "02-results-pi")
    # "What this screen cannot tell you" sits above the table, inside the first screen
    # (human test session, item 14)
    tell = page.get_by_test_id("cannot-tell")
    assert "moisture sensitivity" in tell.inner_text()
    tell_box, table_box = tell.bounding_box(), page.locator("table").first.bounding_box()
    assert tell_box is not None and table_box is not None
    assert tell_box["y"] < table_box["y"]
    assert tell_box["y"] < (page.viewport_size or {"height": 720})["height"]
    rows = page.locator("tbody tr[data-composition]")
    assert rows.count() == 4  # Al2O3, HfO2, ZrO2 and the SiO2 anchor row
    assert rows.nth(0).get_attribute("data-composition") == "Al2O3"
    page.get_by_test_id("unresolved").get_by_text("Unobtainium oxide").wait_for()
    # tied totals read "1=" with the note (human test session, item 7)
    assert rows.nth(0).locator("td").first.inner_text().strip() == "1="
    assert "listed alphabetically" in page.get_by_test_id("ties-note").inner_text()
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
    # every Materials Project value links to its page (human test session, item 10)
    mp = page.locator("a[href='https://next-gen.materialsproject.org/materials/mp-352']")
    assert mp.count() >= 1
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


def test_names_and_lowercase_match_and_the_rest_become_chips(page, server: str) -> None:  # type: ignore[no-untyped-def]
    """Human test session, item 11: "hfo2, hafnia, zirconia" failed the whole list with a
    Python list in a red box."""
    sign_in(page, server, "scientist")
    page.get_by_role("button", name="Rank my list").click()
    page.get_by_label("formulas").fill("hfo2, hafnia, zirconia, sapphire glass")
    page.get_by_role("button", name="Review criteria").click()
    chips = page.get_by_test_id("unresolved")
    chips.get_by_text("sapphire glass").wait_for()
    assert "Not matched; the rest are ranked" in chips.inner_text()
    assert "[" not in page.inner_text("body").split("Confirm criteria", 1)[1]
    assert page.get_by_role("button", name="Confirm and run").is_enabled()
    shot(page, "09-chips")
    page.get_by_label("formulas", exact=True).fill("hafnia??, sapphire glass")
    page.get_by_role("button", name="Review criteria").click()
    page.get_by_text("None of these matched a formula or a known name").wait_for()
    assert not page.get_by_role("button", name="Confirm and run").is_enabled()


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


def test_input_limits_chips_and_the_call_estimate(page, server: str) -> None:  # type: ignore[no-untyped-def]
    """Track H item 3 and item 7: the counter, server-side splitting on three separators, the
    matched chips, Run off while the list is empty, and the estimate sentence."""
    sign_in(page, server, "scientist")
    assert page.get_by_test_id("char-count").inner_text().startswith("0 / 2000")
    page.get_by_label("request").fill("Find stable oxides")
    assert page.get_by_test_id("char-count").inner_text().startswith("18 / 2000")
    page.get_by_role("button", name="Rank my list").click()
    assert page.get_by_role("button", name="Review criteria").is_disabled()
    page.get_by_label("formulas").fill("HfO2; ZrO2\nAl2O3, hfo2")
    page.get_by_role("button", name="Review criteria").click()
    matched = page.get_by_test_id("matched")
    matched.wait_for()
    chips = [c.strip() for c in matched.locator(".chip").all_inner_texts()]
    assert chips == ["HfO2", "ZrO2", "Al2O3"]
    estimate = page.get_by_test_id("estimate")
    assert "No model configured" in estimate.inner_text()  # LLM_PROVIDER=none on this server
    assert page.get_by_role("button", name="Confirm and run").is_enabled()
    # an empty list keeps Run off; the form says what to do
    page.get_by_label("candidates").fill("")
    page.get_by_text("Paste at least one formula or name to rank.").wait_for()
    assert page.get_by_role("button", name="Confirm and run").is_disabled()
    shot(page, "07-limits-and-estimate")


def test_the_role_switcher_is_absent_with_static_tokens(page, server: str) -> None:  # type: ignore[no-untyped-def]
    """Track H item 1: this server runs AUTH_MODE=static, so the dev role select never
    renders and the role is the token's."""
    sign_in(page, server, "fde")
    assert page.get_by_label("dev role").count() == 0
    assert "Role: fde" in page.inner_text("header")


def test_help_panel_tooltips_and_the_help_page(page, server: str) -> None:  # type: ignore[no-untyped-def]
    """Track H item 2: a collapsible panel on each screen, tooltips from help.ts, and the two
    guides rendered on /help from the API."""
    sign_in(page, server, "scientist")
    panel = page.get_by_test_id("screen-help")
    assert "How to use this screen" in panel.inner_text()
    panel.locator("summary").click()
    assert "Rank my list needs no model" in panel.inner_text()
    page.get_by_role("button", name="Rank my list").click()
    page.get_by_label("formulas").fill("HfO2, ZrO2")
    page.get_by_role("button", name="Review criteria").click()
    tip = page.locator("abbr.tip[data-help='criterion']", has_text="band gap")
    assert "band gap that scores" in (tip.get_attribute("title") or "")
    page.get_by_role("link", name="Help").click()
    page.get_by_test_id("guide").get_by_role("heading", name="Scientist guide").wait_for()
    page.get_by_role("button", name="Admin guide").click()
    page.get_by_test_id("guide").get_by_role("heading", name="Admin guide").wait_for()
    assert page.locator("[data-testid='guide'] h2").count() > 3  # rendered markdown, not raw text
    shot(page, "08-help")


def test_the_selection_chart_plots_the_shortlist(page, server: str) -> None:  # type: ignore[no-untyped-def]
    """Track H item 5: the band gap versus dielectric constant chart on the results page,
    with the shortlist filled, the anchor as a diamond, and a hover readout of server text."""
    sign_in(page, server, "scientist")
    page.get_by_role("button", name="Rank my list").click()
    page.get_by_label("formulas").fill("HfO2, ZrO2, Al2O3")
    page.get_by_role("button", name="Review criteria").click()
    page.get_by_test_id("matched").wait_for()
    page.get_by_role("button", name="Confirm and run").click()
    page.wait_for_url(re.compile(r"/runs/[0-9a-f-]{36}$"))
    page.get_by_text("Shown for calibration").wait_for()
    svg = page.locator("svg[aria-label='band gap versus dielectric constant']")
    svg.wait_for()
    assert svg.locator(".point.shortlist[data-composition='HfO2']").count() == 1
    assert svg.locator(".point.anchor").count() <= 1
    svg.locator(".point.shortlist[data-composition='HfO2']").hover()
    readout = page.get_by_test_id("chart-hover").inner_text()
    assert "HfO2" in readout and "band gap" in readout and " k " in readout
    assert "mp-" not in readout  # the PI view names no record ids
    shot(page, "10-chart")
