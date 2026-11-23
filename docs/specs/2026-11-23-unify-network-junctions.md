# Unify network junctions

Use the coupled backward-Euler voltage system for all active Junction
contacts. Remove the gap-only integrator and the solver mode argument.
Keep the cell solver requirement on participating populations and preserve
the existing integration path for populations without active contacts.

Update the dual-simulator Golgi example to use the standard Network API.
Report full-trace voltage errors and interpolated threshold-crossing times
on the shared sample grid. Check parallel contacts, zero-conductance
contacts, contacts on the same cell, and the coupled result against an
independently assembled cable matrix. Rerun the Golgi comparison at both
fixed timesteps.
