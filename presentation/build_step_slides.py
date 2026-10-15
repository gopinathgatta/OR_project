"""Numbered-step slides in the existing deck's style (navy circles, left accent bar).

    python presentation/build_step_slides.py     (run after run_pipeline.py)

Writes presentation/step_slides.pptx. Copy the slides into the main deck with
*Reuse Slides*, or copy/paste with *Use Destination Theme*.
"""
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
S = json.loads((ROOT / "outputs" / "reports" / "summary.json").read_text())

BODY_FONT = "Calibri"
NAVY = RGBColor(0x1F, 0x38, 0x64)        # headings and circles
BODY = RGBColor(0x33, 0x33, 0x33)        # description lines
ACCENT = RGBColor(0x8A, 0x6F, 0xB0)      # the thin bar down the left edge
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PAGENO = RGBColor(0x59, 0x59, 0x59)

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def n(v, d=0):
    return f"{v:,.{d}f}"


def step_slide(items, page=None, title=None, notes=None):
    """items = [(heading, description), ...] - rendered as numbered circles."""
    s = prs.slides.add_slide(BLANK)

    # left accent bar
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.42), Inches(0.0),
                             Inches(0.055), prs.slide_height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False

    top = Inches(0.55)
    if title:
        tb = s.shapes.add_textbox(Inches(1.15), Inches(0.35), Inches(11.4), Inches(0.7))
        p = tb.text_frame.paragraphs[0]
        p.text = title
        p.font.name, p.font.size, p.font.bold, p.font.color.rgb = BODY_FONT, Pt(30), True, NAVY
        top = Inches(1.25)

    gap = (prs.slide_height - top - Inches(0.75)) / len(items)
    circle_d = Inches(0.58)

    for i, (heading, desc) in enumerate(items):
        y = top + gap * i

        c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.78), y, circle_d, circle_d)
        c.fill.solid()
        c.fill.fore_color.rgb = NAVY
        c.line.fill.background()
        c.shadow.inherit = False
        cp = c.text_frame.paragraphs[0]
        cp.text = str(i + 1)
        cp.alignment = PP_ALIGN.CENTER
        cp.font.name, cp.font.size, cp.font.bold, cp.font.color.rgb = BODY_FONT, Pt(16), True, WHITE
        c.text_frame.margin_top = c.text_frame.margin_bottom = 0
        c.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

        tb = s.shapes.add_textbox(Inches(1.62), y - Inches(0.06), Inches(11.1), Inches(1.0))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_bottom = 0

        p = tf.paragraphs[0]
        p.text = heading
        p.font.name, p.font.size, p.font.bold, p.font.color.rgb = BODY_FONT, Pt(20), True, NAVY

        p2 = tf.add_paragraph()
        p2.text = desc
        p2.font.name, p2.font.size, p2.font.color.rgb = BODY_FONT, Pt(14), BODY
        p2.space_before = Pt(2)

    if page is not None:
        tb = s.shapes.add_textbox(Inches(12.5), Inches(6.85), Inches(0.6), Inches(0.35))
        p = tb.text_frame.paragraphs[0]
        p.text = str(page)
        p.alignment = PP_ALIGN.RIGHT
        p.font.name, p.font.size, p.font.color.rgb = BODY_FONT, Pt(12), PAGENO

    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


# --------------------------------------------------------------------------- content
h, proj, bn = S["headline"], S["projection"], S["bottlenecks"]
m1, m2 = S["model1"], S["model2"]

# Slide A - what we did (same five steps, updated wording)
step_slide([
    ("Prepare the data",
     f"Clean and link {n(h['records'])} student-course records across "
     f"{', '.join(str(y) for y in h['academic_years'][:-1])} and {h['academic_years'][-1]}."),
    ("Forecast course demand",
     f"Model student flow to project {n(proj['demand'])} seats of demand per course for 2023."),
    ("Find capacity bottlenecks",
     f"Flag courses whose forecast demand exceeds their seats: {bn['bottleneck_courses']} courses, "
     f"{n(bn['projected_unmet_demand'])} students without a seat."),
    ("Optimise section allocation",
     "Integer Programming for the minimum sections; Binary Programming for a limited budget "
     "of extra sections."),
    ("Support decisions interactively",
     "A UI to load data, generate statistics on demand, choose a model and change capacity "
     "and budget."),
], page=4,
    notes="Methodology overview. Capacity is a planning parameter, not a dataset variable.")

# Slide B - what the models found
step_slide([
    ("The problem",
     f"{bn['bottleneck_courses']} courses will overflow in 2023 and {n(bn['projected_unmet_demand'])} "
     f"students would not get a seat."),
    ("Model 1 - Integer Programming",
     f"Minimise total sections subject to seating every student: {n(m1['total_sections'])} sections, "
     f"a net {m1['total_sections'] - m1['current_sections_modelled']:+,} "
     f"(add {m1['sections_added']}, release {m1['sections_released']})."),
    ("Model 2 - Binary Programming",
     f"Maximise students seated within a budget of {m2['extra_sections_available']} extra sections: "
     f"unseated falls {n(m2['unmet_demand_before'])} to {n(m2['unmet_demand_after'])} "
     f"({m2['unmet_reduction_pct']:.0f}% reduction)."),
    ("Verified three ways",
     "By hand, in Excel Solver and in the application - all agreeing, with both models solved "
     "to proven optimality (HiGHS)."),
], page=5, title="Results",
    notes="Model 1 answers 'what is the ideal?'; Model 2 answers 'what can we afford?'.")

out = ROOT / "presentation" / "step_slides.pptx"
prs.save(out)
print(f"wrote {out}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
