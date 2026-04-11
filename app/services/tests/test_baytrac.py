import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from gundi_core.schemas.v2 import Integration

from app.actions.baytrac_client import BaytracDeviceStatus, BaytracUnauthorizedException
from app.actions.configurations import PullObservationsConfiguration
from app.actions.handlers import action_pull_observations, _transform


BAYTRAC_ENDPOINT = "https://api.baytrac.example.com"
BAYTRAC_TOKEN = "test-api-token"


@pytest.fixture
def sample_device_status():
    return BaytracDeviceStatus(
        imei="123456789012345",
        dt_tracker=datetime(2024, 1, 24, 9, 3, 0, tzinfo=timezone.utc),
        lat=-51.748,
        lng=-72.720,
        altitude=100,
        angle=45,
        speed=10,
        name="Vehicle 1",
        device="DEV001",
        model="Baytrac Model X",
        vin="VIN123",
        odometer=1234.5,
    )


@pytest.fixture
def integration():
    return MagicMock(id="779ff3ab-5589-4f4c-9e0a-ae8d6c9edff0")


@pytest.fixture
def pull_config():
    return PullObservationsConfiguration(endpoint=BAYTRAC_ENDPOINT, token=BAYTRAC_TOKEN)


def test_transform_produces_correct_observation(sample_device_status):
    obs = _transform(sample_device_status)

    assert obs["source"] == "123456789012345"
    assert obs["type"] == "tracking-device"
    assert obs["location"]["lat"] == -51.748
    assert obs["location"]["lon"] == -72.720
    assert obs["additional"]["speed"] == 10
    assert obs["additional"]["altitude"] == 100
    assert obs["additional"]["name"] == "Vehicle 1"
    assert obs["additional"]["vin"] == "VIN123"
    assert obs["additional"]["odometer"] == 1234.5


def test_baytrac_device_status_rejects_nullish_datetime():
    with pytest.raises(Exception):
        BaytracDeviceStatus(
            imei="123456789012345",
            dt_tracker="0000-00-00 00:00:00",
            lat=1.0,
            lng=34.0,
            altitude=100,
            angle=0,
            speed=0,
            name="Test",
            device="DEV001",
            model="Model",
            vin="VIN",
            odometer=0.0,
        )


def test_baytrac_device_status_adds_utc_when_no_timezone():
    device = BaytracDeviceStatus(
        imei="123456789012345",
        dt_tracker="2024-01-24 09:03:00",
        lat=1.0,
        lng=34.0,
        altitude=100,
        angle=0,
        speed=0,
        name="Test",
        device="DEV001",
        model="Model",
        vin="VIN",
        odometer=0.0,
    )
    assert device.dt_tracker.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_action_pull_observations_sends_to_gundi(mocker, integration, pull_config, sample_device_status):
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mock_get_positions = AsyncMock(return_value=[sample_device_status])
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", mock_get_positions)
    mock_send = AsyncMock(return_value={})
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_observations(integration, pull_config)

    assert result == {"observations_extracted": 1}
    mock_send.assert_called_once()
    sent_obs = mock_send.call_args.kwargs["observations"]
    assert len(sent_obs) == 1
    assert sent_obs[0]["source"] == sample_device_status.imei


@pytest.mark.asyncio
async def test_action_pull_observations_empty_list(mocker, integration, pull_config):
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", AsyncMock(return_value=[]))
    mock_send = AsyncMock()
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_observations(integration, pull_config)

    assert result == {"observations_extracted": 0}
    mock_send.assert_not_called()
