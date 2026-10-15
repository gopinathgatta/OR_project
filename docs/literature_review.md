# Literature Review & Research Gap

## Existing research domains
| Domain | Representative work | What it does | What it does not do |
|---|---|---|---|
| **System Dynamics in higher education** | Forrester (1961); Sterman (2000); Galbraith (1998) | Stock-and-flow and feedback models of universities: enrolment, staffing, funding and policy | Aggregate policy view; no course-level capacity decision |
| **Student-flow / Markov manpower models** | Bartholomew (1982) | Transition-rate models of how cohorts move through grades and states | Describe flows; do not optimise capacity |
| **Simulation of curriculum flow** | Saltzman & Roeder (2012) | Simulate students through a business college to test curriculum, prerequisite and staffing changes (time to degree) | Simulation only; no optimisation of section allocation |
| **OR in education (survey)** | Johnes (2015) | Reviews resource allocation, efficiency (DEA) and planning in education | Identifies planning needs; no integrated flow-plus-IP model |
| **Timetabling and course scheduling (IP)** | Schaerf (1999); Burke & Petrovic (2002); Navabi-Shirazi et al. (2022) | Integer programming for rooms, times, faculty and, under scarcity, which courses to offer | Take demand as given; no feedback from repetition into future demand |
| **Learning analytics / dropout prediction** | StudentDropoutDataset (Igualde-Sáez et al., 2025) | Predict which individual students are at risk | Individual prediction, outside this project's scope |

## Identified gap
Student-progression models (SD, Markov, simulation) describe how failure and repetition create demand, but
they do not decide capacity. Capacity and timetabling IPs decide sections, but they treat demand as fixed and
ignore that **unmet capacity and failure return as next year's repeat demand**.

**This project closes the gap.** A course-level SD model, calibrated on real linked student-course records,
produces first-time plus repeat demand. Two IP models allocate sections: minimum sections, and a limited extra
budget. The backlog feedback runs the two in a loop over a multi-year horizon.

## References
- Bartholomew, D. J. (1982). *Stochastic Models for Social Processes* (3rd ed.). Wiley.
- Burke, E. K., & Petrovic, S. (2002). Recent research directions in automated timetabling. *European Journal of Operational Research*, 140(2), 266–280.
- Forrester, J. W. (1961). *Industrial Dynamics*. MIT Press.
- Galbraith, P. L. (1998). System dynamics and university management. *System Dynamics Review*, 14(1), 69–84.
- Igualde-Sáez, A., Maheut, J., Garcia-Sabater, J. P., Marin-Garcia, J. A., Turro, C., Despujol Zabala, I., Puche Garcia, S., Alonso, M., Benlloch-Dualde, J. V., & Soriano Jiménez, P. P. (2025). *StudentDropoutDataset* [Data set]. Zenodo. https://doi.org/10.5281/zenodo.17239943
- Johnes, J. (2015). Operational Research in education. *European Journal of Operational Research*, 243(3), 683–696. https://doi.org/10.1016/j.ejor.2014.10.043
- Navabi-Shirazi, M., El Tonbari, M., Boland, N., Nazzal, D., & Steimle, L. N. (2022). Course scheduling under sudden scarcity: Applications to pandemic planning. *Manufacturing & Service Operations Management*. https://doi.org/10.1287/msom.2021.0996
- Saltzman, R. M., & Roeder, T. M. (2012). Simulating student flow through a college of business for policy and structural change analysis. *Journal of the Operational Research Society*, 63(4), 511–523. https://doi.org/10.1057/jors.2011.59
- Schaerf, A. (1999). A survey of automated timetabling. *Artificial Intelligence Review*, 13(2), 87–127.
- Sterman, J. D. (2000). *Business Dynamics: Systems Thinking and Modeling for a Complex World*. Irwin/McGraw-Hill.

> Check volume and page details against the publishers' pages before final submission. Galbraith (1998) and
> Navabi-Shirazi et al. (2022) were confirmed by title and venue, but their author lists and pages were not
> fully confirmed online.
