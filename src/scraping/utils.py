import os


def resolve_output_path(out_path):
    """Ensure the output path points to a writable location (/tmp for Lambda)."""
    if not os.path.isabs(out_path):
        out_path = os.path.join("/tmp", out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    return out_path