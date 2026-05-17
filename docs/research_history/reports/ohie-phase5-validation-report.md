# OHIE Phase 5 Validation Report

## 1. Analytical & Synthetic Validation

Runnable cases live in:

```text
validation/analytical/
```

Run:

```bash
python3 validation/analytical/run.py
```

Validation cases:

| Test | Expected | Pass Criteria |
|---|---|---|
| Flat Plane Rainfall | downslope movement, mass conservation, no instability | lower-slope water sum exceeds upper-slope sum; mass error < 1% |
| Bowl Depression Filling | water accumulates naturally and persistence is captured | center depth > edge depth; persistence > 0 |
| Dam Break Approximation | qualitative pulse propagation | wetting front moves downstream; mass error < 2% |
| Steep vs Flat Terrain | routing changes sensibly; D8 and D-Infinity differ | measurable accumulation difference |
| Closed Basin | water volume conserved | mass error < 1e-10 |

Observed results are written to:

```text
validation/analytical/observed_output.md
```

## 2. Historical Benchmark Reconstruction

Historical benchmarks are approximate and intentionally labeled **not calibrated**.

### Rann / Gadkabet

Folder:

```text
validation/historical/rann_gadkabet/
```

Purpose:

- flat terrain behavior,
- blue spots,
- D-Infinity drainage spines,
- stagnation/persistence,
- road-ridge damming behavior.

Known limitations:

- no real Gadkabet DEM,
- no SAR comparison,
- no tidal creek network,
- no salinity-viscosity physics,
- road 754K is represented as an idealized ridge.

### Yamuna 2025

Folder:

```text
validation/historical/yamuna_2025/
```

Purpose:

- river-stage boundary behavior,
- persistence near river/outfall zone,
- boundary forcing sanity.

Known limitations:

- no real Yamuna DEM/hydrograph in this phase,
- no IIT Delhi SAR mask,
- no IoU validation,
- no pipe network or calibrated outfalls.

### Gorakhpur

Folder:

```text
validation/historical/gorakhpur/
```

Purpose:

- intervention realism,
- storage + drainage + pump attenuation,
- municipal low-gradient planning behavior.

Known limitations:

- no real Gorakhpur DEM,
- no population exposure,
- no RFSM/GA parity check,
- no calibrated municipal assets.

## 3. Sensitivity Report

Runnable sensitivity suite:

```text
validation/sensitivity/
```

Run:

```bash
python3 validation/sensitivity/run.py
```

Sweeps:

- Manning roughness,
- resolution,
- timestep,
- rainfall intensity,
- detention basin depth.

Observed results are written to:

```text
validation/sensitivity/observed_output.md
```

The goal is not parameter optimization. The goal is to expose solver behavior and identify unsafe regions.

## 4. Comparative Scientific Benchmarking

| Case | OHIE Agreement | Confidence |
|---|---|---|
| Closed basin conservation | Strong agreement with conservation expectation in no-forcing closed domain | High for synthetic case |
| Flat plane rainfall | Qualitatively consistent downslope movement and mass accounting | Medium-High |
| Bowl filling | Qualitatively consistent ponding and persistence | Medium-High |
| Dam break approximation | Qualitative propagation only; not full SWE fidelity | Medium-Low |
| Rann/Gadkabet flat terrain | Captures intended behavior class: ponding, stagnation, road-ridge differential | Medium for behavior, low for real-world reproduction |
| Yamuna boundary forcing | Captures prescribed river-stage influence | Medium for boundary mechanism, low for historical reproduction |
| Gorakhpur intervention behavior | Storage/drainage/pump interventions attenuate synthetic flooding | Medium for mechanism, low for city reproduction |

## 5. Stability Characterization

Detailed stability notes:

```text
docs/numerical-stability.md
```

Summary:

- current synthetic tests are stable across tested Manning, resolution, timestep, and rainfall ranges;
- abrupt boundary jumps and unresolved terrain discontinuities remain risks;
- mass balance should be checked for every experiment;
- D8 should not be trusted alone in flat terrain.

## 6. Reproducibility

Every Phase 5 validation group has:

```text
README.md
config.yaml
run.py
expected_output.md
```

Scripts write `observed_output.md` so reviewers can compare expected vs observed behavior.

## 7. Scientific Honesty

Most important limitations:

- no groundwater coupling,
- approximate backwater,
- incomplete SWE in new package,
- no pipe network hydraulics,
- no SAR calibration,
- no real historical benchmark calibration,
- simplified culverts/weirs/pumps,
- D-Infinity implementation is still simplified relative to full literature formulations.

OHIE is now more scientifically credible for **controlled research exploration**, but it is not yet a calibrated operational flood model.

