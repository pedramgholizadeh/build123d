# Specification: [PART / MECHANISM NAME]

- **Author / owner:** [name]
- **Date:** [date]
- **Status:** [draft | review | approved]
- **Model units:** [mm] (as modeled in build123d)

## 1. Purpose

[One paragraph: what this part/mechanism does, where it lives in the
machine, and what problem it solves. No geometry here — intent only.]

## 2. Interfaces & environment

| Interface | Connects to | Kind | Notes |
|---|---|---|---|
| [mounting face] | [frame] | [bolted, 4× M6] | [pattern per DIN 13] |
| [input shaft] | [motor] | [keyed, rotating] | [300 rpm nominal] |
| [envelope] | [housing cavity] | [clearance] | [min 1 mm all around] |

## 3. Functional requirements

- **FR-1** — [the part shall transmit ≤ X Nm at ≤ Y rpm]
- **FR-2** — [the mechanism shall convert rotary to linear motion, stroke S ± tol]
- **FR-3** — [life / load / environment constraints]

Each FR gets an ID; acceptance criteria in §6 reference these IDs.

## 4. Geometry requirements

Every requirement is a number with a unit and a status. Status vocabulary
(same as `ParamStatus`): `measured` (from physical evidence), `specified`
(requirement), `calculated` (derived), `estimated` (provisional).

| ID | Feature | Parameter | Value | Tolerance | Status | Source |
|----|---------|-----------|-------|-----------|--------|--------|
| G-1 | base plate | width | [40] mm | ±[0.2] | specified | [requirement] |
| G-2 | bore | diameter | [24] mm | H7 | measured | [caliper] |
| G-3 | [gap to wall] | clearance | [1.0] mm | min | calculated | [envelope math] |

Unknown values are listed with value `TBD` and status `needs_data` —
they must be resolved before implementation finishes; they may never be
silently guessed.

## 5. Constraints & standards

- Materials: [material + condition]
- Manufacturing: [process, e.g. 3-axis milling, FDM printing]
- Standards: [DIN/ISO/ASME references that apply]
- Prohibited: [e.g. no weldments, no undercuts]

## 6. Acceptance criteria (all measurable)

- **AC-1** (FR-1, G-2): the built model's bore measures 24.0 ±0.05 in the
  spatial context of the final build.
- **AC-2** (FR-2): `check_interference(assembly)` reports no interference
  across the full stroke range [a..b] sampled at [n] positions.
- **AC-3** (G-3): minimum clearance to the envelope, measured by
  `distance_to`, is ≥ 1.0 mm in every configuration.
- **AC-4**: `FeatureGraph.validate()` returns no errors; every `estimated`
  parameter is either resolved or explicitly accepted in the design notes.

## 7. Open questions

| Question | Owner | Blocks |
|----------|-------|--------|
| [which sealing standard?] | [name] | [G-4] |
