requires "simple-proofs.k"

module SIMPLE-PROOFS-SPEC
    imports SIMPLE-PROOFS
    imports K-EQUAL-SYNTAX

    claim [a-to-e]: <k> a => e </k>
    claim [a-to-f]: <k> a => f </k>

    claim [dep1]: <k> start1 => mid </k>
    claim [dep2]: <k> start2 => mid </k>

    claim [use-deps1]: <k> start1 => end </k> [depends(SIMPLE-PROOFS-SPEC.dep1)]
    claim [use-deps2]: <k> start2 => end </k> [depends(SIMPLE-PROOFS-SPEC.dep2)]

endmodule
