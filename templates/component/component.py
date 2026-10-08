"""Project-neutral Grasshopper Python 3 component template."""

result = []
log = "not started"

try:
    input_values = [] if values is None else list(values)
    result = input_values
    log = f"processed {len(result)} value(s)"
except (TypeError, ValueError) as error:
    result = []
    log = f"error: {type(error).__name__}: {error}"
