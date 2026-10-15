"""Build the manual / Excel-Solver verification workbook.

Produces outputs/reports/manual_solver_models.xlsx: the same two optimisation models the UI
solves, laid out on a small 8-course instance that can be solved by hand and with Excel's
Solver add-in. The three methods (hand, Solver, HiGHS in the app) must agree on this instance.

Course IDs in the dataset are hashes. They are only labels: the models use the demand numbers,
so each course is given a short label C1..C8 and the real ID is kept beside it for traceability.
"""
from __future__ import annotations

import math

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

from curriculum_planner import config

N_COURSES = 8
CAP = config.DEFAULT_SECTION_CAPACITY
BUDGET = 3          # small enough to solve by hand
MAX_PER_PROG = 1    # fairness cap that actually bites on this instance

BOLD = Font(bold=True)
TITLE = Font(bold=True, size=12)
THIN = Side(style="thin")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def instance() -> pd.DataFrame:
    """The 8 largest bottleneck courses from the pipeline's own results."""
    bt = pd.read_csv(config.TABLE_DIR / "capacity_bottleneck_table.csv")
    top = bt[bt["status"] == "Bottleneck"].nlargest(N_COURSES, "unmet_demand").reset_index(drop=True)
    progs = {pid: f"P{i + 1}" for i, pid in enumerate(dict.fromkeys(top["programme_id"]))}
    return pd.DataFrame({
        "label": [f"C{i + 1}" for i in range(len(top))],
        "course_id": top["course_id"],
        "programme": top["programme_id"].map(progs),
        "demand": top["demand"].round(2),
        "current_sections": top["current_sections"].astype(int),
        "unmet": top["unmet_demand"].round(2),
    })


def _header(ws, row, labels):
    for j, text in enumerate(labels, start=1):
        c = ws.cell(row=row, column=j, value=text)
        c.font = BOLD
        c.border = BOX
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")


def _steps(ws, row, lines):
    ws.cell(row=row, column=1, value="HOW TO SOLVE IT IN EXCEL (Data > Solver)").font = BOLD
    for i, line in enumerate(lines, start=1):
        ws.cell(row=row + i, column=1, value=line)


def sheet_model1(wb, df):
    ws = wb.create_sheet("Model 1 - Integer")
    ws["A1"] = "MODEL 1 - MINIMUM SECTION ALLOCATION (INTEGER PROGRAMMING)"
    ws["A1"].font = TITLE
    ws["A2"] = "Objective: open as few sections as possible.  Target: every student gets a seat."

    ws["A4"] = "Section capacity (cap)"
    ws["B4"] = CAP
    ws["A4"].font = BOLD

    head = 7
    _header(ws, head, ["Course", "Course ID (dataset)", "Programme", "Demand D_c",
                       "Required seats = D_c", "Sections x_c  <-- CHANGING CELLS",
                       "Seats provided = cap x x_c", "Slack = provided - required (must be >= 0)",
                       "Current sections", "Change = x_c - current",
                       "Hand check = ROUNDUP(required/cap)"])
    first = head + 1
    for i, row in df.iterrows():
        r = first + i
        ws.cell(row=r, column=1, value=row["label"])
        ws.cell(row=r, column=2, value=row["course_id"])
        ws.cell(row=r, column=3, value=row["programme"])
        ws.cell(row=r, column=4, value=float(row["demand"]))
        ws.cell(row=r, column=5, value=f"=D{r}")
        ws.cell(row=r, column=6, value=1)                       # changing cell, start at 1
        ws.cell(row=r, column=7, value=f"=$B$4*F{r}")
        ws.cell(row=r, column=8, value=f"=G{r}-E{r}")
        ws.cell(row=r, column=9, value=int(row["current_sections"]))
        ws.cell(row=r, column=10, value=f"=F{r}-I{r}")
        ws.cell(row=r, column=11, value=f"=ROUNDUP(E{r}/$B$4,0)")
        for col in range(1, 12):
            ws.cell(row=r, column=col).border = BOX
    last = first + len(df) - 1

    tot = last + 1
    ws.cell(row=tot, column=1, value="TOTAL").font = BOLD
    ws.cell(row=tot, column=4, value=f"=SUM(D{first}:D{last})")
    ws.cell(row=tot, column=6, value=f"=SUM(F{first}:F{last})").font = BOLD
    ws.cell(row=tot, column=9, value=f"=SUM(I{first}:I{last})")
    ws.cell(row=tot, column=10, value=f"=SUM(J{first}:J{last})")
    ws.cell(row=tot, column=11, value=f"=SUM(K{first}:K{last})")
    for col in range(1, 12):
        ws.cell(row=tot, column=col).border = BOX

    ws.cell(row=tot + 2, column=1, value="OBJECTIVE CELL (minimise)").font = BOLD
    ws.cell(row=tot + 2, column=2, value=f"=F{tot}")

    _steps(ws, tot + 4, [
        f"1. Set Objective:            $F${tot}",
        "2. To:                       Min",
        f"3. By Changing Cells:        $F${first}:$F${last}",
        "4. Subject to the Constraints:",
        f"       $F${first}:$F${last}  int      (whole sections)",
        f"       $F${first}:$F${last}  >= 1     (every course runs at least one section)",
        f"       $H${first}:$H${last}  >= 0     (seats provided >= seats required)",
        "5. Solving Method:           Simplex LP",
        "6. Click Solve.",
        "",
        "CHECK: the answer in column F must equal column K (the hand calculation),",
        "because each course's constraint involves only its own x_c - the model separates",
        "by course, so by hand x_c = ROUNDUP(D_c / cap).",
    ])

    widths = [9, 22, 12, 12, 14, 16, 14, 16, 11, 12, 14]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = w
    ws.row_dimensions[head].height = 46
    return ws


