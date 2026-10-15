# Team Roles and Workstreams

| Member | Responsibilities | Code / deliverables owned |
|---|---|---|
| **Member 1** | Problem formulation, literature review, System Dynamics student-flow model | `docs/literature_review.md`, `curriculum_planner/system_dynamics.py` (StudentFlowModel, CourseFlowModel, validation), problem-statement and SD slides |
| **Member 2** | Dataset preprocessing, exploratory descriptive analysis, demand and bottleneck identification | `curriculum_planner/preprocessing.py`, `descriptive.py`, `capacity.py`, `data/processed/`, EDA figures 01–05 |
| **Member 3** | IP model formulation, solver implementation, scenario and sensitivity analysis | `curriculum_planner/optimization.py`, `scenarios.py`, figures 06–09b, model sections of `model_documentation.md` |
| **Member 4** | Streamlit UI, data visualisation, end-to-end integration, cross-component testing | `app.py`, `viz.py`, `run_pipeline.py`, `tests/`, deployment (`requirements.txt`, `.streamlit/`) |

## Interfaces between workstreams
```
Member 2  preprocessing.clean()  ──►  ProcessedData(enrolments, students, courses)
Member 1  system_dynamics.course_flow_parameters() / CourseFlowModel.projected_demand()  ──►  demand table
Member 2  capacity.bottleneck_table(demand, cap)  ──►  bottlenecks
Member 3  optimization.solve_min_sections() / solve_extra_sections()  ──►  allocations
Member 3  scenarios.compare_scenarios()  (SD ⇄ IP loop)  ──►  scenario KPIs
Member 4  app.py / run_pipeline.py  ──►  UI, reports, downloads
```

## Integration checklist (Member 4)
- [x] `python -m pytest tests`: 13 tests (pre-processing, linkage, SD mass balance, backlog feedback, Model 1 integrality, Model 2 budget/priority/fairness, bottleneck flag, LP shadow price, AHP-weighted binary model, AHP consistency)
- [x] `python run_pipeline.py --reprocess`: full dataset end-to-end in about 30 s
- [x] Streamlit AppTest: every tab renders with no exceptions on the full dataset; model switching and parameter changes work
