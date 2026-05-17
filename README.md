# OHIE
## Open Hydrodynamic Intervention Engine

Open scientific research scaffold for intervention-aware hydrodynamic experimentation.

## Why OHIE Exists

Flood studies often identify where flooding happens.

They less often explore how interventions behave, how simplified hydrodynamic approximations transfer, or how intervention assumptions change outcomes.

OHIE exists to support reproducible hydrodynamic experimentation.

## What OHIE Is

OHIE is a bounded empirical hydrodynamic research scaffold focused on:

- intervention-aware experimentation
- flux-coupled boundary approximations
- terrain-regime transferability
- reproducible benchmark workflows

## What OHIE Is Not

OHIE is not:

- a calibrated hydrodynamic engine
- an operational flood forecasting system
- a design-grade drainage model
- validated intervention intelligence
- a coupled river-urban hydraulic model

## Current Scientific Status

OHIE should be read as a Scientifically Serious Hydrodynamic Research Scaffold.

Confidence is strongest in:

- benchmark reproduction
- conservative flux-coupled boundary behavior
- real-terrain sanity testing
- bounded empirical transfer patterns

Uncertainty remains in:

- calibration
- hydraulic realism
- mixed-relief transfer
- universal transferability
- design-grade intervention ranking

## Scientific Evidence Chain

The full internal evidence trail is archived under [docs/research_history/](docs/research_history/README.md).

Use the public-facing chain:

- [docs/scientific_position.md](docs/scientific_position.md)
- [docs/scientific_summary.md](docs/scientific_summary.md)
- [docs/benchmark_guide.md](docs/benchmark_guide.md)
- [docs/evidence_matrix.md](docs/evidence_matrix.md)

## Key Findings

- Flux coupling is more defensible than overwrite forcing.
- Shared-default transferability is limited.
- Moderate transfer appears possible across several terrain regimes.
- Mixed relief weakens approximation behavior.
- Terrain heterogeneity matters.

These findings are empirical and bounded.

## Installation

```bash
git clone https://github.com/prabhat842/OHIE.git
cd OHIE
pip install -r requirements.txt
```

If you are working from source without the pinned requirements file, use the project metadata in `pyproject.toml` and install the `test` and `geo` extras only if needed.

## First Experiment

Run a quick benchmark:

```bash
python3 examples/benchmark_demo.py
```

Or run the small intervention MVP:

```bash
python3 examples/flat_terrain_intervention_mvp.py
```

The goal is to reach a first reproducible result in under 15 minutes.

## Reproducible Benchmarks

The benchmark and transfer cases live under [validation/](validation/) and are summarized in [docs/benchmark_guide.md](docs/benchmark_guide.md).

They cover:

- benchmark reproduction
- external transfer
- terrain-regime testing
- failure modes

## Known Limitations

- empirical coefficient
- no calibration
- simplified hydraulics
- terrain dependence
- mixed-relief weakness
- not design-grade

## Scientific Position

See [docs/scientific_position.md](docs/scientific_position.md).

That document is the single source of truth for claims and limits.

## Contributing

Contributions are welcome when they improve:

- reproducibility
- benchmark coverage
- clarity of limitations
- evidence traceability

Please avoid hype claims, unverifiable claims, and hidden tuning.

New claims should include:

- evidence
- benchmark
- limitation

## Citation

If you use OHIE in a report or paper, cite the project metadata in `CITATION.cff` and reference the scientific position document.

## License

Apache 2.0
