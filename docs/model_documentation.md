# Model Documentation
**University Curriculum Flow and Capacity Planning Using System Dynamics and Integer Programming**

## 1. Purpose and scope
The tool models how students flow through university courses, projects next year's course demand
(first-time plus repeat enrolments), identifies **capacity bottlenecks**, and recommends **section
allocations** using two Integer Programming (IP) models.

**Inside scope:** curriculum flow, course demand, capacity planning, section allocation, scenario analysis.
**Outside scope:** dropout prediction or forecasting for individual students. Withdrawal appears only as an
*aggregate observed flow rate* in the System Dynamics (SD) model. No model scores or predicts any student.

## 2. Data
**Source:** StudentDropoutDataset, Zenodo, DOI [10.5281/zenodo.17239943](https://doi.org/10.5281/zenodo.17239943), CC BY 4.0
(Igualde-Sáez et al., 2025). The dataset contains three academic years (2018, 2021, 2022) of anonymised
student-course records from a Spanish public university.

| Check | Published | Observed |
|---|---|---|
| Student-course records | 464,739 | 464,739 ✅ |
| Students | 39,364 | 39,364 ✅ |
| Courses | 4,989 | 4,989 ✅ |
| Degree programmes | 163 | 163 ✅ |
| Academic years | 3 | 3 ✅ |

### 2.1 Variables used
| Variable type | Raw column | Clean column | Purpose |
|---|---|---|---|
| Student identifier | `dni_hash` | `student_id` | Track student-course records (hashed key, never decrypted) |
| Course identifier | `asi_hash` | `course_id` | Identify courses |
| Academic year | `caca` | `academic_year` | Track progression over time |
| Degree/programme | `tit_hash` | `programme_id` | Group students by programme |
| Course enrolment | one row per enrolment | `enrolment` (count) | Estimate course demand |
| Academic result | `nota_asig_hash` (0–10) | `grade`, `outcome`, `passed` | Identify pass / fail / repetition |
| Credits / course information | `cred_mat_total`, `cred_sup_total`, `cred_sup_tit`, `cred_pend_sup_tit` | `credits_*` | Academic load and credits pending |
| Student status | `curso_mas_alto`, `anyo_inicio_estudios`, `baja_fecha` | `highest_year_level`, `start_year`, `withdrawn_in_year` | Identify progression and withdrawal |

LMS activity, Wi-Fi and socio-demographic columns are dropped because capacity planning does not need them.

### 2.2 Pre-processing pipeline (`curriculum_planner/preprocessing.py`)
1. **Extract & load.** Nested ZIPs are read in memory. Every ID column is read as a **string**, because some
   hexadecimal hashes such as `1e10…` would otherwise be parsed as numbers.
2. **Validate counts** against the published figures (table above).
3. **Missing values / duplicates.** Rows missing a student, course, programme or year are removed. Exact duplicates
   and duplicate *(student, course, year)* keys are removed (0 found). Missing grades (9.4 %) are kept as
   `not_evaluated`. These students earn no credit and re-enrol at the same rate as students who failed
   (53 % vs 52 %), so they count as *not passed*. Missing admission type becomes `UNKNOWN`. `anyo_ingreso` is dropped
   because `start_year` duplicates it.
4. **Standardise identifiers.** Each ID is stripped, lower-cased and checked as a hexadecimal hash.
5. **Variable selection.** 25 modelling variables are retained.
6. **Linkage.** Hashed student × course keys are linked across years. A *repeat enrolment* is a course the
   student also took in the immediately preceding year. This is only observable for 2022, because 2021 is the
   only directly preceding year present. Students who passed a course never re-enrol in it, which supports the
   linkage.
7. **Course statistics.** Enrolment, pass/fail/not-evaluated rates, repeat enrolments and first-time enrolments
   are computed per course and year.

Outputs: `data/processed/student_course_enrolments.parquet` (and `.csv.gz`), `course_year_statistics.csv`,
`cleaning_log.csv`, `count_validation.csv`.

## 3. System Dynamics models (`curriculum_planner/system_dynamics.py`)
Both models use an annual time step with Euler integration. Calibration uses the only consecutive pair of
years, **2021 → 2022**.

### 3.1 Student-flow model (programme level)
**Stocks**

| Stock | Definition |
|---|---|
| Year 1, Year 2, Year 3, Year 4+ (*in progress*) | highest curriculum year enrolled < programme length |
| Final year (*approaching graduation*) | enrolled in the final curriculum year of the programme |
| Repeating (reported stock) | students who stayed in the same stage from one year to the next |
| Graduated, Withdrawn (sinks) | students absent the following year with 0 credits pending (graduated) or > 0 (withdrawn) |

**Flows:** Intake (new entrants + re-entrants) → Year 1…; Progress (stage *i* → *j > i*); Repeat (*i → i*);
Graduate; Withdraw.

$$S_j(t+1) = \sum_i S_i(t)\,P_{ij} + I_j(t), \qquad I_j(t)=I_j(2022)(1+g)^t$$

$P$ is the observed row-stochastic 2021→2022 transition matrix over {stages, Graduated, Withdrawn}.

**Validation (split-half).** Rates are estimated on a random half of the students and used to predict the
other half's 2022 stocks and exits. The mean absolute percentage error is **4.2 %**. Each large stock
is within 2.5 %, and graduates and withdrawals are within 1.3 %. The tiny *Year 4+* stock (89 students) has a 23 % error.

### 3.2 Course-flow model (course level, drives capacity planning)
For each course *c* active in 2022:

| Symbol | Meaning | Estimated from |
|---|---|---|
| $F_c$ | first-time enrolments | 2022 enrolments not taken by the student in 2021 |
| $B_c$ | backlog stock: students who have not yet passed | 2022 failed + not-evaluated |
| $\rho_c$ | retake propensity of the backlog | 2022 repeat enrolments ÷ 2021 not-passed, hierarchical empirical-Bayes shrinkage (course → programme → university, 10 pseudo-observations) |
| $\pi_c$ | pass rate | 2022 passes ÷ enrolment, shrunk to the university mean |
| $g$ | first-time demand growth | parameter (default 0) |
| $cap$ | seats per section | **parameter** (default 50) |
| $x_c(t)$ | sections | chosen by the policy / IP model |
| $u$ | share of unserved students who still need the course | parameter (default 1) |

$$D_c(t) = F_c(1+g)^t + \rho_c B_c(t)$$
$$S_c(t)=\min\{D_c(t),\ cap\cdot x_c(t)\},\qquad U_c(t)=D_c(t)-S_c(t)$$
$$B_c(t+1) = (1-\pi_c)S_c(t) + u\,U_c(t)$$

The backlog equation is the **feedback loop**: a shortfall in sections in year *t* adds demand in year *t+1*.
It is the "Backlog feedback: shortfall adds demand" arrow in the methodology diagram.

**Validation (split-half, per course).** Predicted vs observed 2022 repeat enrolments on held-out students:
R² = **0.91** with course-specific rates, against 0.74 with a single university-wide rate. The course-specific
estimate is biased +6.8 % in total, which errs toward providing capacity.

**Projection 2023.** 161,620 seats are demanded: 145,727 first-time and 15,893 repeat (9.8 %).

## 4. Capacity and bottleneck analysis (`capacity.py`)
> **Capacity is a model parameter, never a dataset variable.** The dataset contains no section or room capacity.

* Modelled current sections: $s_c=\max(1,\lceil E_c^{2022}/cap\rceil)$. This is the fewest sections that seat
  the observed 2022 enrolment.
* Utilisation: $D_c/(cap\cdot s_c)$.
* **Bottleneck:** utilisation ≥ θ, with θ = 1.0 by default. Projected demand meets or exceeds modelled capacity.
  **At risk:** utilisation ≥ 0.9.
* Reported per course: demand (first-time / repeat), capacity, utilisation, unmet demand, and extra sections needed.

At 50 seats/section there are **68 bottleneck courses** in 28 programmes, plus 267 at-risk courses. Projected
unmet demand is **436 students**, and clearing it needs 67 extra sections. Repeat demand makes up 16.4 % of
demand in bottleneck courses, against 9.8 % overall.

## 5. Integer Programming models (`optimization.py`, solver: HiGHS via `scipy.optimize.milp`)

### 5.1 Model 1 – Minimum Section Allocation (Integer Programming)
$$\min \sum_c x_c \quad\text{s.t.}\quad cap\cdot x_c \ge (1+\beta)D_c\ \ \forall c,\qquad x_c\ge 1\ \text{if } D_c>0,\qquad x_c\in\mathbb Z_+$$
β is an optional safety buffer (default 0).

*Result (cap = 50):* **5,612 sections** meet all demand. That is 67 courses gaining one section each and
25 courses that can release one, a net +42 against the modelled current 5,570. The LP relaxation gives
5,062.3 fractional sections; the 550-section integrality gap shows why fractional allocations cannot be
used. All solutions are verified integer, with demand fully met.

*Note:* without coupling constraints, Model 1 separates into $x_c=\lceil(1+\beta)D_c/cap\rceil$. The IP formulation
is kept so that coupling constraints, such as shared rooms or staff limits, can be added without changing the
structure.

### 5.2 Model 2 – Limited Additional Capacity Allocation (Binary Programming)
Unmet demand at current sections: $U_c=\max(0,D_c-cap\cdot s_c)$, with $K_c=\lceil U_c/cap\rceil$ candidate
extra sections per course.

$y_{ck}\in\{0,1\}$ means the *k*-th extra section is given to course *c*. It covers $a_{ck}=\min(cap,\ U_c-(k-1)cap)$ students.

$$\max \sum_{c}\sum_{k\le K_c} w_c\,a_{ck}\,y_{ck}$$
$$\text{s.t.}\quad \sum_{c,k} y_{ck}\le B \quad(\text{budget}),\qquad y_{ck}\le y_{c,k-1}\quad(\text{open in order}),$$
$$\sum_{c\in p}\sum_k y_{ck}\le M_p \quad(\text{optional per-programme fairness cap})$$

Maximising coverage is equivalent to minimising total unmet demand $\sum_c U_c-\sum a_{ck}y_{ck}$.
Weights $w_c$: `uniform` (1); `repeat_weighted` ($1+\lambda\cdot$repeat share), which favours courses that delay
progression; `early_stage` ($1+\lambda$ for first-year courses).

*Result (B = 50):* unmet demand falls from 436 to **9 students (−98 %)**. Courses still short drop from 67 to 17.
With a fairness cap of 5 sections per programme, 20 students remain unmet. Sensitivity analysis shows strongly
diminishing returns: the first 5 sections cover about 30 students each, sections 26–50 cover about 3 each,
and 67 sections clear everything.

### 5.3 LP sensitivity analysis of Model 2
The LP relaxation of Model 2 (0 ≤ y ≤ 1) is solved with `scipy.optimize.linprog` (HiGHS), and the report is
laid out like a spreadsheet Solver sensitivity report:
* **Constraints:** final value, right-hand side, shadow price (dual value) and binding status for the budget
  and every programme cap.
* **Variable cells:** final value, objective coefficient (students the section would seat) and reduced cost
  of every candidate section.
* **Budget ranging:** each y ≤ 1, so the objective is piecewise linear in B with a breakpoint at every whole
  section. The report therefore lists the marginal value of each section from B − 10 to B + 10.

*Result (B = 50):* LP objective 427.7 = IP objective. The relaxation is already integral, because the
sections are opened in decreasing order of value. The shadow price of the budget is 0.92 students per
section: section 50 seats 0.94 students and section 51 would seat 0.92, so more sections buy little. With a
cap of 5 per programme, two programme caps are binding, with shadow prices 2.55 and 8.25. Relaxing those
caps is worth far more than adding budget.

### 5.4 Analytic Hierarchy Process for Model 2 priorities (`mcdm.py`)
Pairwise comparisons on Saaty's 1–9 scale form a reciprocal matrix A. The weights are A's normalised
principal eigenvector, with $CI=(\lambda_{max}-n)/(n-1)$ and $CR = CI/RI(n)$ (RI = 0.58 for n = 3). The
judgements are accepted when CR ≤ 0.10.

With `weight_mode="ahp"`, the criteria are repeat-student share, first-year course, and low pass rate (1 − π).
Each course weight is $w_c = 1 + \sum_k W_k\,\text{score}_k(c)$, with every score in [0, 1]. Illustrative
judgements (3, 5, 2) give W = 0.648 / 0.230 / 0.122 with CR = 0.003. In the app, the planner enters their
own judgements, and the CR is shown with a warning above 0.10.

### 5.5 Mapping to the course syllabus
| Syllabus topic | Where it is used |
|---|---|
| Integer programming | Model 1 – minimum section allocation |
| Binary (0-1) programming, knapsack type | Model 2 – limited additional capacity allocation |
| LP sensitivity analysis and interpretation of sensitivity reports | §5.3 |
| AHP with a consistency check | §5.4 (optional weights in Model 2) |
| System Dynamics (an additional topic, not on the syllabus) | Demand forecasting input to both models |

## 6. Coupled SD-IP loop and scenarios (`scenarios.py`)
Each simulated year runs SD demand → IP policy → served/unserved → backlog → next year's demand.

| Scenario | Policy | Cumulative unserved 2023–27 | Final backlog |
|---|---|---|---|
| S0 Status quo | fixed modelled sections | 3,389 | 46,819 |
| S1 Model 2, B = 50/yr | binary IP each year | 94 | 46,348 |
| S2 Model 2, B = 100/yr | binary IP each year | 0 | 46,329 |
| S3 Model 1 | minimum sections each year | 0 | 46,329 |
| S4 Model 2 + pass rate +5 pp | academic support what-if | 13 | 37,454 |
| S5 Model 2, intake +5 %/yr | demand stress test | 29,345 | 69,124 |

**Sensitivity.** The section-capacity assumption strongly changes bottleneck counts: 133 at 30 seats, 68 at 50
and 31 at 100. The capacity parameter should therefore be set from real room and staffing data before decisions
are made. First-time demand growth of +2 % raises bottlenecks from 68 to 108 and unmet demand to 651.

## 7. Assumptions and limitations
1. Section capacity is uniform and assumed. Real capacity varies by course type (lectures, labs, seminars).
2. Current sections are *modelled* from 2022 enrolment and are not observed.
3. Repeat enrolments are observable only for 2021→2022, and attempts before 2021 are unseen. Some
   "first-time" 2022 enrolments may be second attempts, which would understate repeat demand.
4. 2018 is used for descriptive trends only, because 2019 and 2020 are absent and it is not consecutive with 2021.
5. Credits pending are recorded at the extraction date (2023), which is used to separate graduates from withdrawals.
6. Prerequisite chains between courses are not in the dataset, so courses are coupled only through programme-level fairness.
7. Hashed IDs are anonymous. Course and programme names cannot be shown, and courses are labelled `C-xxxxxx`.

## 8. Reproducibility
```
pip install -r requirements.txt
python run_pipeline.py --reprocess        # all tables, figures and reports in outputs/
python -m pytest tests                    # 13 unit tests
streamlit run app.py                      # interactive UI
```
