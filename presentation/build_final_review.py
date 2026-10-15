"""Build the final-review deck: introduction -> problem -> objectives -> dataset -> methodology ->
operations research technique -> expected outcome.

    python presentation/build_final_review.py      (run after run_pipeline.py; numbers are read from outputs/)
"""
import json
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
S = json.loads((OUT / "reports" / "summary.json").read_text())
T = OUT / "tables"

TITLE_FONT, BODY_FONT = "Cambria", "Calibri"
INK, INK2, MUTED = RGBColor(0x11, 0x11, 0x11), RGBColor(0x44, 0x44, 0x44), RGBColor(0x76, 0x76, 0x76)
PANEL = RGBColor(0xDC, 0xE6, 0xF2)        # light-blue panel of the team deck
NAVY = RGBColor(0x1F, 0x38, 0x64)
ORANGE = RGBColor(0xC8, 0x4B, 0x1C)
GREY = RGBColor(0x89, 0x87, 0x81)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def n(v, d=0):
    return f"{v:,.{d}f}"


# --------------------------------------------------------------------------- helpers
def slide(title, notes):
    s = prs.slides.add_slide(BLANK)
    tb = s.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12.1), Inches(0.9))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = 0
    p = tf.paragraphs[0]
    p.text = title.upper()
    p.font.name, p.font.size, p.font.color.rgb = TITLE_FONT, Pt(36), INK
    s.notes_slide.notes_text_frame.text = notes
    return s


def text(s, x, y, w, h, items, size=16, color=INK2, bold_first=False, bullets=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, font=BODY_FONT, space=6):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    items = [items] if isinstance(items, str) else items
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        runs = it if isinstance(it, list) else [(it, {})]
        if bullets:
            runs = [("•  ", {})] + runs
        for txt, o in runs:
            r = p.add_run()
            r.text = txt
            r.font.name = o.get("font", font)
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold_first and i == 0)
            r.font.italic = o.get("italic", False)
            r.font.color.rgb = o.get("color", color)
    return tb


def box(s, x, y, w, h, fill=PANEL, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, label=None, size=15,
        color=INK, bold=False, align=PP_ALIGN.CENTER):
    sh = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(1.25)
    st_el = sh._element.find(qn("p:style"))
    if st_el is not None:
        sh._element.remove(st_el)
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:          # ~0.15" corner radius whatever the size
        sh.adjustments[0] = min(0.1, 0.15 / min(w, h))
    if label is not None:
        tf = sh.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = tf.margin_right = Inches(0.1)
        lines = label if isinstance(label, list) else [label]
        for i, ln in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            r = p.add_run()
            r.text = ln
            r.font.name, r.font.size, r.font.color.rgb = BODY_FONT, Pt(size if i == 0 else size - 2), color
            r.font.bold = bold and i == 0
    return sh


def arrow(s, x1, y1, x2, y2, color=GREY, width=2.0):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def elbow(s, pts, color=ORANGE, width=2.25):
    """Polyline through `pts` with an arrowhead on the last segment."""
    for (x1, y1), (x2, y2) in zip(pts[:-2], pts[1:-1]):
        c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
        c.line.color.rgb, c.line.width = color, Pt(width)
    arrow(s, *pts[-2], *pts[-1], color=color, width=width)


def stat(s, x, y, w, value, label, color=NAVY, size=36):
    text(s, x, y, w, 0.75, [[(value, {"size": size, "bold": True, "color": color, "font": TITLE_FONT})]])
    text(s, x, y + 0.75, w, 0.7, label, size=14, color=INK2)


def num_badge(s, x, y, label, d=0.6, fill=NAVY):
    box(s, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL, label=label, size=18, color=WHITE, bold=True)


def table(s, x, y, w, rows, col_w, size=14, row_h=0.42):
    gt = s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
                            Inches(row_h * len(rows))).table
    for j, cw in enumerate(col_w):
        gt.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            cell = gt.cell(i, j)
            cell.text = str(v)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if i == 0 else (WHITE if i % 2 else RGBColor(0xF3, 0xF6, 0xFA))
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            para = cell.text_frame.paragraphs[0]
            para.font.name, para.font.size = BODY_FONT, Pt(size)
            para.font.bold = i == 0
            para.font.color.rgb = WHITE if i == 0 else INK
    return gt


