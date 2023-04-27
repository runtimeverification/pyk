module CONDITIONLESS-BRANCH
  imports CONDITIONLESS-BRANCH-SYNTAX
  imports INT

  configuration 
  <k>
    $PGM:K
  </k>

  
  rule a => b
  rule a => c

  rule b => d
  rule c => d

endmodule

module CONDITIONLESS-BRANCH-SYNTAX
  syntax Value ::= "a"
                 | "b"
                 | "c"
                 | "d"
endmodule
