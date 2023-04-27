requires "nondet.k"

module NONDET-VERIFICATION-SYNTAX
    syntax Id ::= "$s" [token]
                | "$k" [token]
                | "$m" [token]
                | "$n" [token]
                | "$i" [token]
endmodule

module NONDET-VERIFICATION
    imports NONDET-VERIFICATION-SYNTAX
    imports NONDET

    syntax KItem ::= "#FINISH"

    rule [halt]: <k> #FINISH => . ... </k>
endmodule

