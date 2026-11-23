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
        pg.wait_for_selector("nav.stages a[aria-current=page]")
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
    go(page, "summary")
    tallies = page.text_content("#overview")
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
    for heading in ["Conditions analysis", "A. Process conditions identified", "B. Observed discrepancies", "C. Boundary and transmission analysis",
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
    go(page, "summary")
    panel = page.inner_text("#report section.adds")
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
    where = section(text, "Where the work did not connect", "Conditions analysis")
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


# ---- Navigation UX revision ----

STAGE_ORDER = ["event", "timeline", "lanes", "ownership", "causes", "risks", "drivers", "actions", "measure", "summary"]


def test_nav_four_groups_in_order_with_existing_hashes(page):
    groups = [g.strip() for g in page.locator("nav.stages .grp").all_inner_texts()]
    assert [g.upper() for g in groups[:4]] == ["RECONSTRUCT", "ANALYZE", "IMPROVE", "REPORT"]
    hrefs = page.eval_on_selector_all("nav.stages ol[aria-labelledby] a", "as => as.map(a => a.getAttribute('href'))")
    assert hrefs == ["#" + s for s in STAGE_ORDER]
    assert page.locator('nav.stages a[href="#save"]').count() == 1


def test_active_stage_is_highlighted(page):
    for stage in ["timeline", "risks", "summary"]:
        go(page, stage)
        current = page.eval_on_selector_all('nav.stages a[aria-current="page"]', "as => as.map(a => a.getAttribute('href'))")
        assert current == ["#" + stage]
    assert page.get_attribute("#top-summary", "aria-current") == "page"


def test_sidebar_collapses_to_an_icon_rail(page):
    go(page, "lanes")
    before = page.locator(".content").bounding_box()["width"]
    page.click("#side-collapse")
    assert page.get_attribute("#side-collapse", "aria-expanded") == "false"
    assert page.locator("#side").bounding_box()["width"] < 90
    assert page.locator(".content").bounding_box()["width"] > before + 120
    # labels stay available to assistive technology in the rail
    assert page.locator('nav.stages a[href="#ownership"]').get_attribute("title") == "Shared responsibilities"
    assert "Shared responsibilities" in page.text_content('nav.stages a[href="#ownership"]')
    page.reload(); page.wait_for_selector("nav.stages a[aria-current=page]")
    assert page.evaluate("document.body.classList.contains('rail')")
    page.click("#side-collapse")
    assert page.locator("#side").bounding_box()["width"] > 200


def test_summary_reachable_from_every_stage(page):
    for stage in STAGE_ORDER + ["save"]:
        go(page, stage)
        assert page.is_visible("#top-summary")
    page.click("#top-summary")
    page.wait_for_selector("#s-summary:not([hidden])")


def test_entered_and_open_evidence_shown_separately_without_status(page):
    meta = page.inner_text('nav.stages a[href="#timeline"] .meta')
    assert "10 steps" in meta and "evidence open: 11" in meta
    assert "evidence open" not in page.inner_text('nav.stages a[href="#drivers"] .meta')
    side = page.inner_text("#side").lower()
    for word in ["approved", "complete ", "completed", "safe ", "passed", "✓"]:
        assert word not in side, word
    assert "not an approval or a safety status" in side


def test_event_page_shows_no_later_stage_findings(page):
    ev = page.text_content("#s-event")
    for phrase in ["What the conditions analysis adds", "unchecked assumptions", "not acknowledged", "failure modes with no action"]:
        assert phrase not in ev, phrase
    assert page.locator("#s-event .tally").count() == 0


def test_contextual_links_open_the_source_record(page):
    go(page, "actions")
    page.click('#act-list [data-ref="action:a1"] a[data-goto="condition:k1"]')
    page.wait_for_selector("#s-lanes:not([hidden])")
    assert page.input_value("#trace-select") == "k1"
    assert page.evaluate("document.activeElement.dataset.ref") == "condition:k1"
    go(page, "risks")
    page.click('#fm-table [data-ref="failure:f2"] a[data-goto="handoff:s7"]')
    page.wait_for_selector("#s-lanes:not([hidden])")
    assert "Patient handover" in page.inner_text("#step-detail")
    assert page.evaluate("document.activeElement.dataset.id") == "s7"
    go(page, "drivers")
    page.click('#drv-list [data-ref="driver:p1"] a[data-goto="duty:d1"]')
    page.wait_for_selector("#s-ownership:not([hidden])")
    assert page.evaluate("document.activeElement.dataset.ref") == "duty:d1"


def test_keyboard_skip_link_and_focus_moves_to_the_stage(page):
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip"
    page.focus('nav.stages a[href="#causes"]')
    page.keyboard.press("Enter")
    page.wait_for_selector("#s-causes:not([hidden])")
    assert page.evaluate("document.activeElement.closest('section') && document.activeElement.closest('section').id") == "s-causes"
    assert page.evaluate("document.activeElement.tagName") == "H2"


def test_back_and_forward_keep_unsaved_input(page):
    go(page, "timeline")
    page.fill("#st-what", "Draft step not yet saved")
    page.click('nav.stages a[href="#lanes"]')
    page.wait_for_selector("#s-lanes:not([hidden])")
    page.go_back()
    page.wait_for_selector("#s-timeline:not([hidden])")
    assert page.input_value("#st-what") == "Draft step not yet saved"
    assert page.eval_on_selector_all('nav.stages a[aria-current="page"]', "as => as.map(a => a.getAttribute('href'))") == ["#timeline"]
    page.go_forward()
    page.wait_for_selector("#s-lanes:not([hidden])")
    assert page.evaluate("location.hash") == "#lanes"


def test_small_screen_drawer(base_url):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 375, "height": 760}, has_touch=True)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base_url + "#event")
        pg.wait_for_selector("#menu-btn")
        assert pg.is_visible("#menu-btn") and not pg.is_visible("#side")
        for stage in STAGE_ORDER + ["save"]:
            pg.evaluate(f"location.hash = '{stage}'")
            pg.wait_for_selector(f"#s-{stage}:not([hidden])")
            assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), stage
        pg.evaluate("location.hash = 'event'"); pg.wait_for_selector("#s-event:not([hidden])")
        pg.click("#menu-btn")
        pg.wait_for_selector("#side", state="visible")
        assert pg.get_attribute("#menu-btn", "aria-expanded") == "true"
        assert pg.evaluate("document.activeElement.getAttribute('href')") == "#event"
        pg.keyboard.press("Escape")
        pg.wait_for_selector("#side", state="hidden")
        assert pg.evaluate("document.activeElement.id") == "menu-btn"
        pg.click("#menu-btn")
        pg.wait_for_selector("#side", state="visible")
        pg.click('nav.stages a[href="#measure"]')
        pg.wait_for_selector("#s-measure:not([hidden])")
        pg.wait_for_selector("#side", state="hidden")
        assert pg.evaluate("document.activeElement.tagName") == "H2"
        assert pg.inner_text("#menu-label") == "Measure"
        assert errors == []
        b.close()


