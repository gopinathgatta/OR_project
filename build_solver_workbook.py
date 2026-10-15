"""Build the Excel Solver workbook for both optimisation models, over ALL courses.

    python build_solver_workbook.py        (run after run_pipeline.py)

Writes outputs/reports/solver_all_courses.xlsx:

  README                 what each sheet holds and how to run it
  Model 1 (all courses)  every course, complete Solver model: changing cells,
                         constraint column, objective cell
  Model 2 (all courses)  every course, complete binary Solver model
  Model 1 - runnable     a subset small enough for Excel's built-in Solver
  Model 2 - runnable     the candidate sections only - the complete Model 2 at 67 variables
  Programmes             every programme of the planning year
  Expected answers       the optimum, so any run can be checked

Excel's built-in Solver is capped at 200 decision variables and 100 constraints, so the
two "all courses" sheets are beyond it. They solve with OpenSolver (free add-in, same
dialog, no size cap). Model 1 also has a closed form, given in a check column, because
its constraints separate by course.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from curriculum_planner import config
from curriculum_planner.capacity import modelled_current_sections
from curriculum_planner.optimization import solve_extra_sections, solve_min_sections

CAP = config.DEFAULT_SECTION_CAPACITY
BUDGET = config.DEFAULT_EXTRA_SECTIONS
RUNNABLE_VARS = 150          # inside Excel's 200-variable cap

BOLD = Font(bold=True)
TITLE = Font(bold=True, size=12)
HEAD = Font(bold=True, color="FFFFFF")
HEADFILL = PatternFill("solid", fgColor="1F3864")
CHANGEFILL = PatternFill("solid", fgColor="FFF2CC")   # changing cells
TARGETFILL = PatternFill("solid", fgColor="D9EAD3")   # objective cell
CONSTRFILL = PatternFill("solid", fgColor="FCE4D6")   # constraint column
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def data() -> pd.DataFrame:
    bt = pd.read_csv(config.TABLE_DIR / "capacity_bottleneck_table.csv")
    s0 = modelled_current_sections(bt["enrolment"], CAP).astype(int)
    bt = bt.assign(current=s0)
    bt["unmet"] = np.maximum(0.0, bt["demand"] - CAP * bt["current"])
    bt["x_opt"] = np.where(bt["demand"] > 0,
                           np.maximum(1, np.ceil(bt["demand"] / CAP)), 0).astype(int)
    return bt


def header(ws, row, labels, widths):
    for j, text in enumerate(labels, start=1):
        c = ws.cell(row=row, column=j, value=text)
        c.font, c.fill, c.border = HEAD, HEADFILL, BOX
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    ws.row_dimensions[row].height = 46
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def steps(ws, row, lines, title="HOW TO RUN IT"):
    ws.cell(row=row, column=1, value=title).font = BOLD
    for i, line in enumerate(lines, start=1):
        ws.cell(row=row + i, column=1, value=line)


def params(ws, extra=()):
    ws["A4"] = "Section capacity (cap)"
    ws["A4"].font = BOLD
    ws["B4"] = CAP
    for i, (label, value, note) in enumerate(extra, start=5):
        ws.cell(row=i, column=1, value=label).font = BOLD
        ws.cell(row=i, column=2, value=value)
        if note:
            ws.cell(row=i, column=3, value=note)


# --------------------------------------------------------------- Model 1, all courses
def sheet_m1_all(wb, bt):
    ws = wb.create_sheet("Model 1 (all courses)")
    ws["A1"] = f"MODEL 1 - MINIMUM SECTION ALLOCATION - ALL {len(bt):,} COURSES"
    ws["A1"].font = TITLE
    ws["A2"] = ("OBJECTIVE  minimise total sections (green cell).   "
                "TARGET  every student gets a seat: cap x sections >= demand (orange column >= 0).   "
                "CHANGING VARIABLES  column E (yellow).")
    params(ws, [("Demand safety buffer (beta)", 0.0, "")])

    head = 7
    header(ws, head,
           ["Course ID", "Programme", "Demand D_c", "Required seats = (1+beta) x D_c",
            "Sections x_c  <-- CHANGING VARIABLES", "Seats provided = cap x x_c",
            "CONSTRAINT: slack = provided - required  (must be >= 0)",
            "Current sections", "Change = x_c - current",
            "Check: closed form ROUNDUP(required/cap)"],
           [16, 16, 11, 15, 17, 14, 19, 11, 11, 16])

    first = head + 1
    for i, r in enumerate(bt.itertuples(index=False)):
        row = first + i
        ws.cell(row=row, column=1, value=r.course_id)
        ws.cell(row=row, column=2, value=r.programme_id)
        ws.cell(row=row, column=3, value=round(float(r.demand), 2))
        ws.cell(row=row, column=4, value=f"=(1+$B$5)*C{row}")
        c = ws.cell(row=row, column=5, value=int(r.x_opt))      # warm start at the optimum
        c.fill, c.border = CHANGEFILL, BOX
        ws.cell(row=row, column=6, value=f"=$B$4*E{row}")
        g = ws.cell(row=row, column=7, value=f"=F{row}-D{row}")
        g.fill, g.border = CONSTRFILL, BOX
        ws.cell(row=row, column=8, value=int(r.current))
        ws.cell(row=row, column=9, value=f"=E{row}-H{row}")
        ws.cell(row=row, column=10, value=f"=IF(D{row}<=0,0,MAX(1,ROUNDUP(D{row}/$B$4,0)))")
    last = first + len(bt) - 1

    tot = last + 2
    ws.cell(row=tot, column=1, value="TOTAL").font = BOLD
    ws.cell(row=tot, column=3, value=f"=SUM(C{first}:C{last})").font = BOLD
    obj = ws.cell(row=tot, column=5, value=f"=SUM(E{first}:E{last})")
    obj.font, obj.fill, obj.border = BOLD, TARGETFILL, BOX
    ws.cell(row=tot, column=6, value=f"=SUM(F{first}:F{last})").font = BOLD
    ws.cell(row=tot, column=8, value=f"=SUM(H{first}:H{last})").font = BOLD
    ws.cell(row=tot, column=9, value=f"=SUM(I{first}:I{last})").font = BOLD
    ws.cell(row=tot, column=10, value=f"=SUM(J{first}:J{last})").font = BOLD

    ws.cell(row=tot + 1, column=1, value="OBJECTIVE CELL (minimise)").font = BOLD
    ws.cell(row=tot + 1, column=5, value=f"=E{tot}")
    ws.cell(row=tot + 2, column=1, value="Smallest slack (must stay >= 0)").font = BOLD
    ws.cell(row=tot + 2, column=5, value=f"=MIN(G{first}:G{last})")
    ws.cell(row=tot + 3, column=1, value="Courses needing more sections").font = BOLD
    ws.cell(row=tot + 3, column=5, value=f'=COUNTIF(I{first}:I{last},">0")')
    ws.cell(row=tot + 4, column=1, value="Courses that can release one").font = BOLD
    ws.cell(row=tot + 4, column=5, value=f'=COUNTIF(I{first}:I{last},"<0")')
    ws.cell(row=tot + 5, column=1, value="Mean seat utilisation").font = BOLD
    u = ws.cell(row=tot + 5, column=5, value=f"=C{tot}/F{tot}")
    u.number_format = "0.0%"

    steps(ws, tot + 7, [
        f"1. Set Objective:          $E${tot}",
        "2. To:                     Min",
        f"3. By Changing Cells:      $E${first}:$E${last}",
        "4. Subject to the Constraints:",
        f"       $E${first}:$E${last}   int      (sections are whole numbers)",
        f"       $E${first}:$E${last}   >= 0",
        f"       $G${first}:$G${last}   >= 0      (seats provided >= required seats)",
        "5. Solving Method:         Simplex LP",
        "6. Solve.",
        "",
        f"Excel's built-in Solver stops at 200 variables and this model has {len(bt):,}.",
        "Use OpenSolver (free add-in: Data > OpenSolver > Solve), which reads this same model",
        "with no size limit, or use the 'Model 1 - runnable' sheet with the built-in Solver.",
        "",
        "Column E already holds the optimum, so the totals are correct before any run.",
        "It equals the closed form in column J: each course's constraint involves only its own",
        "x_c, so the problem separates and x_c = ROUNDUP(required seats / capacity).",
        "A correct solve leaves column E equal to column J.",
    ])
    return ws


# --------------------------------------------------------------- Model 2, all courses
def sheet_m2_all(wb, bt):
    ws = wb.create_sheet("Model 2 (all courses)")
    ws["A1"] = f"MODEL 2 - EXTRA SECTION ALLOCATION (BINARY 0-1) - ALL {len(bt):,} COURSES"
    ws["A1"].font = TITLE
    ws["A2"] = ("OBJECTIVE  maximise students seated (green cell).   "
                "TARGET  use at most B extra sections.   "
                "CHANGING VARIABLES  column F (yellow), each 0 or 1.")
    params(ws, [("Budget B (extra sections)", BUDGET, ""),
                ("Max extra sections per programme (M)", 99, "99 = no cap; see the runnable sheet")])

    head = 8
    header(ws, head,
           ["Course ID", "Programme", "Demand D_c", "Current sections",
            "Unmet demand U_c = max(0, D - cap x current)",
            "Open an extra section?  y_c  <-- CHANGING VARIABLES",
            "Students it would seat  a_c = MIN(cap, U_c)", "Students seated = a_c x y_c"],
           [16, 16, 11, 11, 17, 18, 16, 15])

    first = head + 1
    for i, r in enumerate(bt.itertuples(index=False)):
        row = first + i
        ws.cell(row=row, column=1, value=r.course_id)
        ws.cell(row=row, column=2, value=r.programme_id)
        ws.cell(row=row, column=3, value=round(float(r.demand), 2))
        ws.cell(row=row, column=4, value=int(r.current))
        ws.cell(row=row, column=5, value=f"=MAX(0,C{row}-$B$4*D{row})")
        c = ws.cell(row=row, column=6, value=0)
        c.fill, c.border = CHANGEFILL, BOX
        ws.cell(row=row, column=7, value=f"=MIN($B$4,E{row})")
        ws.cell(row=row, column=8, value=f"=G{row}*F{row}")
    last = first + len(bt) - 1

    tot = last + 2
    ws.cell(row=tot, column=1, value="TOTAL").font = BOLD
    ws.cell(row=tot, column=5, value=f"=SUM(E{first}:E{last})").font = BOLD
    used = ws.cell(row=tot, column=6, value=f"=SUM(F{first}:F{last})")
    used.font, used.border = BOLD, BOX
    obj = ws.cell(row=tot, column=8, value=f"=SUMPRODUCT(G{first}:G{last},F{first}:F{last})")
    obj.font, obj.fill, obj.border = BOLD, TARGETFILL, BOX

    res = tot + 2
    ws.cell(row=res, column=1, value="OBJECTIVE CELL (maximise)").font = BOLD
    ws.cell(row=res, column=2, value=f"=H{tot}")
    ws.cell(row=res + 1, column=1, value="CONSTRAINT: sections used (<= B)").font = BOLD
    ws.cell(row=res + 1, column=2, value=f"=F{tot}")
    ws.cell(row=res + 2, column=1, value="Unmet demand before").font = BOLD
    ws.cell(row=res + 2, column=2, value=f"=E{tot}")
    ws.cell(row=res + 3, column=1, value="Unmet demand remaining").font = BOLD
    ws.cell(row=res + 3, column=2, value=f"=E{tot}-H{tot}")

    steps(ws, res + 5, [
        f"1. Set Objective:          $H${tot}",
        "2. To:                     Max",
        f"3. By Changing Cells:      $F${first}:$F${last}",
        "4. Subject to the Constraints:",
        f"       $F${first}:$F${last}   bin      (open the section, or do not)",
        f"       $F${tot}  <= $B$5                (budget: at most B extra sections)",
        "5. Solving Method:         Simplex LP",
        "6. Solve.",
        "",
        f"This is every course, so there are {len(bt):,} binary variables - beyond Excel's",
        "built-in Solver. Use OpenSolver, or the 'Model 2 - runnable' sheet, which holds the",
        "same problem with only the courses that can actually receive a section.",
        "",
        "A course with no shortfall has U_c = 0, so a_c = 0: opening a section for it seats",
        "nobody and the optimum leaves its y at 0. Those rows cannot change the answer.",
        "",
        "Per-programme caps are on the runnable sheet; adding one for each of the",
        f"{bt['programme_id'].nunique()} programmes here would exceed Excel's 100-constraint limit.",
    ])
    return ws


# --------------------------------------------------------------- runnable subsets
def sheet_m1_runnable(wb, bt):
    sub = bt.nlargest(RUNNABLE_VARS, "demand").reset_index(drop=True)
    ws = wb.create_sheet("Model 1 - runnable")
    ws["A1"] = f"MODEL 1 - THE {len(sub)} LARGEST COURSES (fits Excel's built-in Solver)"
    ws["A1"].font = TITLE
    ws["A2"] = ("The same programme as the all-courses sheet, at a size the built-in Solver "
                "accepts. The totals below apply to these courses only.")
    params(ws)

    head = 6
    header(ws, head,
           ["Course ID", "Programme", "Demand D_c", "Sections x_c  <-- CHANGING VARIABLES",
            "Seats = cap x x_c", "CONSTRAINT: slack (>= 0)", "Current", "Change",
            "Check ROUNDUP(D/cap)"],
           [16, 16, 11, 17, 13, 16, 10, 10, 15])

    first = head + 1
    for i, r in enumerate(sub.itertuples(index=False)):
        row = first + i
        ws.cell(row=row, column=1, value=r.course_id)
        ws.cell(row=row, column=2, value=r.programme_id)
        ws.cell(row=row, column=3, value=round(float(r.demand), 2))
        c = ws.cell(row=row, column=4, value=1)
        c.fill, c.border = CHANGEFILL, BOX
        ws.cell(row=row, column=5, value=f"=$B$4*D{row}")
        g = ws.cell(row=row, column=6, value=f"=E{row}-C{row}")
        g.fill, g.border = CONSTRFILL, BOX
        ws.cell(row=row, column=7, value=int(r.current))
        ws.cell(row=row, column=8, value=f"=D{row}-G{row}")
        ws.cell(row=row, column=9, value=f"=MAX(1,ROUNDUP(C{row}/$B$4,0))")
    last = first + len(sub) - 1

    tot = last + 2
    ws.cell(row=tot, column=1, value="TOTAL").font = BOLD
    obj = ws.cell(row=tot, column=4, value=f"=SUM(D{first}:D{last})")
    obj.font, obj.fill, obj.border = BOLD, TARGETFILL, BOX
    ws.cell(row=tot, column=9, value=f"=SUM(I{first}:I{last})").font = BOLD

    steps(ws, tot + 2, [
        f"1. Set Objective:          $D${tot}",
        "2. To:                     Min",
        f"3. By Changing Cells:      $D${first}:$D${last}",
        "4. Constraints:",
        f"       $D${first}:$D${last}   int",
        f"       $D${first}:$D${last}   >= 1",
        f"       $F${first}:$F${last}   >= 0",
        "5. Solving Method:         Simplex LP   ->   Solve",
        "",
        "CHECK: column D must equal column I after solving.",
    ])
    return ws


def sheet_m2_runnable(wb, bt):
    sub = bt[bt["unmet"] > 1e-9].sort_values("unmet", ascending=False).reset_index(drop=True)
    ws = wb.create_sheet("Model 2 - runnable")
    ws["A1"] = f"MODEL 2 - THE {len(sub)} CANDIDATE EXTRA SECTIONS (fits the built-in Solver)"
    ws["A1"].font = TITLE
    ws["A2"] = ("This is the complete Model 2. Courses with no shortfall are omitted because a "
                "section there seats nobody and can never be chosen.")
    params(ws, [("Budget B (extra sections)", BUDGET, ""),
                ("Max extra sections per programme (M)", 99, "99 = no cap; set 5 to switch on")])

    head = 8
    header(ws, head,
           ["Course ID", "Programme", "Unmet demand U_c",
            "Students seated if opened  a_c = MIN(cap, U_c)",
            "Open it?  y_c  <-- CHANGING VARIABLES", "Students seated = a_c x y_c"],
           [16, 16, 13, 18, 18, 15])

    first = head + 1
    for i, r in enumerate(sub.itertuples(index=False)):
        row = first + i
        ws.cell(row=row, column=1, value=r.course_id)
        ws.cell(row=row, column=2, value=r.programme_id)
        ws.cell(row=row, column=3, value=round(float(r.unmet), 2))
        ws.cell(row=row, column=4, value=f"=MIN($B$4,C{row})")
        c = ws.cell(row=row, column=5, value=0)
        c.fill, c.border = CHANGEFILL, BOX
        ws.cell(row=row, column=6, value=f"=D{row}*E{row}")
    last = first + len(sub) - 1

    tot = last + 2
    ws.cell(row=tot, column=1, value="TOTAL").font = BOLD
    ws.cell(row=tot, column=3, value=f"=SUM(C{first}:C{last})").font = BOLD
    used = ws.cell(row=tot, column=5, value=f"=SUM(E{first}:E{last})")
    used.font, used.border = BOLD, BOX
    obj = ws.cell(row=tot, column=6, value=f"=SUMPRODUCT(D{first}:D{last},E{first}:E{last})")
    obj.font, obj.fill, obj.border = BOLD, TARGETFILL, BOX

    pr = tot + 2
    ws.cell(row=pr, column=1, value="Programme").font = BOLD
    ws.cell(row=pr, column=2, value="Sections opened").font = BOLD
    ws.cell(row=pr, column=3, value="Limit M").font = BOLD
    progs = sorted(sub["programme_id"].unique())
    for i, pg in enumerate(progs, start=1):
        row = pr + i
        ws.cell(row=row, column=1, value=pg)
        ws.cell(row=row, column=2,
                value=f"=SUMIF($B${first}:$B${last},A{row},$E${first}:$E${last})").border = BOX
        ws.cell(row=row, column=3, value="=$B$6")
    pf, pl = pr + 1, pr + len(progs)

    res = pl + 2
    ws.cell(row=res, column=1, value="OBJECTIVE CELL (maximise)").font = BOLD
    ws.cell(row=res, column=2, value=f"=F{tot}")
    ws.cell(row=res + 1, column=1, value="Sections used").font = BOLD
    ws.cell(row=res + 1, column=2, value=f"=E{tot}")
    ws.cell(row=res + 2, column=1, value="Unmet demand remaining").font = BOLD
    ws.cell(row=res + 2, column=2, value=f"=C{tot}-F{tot}")
    ws.cell(row=res + 3, column=1,
            value=f"Only these {len(progs)} programmes of "
                  f"{bt['programme_id'].nunique()} have a candidate section; for the rest the "
                  "constraint would read 0 <= M and can never bind.")

    steps(ws, res + 5, [
        f"1. Set Objective:          $F${tot}",
        "2. To:                     Max",
        f"3. By Changing Cells:      $E${first}:$E${last}",
        "4. Constraints:",
        f"       $E${first}:$E${last}   bin",
        f"       $E${tot}  <= $B$5",
        f"       $B${pf}:$B${pl}  <= $B$6     (per-programme cap)",
        "5. Solving Method:         Simplex LP   ->   Solve",
        "",
        "Set B6 to 5 and solve again to see what the fairness cap costs.",
    ])
    return ws


# --------------------------------------------------------------- programmes
def sheet_programmes(wb, bt):
    g = bt.groupby("programme_id").agg(courses=("course_id", "count"),
                                       demand=("demand", "sum"),
                                       current=("current", "sum"),
                                       unmet=("unmet", "sum"))
    g["short"] = bt[bt["unmet"] > 1e-9].groupby("programme_id").size().reindex(g.index).fillna(0)
    g = g.sort_values(["unmet", "demand"], ascending=False).reset_index()

    ws = wb.create_sheet(f"Programmes ({len(g)})")
    ws["A1"] = f"ALL {len(g)} PROGRAMMES OF THE PLANNING YEAR"
    ws["A1"].font = TITLE
    ws["A2"] = "Only programmes with a short course can receive an extra section in Model 2."

    head = 4
    header(ws, head,
           ["Programme", "Courses", "Projected demand", "Current sections", "Courses short",
            "Unmet demand", "Can receive a section?"],
           [18, 9, 15, 13, 11, 13, 17])
    first = head + 1
    for i, r in enumerate(g.itertuples(index=False)):
        row = first + i
        ws.cell(row=row, column=1, value=r.programme_id)
        ws.cell(row=row, column=2, value=int(r.courses))
        ws.cell(row=row, column=3, value=round(float(r.demand), 1))
        ws.cell(row=row, column=4, value=int(r.current))
        ws.cell(row=row, column=5, value=int(r.short))
        ws.cell(row=row, column=6, value=round(float(r.unmet), 2))
        ws.cell(row=row, column=7, value="yes" if r.short else "no")
    last = first + len(g) - 1

    tot = last + 2
    ws.cell(row=tot, column=1, value="TOTAL").font = BOLD
    for col, f in ((2, f"=SUM(B{first}:B{last})"), (3, f"=SUM(C{first}:C{last})"),
                   (4, f"=SUM(D{first}:D{last})"), (5, f"=SUM(E{first}:E{last})"),
                   (6, f"=SUM(F{first}:F{last})")):
        c = ws.cell(row=tot, column=col, value=f)
        c.font, c.border = BOLD, BOX
    ws.cell(row=tot + 2, column=1, value="Programmes that can receive a section").font = BOLD
    ws.cell(row=tot + 2, column=3, value=f'=COUNTIF(G{first}:G{last},"yes")')
    ws.cell(row=tot + 3, column=1, value="Programmes with no shortfall").font = BOLD
    ws.cell(row=tot + 3, column=3, value=f'=COUNTIF(G{first}:G{last},"no")')
    return ws


# --------------------------------------------------------------- README + answers
def sheet_readme(wb, bt):
    ws = wb.create_sheet("README")
    ws.column_dimensions["A"].width = 112
    n_short = int((bt["unmet"] > 1e-9).sum())
    n_prog = bt["programme_id"].nunique()
    lines = [
        ("University Curriculum Capacity Planning - Excel Solver workbook", TITLE),
        ("", None),
        (f"Section capacity: {CAP} students per section.   Courses: {len(bt):,}.   "
         f"Programmes: {n_prog}.", None),
        ("Course and programme identifiers are hashes in the published dataset. They are labels", None),
        ("only - the models use the demand figures, so hashing affects no calculation.", None),
        ("", None),
        ("COLOUR KEY", BOLD),
        ("   Yellow  = changing variables (what Solver may alter)", None),
        ("   Orange  = constraint column (the rule that must hold)", None),
        ("   Green   = objective cell (what Solver minimises or maximises)", None),
        ("", None),
        ("SHEETS", BOLD),
        (f"   Model 1 (all courses)   all {len(bt):,} courses, complete model", None),
        (f"   Model 2 (all courses)   all {len(bt):,} courses, complete binary model", None),
        (f"   Model 1 - runnable      {RUNNABLE_VARS} largest courses, built-in Solver runs it", None),
        (f"   Model 2 - runnable      the {n_short} candidate sections = complete Model 2", None),
        (f"   Programmes ({n_prog})         every programme of the planning year", None),
        ("   Expected answers        the optimum, so any run can be checked", None),
        ("", None),
        ("EXCEL SOLVER SIZE LIMITS - READ THIS", BOLD),
        ("   The built-in Solver accepts at most 200 decision variables and 100 constraints.", None),
        (f"   Both 'all courses' sheets have {len(bt):,} variables, so the built-in Solver will", None),
        ("   refuse them with 'the problem is too large'.", None),
        ("", None),
        ("   Two ways to solve them anyway:", BOLD),
        ("   1. OpenSolver - a free Excel add-in from opensolver.org. It reads the same model", None),
        ("      set up for Solver, with no size limit. Install, then Data > OpenSolver > Solve.", None),
        ("   2. Model 1 needs no solver at all. Its constraints separate by course, so the", None),
        ("      optimum is the closed form ROUNDUP(required seats / capacity), already in the", None),
        ("      check column. The totals on that sheet are the exact optimum for all courses.", None),
        ("", None),
        ("   The 'runnable' sheets work in the built-in Solver today, with no add-in.", None),
        ("   For Model 2 the runnable sheet is not a sample: a course with no shortfall seats", None),
        ("   nobody, so leaving it out cannot change the answer. It is the whole problem.", None),
        ("", None),
        ("IF SOLVER IS NOT ON THE DATA RIBBON", BOLD),
        ("   File > Options > Add-ins > Manage: Excel Add-ins > Go > tick 'Solver Add-in' > OK.", None),
    ]
    for i, (text, font) in enumerate(lines, start=1):
        c = ws.cell(row=i, column=1, value=text)
        if font:
            c.font = font
    return ws


def sheet_answers(wb, bt):
    s0 = bt["current"].to_numpy()
    r1 = solve_min_sections(bt[["course_id", "programme_id", "demand"]], CAP)
    r2 = solve_extra_sections(bt, s0, BUDGET, CAP)
    r2f = solve_extra_sections(bt, s0, BUDGET, CAP, max_per_programme=5)
    change = r1.allocation["sections"].to_numpy() - s0
    sub1 = bt.nlargest(RUNNABLE_VARS, "demand")
    x_sub = np.maximum(1, np.ceil(sub1["demand"] / CAP)).astype(int)

    ws = wb.create_sheet("Expected answers")
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 50
    ws["A1"] = "EXPECTED ANSWERS - any correct solve must reproduce these"
    ws["A1"].font = TITLE

    rows = [
        ("", "", ""),
        ("MODEL 1 - all courses", "", ""),
        ("Total sections (optimum)", int(r1.summary["total_sections"]), "closed form, exact"),
        ("Modelled current sections", int(s0.sum()), ""),
        ("Net change", int(r1.summary["total_sections"] - s0.sum()), ""),
        ("Courses needing more", int((change > 0).sum()), ""),
        ("Courses that can release", int((change < 0).sum()), ""),
        ("Mean seat utilisation", round(float(r1.summary["mean_utilisation"]), 3), ""),
        ("Smallest slack", 0, "never negative, or the plan is infeasible"),
        ("", "", ""),
        ("MODEL 1 - runnable sheet", "", ""),
        (f"Total sections over the {len(sub1)} largest courses", int(x_sub.sum()),
         "column D must equal column I"),
        ("", "", ""),
        (f"MODEL 2 (B = {BUDGET}, no programme cap)", "", ""),
        ("Unmet demand before", round(float(r2.summary["unmet_demand_before"]), 2), "students"),
        ("Students seated (objective)", round(float(r2.summary["demand_covered"]), 2), "maximised"),
        ("Unmet demand remaining", round(float(r2.summary["unmet_demand_after"]), 2), "students"),
        ("Sections used", int(r2.summary["extra_sections_used"]), f"of {BUDGET}"),
        ("Courses still short", int(r2.summary["courses_short_after"]),
         f"was {int(r2.summary['courses_short_before'])}"),
        ("", "", ""),
        ("MODEL 2 with programme cap M = 5", "", ""),
        ("Unmet demand remaining", round(float(r2f.summary["unmet_demand_after"]), 2),
         "the cap costs "
         f"{r2f.summary['unmet_demand_after'] - r2.summary['unmet_demand_after']:.2f} students"),
    ]
    for i, (a, b, c) in enumerate(rows, start=2):
        cell = ws.cell(row=i, column=1, value=a)
        if a and b == "":
            cell.font = BOLD
        ws.cell(row=i, column=2, value=b)
        ws.cell(row=i, column=3, value=c)
    return ws


def main():
    bt = data()
    wb = Workbook()
    wb.remove(wb.active)
    sheet_readme(wb, bt)
    sheet_m1_all(wb, bt)
    sheet_m2_all(wb, bt)
    sheet_m1_runnable(wb, bt)
    sheet_m2_runnable(wb, bt)
    sheet_programmes(wb, bt)
    sheet_answers(wb, bt)
    out = config.REPORT_DIR / "solver_all_courses.xlsx"
    wb.save(out)
    n_short = int((bt["unmet"] > 1e-9).sum())
    print(f"wrote {out}")
    print(f"  Model 1 (all courses) : {len(bt):,} variables")
    print(f"  Model 2 (all courses) : {len(bt):,} binary variables")
    print(f"  Model 1 - runnable    : {RUNNABLE_VARS} variables")
    print(f"  Model 2 - runnable    : {n_short} binary variables, "
          f"{bt.loc[bt['unmet'] > 1e-9, 'programme_id'].nunique()} programme constraints")
    print(f"  Programmes            : {bt['programme_id'].nunique()}")


if __name__ == "__main__":
    main()
