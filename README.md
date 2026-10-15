# University Curriculum Flow and Capacity Planning Using System Dynamics

This project models how students flow through university courses with **System Dynamics** and allocates course
sections with **Integer Programming**. It is calibrated on the StudentDropoutDataset (Zenodo
[10.5281/zenodo.17239943](https://doi.org/10.5281/zenodo.17239943)).

> Scope: curriculum flow and capacity planning only. **Section capacity is a model parameter**, not a dataset
> variable, and the project does **not** predict which students drop out.

## Quick start
```bash
pip install -r requirements.txt
python run_pipeline.py --reprocess      # preprocessing → SD → bottlenecks → IP → scenarios → reports (~30 s)
python flask_app.py                     # web interface  -> http://127.0.0.1:5000   (or: run_web.bat)
streamlit run app.py                    # alternative Streamlit interface
python build_manual_excel.py            # rebuild the Excel-Solver / hand-calculation workbook
python -m pytest tests                  # 13 unit tests + 19 tests on the real dataset (~20 s)
python presentation/build_slides.py     # rebuild the supplementary slides from the latest results
```
## Interfaces
Two interfaces read the same results and solve the same two models.

| | Pages / tabs |
|---|---|
| **Flask** (`flask_app.py`, port 5000) | Dashboard · Dataset · Model 1 Integer · Model 2 Binary · Comparison |
| **Streamlit** (`app.py`, port 8501) | Data · Statistics · Student flow · Demand & bottlenecks · Model 1 · Model 2 · Scenarios · Download |

The Flask app re-solves both models live for any capacity, budget or fairness cap, reading the cached
projection from `outputs/tables/`; it does not recompute the System Dynamics calibration, so every page
responds in well under a second.

`run_pipeline.py` options: `--capacity 50 --extra 50 --growth 0.0 --horizon 5 --max-per-programme 5`.
The raw archive `17239943.zip` should sit in the project root. Extracted CSVs in `data/raw/` are used if present.

## Headline results (capacity = 50 students/section, planning year 2023)
| | |
|---|---|
| Projected course demand | 161,620 seats (145,727 first-time + 15,893 repeat) |
| Bottleneck courses (demand ≥ capacity) | **68** in 28 programmes; 267 more at risk |
| Projected unmet demand at modelled current sections | 436 students |
| Model 1: minimum sections meeting all demand | 5,612 (+67 / −25 against modelled current) |
| Model 2: 50 extra sections | unmet demand 436 → **9** (−98 %) |
| SD validation | stocks MAPE 4.2 %; repeat-flow R² 0.91 |

## How the project meets the course brief
| Requirement | Where |
|---|---|
| Publicly available dataset | StudentDropoutDataset, Zenodo (CC BY 4.0) |
| UI to load the data | App tab ① (upload ZIP/CSV/parquet, or use the bundled data) |
| Statistics generated on demand | App tab ② → *Generate statistics on demand* (choose year, programme, statistic, top N) |
| At least two optimisations, chosen by the user | **Integer Programming** (Model 1) and **Binary Programming** (Model 2), each on its own page |
| Solved manually and in Excel | `outputs/reports/manual_solver_models.xlsx` — both models on an 8-course instance, Solver-ready, with the hand calculation beside them; downloadable from the *Comparison* page |

| Course topic | Used in |
|---|---|
| Integer programming | Model 1: minimum section allocation |
| Binary (0-1) programming, knapsack type | Model 2: allocation of B extra sections |
| LP sensitivity analysis | Model 2 → *LP sensitivity report*: shadow prices, binding constraints, reduced costs, budget ranging |
| AHP with consistency check | Optional course-priority weights in Model 2 (λmax, CI, CR ≤ 0.10) |
| *Off-syllabus:* System Dynamics | Demand forecasting that feeds the optimisation models (needs the instructor's permission as an additional topic) |

## Project layout
```
curriculum_planner/
  config.py           parameters (capacity etc.) and paths
  preprocessing.py    ZIP/CSV → cleaned, linked student-course tables          (Member 2)
  descriptive.py      enrolment, outcomes, demand, progression statistics      (Member 2)
  system_dynamics.py  student-flow and course-flow SD models + validation      (Member 1)
  capacity.py         modelled capacity, bottleneck identification             (Member 2)
  optimization.py     Model 1 (integer), Model 2 (binary), LP sensitivity, HiGHS (Member 3)
  mcdm.py             AHP weights and consistency ratio                        (Member 3)
  scenarios.py        SD⇄IP loop, scenarios, sensitivity analysis              (Member 3)
  viz.py              chart styling                                            (Member 4)
app.py                Streamlit UI                                             (Member 4)
flask_app.py          Flask web UI (templates/ + static/)                      (Member 4)
build_manual_excel.py Excel-Solver workbook for the hand-solved instance       (Member 3)
run_pipeline.py       batch run → outputs/                                     (Member 4)
tests/                unit tests
data/processed/       cleaned dataset (parquet, csv.gz), cleaning log, count validation
outputs/tables/       every result table (CSV)
outputs/figures/      report figures (PNG)
outputs/reports/      results_and_validation_report.md, capacity_planning_results.xlsx, summary.json
docs/                 model documentation, literature review, team roles, validation checklist
presentation/         supplementary_slides.pptx (+ build script)
```

## Documentation
- [docs/model_documentation.md](docs/model_documentation.md): data, preprocessing, SD equations, IP formulations, assumptions, limitations
- [outputs/reports/results_and_validation_report.md](outputs/reports/results_and_validation_report.md): all numbers, auto-generated
- [docs/literature_review.md](docs/literature_review.md): research domains and gap
- [docs/team_roles.md](docs/team_roles.md) · [docs/final_validation_checklist.md](docs/final_validation_checklist.md)

## Presentation
`presentation/supplementary_slides.pptx` has 13 slides in the existing deck's style:
1. **Why This Dataset?**: insert directly after the dataset overview slide
2. **Literature Review & Research Gap**: insert after the problem statement / objectives
3–10. Preprocessing results, progression, SD model, demand loop, bottlenecks, Model 1, Model 2, scenarios
11–13. Interactive UI, conclusions and recommendations, team roles

Copy them into the main deck with *Reuse Slides* or copy/paste with *Use Destination Theme*. All charts are
native PowerPoint charts and can be edited.
