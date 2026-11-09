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

"""Unit tests for coordinate resolution scaling in McpActionExecutor and AdbActuator.

Verifies end-to-end bidirectional coordinate mapping across:
1. Native resolution (MODEL_SCREENSHOT_MAX_WIDTH=0 or unset).
2. Proportional downscaled resolutions (e.g. 1920x1080 downscaled to 1280x720).
3. Mobile portrait aspect ratios (e.g. 1440x3120 downscaled to 720x1560).
4. Actions: click, click_sequence, swipe, long_press, input_text.
5. Letterboxing and padding offset compensation.
6. UnifiedMobileController coordinate scaling helper methods.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from artemis.controllers.unified_controller import UnifiedMobileController
from artemis.mcp.action_executor import McpActionExecutor
from artemis.mcp.actuators.adb import AdbActuator
from artemis.utils.coordinates import scale_model_coordinates_to_native
from artemis.utils.screenshot_scaler import ScalingTransform


def _make_context(
    native_width: int = 1920,
    native_height: int = 1080,
    scaled_width: int | None = None,
    scaled_height: int | None = None,
    offset_x: int = 0,
    offset_y: int = 0,
):
    ctx = Mock()
    ctx.device = Mock()
    ctx.device.device_width = native_width
    ctx.device.device_height = native_height

    if scaled_width is not None and scaled_height is not None:
        ctx.scaling_transform = ScalingTransform(
            native_width=native_width,
            native_height=native_height,
            scaled_width=scaled_width,
            scaled_height=scaled_height,
            offset_x=offset_x,
            offset_y=offset_y,
        )
    else:
        ctx.scaling_transform = None

    return ctx


def _state():
    state = Mock()
    state.indexed_elements = []
    state.indexed_points = []
    state.latest_ui_hierarchy = None
    return state


# ====================================================================================
# 1. Native Resolution Execution (Resolution = 0 or unset)
# ====================================================================================


def test_native_resolution_click_translation_matches_historical_behavior():
    """When resolution is native (no scaling), coordinates pass through normalized."""
    ctx = _make_context(native_width=1080, native_height=2400)
    executor = McpActionExecutor(ctx)

    wire_name, wire_args, _, recorded = executor._translate(
        "click",
        {"target": [500, 500], "target_description": "center button"},
        _state(),
    )

    assert wire_name == "click"
    assert wire_args["target"] == [500, 500]
    assert recorded["target_description"] == "center button"
    assert "target_native_coordinates" not in recorded


def test_native_resolution_actuator_maps_normalized_to_native_physical_pixels():
    """Actuator converts 0-1000 normalized coordinates to physical device pixels."""
    ctx = _make_context(native_width=1080, native_height=2400)
    actuator = AdbActuator(ctx)

    px, py = actuator._to_px(500, 500)
    # 500/1000 * 1080 = 540, 500/1000 * 2400 = 1200
    assert px == 540
    assert py == 1200


# ====================================================================================
# 2. Downscaled Landscape (1920x1080 -> 1280x720, Scaling factor = 1.5)
# ====================================================================================


def test_downscaled_click_coordinate_scaling():
    """Click coordinates from model image (1280x720) scale back to physical screen (1920x1080)."""
    ctx = _make_context(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
    )
    executor = McpActionExecutor(ctx)

    # Center of downscaled image is [640, 360]
    wire_name, wire_args, _, recorded = executor._translate(
        "click",
        {"target": [640, 360], "target_description": "play button"},
        _state(),
    )

    assert wire_name == "click"
    # Physical: 640 * 1.5 = 960, 360 * 1.5 = 540
    # Normalized for wire: 960/1920 * 1000 = 500, 540/1080 * 1000 = 500
    assert wire_args["target"] == [500, 500]
    assert recorded["target_description"] == "play button"
    assert recorded["target_native_coordinates"] == [960, 540]

    # Verify actuator translates wire coordinates back to exact native pixel
    actuator = AdbActuator(ctx)
    px, py = actuator._to_px(wire_args["target"][0], wire_args["target"][1])
    assert px == 960
    assert py == 540


def test_downscaled_click_sequence_scaling():
    """click_sequence coordinates scale to physical screen for all sequence points."""
    ctx = _make_context(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
    )
    executor = McpActionExecutor(ctx)

    # Point 1: [640, 360] -> physical [960, 540] -> wire [500, 500]
    # Point 2: [128, 72] -> physical [192, 108] -> wire [100, 100]
    wire_name, wire_args, _, recorded = executor._translate(
        "click_sequence",
        {
            "sequence": [[640, 360], [128, 72]],
            "target_descriptions": ["center icon", "corner avatar"],
        },
        _state(),
    )

    assert wire_name == "click_sequence"
    assert wire_args["sequence"] == [[500, 500], [100, 100]]
    assert recorded["target_descriptions"] == ["center icon", "corner avatar"]
    assert recorded["target_native_coordinates"] == [[960, 540], [192, 108]]

    # Test actuator execution
    actuator = AdbActuator(ctx)
    p1 = actuator._to_px(wire_args["sequence"][0][0], wire_args["sequence"][0][1])
    p2 = actuator._to_px(wire_args["sequence"][1][0], wire_args["sequence"][1][1])
    assert p1 == (960, 540)
    assert p2 == (192, 108)


def test_downscaled_swipe_coordinate_scaling():
    """Coordinate swipe gesture scales both start and end points to physical screen."""
    ctx = _make_context(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
    )
    executor = McpActionExecutor(ctx)

    # Start: [100, 200] -> physical [150, 300]
    # End: [500, 600] -> physical [750, 900]
    wire_name, wire_args, _, recorded = executor._translate(
        "swipe",
        {
            "start": [100, 200],
            "end": [500, 600],
            "target_description": "slider bar",
            "duration": 450,
        },
        _state(),
    )

    assert wire_name == "swipe"
    assert recorded["target_description"] == "slider bar"
    assert recorded["target_native_coordinates"] == [150, 300, 750, 900]

    # Verify wire coordinates normalized to physical screen dimensions
    # 150 / 1920 * 1000 = 78, 300 / 1080 * 1000 = 278
    # 750 / 1920 * 1000 = 391, 900 / 1080 * 1000 = 833
    assert wire_args["start"] == [78, 278]
    assert wire_args["end"] == [391, 833]
    assert wire_args["duration_ms"] == 450

    # Verify actuator translates to native coordinates
    actuator = AdbActuator(ctx)
    px1, py1 = actuator._to_px(wire_args["start"][0], wire_args["start"][1])
    px2, py2 = actuator._to_px(wire_args["end"][0], wire_args["end"][1])
    # Verify close correspondence to 150, 300 and 750, 900 (within 1 px quantization)
    assert abs(px1 - 150) <= 1
    assert abs(py1 - 300) <= 1
    assert abs(px2 - 750) <= 1
    assert abs(py2 - 900) <= 1


def test_downscaled_long_press_coordinate_scaling():
    """long_press target scales to physical screen and records native coordinates."""
    ctx = _make_context(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
    )
    executor = McpActionExecutor(ctx)

    wire_name, wire_args, _, recorded = executor._translate(
        "long_press",
        {"target": [640, 360], "target_description": "app icon", "duration": 1500},
        _state(),
    )

    assert wire_name == "long_press"
    assert wire_args["target"] == [500, 500]
    assert wire_args["duration_ms"] == 1500
    assert recorded["target_description"] == "app icon"
    assert recorded["target_native_coordinates"] == [960, 540]


def test_downscaled_input_text_coordinate_scaling():
    """input_text target scales to physical screen and records native coordinates."""
    ctx = _make_context(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
    )
    executor = McpActionExecutor(ctx)

    wire_name, wire_args, _, recorded = executor._translate(
        "input_text",
        {
            "text": "nemesis automation",
            "target": [640, 360],
            "target_description": "search box",
        },
        _state(),
    )

    assert wire_name == "input_text"
    assert wire_args["text"] == "nemesis automation"
    assert wire_args["target"] == [500, 500]
    assert recorded["target_description"] == "search box"
    assert recorded["target_native_coordinates"] == [960, 540]


# ====================================================================================
# 3. Mobile Portrait Scaling (1440x3120 -> 720x1560, Scaling factor = 2.0)
# ====================================================================================


def test_mobile_portrait_downscaled_coordinates():
    """Tests typical mobile portrait aspect ratio downscaled to width 720."""
    ctx = _make_context(
        native_width=1440,
        native_height=3120,
        scaled_width=720,
        scaled_height=1560,
    )
    executor = McpActionExecutor(ctx)

    # Point [360, 780] is center of downscaled portrait
    wire_name, wire_args, _, recorded = executor._translate(
        "click",
        {"target": [360, 780], "target_description": "portrait center"},
        _state(),
    )

    assert wire_name == "click"
    # Physical center: 360 * 2.0 = 720, 780 * 2.0 = 1560
    assert recorded["target_native_coordinates"] == [720, 1560]
    assert wire_args["target"] == [500, 500]

    # Extreme corner [720, 1560] clamped to [native_width - 1, native_height - 1]
    _, _, _, recorded_corner = executor._translate(
        "click",
        {"target": [720, 1560], "target_description": "bottom right corner"},
        _state(),
    )
    assert recorded_corner["target_native_coordinates"] == [1439, 3119]


# ====================================================================================
# 4. Letterboxing and Padding Offset Handling
# ====================================================================================


def test_letterbox_offset_compensation():
    """Padded/letterboxed image offsets are correctly deducted before scaling."""
    # Screen is 1920x1080. Fitted into 1280x1280 canvas with vertical letterboxing.
    # Scaled content is 1280x720, offset_y = 280, offset_x = 0.
    transform = ScalingTransform(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
        offset_x=0,
        offset_y=280,
    )
    ctx = Mock()
    ctx.device = Mock(device_width=1920, device_height=1080)
    ctx.scaling_transform = transform
    executor = McpActionExecutor(ctx)

    # Model clicks at y = 640 on canvas (which is y = 640 - 280 = 360 on content)
    # x = 640 on canvas (x = 640 on content)
    # Native content center is [960, 540]
    wire_name, wire_args, _, recorded = executor._translate(
        "click",
        {"target": [640, 640], "target_description": "letterboxed center"},
        _state(),
    )

    assert recorded["target_native_coordinates"] == [960, 540]
    assert wire_args["target"] == [500, 500]


# ====================================================================================
# 5. UnifiedMobileController Scaling Helpers & Utility Function
# ====================================================================================


def test_unified_mobile_controller_scaling_helpers():
    """UnifiedMobileController provides bidirectional scaling helpers."""
    ctx = _make_context(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
    )
    controller = UnifiedMobileController(ctx)

    assert controller.get_scaling_transform() is not None
    assert controller.get_scaling_transform().is_scaled is True

    # Model -> Native
    nat_x, nat_y = controller.scale_model_to_native(640, 360)
    assert (nat_x, nat_y) == (960, 540)

    # Native -> Model
    mod_x, mod_y = controller.scale_native_to_model(960, 540)
    assert (mod_x, mod_y) == (640, 360)


def test_scale_model_coordinates_to_native_standalone_function():
    """Tests the standalone scale_model_coordinates_to_native utility function."""
    nat_x, nat_y = scale_model_coordinates_to_native(
        x_model=640,
        y_model=360,
        width_native=1920,
        height_native=1080,
        width_scaled=1280,
        height_scaled=720,
    )
    assert (nat_x, nat_y) == (960, 540)


# ====================================================================================
# 6. Actuator End-to-End Async Execution Mock
# ====================================================================================


@pytest.mark.asyncio
async def test_actuator_click_sequence_dispatches_native_physical_coordinates():
    """Verifies AdbActuator.click_sequence dispatches scaled physical coordinates to controller."""
    ctx = _make_context(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
    )
    mock_controller = Mock()
    mock_controller.tap_at = AsyncMock(return_value=Mock(error=None))
    actuator = AdbActuator(ctx, controller=mock_controller)

    # Normalized points [500, 500] and [100, 100]
    result = await actuator.click_sequence([(500, 500), (100, 100)])
    assert result.ok is True
    assert mock_controller.tap_at.call_count == 2
    # First tap at physical (960, 540)
    assert mock_controller.tap_at.call_args_list[0].args == (960, 540)
    # Second tap at physical (192, 108)
    assert mock_controller.tap_at.call_args_list[1].args == (192, 108)


@pytest.mark.asyncio
async def test_actuator_swipe_dispatches_native_physical_coordinates():
    """Verifies AdbActuator.swipe dispatches scaled physical coordinates to controller."""
    ctx = _make_context(
        native_width=1920,
        native_height=1080,
        scaled_width=1280,
        scaled_height=720,
    )
    mock_controller = Mock()
    mock_controller.swipe_coords = AsyncMock(return_value=None)
    actuator = AdbActuator(ctx, controller=mock_controller)

    # Normalized start [500, 500] -> native [960, 540]
    # Normalized end [250, 250] -> native [480, 270]
    result = await actuator.swipe((500, 500), (250, 250), duration_ms=600)
    assert result.ok is True
    mock_controller.swipe_coords.assert_called_once_with(960, 540, 480, 270, 600)
