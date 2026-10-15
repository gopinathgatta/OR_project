# Final Project Validation Checklist

| # | Success criterion | Status | Evidence |
|---|---|---|---|
| 1 | Record counts match the source (464,739 / 39,364 / 4,989 / 163 / 3 years) | ✅ | `data/processed/count_validation.csv`; UI tab ① |
| 2 | Cleaned, anonymised student-course dataset; hashed IDs kept as keys and never decrypted | ✅ | `data/processed/student_course_enrolments.parquet`, `cleaning_log.csv` |
| 3 | Course demand statistics | ✅ | `outputs/tables/course_year_statistics.csv`, `eda_*.csv`, figures 01, 04 |
| 4 | Student progression analysis | ✅ | `progression_flows_2021_2022.csv`, `progression_transition_matrix.csv`, figure 02 |
| 5 | SD student-flow model (enrolled, progressing, repeating, approaching graduation; completion, failure, repetition, progression, withdrawal, graduation flows) | ✅ | `system_dynamics.py`; figure 03; split-half MAPE 4.2 % |
| 6 | Demand includes first-time **and** repeat enrolees | ✅ | `D = F(1+g)^t + ρB`; repeat-flow R² = 0.91 |
| 7 | **Capacity is a model parameter, never a dataset variable** | ✅ | `config.DEFAULT_SECTION_CAPACITY`; stated in the UI sidebar, every report and the slides |
| 8 | Bottlenecks: demand ≥ modelled capacity, with demand, utilisation and unmet-demand metrics | ✅ | `bottleneck_courses.csv` (68 courses at 50 seats/section) |
| 9 | Model 1: minimum sections, integer-only, all demand met | ✅ | `model1_minimum_sections.csv`; `all_integer=True`, `demand_fully_met=True`; LP relaxation compared |
| 10 | Model 2: binary IP, budget constraint, prioritises highest unmet demand when the budget is insufficient | ✅ | `model2_extra_section_allocation.csv`; unit test `test_model2_budget_and_priority` |
| 11 | Sensitivity: capacity parameter, extra-section budget, demand growth | ✅ | `sensitivity_*.csv`, figures 06–08 |
| 12 | Scenario comparison reports | ✅ | `scenario_comparison.csv`, `scenario_trajectories.csv`, figures 09/09b, Excel workbook |
| 13 | Streamlit UI: upload → statistics → model selection → results → download | ✅ | `app.py`; AppTest run with no exceptions on the full dataset |
| 14 | **No dropout prediction or forecasting** | ✅ | Withdrawal is only an aggregate observed flow rate. No per-student model, score or forecast exists anywhere in the code; the UI header states the scope. |
| 15 | PPT: "Why This Dataset?" and "Literature Review & Research Gap" slides | ✅ | `presentation/supplementary_slides.pptx`, slides 1–2 |
| 16 | Team roles aligned to workstreams | ✅ | `docs/team_roles.md`; slide 13 |
| 17 | Automated tests | ✅ | `python -m pytest tests`: 10 passed |
