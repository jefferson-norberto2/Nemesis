# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configurable screenshot resolution and bidirectional coordinate scaling for Nemesis.

Provides aspect-ratio preserving screenshot downscaling for multimodal model payloads
and exact coordinate transformation from model visual space back to native physical screen resolution.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import math
import os
import re
from typing import Any

from PIL import Image

from artemis.config.constants import (
    ENV_MODEL_SCREENSHOT_MAX_WIDTH,
    ENV_MODEL_SCREENSHOT_RESOLUTION,
    ENV_NEMESIS_MODEL_SCREENSHOT_MAX_WIDTH,
    ENV_NEMESIS_MODEL_SCREENSHOT_RESOLUTION,
)
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger("nemesis.screenshot_scaler")

__all__ = [
    "ScalingTransform",
    "get_model_screenshot_max_width",
    "parse_screenshot_resolution",
    "scale_screenshot",
]


def parse_screenshot_resolution(value: Any) -> int:
    """Parses a screenshot resolution value into a non-negative integer maximum width.

    Accepted formats:
    - 0, None, or empty string: 0 (signals native resolution, no downscaling).
    - Positive integers or floats (e.g. 1280, 1024, 1280.0): rounded integer.
    - String representations of numbers (e.g. "1280", "1024").
    - Dimension strings (e.g. "1280x720"): parses the width component.

    Robustness & Error Handling:
    - Negative values log a warning and fall back to 0 (native resolution).
    - Invalid or non-numeric strings log a warning and fall back to 0 (native resolution).
    """
    if value is None:
        return 0

    if isinstance(value, bool):
        logger.warning(
            f"Boolean value {value!r} is invalid for screenshot resolution in nemesis; "
            "falling back to native resolution (0)."
        )
        return 0

    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            logger.warning(
                f"Non-finite resolution value {value!r} is invalid in nemesis; "
                "falling back to native resolution (0)."
            )
            return 0
        if value < 0:
            logger.warning(
                f"Negative screenshot resolution {value!r} is invalid in nemesis; "
                "falling back to native resolution (0)."
            )
            return 0
        return int(round(value))

    if isinstance(value, str):
        clean = value.strip()
        if not clean or clean == "0":
            return 0

        # Support dimensions like "1280x720" or "1024x768"
        dim_match = re.match(r"^(\d+)\s*[xX*]\s*(\d+)$", clean)
        if dim_match:
            try:
                width_part = int(dim_match.group(1))
                if width_part > 0:
                    return width_part
            except (ValueError, TypeError):
                pass

        try:
            float_val = float(clean)
            if not math.isfinite(float_val):
                logger.warning(
                    f"Non-finite screenshot resolution string '{clean}' in nemesis; "
                    "falling back to native resolution (0)."
                )
                return 0
            if float_val < 0:
                logger.warning(
                    f"Negative screenshot resolution '{clean}' in nemesis; "
                    "falling back to native resolution (0)."
                )
                return 0
            return int(round(float_val))
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid non-numeric screenshot resolution '{clean}' in nemesis; "
                "falling back to native resolution (0)."
            )
            return 0

    logger.warning(
        f"Unsupported screenshot resolution type {type(value).__name__} ({value!r}) in nemesis; "
        "falling back to native resolution (0)."
    )
    return 0


def get_model_screenshot_max_width() -> int:
    """Resolves the configured screenshot downscaling resolution for multimodal models.

    Checks configuration sources in priority order:
    1. MODEL_SCREENSHOT_MAX_WIDTH (env / settings)
    2. MODEL_SCREENSHOT_RESOLUTION (env / settings)
    3. NEMESIS_MODEL_SCREENSHOT_MAX_WIDTH (env / settings)
    4. NEMESIS_MODEL_SCREENSHOT_RESOLUTION (env / settings)

    Returns:
        Positive integer max width in pixels, or 0 for native resolution.
    """
    for env_key in (
        ENV_MODEL_SCREENSHOT_MAX_WIDTH,
        ENV_MODEL_SCREENSHOT_RESOLUTION,
        ENV_NEMESIS_MODEL_SCREENSHOT_MAX_WIDTH,
        ENV_NEMESIS_MODEL_SCREENSHOT_RESOLUTION,
    ):
        raw = os.environ.get(env_key)
        if raw is not None and str(raw).strip():
            return parse_screenshot_resolution(raw)

    try:
        from artemis.config.settings import settings

        for attr in (
            "MODEL_SCREENSHOT_MAX_WIDTH",
            "MODEL_SCREENSHOT_RESOLUTION",
            "NEMESIS_MODEL_SCREENSHOT_MAX_WIDTH",
            "NEMESIS_MODEL_SCREENSHOT_RESOLUTION",
        ):
            val = getattr(settings, attr, None)
            if val is not None and str(val).strip():
                return parse_screenshot_resolution(val)
    except (AttributeError, KeyError, ValueError, TypeError) as exc:
        logger.debug(f"Settings lookup for screenshot resolution failed: {exc}; using default (0).")

    return 0


