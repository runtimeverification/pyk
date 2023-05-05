requires "refute-node.k"

module REFUTE-NODE-SPEC
    imports REFUTE-NODE

    claim [split-int-fail]: d(N) => e(N +Int 1)
endmodule