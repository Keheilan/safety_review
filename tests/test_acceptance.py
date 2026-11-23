"""Acceptance tests for the process-conditions increment.

Runs the page in a real browser (Playwright, Chromium) against the bundled
fictional example case. No network access is needed beyond a local server.

    python -m pytest tests/test_acceptance.py -q
"""
import functools
import http.server
import json
import re
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def base_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/index.html"
    server.shutdown()


@pytest.fixture()
def page(base_url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(base_url + "#event")
        pg.wait_for_selector("#overview .tally")
        pg.errors = errors
        yield pg
        browser.close()


def go(pg, stage):
    pg.evaluate(f"location.hash = '{stage}'")
    pg.wait_for_selector(f"#s-{stage}:not([hidden])")


def report_text(pg):
    go(pg, "summary")
    return pg.inner_text("#report")


def test_1_required_conditions_at_a_step_and_handoff(page):
    go(page, "lanes")
    page.click('#lane-frame .step-dot[data-id="s5"]')
    detail = page.inner_text("#step-detail")
    assert "Required: The nurse responsible for the patient receives the critical lactate result" in detail
    assert "Handed over: Critical lactate result" in detail
    assert "Acknowledgment: confirmed" in detail


def test_2_missing_evidence_is_not_confirmed_failure(page):
    tallies = page.inner_text("#overview")
    assert "handoffs documented as not acknowledged" in tallies
    assert "handoffs with acknowledgment not established" in tallies
    text = report_text(page)
    assert "Not established: no evidence either way: The nurse responsible" in text
    assert "Absent (documented): A named role escalates again" in text
    assert "An absent record is not evidence that something failed" in text
    # a step's handoff with no evidence either way is never reported as documented failure
    assert "Rapid response team to On-call surgical resident (Treatment started; resident informed): documented as not acknowledged" not in text


def test_3_condition_traced_across_several_steps(page):
    go(page, "lanes")
    page.select_option("#trace-select", "k1")
    rings = page.locator("#lane-frame .trace-ring").count()
    assert rings >= 3
    cond = page.inner_text("#cond-list")
    assert re.search(r"traced across\s*step 5 .*→ step 6 .*→ step 7", cond, re.I)


def test_4_actions_and_measures_related_to_a_condition(page):
    text = report_text(page)
    section_e = text.split("E. Improvement opportunities")[1].split("F. Evidence limitations")[0]
    line = [ln for ln in section_e.splitlines() if ln.startswith("The nurse responsible for the patient receives")][0]
    assert "Action 1" in line and "Action 2" in line
    assert "% critical results acknowledged by the responsible nurse" in line


def test_5_revised_workflow_compared_without_overwriting(page):
    go(page, "timeline")
    page.click('#ver-list button:has-text("Compare with current")')
    diff = page.inner_text("#ver-diff")
    assert "Step added" in diff and "Took the critical result call" in diff
    assert "acknowledgment not established → acknowledged" in diff
    assert "Condition changed" in diff
    data = page.evaluate("icaReviewData()")
    assert len(data["versions"][0]["snapshot"]["steps"]) == len(data["steps"]) - 1


def test_6_human_readable_report_with_uncertainty(page):
    text = report_text(page)
    for heading in ["ICA conditions analysis", "A. Process conditions identified", "B. Observed discrepancies", "C. Boundary and transmission analysis",
                    "D. Functional consequences", "E. Improvement opportunities", "F. Evidence limitations"]:
        assert heading in text
    assert "{" not in text and '"id"' not in text
    assert "Open question: Did the day nurse see the board before handover?" in text
    assert "was acknowledged, so the handoff was procedurally complete" in text


def test_7_same_data_same_report(page, base_url):
    first = report_text(page)
    data = page.evaluate("JSON.stringify(icaReviewData())")
    page.goto(base_url + "#save")
    page.wait_for_selector("#load-paste")
    page.fill("#load-paste", data)
    page.click("#load-btn")
    assert report_text(page) == first
    assert json.loads(data)["conditions"][0]["id"] == "k1"


def test_8_no_unpublished_doctrine_in_the_page(page):
    html = page.content()
    for phrase in ["Source Orientation", "Regime", "elemental", "Fire", "Water", "Earth", "Air ", "Space"]:
        assert phrase not in html, phrase


def test_9_no_gatr_decision(page):
    html = page.content()
    assert "GATR" not in html and "admissib" not in html.lower()
    go(page, "actions")
    assert "it makes no authorization decision" in page.text_content("#act-form")


def test_10_existing_pages_intact(page):
    for stage in ["event", "timeline", "lanes", "ownership", "causes", "risks", "drivers", "actions", "measure", "summary", "save"]:
        go(page, stage)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), stage
    assert page.locator("#lane-frame .step-dot").count() == 10
    assert page.locator("#fm-table tbody tr").count() == 4
    assert page.locator("#drv-chart svg rect").count() >= 9
    assert page.locator("#run-chart svg").count() == 1
    assert page.errors == []


def test_old_review_files_still_load(page, base_url):
    old = page.evaluate("""(() => { const o = icaReviewData(); delete o.conditions; delete o.versions; delete o.aim; delete o.drivers; delete o.failures;
        o.actions.forEach(a => { delete a.conditions; delete a.drivers; }); return JSON.stringify(o); })()""")
    page.goto(base_url + "#save")
    page.fill("#load-paste", old)
    page.click("#load-btn")
    assert page.inner_text("#load-msg") == "Review loaded."
    assert page.evaluate("icaReviewData().conditions.length") == 0
    assert "Executive summary" in report_text(page)
