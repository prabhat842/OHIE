# Reproducible Benchmark Case

## Case

Brahmaputra floodplain micro-extent near Dhakuakhana, Assam

## Purpose

Single external open-DEM transfer test for the flux-coupled boundary approximation.

## Reproduction command

```bash
python3 validation/external_transfer/run.py
```

## What it uses

- AWS Terrain Tiles GeoTIFF z12 open DEM
- a fixed coefficient of `1e-6`
- one simple river-adjacent edge forcing

## What to inspect

- `../validation/external_transfer/observed_output.md`
- `../ohie-phase7x-external-transfer-report.md`

## Interpretation

The case is intended to answer one narrow question:

> does the transfer problem remain after leaving the benchmark family?

It does not claim calibration, validation, or operational accuracy.
