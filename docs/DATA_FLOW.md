# Connected-component data flow

The component boundary should remain visible to Grasshopper and portable across
Python recomputations.

| Value | Representation |
| --- | --- |
| Number, string, boolean | Native scalar wire |
| Rhino geometry | Native geometry wire |
| Repeated values | Grasshopper list |
| Complex portable state | Versioned JSON string |
| Human diagnostics | Separate `log` string |

Do not pass Python dictionaries, custom class instances, module objects,
callbacks, or other interpreter-specific state across a component wire. These
objects are opaque to Grasshopper and brittle across recomputation.

When structured state is necessary, use a JSON text envelope:

```json
{
  "schema": "example.settings",
  "version": 1,
  "producer": "prepare-settings",
  "payload": {"spacing": 2.5, "count": 12},
  "warnings": []
}
```

A consumer validates `schema`, rejects unknown versions, and validates required
payload fields before use. Keep geometry out of JSON when it can stay on a
native wire. Keep the component `log` human-readable even when warnings also
appear in a machine-readable envelope.
