File [schema.graphql](schema.graphql) contains the proposed schema for the K-REPL Server GraphQL API.

The following table lists how each REPL command, as described in the [README](../README.md), is covered by a query or mutation of the GraphQL API.

|    REPL command    |      GraphQL API       |
|--------------------|------------------------|
| `load`             | `mutation load`        |
| `load-raw`         | `mutation load-raw`    |
| `step`             | `mutation step`        |  
| `step-to-branch`   | `mutation step`        |
| `rewind`           | `mutation rewind`      |
| `alias`            | `mutation addAlias`    |
| `rm-alias`         | `mutation removeAlias` |
| `edit`             | `mutation updateCell`  |
| `wait-for`         | `query wait`           |
| `check-completion` | `query processes`      |
| `show-diff`        | `query diff`           |
| `show`             | `query graph`          |
| `show-cell`        | `query graph`          |
| `show-cfg`         | `query graph`          |
| `list-aliases`     | `query graph`          |
| `predecessor`      | `query graph`          |
| `successors`       | `query graph`          | 