def test_no_stage_numbers_suggesting_a_fixed_order(page):
    import re as _re
    side = page.inner_text("#side")
    assert not _re.search(r"\d+\s*\n?\s*(Event|Timeline|Swimlanes|Causes|Summary)\b", side)
    assert page.locator("nav.stages a .ic svg").count() == 11
    body = page.evaluate("(() => { const c = document.body.cloneNode(true); c.querySelectorAll('script').forEach(s => s.remove()); return c.textContent; })()")
    assert not _re.search(r"\b[Ss]tages? \d+", body)


def test_page_contacts_no_other_host_and_fonts_load(base_url):
    from urllib.parse import urlparse
    host = urlparse(base_url).netloc
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        hosts = set()
        pg.on("request", lambda r: hosts.add(urlparse(r.url).netloc) if r.url.startswith("http") else None)
        for stage in STAGE_ORDER + ["save"]:
            pg.goto(base_url + "#" + stage)
            pg.wait_for_selector(f"#s-{stage}:not([hidden])")
        pg.evaluate("document.fonts.ready")
        assert hosts == {host}, hosts
        for fam in ["16px 'Atkinson Hyperlegible'", "700 16px 'Atkinson Hyperlegible'"]:
            assert pg.evaluate(f"document.fonts.check(\"{fam}\")"), fam
        loaded = pg.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/\"/g, ''))")
        assert set(loaded) == {"Atkinson Hyperlegible"}
        b.close()


