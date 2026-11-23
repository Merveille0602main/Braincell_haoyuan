TITLE Ohmic half-junction for the two-Golgi comparison

NEURON {
    POINT_PROCESS GoCGapHalf
    POINTER vpeer
    RANGE g, i
    NONSPECIFIC_CURRENT i
}

UNITS {
    (nA) = (nanoamp)
    (mV) = (millivolt)
    (uS) = (microsiemens)
}

PARAMETER {
    g = 0.001 (uS)
}

ASSIGNED {
    v (mV)
    vpeer (mV)
    i (nA)
}

BREAKPOINT {
    i = g * (v - vpeer)
}