@dataclass(frozen=True)
class ScalingTransform:
    """Bidirectional coordinate mapping between model downscaled image and native device screen.

    Attributes:
        native_width: Physical device screen width in pixels.
        native_height: Physical device screen height in pixels.
        scaled_width: Downscaled image width delivered to the multimodal model.
        scaled_height: Downscaled image height delivered to the multimodal model.
        offset_x: Horizontal padding / letterbox offset (if padding was used).
        offset_y: Vertical padding / letterbox offset (if padding was used).
    """

    native_width: int
    native_height: int
    scaled_width: int
    scaled_height: int
    offset_x: int = 0
    offset_y: int = 0

    @property
    def is_scaled(self) -> bool:
        """True if downscaling or offset transformation is actively modifying coordinates."""
        return (
            (self.scaled_width != self.native_width)
            or (self.scaled_height != self.native_height)
            or (self.offset_x != 0)
            or (self.offset_y != 0)
        )

    @property
    def scale_x(self) -> float:
        """Ratio of scaled width to native width."""
        return self.scaled_width / self.native_width if self.native_width > 0 else 1.0

    @property
    def scale_y(self) -> float:
        """Ratio of scaled height to native height."""
        return self.scaled_height / self.native_height if self.native_height > 0 else 1.0

    def model_to_native(self, x_model: float, y_model: float) -> tuple[int, int]:
        """Maps predicted model coordinates (x_model, y_model) back to native screen coordinates.

        Formula:
            x_native = round((x_model - offset_x) * (width_native / width_scaled))
            y_native = round((y_model - offset_y) * (height_native / height_scaled))

        Guarantees rounding logic avoids off-by-one errors and coordinates stay strictly
        within valid screen boundaries [0, native_width - 1] and [0, native_height - 1].
        """
        if not self.is_scaled:
            x_int = int(round(float(x_model)))
            y_int = int(round(float(y_model)))
            max_x = max(0, self.native_width - 1)
            max_y = max(0, self.native_height - 1)
            return max(0, min(max_x, x_int)), max(0, min(max_y, y_int))

        unpadded_x = float(x_model) - self.offset_x
        unpadded_y = float(y_model) - self.offset_y

        scale_ratio_x = self.native_width / self.scaled_width if self.scaled_width > 0 else 1.0
        scale_ratio_y = self.native_height / self.scaled_height if self.scaled_height > 0 else 1.0

        native_x = int(round(unpadded_x * scale_ratio_x))
        native_y = int(round(unpadded_y * scale_ratio_y))

        max_x = max(0, self.native_width - 1)
        max_y = max(0, self.native_height - 1)
        return max(0, min(max_x, native_x)), max(0, min(max_y, native_y))

    def native_to_model(self, x_native: float, y_native: float) -> tuple[int, int]:
        """Maps native screen coordinates (x_native, y_native) to downscaled model image coordinates.

        Formula:
            x_model = round(x_native * (width_scaled / width_native)) + offset_x
            y_model = round(y_native * (height_scaled / height_native)) + offset_y
        """
        if not self.is_scaled:
            x_int = int(round(float(x_native)))
            y_int = int(round(float(y_native)))
            max_x = max(0, self.native_width - 1)
            max_y = max(0, self.native_height - 1)
            return max(0, min(max_x, x_int)), max(0, min(max_y, y_int))

        scale_ratio_x = self.scaled_width / self.native_width if self.native_width > 0 else 1.0
        scale_ratio_y = self.scaled_height / self.native_height if self.native_height > 0 else 1.0

        model_x = int(round(float(x_native) * scale_ratio_x)) + self.offset_x
        model_y = int(round(float(y_native) * scale_ratio_y)) + self.offset_y

        max_x = max(0, self.scaled_width - 1 + self.offset_x)
        max_y = max(0, self.scaled_height - 1 + self.offset_y)
        return max(0, min(max_x, model_x)), max(0, min(max_y, model_y))

    def model_sequence_to_native(
        self, sequence: list[tuple[float, float] | list[float]]
    ) -> list[tuple[int, int]]:
        """Maps a sequence of model coordinates to physical native screen coordinates."""
        return [self.model_to_native(pt[0], pt[1]) for pt in sequence]

    def model_bounds_to_native(self, bounds: list[float] | tuple[float, ...]) -> list[int]:
        """Maps model bounding box [x1, y1, x2, y2] to physical screen bounds."""
        if len(bounds) != 4:
            return [int(round(x)) for x in bounds]
        x1, y1 = self.model_to_native(bounds[0], bounds[1])
        x2, y2 = self.model_to_native(bounds[2], bounds[3])
        return [x1, y1, x2, y2]


