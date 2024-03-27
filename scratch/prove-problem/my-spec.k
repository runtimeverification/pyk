requires "imp-verification.k"

module MY-SPEC
  imports IMP-VERIFICATION

  claim [aClaim]:
      <k>
        while (! (0 == $s))
          $s = $s + -1; // original version
          // $s = $s + 1; // _loops with modified condition, _passes_ despite non-termination with original 0 <= S
          =>
        .K
        ...
      </k>
    <env>
        $s |-> (S => 0)
    </env>
  // requires 0 <=Int S // original version, passes
  requires 0 >=Int S // -> _passes_, despite non-termination when 0 =/= S
  // requires 0 >Int S // -> loops in execute request when proving
  // requires 0 <Int S // loops (non-termination) when loop-body changed

endmodule
