# OHIE Validation Reproducibility Package

This folder contains rerunnable validation and benchmark exercises for OHIE Phase 5.

Cases:

- `analytical/`: controlled synthetic hydrodynamic checks.
- `sensitivity/`: parameter sensitivity sweeps.
- `historical/rann_gadkabet/`: approximate Rann/Kutch behavioral benchmark notes.
- `historical/yamuna_2025/`: approximate Yamuna boundary-condition benchmark notes.
- `historical/gorakhpur/`: approximate intervention realism benchmark notes.

Run:

```bash
python3 validation/analytical/run.py
python3 validation/sensitivity/run.py
python3 validation/historical/rann_gadkabet/run.py
python3 validation/historical/yamuna_2025/run.py
python3 validation/historical/gorakhpur/run.py
```

These are synthetic or approximate reconstructions unless stated otherwise. They are not calibrated real-world models.