def sheet_model2(wb, df):
    ws = wb.create_sheet("Model 2 - Binary")
    ws["A1"] = "MODEL 2 - ALLOCATION OF EXTRA SECTIONS (BINARY 0-1 PROGRAMMING)"
    ws["A1"].font = TITLE
    ws["A2"] = "Objective: seat as many students as possible.  Target: use no more than B extra sections."

    ws["A4"] = "Section capacity (cap)"
    ws["B4"] = CAP
    ws["A5"] = "Budget B (extra sections available)"
    ws["B5"] = BUDGET
    ws["A6"] = "Max extra sections per programme (M)"
    ws["B6"] = MAX_PER_PROG
    ws["C6"] = "set M = 99 to switch the fairness cap off"
    for r in ("A4", "A5", "A6"):
        ws[r].font = BOLD

    head = 8
    _header(ws, head, ["Course", "Course ID (dataset)", "Programme", "Unmet demand U_c",
                       "Covered if opened  a_c = MIN(cap, U_c)", "Open it?  y_c (0 or 1)  <-- CHANGING CELLS",
                       "Students covered = a_c x y_c"])
    first = head + 1
    for i, row in df.iterrows():
        r = first + i
        ws.cell(row=r, column=1, value=row["label"])
        ws.cell(row=r, column=2, value=row["course_id"])
        ws.cell(row=r, column=3, value=row["programme"])
        ws.cell(row=r, column=4, value=float(row["unmet"]))
        ws.cell(row=r, column=5, value=f"=MIN($B$4,D{r})")
        ws.cell(row=r, column=6, value=0)                       # changing cell
        ws.cell(row=r, column=7, value=f"=E{r}*F{r}")
        for col in range(1, 8):
            ws.cell(row=r, column=col).border = BOX
    last = first + len(df) - 1

    tot = last + 1
    ws.cell(row=tot, column=1, value="TOTAL").font = BOLD
    ws.cell(row=tot, column=4, value=f"=SUM(D{first}:D{last})")
    ws.cell(row=tot, column=6, value=f"=SUM(F{first}:F{last})").font = BOLD
    ws.cell(row=tot, column=7, value=f"=SUMPRODUCT(E{first}:E{last},F{first}:F{last})").font = BOLD
    for col in range(1, 8):
        ws.cell(row=tot, column=col).border = BOX

    pr = tot + 2
    ws.cell(row=pr, column=1, value="Programme").font = BOLD
    ws.cell(row=pr, column=2, value="Sections opened").font = BOLD
    ws.cell(row=pr, column=3, value="Limit M").font = BOLD
    for i, prog in enumerate(sorted(df["programme"].unique()), start=1):
        r = pr + i
        ws.cell(row=r, column=1, value=prog)
        ws.cell(row=r, column=2, value=f"=SUMIF($C${first}:$C${last},A{r},$F${first}:$F${last})")
        ws.cell(row=r, column=3, value="=$B$6")
        for col in range(1, 4):
            ws.cell(row=r, column=col).border = BOX
    prog_first, prog_last = pr + 1, pr + len(df["programme"].unique())

    res = prog_last + 2
    ws.cell(row=res, column=1, value="OBJECTIVE CELL (maximise)").font = BOLD
    ws.cell(row=res, column=2, value=f"=G{tot}")
    ws.cell(row=res + 1, column=1, value="Sections used").font = BOLD
    ws.cell(row=res + 1, column=2, value=f"=F{tot}")
    ws.cell(row=res + 2, column=1, value="Unmet demand remaining").font = BOLD
    ws.cell(row=res + 2, column=2, value=f"=D{tot}-G{tot}")

    _steps(ws, res + 4, [
        f"1. Set Objective:            $G${tot}",
        "2. To:                       Max",
        f"3. By Changing Cells:        $F${first}:$F${last}",
        "4. Subject to the Constraints:",
        f"       $F${first}:$F${last}  bin      (open it or not - nothing in between)",
        f"       $F${tot}  <= $B$5              (budget: at most B extra sections)",
        f"       $B${prog_first}:$B${prog_last}  <= $B$6     (at most M per programme)",
        "5. Solving Method:           Simplex LP",
        "6. Click Solve.",
        "",
        "BY HAND: every course here has unmet demand below one section's capacity, so one extra",
        "section clears the whole shortfall. Without the programme cap you simply pick the B",
        "courses with the largest unmet demand. With M = 1 you may take only one course per",
        "programme, so the answer changes - that is the fairness cap binding.",
    ])

    widths = [9, 22, 12, 14, 18, 18, 16]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = w
    ws.row_dimensions[head].height = 46
    return ws


