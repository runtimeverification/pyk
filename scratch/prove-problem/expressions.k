module VALUE-SYNTAX
  imports UNSIGNED-INT-SYNTAX
  imports BOOL-SYNTAX

  syntax Value ::= Int
                 | Bool

  syntax KResult ::= Value
endmodule

module EXPRESSIONS-SYNTAX
  imports VALUE-SYNTAX

  syntax Expr     ::= Value
                    | "(" Expr ")" [bracket]

  syntax Expr     ::= "-" Expr      [group(unary), strict, non-assoc]
                    > left:
                      Expr "*" Expr [group(mul), seqstrict]
                    | Expr "/" Expr [group(mul), seqstrict]
                    > left:
                      Expr "+" Expr [group(add), seqstrict]
                    | Expr "-" Expr [group(add), strict]

  syntax Expr     ::= Expr "==" Expr [group(comp), seqstrict, non-assoc]
                    | Expr "!=" Expr [group(comp), seqstrict, non-assoc]
                    | Expr ">=" Expr [group(comp), seqstrict, non-assoc]
                    | Expr ">"  Expr [group(comp), seqstrict, non-assoc]
                    | Expr "<=" Expr [group(comp), seqstrict, non-assoc]
                    | Expr "<"  Expr [group(comp), strict, non-assoc]

  syntax Expr     ::= "!" Expr       [group(unary), strict, non-assoc]
                    > Expr "&&" Expr [group(bool), seqstrict, left]
                    > Expr "||" Expr [group(bool), seqstrict, left]

  syntax priority unary > mul > add > comp > bool

endmodule

module EXPRESSIONS
  imports EXPRESSIONS-SYNTAX // also imports VALUE-SYNTAX (transitive)
  imports INT
  imports BOOL

  rule   - X => 0 -Int X

  rule X + Y => X +Int Y
  rule X - Y => X -Int Y
  rule X * Y => X *Int Y
  rule X / Y => X /Int Y

  rule B1 == B2 => B1 ==Bool B2
  rule I1 == I2 => I1 ==Int I2

  rule B1 != B2 => B1 =/=Bool B2
  rule I1 != I2 => I1 =/=Int  I2

  rule I1 >= I2 => I1 >=Int I2
  rule I1 >  I2 => I1 >Int  I2
  rule I1 <= I2 => I1 <=Int I2
  rule I1 <  I2 => I1 <Int  I2

  rule ! B => notBool B
  rule B1 && B2 => B1 andBool B2
  rule B1 || B2 => B1 orBool B2
endmodule