def scale_screenshot(
    image_input: bytes | str | Image.Image,
    max_width: int | None = None,
    letterbox_target: tuple[int, int] | None = None,
) -> tuple[bytes, str, ScalingTransform]:
    """Resizes a screenshot before sending to the multimodal model according to configured resolution.

    Strictly preserves the original aspect ratio without distortion or cropping.

    Args:
        image_input: Raw image bytes, base64-encoded string, or PIL Image.
        max_width: Explicit max width override; if None, resolves from environment/settings.
        letterbox_target: Optional (target_width, target_height) canvas box for padded letterboxing.

    Returns:
        Tuple of (output_bytes, output_b64, scaling_transform).
    """
    if max_width is None:
        max_width = get_model_screenshot_max_width()

    # Load image and extract raw bytes
    if isinstance(image_input, Image.Image):
        pil_img = image_input
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=90)
        orig_bytes = buf.getvalue()
        orig_b64 = base64.b64encode(orig_bytes).decode("utf-8")
    elif isinstance(image_input, str):
        clean_b64 = image_input.split(",", 1)[-1] if "," in image_input else image_input
        orig_bytes = base64.b64decode(clean_b64)
        orig_b64 = clean_b64
        pil_img = Image.open(io.BytesIO(orig_bytes))
    elif isinstance(image_input, (bytes, bytearray)):
        orig_bytes = bytes(image_input)
        orig_b64 = base64.b64encode(orig_bytes).decode("utf-8")
        pil_img = Image.open(io.BytesIO(orig_bytes))
    else:
        raise TypeError(f"Unsupported image_input type: {type(image_input).__name__}")

    native_width, native_height = pil_img.size

    # Fast path: Native resolution requested or already within max_width bounds without padding
    if (max_width <= 0 or native_width <= max_width) and not letterbox_target:
        transform = ScalingTransform(
            native_width=native_width,
            native_height=native_height,
            scaled_width=native_width,
            scaled_height=native_height,
            offset_x=0,
            offset_y=0,
        )
        return orig_bytes, orig_b64, transform

    # Calculate proportional downscaled dimensions strictly preserving aspect ratio
    if max_width > 0 and native_width > max_width:
        scale_ratio = float(max_width) / float(native_width)
        scaled_width = int(max_width)
        scaled_height = max(1, int(round(native_height * scale_ratio)))
    else:
        scaled_width = native_width
        scaled_height = native_height

    # Perform high-performance Lanczos downscaling
    resized_pil = pil_img.resize((scaled_width, scaled_height), resample=Image.Resampling.LANCZOS)

    # Optional letterbox canvas padding
    offset_x = 0
    offset_y = 0
    final_pil = resized_pil
    if letterbox_target:
        target_w, target_h = letterbox_target
        if target_w > scaled_width or target_h > scaled_height:
            canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
            offset_x = max(0, (target_w - scaled_width) // 2)
            offset_y = max(0, (target_h - scaled_height) // 2)
            canvas.paste(resized_pil, (offset_x, offset_y))
            final_pil = canvas

    out_buf = io.BytesIO()
    # Save as JPEG for minimal payload and low serialization latency
    if final_pil.mode in ("RGBA", "P"):
        final_pil = final_pil.convert("RGB")
    final_pil.save(out_buf, format="JPEG", quality=85, optimize=True)
    scaled_bytes = out_buf.getvalue()
    scaled_b64 = base64.b64encode(scaled_bytes).decode("utf-8")

    transform = ScalingTransform(
        native_width=native_width,
        native_height=native_height,
        scaled_width=scaled_width,
        scaled_height=scaled_height,
        offset_x=offset_x,
        offset_y=offset_y,
    )
    return scaled_bytes, scaled_b64, transform
