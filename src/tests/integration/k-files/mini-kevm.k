requires "domains.md"

module MINI-KEVM
    imports INT
    imports BOOL
    imports BYTES
    imports K-EQUAL

    configuration
        <k> $PGM:KItem </k>
        <callData> .Bytes </callData>
        <id> 0 </id>
        <accounts>
          <account multiplicity="*" type="Map">
            <acctID> 0 </acctID>
            <storage> .Map </storage>
            <origStorage> .Map </origStorage>
          </account>
        </accounts>

    syntax KItem ::= "a" | "b"
    rule <k> a => b ... </k>

    // Words

    syntax Int ::= "pow160" [alias]
                 | "pow256" [alias]
    rule pow160 => 1461501637330902918203684832716283019655932542976
    rule pow256 => 115792089237316195423570985008687907853269984665640564039457584007913129639936

    syntax Bool ::= #rangeUInt ( Int , Int ) [alias]
    rule #rangeUInt(160, X) => 0 <=Int X andBool X <Int pow160
    rule #rangeUInt(256, X) => 0 <=Int X andBool X <Int pow256

    syntax Int ::= chop ( Int ) [function, total, smtlib(chop)]
    rule chop(X) => X modInt pow256 [concrete, smt-lemma]

    syntax Int ::= Int "+Word" Int [function, total]
    rule X +Word Y => chop(X +Int Y)

    // ABI Typed Args

    syntax TypedArgs ::= List{TypedArg, ","}
    syntax TypedArg ::= #uint256 ( Int )
                      | #address ( Int )

    syntax Int ::= #getValue ( TypedArg ) [function]
    rule #getValue(#uint256(X)) => X requires #rangeUInt(256, X)
    rule #getValue(#address(X)) => X requires #rangeUInt(160, X)

    syntax Bytes ::= #abiCallData ( String , TypedArgs ) [function]
    rule #abiCallData( FNAME , ARGS ) => b"\x00\x00\x00\x00" +Bytes #encodeArgs(ARGS)

    syntax Bytes ::= #encodeArgs    ( TypedArgs )                       [function]
    syntax Bytes ::= #encodeArgsAux ( TypedArgs , Int , Bytes , Bytes ) [function]
    rule #encodeArgs(ARGS) => #encodeArgsAux(ARGS, #lenOfHeads(ARGS), .Bytes, .Bytes)

    rule #encodeArgsAux(.TypedArgs, _:Int, HEADS, TAILS) => HEADS +Bytes TAILS

    rule #encodeArgsAux((ARG, ARGS), OFFSET, HEADS, TAILS)
        => #encodeArgsAux(ARGS, OFFSET, HEADS +Bytes #enc(ARG), TAILS)

    syntax Int ::= #lenOfHeads ( TypedArgs ) [function, total]
    rule #lenOfHeads(.TypedArgs) => 0
    rule #lenOfHeads(ARG, ARGS)  => #lenOfHead(ARG) +Int #lenOfHeads(ARGS)

    syntax Int ::= #lenOfHead ( TypedArg ) [function, total]
    rule #lenOfHead(#address( _ )) => 32
    rule #lenOfHead(#uint256( _ )) => 32

    syntax Bytes ::= #enc ( TypedArg ) [function]
    rule #enc(#address( DATA )) => #bufStrict(32, #getValue(#address( DATA )))
    rule #enc(#uint256( DATA )) => #bufStrict(32, #getValue(#uint256( DATA )))

    // Buffers

    syntax Bytes ::= #bufStrict ( Int , Int ) [function]
    syntax Bytes ::= #buf ( Int , Int ) [function, total, smtlib(buf)]

    syntax Int ::= #powByteLen ( Int ) [function, no-evaluators]
    rule 2 ^Int (SIZE *Int 8) => #powByteLen(SIZE) [symbolic(SIZE), simplification]

    rule 0    <Int #powByteLen(SIZE) => true requires 0 <=Int SIZE [simplification]
    rule SIZE <Int #powByteLen(SIZE) => true requires 0 <=Int SIZE [simplification]

    rule #bufStrict(SIZE, DATA) => #buf(SIZE, DATA)
      requires 0 <=Int DATA andBool DATA <Int (2 ^Int (SIZE *Int 8))

    rule #buf(SIZE, DATA) => #padToWidth(SIZE, #asByteStack(DATA %Int (2 ^Int (SIZE *Int 8))))
      requires 0 <Int SIZE
      [concrete]
    rule #buf(_SIZE, _) => .Bytes [owise, concrete] // SIZE <= 0

    syntax Bytes ::= #padToWidth ( Int , Bytes ) [function, total]
    rule #padToWidth(N, BS) =>              BS        requires notBool (0 <=Int N) [concrete]
    rule #padToWidth(N, BS) => padLeftBytes(BS, N, 0) requires          0 <=Int N  [concrete]

    syntax Bytes ::= #asByteStack ( Int ) [function, total]
    rule #asByteStack(W) => Int2Bytes(W, BE, Unsigned) [concrete]

    // Hashed Locations

    syntax IntList ::= List{Int, ""} [klabel(intList), smtlib(intList)]

    syntax Int ::= keccak ( Bytes ) [function, total, no-evaluators, smtlib(keccak)]

    syntax Int ::= #hashedLocation( String , Int , IntList ) [function, klabel(hashLoc), smtlib(hashLoc)]
    rule #hashedLocation(_LANG, BASE, .IntList      ) => BASE
    rule #hashedLocation( LANG, BASE, OFFSET OFFSETS) => #hashedLocation(LANG, #hashedLocation(LANG, BASE, OFFSET .IntList), OFFSETS) requires OFFSETS =/=K .IntList

    rule #hashedLocation("Vyper",    BASE, OFFSET .IntList) => keccak(#bufStrict(32, BASE)   +Bytes #bufStrict(32, OFFSET)) requires #rangeUInt(256, BASE) andBool #rangeUInt(256, OFFSET)
    rule #hashedLocation("Solidity", BASE, OFFSET .IntList) => keccak(#bufStrict(32, OFFSET) +Bytes #bufStrict(32, BASE))   requires #rangeUInt(256, BASE) andBool #rangeUInt(256, OFFSET) [simplification]
    rule #hashedLocation("Array",    BASE, OFFSET .IntList) => keccak(#bufStrict(32, BASE))  +Word OFFSET                   requires #rangeUInt(256, BASE) andBool #rangeUInt(256, OFFSET)

endmodule