def test_named_seamline(page):
    assert page.title() == "Event · Seamline"
    assert page.inner_text("header.top h1") == "Seamline Process Intelligence & Safety Improvement"
    text = report_text(page)
    assert text.startswith("SEAMLINE · SAFETY IMPROVEMENT REVIEW") or "Seamline · Safety improvement review" in text
    assert "Prepared with Seamline" in text and "ICA Safety Review" not in page.content()
    go(page, "save")
    assert "Trace the conditions behind continuity." in page.inner_text("#s-save")


def test_one_typeface_and_regular_weight_inputs(page):
    families = page.evaluate("""[...new Set([...document.querySelectorAll('body *')].filter(e => e.offsetParent !== null || e.tagName === 'text').map(e => getComputedStyle(e).fontFamily.split(',')[0].replace(/["']/g, '').trim()))]""")
    assert families == ["Atkinson Hyperlegible"], families
    go(page, "timeline")
    assert page.eval_on_selector("#st-role", "e => getComputedStyle(e).fontWeight") == "400"
    assert page.eval_on_selector("#st-what", "e => getComputedStyle(e).fontWeight") == "400"


def test_stage_heading_draws_no_box_over_its_label(page):
    page.focus('nav.stages a[href="#timeline"]')
    page.keyboard.press("Enter")
    page.wait_for_selector("#s-timeline:not([hidden])")
    assert page.evaluate("document.activeElement.tagName") == "H2"
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") == "none"
    eb = page.locator("#s-timeline .eyebrow").first.bounding_box(); h2 = page.locator("#s-timeline h2").bounding_box()
    assert eb["y"] + eb["height"] <= h2["y"] + 1


def test_security_policy_blocks_sending_and_allows_normal_use(base_url):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(accept_downloads=True)
        pg = ctx.new_page()
        pg.add_init_script("window.__violations = []; document.addEventListener('securitypolicyviolation', e => window.__violations.push(e.violatedDirective + ' ' + e.blockedURI));")
        errors, outside = [], []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("requestfinished", lambda r: outside.append(r.url) if "example.com" in r.url else None)
        pg.goto(base_url + "#event")
        pg.wait_for_selector("nav.stages a[aria-current=page]")
        assert "connect-src 'none'" in pg.get_attribute('meta[http-equiv="Content-Security-Policy"]', "content")
        # normal use: every stage, a step, a saved file, a reload of the data
        for stage in STAGE_ORDER + ["save"]:
            pg.evaluate(f"location.hash = '{stage}'")
            pg.wait_for_selector(f"#s-{stage}:not([hidden])")
        pg.evaluate("location.hash = 'timeline'"); pg.wait_for_selector("#s-timeline:not([hidden])")
        pg.fill("#st-time", "23:00"); pg.fill("#st-what", "Test step"); pg.click("#st-save")
        pg.evaluate("location.hash = 'save'"); pg.wait_for_selector("#s-save:not([hidden])")
        with pg.expect_download() as d:
            pg.click("#save-file")
        assert d.value.suggested_filename.endswith(".seamline.json")
        assert pg.evaluate("window.__violations") == []
        assert errors == []
        # sending anything to another site is refused by the browser
        assert pg.evaluate("fetch('https://example.com/collect', {method: 'POST', body: 'x'}).then(() => 'sent', () => 'blocked')") == "blocked"
        pg.evaluate("navigator.sendBeacon('https://example.com/collect', 'x')")
        pg.evaluate("new Image().src = 'https://example.com/pixel.gif'")
        pg.wait_for_timeout(300)
        v = pg.evaluate("window.__violations")
        assert any(x.startswith("connect-src") for x in v) and any(x.startswith("img-src") for x in v), v
        assert sum(x.startswith("connect-src") for x in v) >= 2, v  # the fetch and the beacon
        assert outside == [], outside
        # a script injected into the page does not run
        pg.evaluate("const s = document.createElement('script'); s.textContent = 'window.__injected = true'; document.body.appendChild(s)")
        assert pg.evaluate("window.__injected === true") is False
        b.close()
