# Tasks: [PART / MECHANISM NAME]

**Plan:** [link] · Each task ends with a verifiable command. A task is done
when its command passes — not when the code "looks right".

## Phase 1 — skeleton

- [ ] **T1** Create `src/…/[part].py` with the parameter defaults from plan
      §2 and a build function returning labeled parts.
      Verify: `python -c "from … import …; ….build()"`
- [ ] **T2** Wrap it in a `ParametricModel` with the parameter table (ranges
      from plan §2) and record the manifest.
      Verify: manifest lists every spec parameter with unit + range.

## Phase 2 — geometry

- [ ] **T3** Model [part A] per spec G-x …
      Verify: `SpatialContext` of the part shows G-x values (±tolerance).
- [ ] **T4** Model [part B] …
      Verify: same pattern as T3.
- [ ] **T5** Compose the assembly (`compose` or explicit `Compound`), set
      labels from plan §1.
      Verify: composition manifest lists every part with its snippet/version.

## Phase 3 — validation gates

- [ ] **T6** Interference sweep (AC-2): run `check_interference` at [n]
      stroke positions in pytest; assert `report.ok`.
- [ ] **T7** Clearance check (AC-3): assert min distance ≥ [value].
- [ ] **T8** Feature graph (AC-4): build `FeatureGraph.from_model`,
      encode plan §3 relations, assert `validate()` has no errors.
- [ ] **T9** Assumption report: `ParameterLedger.to_markdown()` attached to
      the design notes; every `estimated` value either resolved (update
      spec §4) or accepted with a reason.

## Phase 4 — delivery

- [ ] **T10** Export [STEP/STL/DXF] via `exporters3d`/`exporters`.
- [ ] **T11** Design notes: context diff vs. spec table, final ledger, open
      questions moved to spec §7.

## Definition of done

- All tasks checked with their verification commands green
- `pytest tests/` green (repo-wide, not just the new tests)
- No `estimated` parameter left unflagged in the final ledger
- Spec §6 acceptance criteria all demonstrably met by a check output
  (attach the report, not a claim)
