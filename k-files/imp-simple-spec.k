requires "imp-verification.k"

module IMP-SIMPLE-SPEC
    imports IMP-VERIFICATION

    claim [addition-1]: <k> 3 + 4 => 7 ... </k>

    claim [addition-2]: <k> $s + $n => 7 ... </k> <state> $s |-> 3 $n |-> 4 </state>
endmodule