b, m1, m2 = S["bottlenecks"], S["model1"], S["model2"]
h, cap = S["headline"], int(S["parameters"]["section_capacity"])
vr = S["validation_repeat_flow"]["course_specific"]
lp, ahp = S["lp_sensitivity"], S["ahp"]

# 0. Title -----------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
box(s, 0, 0, 13.333, 7.5, fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
text(s, 0.9, 1.6, 11.5, 0.5, "OPERATIONS RESEARCH  ·  FINAL REVIEW", size=16, color=PANEL)
text(s, 0.9, 2.2, 11.5, 2.2, [[("University Curriculum Flow and Capacity Planning", {"font": TITLE_FONT, "size": 44, "bold": True,
                                                                                    "color": WHITE})]])
text(s, 0.9, 4.1, 11.5, 1.0, "Forecasting course demand with System Dynamics and allocating class sections "
                             "with Integer and Binary Programming", size=20, color=PANEL)
text(s, 0.9, 5.7, 11.5, 0.5, "Dataset: StudentDropoutDataset (Zenodo 10.5281/zenodo.17239943)  ·  Team of 4",
     size=14, color=PANEL)
s.notes_slide.notes_text_frame.text = ("Introduce the team and the one-line idea: we forecast how many students "
                                       "each course will have next year and decide how many sections to open.")

# 1. Introduction ------------------------------------------------------------------------
s = slide("Introduction",
          "Every year a university must decide how many class sections to open per course. Demand is not just "
          "new students: students who fail come back, and students who could not get a seat come back too. "
          "Operations Research turns this into a forecast plus an optimal decision.")
text(s, 0.6, 1.5, 5.6, 4.8, [
    [("Every year a university decides ", {}), ("how many sections", {"bold": True, "color": NAVY}),
     (" (class groups) to open for each course.", {})],
    [("Each section has a ", {}), ("limited number of seats", {"bold": True, "color": NAVY}), (".", {})],
    [("Next year's students = ", {}), ("new students + repeaters + students left without a seat", {"bold": True, "color": NAVY}),
     (".", {})],
    [("Too few sections leave students waiting; too many waste teachers and rooms.", {})],
    [("We combine a ", {}), ("forecast", {"bold": True, "color": NAVY}), (" with an ", {}),
     ("optimisation model", {"bold": True, "color": NAVY}), (" to plan sections.", {})],
], size=18, bullets=True, space=14)
for i, (lab, sub) in enumerate([("New students", "first-time enrolments"), ("Repeaters", "failed and re-enrol"),
                                ("Left without a seat", "unserved last year")]):
    y = 1.6 + i * 1.45
    box(s, 6.9, y, 2.6, 1.05, label=[lab, sub], size=17, bold=True)
    arrow(s, 9.5, y + 0.52, 10.25, 3.17)
box(s, 10.3, 2.6, 2.4, 1.15, fill=NAVY, label=["Course demand", "next year"], size=18, color=WHITE, bold=True)
arrow(s, 11.5, 3.75, 11.5, 4.55)
box(s, 10.3, 4.6, 2.4, 1.15, fill=WHITE, line=NAVY, label=["Sections × seats", "our decision"], size=17, bold=True)
text(s, 6.9, 6.05, 5.8, 0.6, "The two return flows make demand grow when capacity is short.", size=14, color=MUTED)

# 2. Problem statement -------------------------------------------------------------------
s = slide("Problem Statement",
          "Read the statement, then walk through the small example: with fixed seats, the shortage doubles in "
          "one year because failed and unserved students come back.")
box(s, 0.6, 1.5, 12.1, 1.35, fill=PANEL)
text(s, 0.9, 1.62, 11.5, 1.15, [[("How many sections should each of the university's 3,787 active courses open next "
                                   "year so that every student who needs the course gets a seat, using as few sections "
                                   "as possible or a limited budget of extra sections?", {"size": 20, "color": INK})]],
     anchor=MSO_ANCHOR.MIDDLE)
text(s, 0.6, 3.15, 6.0, 0.5, "Why it is hard: the shortage snowballs", size=20, color=NAVY, bold_first=True)
table(s, 0.6, 3.7, 6.3, [["Year", "New", "Repeat", "Left over", "Demand", "Seats", "No seat"],
                          ["Year 1", "100", "0", "0", "100", "100", "0"],
                          ["Year 2", "100", "30", "0", "130", "100", "30"],
                          ["Year 3", "100", "30", "30", "160", "100", "60"]],
      [0.95, 0.75, 0.9, 1.05, 0.95, 0.8, 0.9], size=15)
text(s, 0.6, 5.55, 6.3, 0.8, "Illustration: one course with 2 sections × 50 seats and no planning.", size=14,
     color=MUTED)
text(s, 7.4, 3.15, 5.3, 0.5, "Questions we answer", size=20, color=NAVY, bold_first=True)
for i, q in enumerate(["Which courses will be over-full next year?",
                       "What is the minimum number of sections that seats everyone?",
                       "With only B extra sections, which courses should get them?"]):
    y = 3.75 + i * 0.95
    num_badge(s, 7.4, y, str(i + 1), d=0.55)
    text(s, 8.15, y - 0.02, 4.6, 0.8, q, size=17, color=INK, anchor=MSO_ANCHOR.MIDDLE)

# 3. Objectives ----------------------------------------------------------------------------
s = slide("Objectives",
          "Five objectives, each delivered by a part of the project: data, forecast, bottlenecks, two optimisation "
          "models and the user interface.")
objs = [("Prepare the data", "Clean and link 464,739 student-course records across 2018, 2021 and 2022."),
        ("Forecast course demand", "Build a System Dynamics model of student flow to project 2023 demand per course."),
        ("Find capacity bottlenecks", "Flag courses whose forecast demand exceeds their seats."),
        ("Optimise section allocation", "Integer Programming for the minimum sections; Binary Programming for a "
                                        "limited budget of extra sections."),
        ("Support decisions interactively", "A UI to load data, generate statistics on demand, choose a model and "
                                            "change capacity, growth and budget.")]
for i, (a, d) in enumerate(objs):
    y = 1.5 + i * 1.08
    num_badge(s, 0.6, y + 0.08, str(i + 1))
    text(s, 1.45, y, 11.3, 1.0, [[(a, {"bold": True, "color": NAVY, "size": 20})], d], size=16, color=INK, space=2)

# 4. Dataset information ---------------------------------------------------------------------
s = slide("Dataset Information",
          "Public dataset from the Universitat Politecnica de Valencia, Spain, published on Zenodo in 2025. All "
          "five counts we loaded match the published description exactly.")
for i, (v, l) in enumerate([(n(h["records"]), "student-course records"), (n(h["students"]), "students"),
                            (n(h["courses"]), "courses"), (str(h["programmes"]), "degree programmes"),
                            ("3", "academic years (2018, 2021, 2022)")]):
    stat(s, 0.6 + i * 2.5, 1.45, 2.35, v, l)
box(s, 0.6, 3.35, 5.9, 3.55, fill=PANEL)
text(s, 0.85, 3.5, 5.4, 3.3, [
    [("Source", {"bold": True, "color": NAVY, "size": 19})],
    [("Name: ", {"bold": True, "color": INK}), ("StudentDropoutDataset", {})],
    [("Publisher: ", {"bold": True, "color": INK}), ("Zenodo, DOI 10.5281/zenodo.17239943 (Oct 2025)", {})],
    [("University: ", {"bold": True, "color": INK}), ("Universitat Politècnica de València, Spain", {})],
    [("Licence: ", {"bold": True, "color": INK}), ("CC BY 4.0, IDs anonymised (hashed)", {})],
    [("Files: ", {"bold": True, "color": INK}), ("3 yearly CSVs, one row = one student in one course", {})],
], size=16, space=8)
text(s, 6.9, 3.4, 5.8, 0.5, "Key facts", size=19, color=NAVY, bold_first=True)
text(s, 6.9, 3.95, 5.8, 3.0, [
    f"Overall pass rate {h['pass_rate']:.0%} (pass mark 5 on a 0–10 scale)",
    f"{S['repeat_burden_2022']['share_of_students']:.0%} of 2022 students were repeating at least one course",
    "2021 → 2022 is the only consecutive pair, used to estimate the flow rates",
    f"Section capacity is not in the data: it is a model parameter (default {cap} seats)",
], size=16, bullets=True, space=10, color=INK)

# 5. Dataset variables -------------------------------------------------------------------------
s = slide("Variables Used from the Dataset",
          "We keep 17 of the dataset's columns. There is no official codebook, so each meaning was verified: the "
          "counts match the publication, and no student who passed a course took it again the next year.")
table(s, 0.6, 1.45, 12.1, [
    ["Raw column", "Meaning (Spanish term)", "Used as", "Purpose in the model"],
    ["dni_hash", "student ID (DNI)", "student_id", "Track each student across years"],
    ["asi_hash", "course (asignatura)", "course_id", "Unit of planning"],
    ["tit_hash", "degree programme (titulación)", "programme_id", "Group courses; fairness cap"],
    ["caca", "academic year (curso académico)", "academic_year", "Link 2021 → 2022"],
    ["nota_asig_hash", "course grade, 0–10", "grade → pass / fail", "Who will need the course again"],
    ["curso_mas_alto", "highest curriculum year", "stage", "Year 1 … Final year stocks"],
    ["cred_pend_sup_tit", "credits still pending", "graduated / withdrawn", "Exit flows of the student model"],
], [2.2, 3.4, 2.6, 3.9], size=15, row_h=0.5)
box(s, 0.6, 5.7, 12.1, 1.15, fill=PANEL)
text(s, 0.85, 5.78, 11.6, 1.0, [[("Derived attributes: ", {"bold": True, "color": NAVY}),
                                 ("outcome (pass ≥ 5, fail, not evaluated), repeat enrolment, first-time students F, "
                                  "backlog B, pass rate π and retake rate ρ for every course.", {})]],
     size=16, color=INK, anchor=MSO_ANCHOR.MIDDLE)

# 6. Methodology pipeline ------------------------------------------------------------------------
s = slide("Methodology",
          "Six steps from raw files to a section plan. The orange arrow is the feedback loop: students still "
          "without a seat return to next year's forecast.")
steps = [("1  Data", "Load 3 files, validate counts"), ("2  Clean", "Fix IDs, label pass / fail, link years"),
         ("3  Statistics", "Pass, repeat and progression rates"), ("4  Forecast (SD)", "2023 demand per course"),
         ("5  Bottlenecks", "Demand vs seats"), ("6  Optimise", "Integer and Binary Programming")]
bw, gap, y0 = 1.8, 0.26, 2.0
for i, (a, d) in enumerate(steps):
    x = 0.6 + i * (bw + gap)
    hl = i in (3, 5)
    box(s, x, y0, bw, 1.9, fill=NAVY if hl else PANEL, label=[a, d], size=17,
        color=WHITE if hl else INK, bold=True)
    if i < len(steps) - 1:
        arrow(s, x + bw, y0 + 0.95, x + bw + gap, y0 + 0.95)
x_sd, x_opt = 0.6 + 3 * (bw + gap) + bw / 2, 0.6 + 5 * (bw + gap) + bw / 2
elbow(s, [(x_opt, y0 + 1.9), (x_opt, 4.55), (x_sd, 4.55), (x_sd, y0 + 1.9)])
text(s, 0.6, 4.35, x_sd - 0.75, 0.5, "Feedback loop: unserved students return to next year's demand",
     size=14, color=ORANGE, align=PP_ALIGN.RIGHT)
box(s, 0.6, 5.35, 12.1, 1.5, fill=WHITE, line=PANEL)
text(s, 0.85, 5.45, 11.6, 1.3, [
    [("User inputs: ", {"bold": True, "color": NAVY}),
     (f"section capacity (default {cap}), demand growth, bottleneck threshold, safety buffer, extra-section budget B, "
      "programme cap, priority weights.", {})],
    [("Tools: ", {"bold": True, "color": NAVY}),
     ("Python (pandas, SciPy HiGHS solver), Streamlit user interface, 32 automated tests.", {})],
], size=16, color=INK, space=8)

# 7. Methodology – System Dynamics forecast --------------------------------------------------------
s = slide("Forecasting Demand with System Dynamics",
          "System Dynamics models stocks and flows. The backlog stock collects students who failed or got no "
          "seat; a share of it returns as demand next year. S = students served, U = students unserved, "
          "π = pass rate, ρ = retake rate. Validated on held-out students.")
box(s, 0.6, 1.6, 2.4, 1.1, label=["New students F", "× (1 + growth g)"], size=17, bold=True)
box(s, 3.7, 1.6, 2.4, 1.1, fill=NAVY, label=["Demand D", "this year"], size=18, color=WHITE, bold=True)
box(s, 6.8, 1.6, 2.6, 1.1, fill=WHITE, line=NAVY, label=["Seats = cap × x", "x from the optimiser"], size=17, bold=True)
box(s, 6.95, 3.6, 2.3, 0.95, fill=WHITE, line=GREY, label=["Passed", "leave the course"], size=16, bold=True)
box(s, 3.7, 4.6, 2.4, 1.1, fill=PANEL, line=ORANGE, label=["Backlog B (stock)", "still need the course"], size=17,
    bold=True)
arrow(s, 3.0, 2.15, 3.7, 2.15)
arrow(s, 6.1, 2.15, 6.8, 2.15)
arrow(s, 8.1, 2.7, 8.1, 3.6)
text(s, 8.2, 2.95, 1.6, 0.4, "π × served", size=14, color=MUTED)
elbow(s, [(7.2, 2.7), (7.2, 3.15), (6.5, 3.15), (6.5, 5.15), (6.1, 5.15)])
text(s, 6.55, 5.25, 2.9, 0.7, "failed + unserved", size=14, color=ORANGE)
elbow(s, [(4.9, 4.6), (4.9, 2.7)])
text(s, 5.0, 3.4, 1.4, 0.7, "ρ × B re-enrol", size=14, color=ORANGE)
text(s, 9.75, 1.55, 3.3, 4.3, [
    [("Equations", {"bold": True, "color": NAVY, "size": 19})],
    [("D = F(1+g) + ρ·B", {"font": TITLE_FONT, "size": 17, "color": INK})],
    [("S = min(D, cap·x),  U = D − S", {"font": TITLE_FONT, "size": 17, "color": INK})],
    [("B(next) = (1−π)·S + U", {"font": TITLE_FONT, "size": 17, "color": INK})],
    [("Validation", {"bold": True, "color": NAVY, "size": 19})],
    f"Student stocks: {S['validation_student_flow_mape']:.1f}% error",
    f"Repeat demand: R² = {vr['R2']:.2f}",
], size=16, color=INK2, space=10)
text(s, 0.6, 6.15, 9.0, 0.6, f"Forecast for 2023: {n(S['projection']['demand'])} seats "
                             f"({n(S['projection']['first_time'])} new + {n(S['projection']['repeat'])} repeat).",
     size=16, color=INK)

# 8. Operations research techniques – overview --------------------------------------------------
s = slide("Operations Research Techniques",
          "Two optimisation models, both chosen by the user in the app. Integer Programming answers how many "
          "sections in total; Binary Programming answers where to put a limited number of extra sections.")
cols = [("Model 1 · Integer Programming", "Minimum Section Allocation",
         [("Decision", "x_c = sections of course c, a whole number"),
          ("Objective", "minimise the total number of sections"),
          ("Constraint", "seats ≥ forecast demand for every course"),
          ("Answers", "the smallest plan that seats every student")]),
        ("Model 2 · Binary Programming", "Limited Additional Capacity Allocation",
         [("Decision", "y_ck = 1 if extra section k of course c is opened, else 0"),
          ("Objective", "maximise the students seated"),
          ("Constraints", "at most B extra sections; open in order; optional cap per programme"),
          ("Answers", "where a limited budget helps most (a 0-1 knapsack)")])]
for i, (head, sub, rows) in enumerate(cols):
    x = 0.6 + i * 6.2
    box(s, x, 1.5, 5.9, 0.95, fill=NAVY, label=[head, sub], size=19, color=WHITE, bold=True)
    box(s, x, 2.55, 5.9, 3.55, fill=PANEL)
    text(s, x + 0.25, 2.7, 5.4, 3.3, [[(f"{a}: ", {"bold": True, "color": NAVY}), (d, {})] for a, d in rows],
         size=17, color=INK, space=14)
text(s, 0.6, 6.3, 12.1, 0.6, [[("Supporting analysis: ", {"bold": True, "color": NAVY}),
                               ("LP sensitivity report (shadow prices) and AHP weights with a consistency check. "
                                "Solver: HiGHS.", {})]], size=16, color=INK)

# 9. Model 1 – Integer Programming ------------------------------------------------------------------
s = slide("Model 1: Integer Programming",
          "Sections are whole classes, so the variable must be an integer. The LP relaxation would allow fractional "
          "sections and understates the requirement by about 550 sections.")
box(s, 0.6, 1.5, 7.2, 2.4, fill=PANEL)
text(s, 0.85, 1.65, 6.8, 2.2, [
    [("Minimise   Σ x_c", {"font": TITLE_FONT, "size": 22, "color": INK})],
    [("subject to   cap · x_c ≥ (1 + β) · D_c    for every course c", {"font": TITLE_FONT, "size": 18, "color": INK})],
    [("x_c ≥ 1 for active courses,   x_c integer", {"font": TITLE_FONT, "size": 18, "color": INK})],
], space=12)
text(s, 0.6, 4.15, 7.2, 2.7, [
    [("x_c", {"bold": True, "color": NAVY}), (" sections of course c (decision)", {})],
    [("D_c", {"bold": True, "color": NAVY}), (" forecast demand from the SD model", {})],
    [("cap", {"bold": True, "color": NAVY}), (f" seats per section (parameter, default {cap})", {})],
    [("β", {"bold": True, "color": NAVY}), (" optional safety buffer, e.g. 0.10 = 10% extra", {})],
], size=17, color=INK, space=10)
stat(s, 8.4, 1.5, 4.3, n(m1["total_sections"]), f"minimum sections at {cap} seats each")
stat(s, 8.4, 3.05, 4.3, f"+{m1['sections_added']} / −{m1['sections_released']}",
     "courses that need one more section / can close one")
stat(s, 8.4, 4.6, 4.3, n(m1["lp_relaxation_sections"], 1), "LP relaxation (fractional): integrality matters")

# 10. Model 2 – Binary Programming -------------------------------------------------------------------
s = slide("Model 2: Binary Programming",
          "Each candidate extra section is a yes/no decision. The chart shows diminishing returns: the first "
          "sections seat many students, later ones very few.")
box(s, 0.6, 1.5, 6.4, 2.75, fill=PANEL)
text(s, 0.85, 1.62, 6.0, 2.55, [
    [("Maximise   Σ w_c · a_ck · y_ck", {"font": TITLE_FONT, "size": 20, "color": INK})],
    [("Σ y_ck ≤ B   (budget)", {"font": TITLE_FONT, "size": 17, "color": INK})],
    [("y_ck ≤ y_c,k−1   (open in order)", {"font": TITLE_FONT, "size": 17, "color": INK})],
    [("Σ_{c∈p} y_ck ≤ M_p   (programme cap)", {"font": TITLE_FONT, "size": 17, "color": INK})],
    [("y_ck ∈ {0, 1}", {"font": TITLE_FONT, "size": 17, "color": INK})],
], space=8)
text(s, 0.6, 4.45, 6.4, 2.4, [
    [("a_ck", {"bold": True, "color": NAVY}), (" students seated by extra section k of course c", {})],
    [("w_c", {"bold": True, "color": NAVY}), (" priority weight: uniform, repeaters, first-year, or AHP", {})],
    [("Result (B = 50): ", {"bold": True, "color": NAVY}),
     (f"unmet demand {n(m2['unmet_demand_before'])} → {n(m2['unmet_demand_after'])} students "
      f"(−{m2['unmet_reduction_pct']:.0f}%)", {"bold": True, "color": INK})],
], size=17, color=INK, space=10)
sb = pd.read_csv(T / "sensitivity_budget.csv")
cd = CategoryChartData()
cd.categories = [str(int(v)) for v in sb["extra_sections"]]
cd.add_series("Students still without a seat", [round(v) for v in sb["unmet_demand_after"]])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(7.3), Inches(1.5), Inches(5.4), Inches(4.6), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Unmet demand vs extra sections B"
ch.chart_title.text_frame.paragraphs[0].font.size = Pt(15)
ch.chart_title.text_frame.paragraphs[0].font.name = BODY_FONT
ch.font.name, ch.font.size = BODY_FONT, Pt(12)
ch.has_legend = False
pl = ch.plots[0]
pl.gap_width = 60
pl.series[0].format.fill.solid()
pl.series[0].format.fill.fore_color.rgb = NAVY
pl.has_data_labels = True
pl.data_labels.number_format, pl.data_labels.number_format_is_linked = "0", False
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
pl.data_labels.font.size = Pt(11)
ch.value_axis.major_gridlines.format.line.color.rgb = RGBColor(0xE1, 0xE0, 0xD9)
ch.value_axis.tick_labels.font.color.rgb = MUTED
ch.category_axis.tick_labels.font.color.rgb = INK2
text(s, 7.3, 6.2, 5.4, 0.6, "Extra sections B (x-axis) vs students still unseated", size=13, color=MUTED)

# 11. Supporting analysis – LP sensitivity and AHP ---------------------------------------------------
s = slide("Sensitivity Analysis and AHP",
          "The shadow price tells the planner what one more section is worth. AHP lets the planner rank the "
          "priority criteria with pairwise comparisons; CR below 0.10 means the judgements are consistent.")
box(s, 0.6, 1.5, 5.95, 5.35, fill=PANEL)
text(s, 0.85, 1.65, 5.5, 0.5, "LP sensitivity report (Model 2)", size=20, color=NAVY, bold_first=True)
stat(s, 0.85, 2.25, 5.5, f"{lp['budget_shadow_price']:.2f}", "shadow price of the budget: students seated by one "
                                                              "more extra section")
text(s, 0.85, 3.9, 5.5, 2.9, [
    f"Section 50 seats {lp['value_of_last_section']:.2f} students; section 51 would seat "
    f"{lp['value_of_next_section']:.2f}",
    "LP objective = IP objective (427.7): the relaxation is already integral",
    "With a cap of 5 per programme, the binding caps have shadow prices 2.55 and 8.25: relaxing them is worth "
    "more than adding budget",
], size=16, bullets=True, color=INK, space=8)
box(s, 6.75, 1.5, 5.95, 5.35, fill=PANEL)
text(s, 7.0, 1.65, 5.5, 0.5, "AHP priority weights (Model 2)", size=20, color=NAVY, bold_first=True)
cw = ahp["criteria_weights"]
table(s, 7.0, 2.3, 5.45, [["Criterion", "Weight"]] + [[k, f"{v:.3f}"] for k, v in cw.items()],
      [3.85, 1.6], size=16, row_h=0.48)
text(s, 7.0, 4.4, 5.5, 2.4, [
    "Pairwise comparisons on Saaty's 1–9 scale",
    "Weights = principal eigenvector",
    f"Consistency ratio CR = {ahp['criteria_cr']:.3f} (≤ 0.10, consistent)",
    "Course weight w_c = 1 + Σ weight × score",
], size=16, bullets=True, color=INK, space=8)

# 12. Expected outcome ------------------------------------------------------------------------------
s = slide("Expected Outcome",
          "Results at 50 seats per section for planning year 2023. These are the numbers the app reproduces; "
          "changing capacity or budget in the app updates them.")
for i, (v, l, c) in enumerate([(str(b["bottleneck_courses"]), f"bottleneck courses in {b['programmes_affected']} "
                                                              "programmes", ORANGE),
                               (n(b["projected_unmet_demand"]), "students without a seat if nothing changes", ORANGE),
                               (n(m1["total_sections"]), "minimum sections (Integer Programming)", NAVY),
                               (f"{n(m2['unmet_demand_before'])} → {n(m2['unmet_demand_after'])}",
                                "unseated students with 50 extra sections (Binary)", NAVY)]):
    stat(s, 0.6 + i * 3.1, 1.5, 2.95, v, l, color=c, size=40)
text(s, 0.6, 3.4, 6.0, 0.5, "What the project delivers", size=20, color=NAVY, bold_first=True)
text(s, 0.6, 3.95, 6.0, 3.0, [
    "A per-course section plan for 2023 (CSV and Excel)",
    "A ranked list of bottleneck courses",
    "An interactive app: load data, statistics on demand, choose a model, change inputs",
    "Scenario and sensitivity charts for capacity and budget",
], size=16, bullets=True, color=INK, space=8)
box(s, 6.95, 3.4, 5.75, 3.45, fill=PANEL)
text(s, 7.2, 3.55, 5.3, 3.2, [
    [("Key insights", {"bold": True, "color": NAVY, "size": 20})],
    "Shortages come from repeat demand: failed students returning",
    "About 1% more sections (50 of 5,612) removes 98% of the shortage",
    "Returns diminish fast: 67 sections clear everything",
    "Higher pass rates also reduce capacity pressure",
], size=16, bullets=False, color=INK, space=10)

# 13. Thank you ----------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
box(s, 0, 0, 13.333, 7.5, fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
text(s, 0.9, 2.6, 11.5, 1.2, [[("Thank You", {"font": TITLE_FONT, "size": 54, "bold": True, "color": WHITE})]])
text(s, 0.9, 3.9, 11.5, 0.8, "Questions and live demo of the planning app", size=22, color=PANEL)
s.notes_slide.notes_text_frame.text = "Switch to the app: Tab 4 bottlenecks, Tab 5 both models."

out = ROOT / "presentation" / "final_review.pptx"
prs.save(out)
print("saved", out, len(prs.slides), "slides")
