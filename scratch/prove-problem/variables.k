requires "expressions.k"

module VARIABLES-SYNTAX
  imports EXPRESSIONS-SYNTAX
  imports ID-SYNTAX

  syntax Expr ::= Id
                | "let" Id "=" Expr "in" Expr [strict(2), avoid]
endmodule

module VARIABLES
  imports VARIABLES-SYNTAX
  imports EXPRESSIONS
  imports MAP

  configuration
    <k>   $PGM:Expr </k>
    <env> .Map      </env>

  rule
    <k> X:Id => V ... </k>
    <env> X |-> V ... </env>

  rule
    <k> let X = V in E => E ... </k>
    <env> M => M[X <- V] </env>
      requires isKResult(V)

endmodule
