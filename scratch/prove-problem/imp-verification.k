requires "statements.k"

module IMP-VERIFICATION-SYNTAX
    imports ID-SYNTAX
    imports INT-SYNTAX

    syntax Id ::= "$s" [token]
                | "$s1" [token]
                | "$s2" [token]
                | "$n" [token]
                | "$m" [token]
                | "$k" [token]
endmodule


module IMP-VERIFICATION
    imports IMP-VERIFICATION-SYNTAX
    imports STATEMENTS

    // inequality sign normalization
    rule          A  >Int B  => B  <Int A [simplification]
    rule          A >=Int B  => B <=Int A [simplification]
    rule notBool (A  <Int B) => B <=Int A [simplification]
    rule notBool (A <=Int B) => B  <Int A [simplification]

endmodule
