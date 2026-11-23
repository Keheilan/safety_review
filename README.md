# Seamline

**Process Intelligence & Safety Improvement.** Trace the conditions behind continuity.

Seamline is a guided review of a patient-safety event that runs entirely in the browser.

It builds role swimlanes from a timeline, shows handoffs and the steps that waited on others, surfaces hidden assumptions and responsibilities that no role believed were theirs, and supports cause and effect analysis, causal statements, failure modes and effects analysis (FMEA) on the same steps and handoffs, a driver diagram, an action plan grouped by strength, and run charts that mark when each action's test started. Every action can be traced back to the findings it came from and forward to its measured result.

Process conditions record what had to be true for the work to function, what was observed, and the evidence, using six provisional process domains. Missing evidence is reported as "not established", never as a confirmed failure. A condition can be traced across several steps, linked to actions, drivers, failure modes and measures, and summarized in the report's conditions analysis. Saved workflow versions let a revised timeline be compared with the original without overwriting it.

The ten stages sit in a left sidebar in four groups (Reconstruct, Analyze, Improve, Report). Stages are marked with icons rather than numbers, because a review does not have to follow them in order. The sidebar collapses to an icon rail for wide diagrams and becomes a drawer on small screens. Under each stage it shows what has been entered and how much evidence is still open; these counts are not an approval or a safety status. Records link to related records in other stages, and the Summary is one click away from every stage.

How findings are kept honest:

- A responsibility every answering role disclaimed is reported apart from one where no role claimed it and at least one role was unsure.
- Receipt of a handoff comes from a receipt record, an acknowledgment, or a linked step in the receiving role. A handoff documented as not received, one whose receipt is not established, and a received handoff with no later step linked are reported separately. Records that disagree are both kept and shown.
- A measure's goal is read only when the team has recorded whether a higher or lower value is better. No baseline uses points after a recorded change. Each period of a run chart lists every change started by then, and where changes overlap the result is not credited to any one action. Before-and-after medians show timing, not cause.
- FMEA shows severity on its own beside the RPN, never adds RPNs together, and separates the current workflow from the proposed one.

Live page: https://tools.confluencecocenter.org

## Tests

Acceptance tests run the page in a real browser with Playwright:

    python -m pytest tests/test_acceptance.py -q

## Privacy

For fictional or de-identified cases only. Nothing is sent or stored by the page. A review leaves the browser only when the user copies it out.

The page loads nothing from other sites: its fonts are served from this repository (`fonts/`), and there are no analytics, trackers or external scripts. An automated test checks that every request the page makes goes to its own site. The site is hosted on GitHub Pages, which, like any web host, receives the visitor's IP address when the page is requested.

The fonts (Atkinson Hyperlegible, IBM Plex Mono, Newsreader) are licensed under the SIL Open Font License 1.1; the license texts are in `fonts/`.

## Methods

The tool follows quality improvement methods described by the Institute for Healthcare Improvement (QI Essentials Toolkit: cause and effect diagram, flowchart, FMEA, driver diagram, run chart) and the RCA² approach to root cause analysis. All wording is original. This project is not affiliated with or endorsed by IHI.

It does not decide root causes, rate anyone's performance, or determine fault. FMEA ratings are entered by the team; the tool only multiplies them to rank the team's own ratings, and the result does not decide whether a risk is acceptable. Action types follow the RCA² action hierarchy as paraphrased in the tool; prompts ask the team to classify an action by what it does to the work, not by the technology it uses. Causal-statement wording prompts read words only and do not validate a statement.
