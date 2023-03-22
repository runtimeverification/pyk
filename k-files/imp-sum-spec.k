requires "imp-verification.k"

module IMP-SUM-SPEC
  imports IMP-VERIFICATION

  claim [sum-spec]:
      <k>
        while (!($n <= 0)) {
          $s = $s + $n;
          $n = $n + -1;
        }
      =>
        .K
      ...
      </k>
    <state>
        $n   |-> (N:Int => 0)
        $s |-> (S:Int => S +Int ((N +Int 1) *Int N /Int 2))
    </state>
  requires N >=Int 0

endmodule