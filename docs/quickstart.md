# OHIE Quickstart

Target: first experiment in under 15 minutes.

## 1. Install

From the repository root:

```bash
python3 -m pip install -e ".[test,config,geo]"
```

If optional geospatial dependencies are already installed, the local benchmark scripts can run directly with NumPy and the OHIE package.

## 2. Run Synthetic Validation

```bash
python3 validation/analytical/run.py
```

This runs controlled scientific sanity checks such as closed-basin mass conservation, bowl filling, and terrain slope behavior.

## 3. Run Real-Terrain-Informed Benchmark

```bash
python3 validation/real_terrain/flat_terrain_case/run.py
```

This runs a low-gradient terrain chip from `ohie-data/real_terrain/flat_terrain_small.npz`.

## 4. Inspect Output

The script prints:

- maximum depth
- total volume
- mass balance error
- persistence
- stagnation proxy
- D8 and D-Infinity routing diagnostics

For the river boundary example:

```bash
python3 validation/real_terrain/river_adjacent_case/run.py
```

## 5. Modify Forcing

Edit:

```text
validation/real_terrain/flat_terrain_case/config.yaml
```

Change:

```yaml
forcing:
  rainfall_mm_hr: 35
```

The current run script uses the Python validation function directly. The YAML file documents the experiment parameters and is intended to become the shared experiment record.

## 6. Modify an Intervention

Start from the existing intervention examples:

```bash
python3 examples/intervention_scenario.py
```

Useful intervention classes are in:

```text
ohie/interventions/
```

Current first-class intervention examples include:

- detention basin
- channel carving
- pump
- hydraulic structures scaffold

## 7. Run Observation-Mask Comparison

```bash
python3 validation/remote_sensing/run.py
```

Important:

This is a **proxy comparison only**. It computes IoU, observed overlap percent, and flooded area agreement against a local historical flood-output mask. It is not raw Sentinel-1 or NDWI validation.

## 8. Read Scientific Limits

Before using OHIE for research claims, read:

```text
docs/known_limitations.md
docs/scientific_position.md
docs/benchmark_guide.md
```

OHIE is currently suitable for transparent, reproducible experimentation. It is not yet a calibrated municipal flood forecasting system.
