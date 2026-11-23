# Coupled gap voltage solve

Historical design. See [Unify network junctions](2026-11-23-unify-network-junctions.md) for the current integration path.

Add an opt-in coupled electrical voltage step to Network with the original
split step as its default. The coupled step accepts staggered Cell solvers
and uses the same membrane-current linearization, clamp sampling, cable
operator and post-voltage mechanism updates as the existing solver.
Both junction voltages are taken at the new timestep. Ion and receptor
states retain their staggered update.

Prepare a dendritic hierarchical system for each participating population.
Eliminate the local systems and solve the remaining junction system through
a matrix-free Woodbury reduction. Scale the incidence of each electrical
contact by the square root of its conductance times the timestep and scale
each endpoint row by its physical capacitance. Apply the correction through
the existing tree solves. This yields the globally coupled implicit voltage
equations without allocating a dense network matrix.

Compare against a small monolithic NumPy solve across two branched cells
with different capacitances and multiple electrical contacts, check that
the current signs conserve charge, and run the same Golgi pair in BrainCell
and NEURON at the original and half timesteps.
