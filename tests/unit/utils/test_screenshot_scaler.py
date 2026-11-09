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

"""Unit tests for configurable screenshot resolution and coordinate scaling in Nemesis."""

from __future__ import annotations

import io
import logging

from PIL import Image
import pytest

from artemis.utils.screenshot_scaler import (
    ScalingTransform,
    get_model_screenshot_max_width,
    parse_screenshot_resolution,
    scale_screenshot,
)


def _create_test_image(width: int, height: int, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """Creates a raw JPEG image of specified dimensions."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class TestResolutionConfiguration:
    """Tests environment and settings resolution parsing and error handling."""

    @pytest.mark.parametrize(
        "val, expected",
        [
            (0, 0),
            ("0", 0),
            (None, 0),
            ("", 0),
            ("   ", 0),
            (1280, 1280),
            ("1280", 1280),
            (1024, 1024),
            ("1024", 1024),
            ("1280x720", 1280),
            ("1024X768", 1024),
            (1280.0, 1280),
        ],
    )
    def test_parse_valid_resolutions(self, val, expected):
        assert parse_screenshot_resolution(val) == expected

    @pytest.mark.parametrize(
        "invalid_val",
        [
            -1,
            "-1",
            -500,
            "-1280",
            "invalid",
            "not_a_number",
            "auto",
            "[1280]",
            float("nan"),
            float("inf"),
            True,
            False,
        ],
    )
    def test_parse_invalid_resolutions_fallback_and_warning(self, invalid_val, caplog):
        with caplog.at_level(logging.WARNING, logger="nemesis.screenshot_scaler"):
            result = parse_screenshot_resolution(invalid_val)
        assert result == 0, f"Expected 0 fallback for {invalid_val!r}, got {result}"
        assert any(
            "nemesis" in record.name or "nemesis" in record.message for record in caplog.records
        )

    def test_get_model_screenshot_max_width_priority(self, monkeypatch):
        # 1. Unset -> 0
        monkeypatch.delenv("MODEL_SCREENSHOT_MAX_WIDTH", raising=False)
        monkeypatch.delenv("MODEL_SCREENSHOT_RESOLUTION", raising=False)
        monkeypatch.delenv("NEMESIS_MODEL_SCREENSHOT_MAX_WIDTH", raising=False)
        monkeypatch.delenv("NEMESIS_MODEL_SCREENSHOT_RESOLUTION", raising=False)
        assert get_model_screenshot_max_width() == 0

        # 2. MODEL_SCREENSHOT_MAX_WIDTH
        monkeypatch.setenv("MODEL_SCREENSHOT_MAX_WIDTH", "1280")
        assert get_model_screenshot_max_width() == 1280

        # 3. NEMESIS namespace override
        monkeypatch.delenv("MODEL_SCREENSHOT_MAX_WIDTH", raising=False)
        monkeypatch.setenv("NEMESIS_MODEL_SCREENSHOT_MAX_WIDTH", "1024")
        assert get_model_screenshot_max_width() == 1024

        # 4. MODEL_SCREENSHOT_RESOLUTION
        monkeypatch.delenv("NEMESIS_MODEL_SCREENSHOT_MAX_WIDTH", raising=False)
        monkeypatch.setenv("MODEL_SCREENSHOT_RESOLUTION", "720")
        assert get_model_screenshot_max_width() == 720


class TestScalingTransformMath:
    """Tests the mathematical accuracy and edge-case handling of coordinate scaling."""

    def test_native_resolution_identity(self):
        """When not scaled, model coordinates map 1:1 to native coordinates."""
        transform = ScalingTransform(
            native_width=1920,
            native_height=1080,
            scaled_width=1920,
            scaled_height=1080,
        )
        assert not transform.is_scaled
        assert transform.scale_x == 1.0
        assert transform.scale_y == 1.0
        assert transform.model_to_native(960, 540) == (960, 540)
        assert transform.native_to_model(960, 540) == (960, 540)

    def test_downscaled_proportional_mapping(self):
        """Verify: x_native = x_model * (width_native / width_scaled)"""
        # Native: 1920x1080, Scaled: 1280x720 (scale ratio = 1.5)
        transform = ScalingTransform(
            native_width=1920,
            native_height=1080,
            scaled_width=1280,
            scaled_height=720,
        )
        assert transform.is_scaled

        # Center point
        assert transform.model_to_native(640, 360) == (960, 540)
        assert transform.native_to_model(960, 540) == (640, 360)

        # Arbitrary target
        # 100 * 1.5 = 150; 200 * 1.5 = 300
        assert transform.model_to_native(100, 200) == (150, 300)
        assert transform.native_to_model(150, 300) == (100, 200)

    def test_boundary_and_rounding_avoidance_of_out_of_bounds(self):
        """Ensure boundary coordinates never result in off-by-one out-of-bounds pixels."""
        transform = ScalingTransform(
            native_width=1920,
            native_height=1080,
            scaled_width=1280,
            scaled_height=720,
        )
        # Top-left corner
        assert transform.model_to_native(0, 0) == (0, 0)
        # Bottom-right corner (1280, 720) must clamp to (1919, 1079)
        assert transform.model_to_native(1280, 720) == (1919, 1079)
        # Negative coordinates clamp to 0
        assert transform.model_to_native(-50, -100) == (0, 0)
        # Far out-of-bounds clamp to maximum screen boundary
        assert transform.model_to_native(5000, 5000) == (1919, 1079)

    def test_letterbox_offset_subtraction(self):
        """Padding/letterbox offsets must be subtracted before applying resolution scaling."""
        # Scaled image 1280x720 centered inside 1280x800 letterbox canvas (offset_y = 40)
        transform = ScalingTransform(
            native_width=1920,
            native_height=1080,
            scaled_width=1280,
            scaled_height=720,
            offset_x=0,
            offset_y=40,
        )
        # Model click at y=400 corresponds to unpadded y = 360, which scales to 360 * 1.5 = 540
        assert transform.model_to_native(640, 400) == (960, 540)
        # Inverse: native y=540 maps to model y=360 + 40 = 400
        assert transform.native_to_model(960, 540) == (640, 400)

    def test_mobile_portrait_aspect_ratio_scaling(self):
        """Test with high-DPI Android phone screen: 1440x3120 scaled to 720x1560."""
        transform = ScalingTransform(
            native_width=1440,
            native_height=3120,
            scaled_width=720,
            scaled_height=1560,
        )
        # Center of phone screen
        assert transform.model_to_native(360, 780) == (720, 1560)
        assert transform.native_to_model(720, 1560) == (360, 780)

    def test_sequence_and_bounds_scaling(self):
        transform = ScalingTransform(
            native_width=1920,
            native_height=1080,
            scaled_width=1280,
            scaled_height=720,
        )
        sequence = [(100, 100), (200, 200)]
        assert transform.model_sequence_to_native(sequence) == [(150, 150), (300, 300)]
        bounds = [100, 100, 200, 200]
        assert transform.model_bounds_to_native(bounds) == [150, 150, 300, 300]


class TestScreenshotResizing:
    """Tests image resizing, aspect ratio preservation, and payload efficiency."""

    def test_native_resolution_zero_preserves_original(self):
        native_bytes = _create_test_image(1920, 1080)
        out_bytes, out_b64, transform = scale_screenshot(native_bytes, max_width=0)
        assert out_bytes == native_bytes
        assert not transform.is_scaled
        assert transform.native_width == 1920
        assert transform.native_height == 1080
        assert transform.scaled_width == 1920
        assert transform.scaled_height == 1080

    def test_smaller_image_not_upscaled(self):
        native_bytes = _create_test_image(800, 600)
        out_bytes, out_b64, transform = scale_screenshot(native_bytes, max_width=1280)
        assert out_bytes == native_bytes
        assert not transform.is_scaled
        assert transform.scaled_width == 800
        assert transform.scaled_height == 600

    def test_landscape_downscaling_strictly_preserves_aspect_ratio(self):
        native_bytes = _create_test_image(1920, 1080)
        out_bytes, out_b64, transform = scale_screenshot(native_bytes, max_width=1280)

        assert transform.is_scaled
        assert transform.native_width == 1920
        assert transform.native_height == 1080
        assert transform.scaled_width == 1280
        assert transform.scaled_height == 720

        # Check decoded image
        decoded_img = Image.open(io.BytesIO(out_bytes))
        assert decoded_img.size == (1280, 720)

        # Aspect ratio must match 16:9 exactly
        native_ratio = 1920 / 1080
        scaled_ratio = 1280 / 720
        assert abs(native_ratio - scaled_ratio) < 1e-4

        # Payload size must be significantly smaller than original
        assert len(out_bytes) < len(native_bytes)

    def test_portrait_downscaling_strictly_preserves_aspect_ratio(self):
        # High resolution mobile screen: 1440x3120 (19.5:9)
        native_bytes = _create_test_image(1440, 3120)
        out_bytes, out_b64, transform = scale_screenshot(native_bytes, max_width=720)

        assert transform.is_scaled
        assert transform.scaled_width == 720
        assert transform.scaled_height == 1560

        decoded_img = Image.open(io.BytesIO(out_bytes))
        assert decoded_img.size == (720, 1560)

        native_ratio = 1440 / 3120
        scaled_ratio = 720 / 1560
        assert abs(native_ratio - scaled_ratio) < 1e-4
        assert len(out_bytes) < len(native_bytes)

    def test_resolution_1024_downscaling(self):
        native_bytes = _create_test_image(2048, 1536)  # 4:3
        out_bytes, out_b64, transform = scale_screenshot(native_bytes, max_width=1024)

        assert transform.scaled_width == 1024
        assert transform.scaled_height == 768
        decoded_img = Image.open(io.BytesIO(out_bytes))
        assert decoded_img.size == (1024, 768)

    def test_letterbox_padding(self):
        native_bytes = _create_test_image(1920, 1080)
        # Scale to width 1280 (scaled size: 1280x720) into letterbox canvas of 1280x800
        out_bytes, out_b64, transform = scale_screenshot(
            native_bytes, max_width=1280, letterbox_target=(1280, 800)
        )
        assert transform.offset_x == 0
        assert transform.offset_y == 40
        decoded_img = Image.open(io.BytesIO(out_bytes))
        assert decoded_img.size == (1280, 800)