def sheet_answers(wb, df):
    """The expected answers, so the three methods can be compared."""
    ws = wb.create_sheet("Expected answers")
    ws["A1"] = "EXPECTED ANSWERS - hand, Excel Solver and the app must all agree"
    ws["A1"].font = TITLE

    m1_hand = [max(1, math.ceil(d / CAP)) for d in df["demand"]]
    rows = [
        ("", "", ""),
        ("MODEL 1", "", ""),
        ("Total sections (minimum)", sum(m1_hand), "= sum of ROUNDUP(D_c / 50)"),
        ("Current sections", int(df["current_sections"].sum()), ""),
        ("Change", sum(m1_hand) - int(df["current_sections"].sum()), ""),
        ("", "", ""),
        ("MODEL 2  (budget B = %d)" % BUDGET, "", ""),
    ]
    unmet = df["unmet"].tolist()
    progs = df["programme"].tolist()

    free = sorted(unmet, reverse=True)[:BUDGET]
    rows.append(("Without fairness cap: students covered", round(sum(free), 2),
                 "pick the %d largest unmet demands" % BUDGET))

    best_per_prog, taken = {}, []
    for u, pg in sorted(zip(unmet, progs), reverse=True):
        if best_per_prog.get(pg, 0) < MAX_PER_PROG and len(taken) < BUDGET:
            best_per_prog[pg] = best_per_prog.get(pg, 0) + 1
            taken.append(u)
    rows.append(("With fairness cap M = %d: students covered" % MAX_PER_PROG, round(sum(taken), 2),
                 "at most %d per programme" % MAX_PER_PROG))
    rows.append(("Cost of the fairness cap", round(sum(free) - sum(taken), 2), "students"))
    rows.append(("", "", ""))
    rows.append(("NOTE", "", "The app solves all 3,787 courses; this sheet is the 8-course instance."))

    for i, (a, b, c) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=a)
        ws.cell(row=i, column=2, value=b)
        ws.cell(row=i, column=3, value=c)
        if a and not b == "":
            ws.cell(row=i, column=1).font = BOLD
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 54
    return ws


def main():
    df = instance()
    wb = Workbook()
    wb.remove(wb.active)
    sheet_model1(wb, df)
    sheet_model2(wb, df)
    sheet_answers(wb, df)
    out = config.REPORT_DIR / "manual_solver_models.xlsx"
    wb.save(out)
    print(f"wrote {out}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
