# `booster-doctor`

Analyze `kore-rpc-booster` fallback logs and convert them to K claims.

## Workflow

### Prerequisites

The tool needs two inputs:
* a kompiled (with `--backend haskell`) definition directory
* a bug report archive `bug_report.tar.gz` produced by a `pyk`-powered K semantics tool (e.g. Kontrol) based on the abode definition
  - the requests in the bug report must have `"log-fallback": true` and `"log-failed-rewrites": true`
  - if the log options are provided in the requests, their corresponded responses will contain informative `"fallback"` log entries in the `"logs"` field

### Running `booster-doctor`

Create a directory `<output_dir>` to store the output `booster-doctor`.

From the root of your `pyk` source code checkout, run:

```
poetry run booster-doctor --verbose --definition-dir <defintion_dir> <bug_report.tar.gz_file> --build-claims --output-dir <output_dir>
```

The tool will unpack the bug report into a temporary directory and start producing K claims from the fallback log entries, the output will looks similar to:

```
INFO pyk.booster_doctor.__main__ - Found execute request testing_br/rpc_42/003_request.json
INFO pyk.booster_doctor.__main__ - Processing /tmp/tmplrplicm3/testing_br/rpc_42/003_response.json
INFO pyk.booster_doctor.__main__ - Found 1 fallback logs
INFO pyk.booster_doctor.__main__ - Generated claim 003_response-1
INFO pyk.booster_doctor.__main__ - Writing claims to file testing_br_booster_fallbacks/testing_br.tar.gz-testing_br/rpc_42/003_response.json.k
...
```

The K claims will be written into a separate K file for every response, i.e. if a response has 7 fallback logs, it's corresponding K file in `<output_dir>` will contain 7 claims.

## Using `booster-doctor` as a library

The K claims for every response are bundled into `dict[str, KClaimWithComment]` data structure that contains the claims and the falllback reasons that `kore-rpc-booster` returned. These are returned from the `process_single_response` function and can be manipulated with `pyk` as needed (minimized, proven, etc.)
