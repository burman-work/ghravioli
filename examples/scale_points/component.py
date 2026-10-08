"""Scale native point values without converting geometry to JSON."""

scaled_points = []
log = "not started"

try:
    input_points = [] if points is None else list(points)
    scale_factor = 1.0 if factor is None else float(factor)
    scaled_points = [point * scale_factor for point in input_points if point is not None]
    skipped = len(input_points) - len(scaled_points)
    log = f"scaled {len(scaled_points)} point(s) by {scale_factor:g}; skipped {skipped} null value(s)"
except (TypeError, ValueError) as error:
    scaled_points = []
    log = f"error: {type(error).__name__}: {error}"
