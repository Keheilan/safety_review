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
    assert page.locator("#fm-table tbody tr").count() == 5
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


def test_conditions_panel_shows_what_the_analysis_adds(page):
    panel = page.inner_text("#adds-event")
    assert "What the conditions analysis adds" in panel
    assert "Step 7 (19:00, Day nurse to Night nurse)" in panel and "Step 2 (15:20" not in panel
    assert "On-call surgical resident expected to act but could not" in panel
    assert "Charge nurse could act but was not clearly expected to" in panel
    assert "A named role escalates again" in panel
    text = report_text(page)
    assert text.index("What the conditions analysis adds") < text.index("Executive summary")


def test_collapsed_responsibility_boxes_show_their_result(page):
    go(page, "ownership")
    lines = page.locator("#duty-dims .dim-line").all_inner_texts()
    assert lines[0] == "2 mismatches · 2 conflicts · escalation: Not defined when the resident is in theatre"
    assert lines[1].startswith("not yet answered")
    box = page.locator("#duty-dims details").first
    assert box.evaluate("d => d.open") is False
    assert box.bounding_box()["height"] < 80


# ---- Independent pressure-test decision, P0 and P2 ----

def load_modified(pg, base_url, js):
    """Load the example case after changing it with a JavaScript expression on `o`."""
    data = pg.evaluate("(() => { const o = icaReviewData(); " + js + "; return JSON.stringify(o); })()")
    pg.goto(base_url + "#save")
    pg.wait_for_selector("#load-paste")
    pg.fill("#load-paste", data)
    pg.click("#load-btn")
    assert pg.inner_text("#load-msg") == "Review loaded."


def section(text, start, end):
    return text.split(start)[1].split(end)[0]


def test_p0_1_uncertain_responsibility_is_not_reported_as_disclaimed(page):
    text = report_text(page)
    where = section(text, "Where the work did not connect", "ICA conditions analysis")
    disclaimed = section(where, "every answering role said belonged to another role", "Responsibilities with ownership uncertain")
    uncertain = where.split("Responsibilities with ownership uncertain")[1]
    assert "Acting on the critical lactate result" in disclaimed
    assert "Resolving the antibiotic allergy question" not in disclaimed
    assert "Resolving the antibiotic allergy question" in uncertain
    assert "not a finding that nobody owned it" in uncertain
    assert "1 shared responsibility that no role claimed while at least one role was unsure" in text


def test_p0_2_receipt_failed_unknown_and_unlinked_are_separate(page, base_url):
    text = report_text(page)
    where = section(text, "Handoffs whose receipt is not established", "Responsibilities every")
    assert "Allergy question" in where and "Critical lactate result, via the ward board" in where
    # the handover was acknowledged: received, but nothing later is linked. That is a timeline gap, not a receipt finding.
    assert "Patient handover" not in where
    c = section(text, "C. Boundary and transmission analysis", "D. Functional consequences")
    assert "(Patient handover): received (shown by the acknowledgment), but no later step in the receiving role is linked" in c
    load_modified(page, base_url, 'o.steps.find(s => s.id === "s6").recv = "no"; o.steps.find(s => s.id === "s6").recvEvidence = "Day nurse interview"; o.steps.find(s => s.id === "s5").recv = "no"')
    text = report_text(page)
    assert "Handoffs documented as not received" in text
    assert "Critical lactate result, via the ward board (evidence: Day nurse interview)" in text
    conflict = section(text, "Records that disagree", "Responsibilities every")
    assert "Critical lactate result 3.8 mmol/L: documented as not received, but acknowledgment is recorded as confirmed" in conflict


def test_p0_3_no_total_rpn(page):
    go(page, "risks")
    assert "Total RPN" not in page.inner_text("#s-risks")
    text = report_text(page)
    assert "Total RPN" not in text and "RPNs are not added up" in text
    assert "Severity" in section(text, "Prospective failure-mode analysis", "Improvement aim")


def test_p0_4_goal_needs_a_recorded_direction(page, base_url):
    text = report_text(page)
    assert "The goal has not yet been reached in any period." in text
    load_modified(page, base_url, 'o.measures.forEach(m => { delete m.direction; })')
    text = report_text(page)
    assert "not read as reached or not reached" in text
    assert "has not yet been reached" not in text and "has been reached" not in text
    assert "a goal but no recorded direction of improvement" in text
    go(page, "measure")
    assert "Improvement direction not recorded" in page.inner_text("#run-signals")


def test_p0_5_baseline_excludes_points_after_a_change(page, base_url):
    text = report_text(page)
    aim = section(text, "Improvement aim", "Actions and results so far")
    assert "Before any recorded change · Wk 1–Wk 2, 2 points" in aim
    assert "Wk 1–Wk 6" not in aim
    assert "With Action 3 · Wk 3–Wk 6, 4 points" in aim and "With Action 3 + Action 1 · Wk 7–Wk 12, 6 points" in aim
    # no recorded start: no baseline is invented
    load_modified(page, base_url, 'o.actions.forEach(a => { a.start = ""; })')
    aim = section(report_text(page), "Improvement aim", "Actions and results so far")
    assert "no baseline or before-and-after comparison is made" in aim and "Before any recorded change" not in aim


def test_p0_6_overlapping_changes_are_not_credited_to_one_action(page, base_url):
    text = report_text(page)
    row = section(text, "Action 1. Send critical results", "Action 2.")
    assert "Median 51.5% in Wk 3–Wk 6, 4 points (with Action 3 already started); 73.5% in Wk 7–Wk 12" in row
    assert "Action 3 began earlier and has no recorded end, so the difference is not this action alone" in row
    load_modified(page, base_url, 'o.actions.find(a => a.id === "a2").measureId = "m1"; o.actions.find(a => a.id === "a2").start = "Wk 7"')
    text = report_text(page)
    rows = section(text, "Actions and results so far", "Items requiring")
    assert "Action 2 started at the same point, so this change cannot be separated from it" in rows
    assert "Action 1 started at the same point" in rows
    assert "Changes overlap in time" in text


def test_p2_hierarchy_mechanism_and_prompts(page):
    go(page, "actions")
    assert "New device with usability testing" in page.inner_text("#tiers")
    page.select_option("#act-type", "intermediate:Software enhancement")
    assert "An alert that can be dismissed works like a warning" in page.inner_text("#act-type-prompt")
    go(page, "causes")
    page.fill("#stmt-cause", "the nurse forgot to call")
    page.fill("#stmt-effect", "x")
    lint = page.inner_text("#stmt-lint")
    assert lint.startswith("Prompt:") and "Check:" not in lint
    text = report_text(page)
    assert "Proposed workflow, after the changes" in text and "Result sent to a phone no nurse is holding" in text
    assert "How it works: Routes the result to the responsible nurse" in text


def test_p3_missing_and_incomplete_inputs_do_not_break_the_report(page, base_url):
    load_modified(page, base_url, 'o.steps.forEach(s => { delete s.ack; delete s.recv; delete s.wait; }); o.duties.forEach(d => { d.claims = {}; delete d.dims; }); o.measures[0].points = o.measures[0].points.slice(0, 1); o.actions[0].start = "Week 99"; o.failures.forEach(f => { f.occ = null; })')
    text = report_text(page)
    assert "Executive summary" in text and "{" not in text
    assert "No role has answered yet for: Acting on the critical lactate result" in text
    assert "fewer than two data points" in text
    go(page, "actions")
    assert "Starts at Week 99, which is not a data point yet" in page.inner_text("#act-list")
    assert page.errors == []
