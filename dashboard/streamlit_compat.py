"""Small Streamlit compatibility helpers for mixed local environments."""

from __future__ import annotations

import inspect
from typing import Any


def _image_accepts_stretch_width(image_func: Any) -> bool:
    try:
        width_param = inspect.signature(image_func).parameters.get("width")
    except (TypeError, ValueError):
        return False

    return width_param is not None and width_param.default == "content"


def image_full_width(st_module: Any, image: Any, **kwargs: Any) -> Any:
    """Render an image at container width across Streamlit 1.39 and 1.56+."""
    if _image_accepts_stretch_width(st_module.image):
        return st_module.image(image, width="stretch", **kwargs)

    return st_module.image(image, use_column_width=True, **kwargs)
