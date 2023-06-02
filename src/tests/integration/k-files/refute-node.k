module REFUTE-NODE-SYNTAX
    imports INT

    syntax A ::= "a" | "b" | "c" | d(Int) | e(Int) | "f"
endmodule

module REFUTE-NODE
    imports REFUTE-NODE-SYNTAX

    rule <k> d(N) => e(N +Int 1) ... </k> requires N >Int 0
    rule <k> d(N) => e(N -Int 1) ... </k> requires N <=Int 0

endmodule
