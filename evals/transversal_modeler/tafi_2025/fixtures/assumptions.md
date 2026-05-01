# Assumptions and risk notes — Tafi 2025

> Synthesized fixture. Captured from a hypothetical ingestion run on the Tafi 2025 contract for the purpose of stress-testing the eval scaffold against the `transversal_modeler` role. Values are illustrative.

## Going concern

- 2025 reported equity is **negative** (-80M ARS). Auditor's report (page 12 of source PDF, in real document) flags going-concern. Modelers must reflect this — do not auto-correct.
- Net income deteriorated dramatically YoY: 104M → 40.3M, driven primarily by interest-expense surge (180M → 310M, +72%) outpacing revenue growth (+21%).

## Industry context

- Argentine micro-credit lender; biweekly portfolio snapshots stored cumulatively in source CSV (~142k rows over ~14 months).
- Interest rates in ARS environment were extremely volatile across the reporting period — the Interest line should NOT be straight-lined for the forecast.

## TODO(bespoke)

The following parameters need bespoke_modeler attention; transversal_modeler should leave the cells empty with `Assumptions!<cell>` references and `TODO(bespoke)` flags:

- `WACC` — placeholder cell on Valuation sheet
- `terminal_growth_rate` — placeholder cell on Valuation sheet
- `industry_benchmark.NIM` — net interest margin peer comparison
- `industry_benchmark.CAR` — capital adequacy ratio
- `provision_loss_rate` — has been highly volatile; bespoke needed

## Source caveats

- 9.2% of Cliente field rows in source CSV have UTF-8 mojibake (e.g., "Martínez" rendered as "MartÃ­nez"). Cleaned in normalization but flagged.
- Source CSV is *cumulative* snapshots, not deltas; aggregation requires deduplication on (loan_id, period).
