requires "mini-kevm.k"

module MINI-KEVM-SPEC
    imports MINI-KEVM

    claim [ensures-constraint]:
      <k> a => b ... </k>
      <callData> #abiCallData("transferFrom", #address(FROM_ID), #address(TO_ID), #uint256(VALUE)) </callData>
      <id> ACCT_ID </id>
      <accounts>
        <account>
          <acctID> ACCT_ID </acctID>
          <storage>
            #hashedLocation("Solidity", 4, .IntList)          |-> STOPPED
            #hashedLocation("Solidity", 1, FROM_ID)           |-> BAL_FROM
            #hashedLocation("Solidity", 2, FROM_ID CALLER_ID) |-> ALLOW
            _:Map
          </storage>
          <origStorage>
            #hashedLocation("Solidity", 4, .IntList)          |-> STOPPED
            #hashedLocation("Solidity", 1, FROM_ID)           |-> BAL_FROM
            #hashedLocation("Solidity", 2, FROM_ID CALLER_ID) |-> ALLOW
            _:Map
          </origStorage>
        </account>
        ...
      </accounts>
    requires #rangeUInt(160, ACCT_ID)
     andBool #rangeUInt(160, CALLER_ID)
     andBool #rangeUInt(160, FROM_ID)
     andBool #rangeUInt(160, TO_ID)
     andBool #rangeUInt(256, VALUE)
     andBool #rangeUInt(256, BAL_FROM)
     andBool #rangeUInt(256, BAL_TO)
     andBool #rangeUInt(256, ALLOW)
     andBool #rangeUInt(256, STOPPED)
     andBool FROM_ID ==Int TO_ID
     andBool #hashedLocation("Solidity", 4, .IntList)          =/=Int #hashedLocation("Solidity", 1, FROM_ID)
     andBool #hashedLocation("Solidity", 4, .IntList)          =/=Int #hashedLocation("Solidity", 2, FROM_ID CALLER_ID)
     andBool #hashedLocation("Solidity", 2, FROM_ID CALLER_ID) =/=Int #hashedLocation("Solidity", 1, FROM_ID)
     andBool STOPPED ==Int 1 <<Int (20 *Int 8)

endmodule
