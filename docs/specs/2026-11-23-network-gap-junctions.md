# Network gap junctions

Historical design. See [Unify network junctions](2026-11-23-unify-network-junctions.md) for the current integration path.

Extend the existing frozen Junction declaration with a partner endpoint. A
network registers both endpoints and a scalar or row-aligned conductance in
brainunit units. Endpoint rows specify a population member and a morphology
location. Each row describes one physical, bidirectional junction. Repeated
rows represent parallel conductances. Locations resolve to containing control
volumes, using the same rule as voltage event sources.

The compiled network loop advances participating voltages through one
backward-Euler gap-only substep before each regular cell voltage update. This
first-order operator split keeps the existing cell solvers and computes both
junction currents from the same voltage solution. The compact symmetric
positive-definite system contains only participating control volumes. Its
matrix-vector product scatters the paired currents, and a diagonally
preconditioned conjugate-gradient solve avoids a dense network matrix.
Spike detection compares the voltage at the start and end of the complete
network step. Cells without junctions use the existing path.

Test the analytic two-cell solution, bidirectional charge conservation,
location and unit validation, parallel contacts, and same-cell coupling between
different control volumes. Exercise the same routing in the granular-layer
model with the published Golgi contact locations.

The pre-existing population selection on this branch scans every resolved CV
row once per selected member. This blocks materialization of the full chemical
and electrical network. Group selected rows by population in one pass and
emit them in requested order, preserving the stable order within each member.
