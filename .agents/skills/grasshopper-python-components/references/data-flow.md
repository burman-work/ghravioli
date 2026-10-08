# Data flow between components

Choose the narrowest portable representation:

| Value | Wire representation |
| --- | --- |
| Number, text, boolean | Native scalar |
| Point, curve, mesh, Brep, other Rhino geometry | Native geometry |
| Repeated values | Grasshopper list |
| Complex portable state | Versioned JSON string |
| Human diagnostics | Separate `log` string |

Never pass Python dictionaries, custom class instances, module objects, callbacks, or other interpreter-specific runtime state between components. These values are opaque to Grasshopper, hard to inspect, and fragile across recomputation or interpreter boundaries.

## JSON envelope

Use a small versioned envelope for complex state:

```json
{
  "schema": "example.settings",
  "version": 1,
  "producer": "prepare_settings",
  "payload": {
    "spacing": 2.5,
    "count": 12
  },
  "warnings": []
}
```

Consumers must validate `schema`, reject unsupported `version` values, validate required payload fields, and report failures through their own `log` output.

Do not serialise Rhino geometry into JSON just to move it between adjacent nodes. Keep geometry on native wires and use JSON only for portable metadata or configuration. Warnings inside an envelope are machine-readable state; the component `log` remains the human-readable execution summary.
