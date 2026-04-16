import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from app.actions.baytrac_client import BaytracDeviceStatus, BaytracRoutePoint
from app.actions.configurations import PullObservationsConfiguration, PullHistoricalObservationsConfiguration
from app.actions.handlers import (
    action_pull_observations,
    action_pull_historical_observations,
    _transform,
    _transform_route_point,
)


BAYTRAC_ENDPOINT = "https://api.baytrac.example.com"
BAYTRAC_TOKEN = "test-api-token"


def make_device(imei="123456789012345", loc_valid="1", **kwargs):
    defaults = dict(
        imei=imei,
        dt_tracker=datetime(2024, 1, 24, 9, 3, 0, tzinfo=timezone.utc),
        lat=-51.748,
        lng=-72.720,
        altitude=100,
        angle=45,
        speed=10,
        name="Vehicle 1",
        device="FMB120",
        model="TOYOTA FORTUNER",
        vin="VIN123",
        odometer=1234.5,
        loc_valid=loc_valid,
    )
    defaults.update(kwargs)
    return BaytracDeviceStatus(**defaults)


@pytest.fixture
def sample_device_status():
    return make_device()


@pytest.fixture
def invalid_gps_device():
    return make_device(imei="999999999999999", loc_valid="0")


@pytest.fixture
def sample_route_point():
    return BaytracRoutePoint(
        imei="123456789012345",
        dt_tracker=datetime(2024, 1, 24, 9, 3, 0, tzinfo=timezone.utc),
        lat=-51.748,
        lng=-72.720,
        altitude=100,
        angle=45,
        speed=10,
    )


@pytest.fixture
def integration():
    mock = MagicMock(id="779ff3ab-5589-4f4c-9e0a-ae8d6c9edff0")
    mock.get_action_config.return_value = MagicMock(
        data={"endpoint": BAYTRAC_ENDPOINT, "token": BAYTRAC_TOKEN}
    )
    return mock


@pytest.fixture
def pull_config():
    return PullObservationsConfiguration(endpoint=BAYTRAC_ENDPOINT, token=BAYTRAC_TOKEN)


@pytest.fixture
def historical_config():
    return PullHistoricalObservationsConfiguration(hours=6)


# --- BaytracDeviceStatus ---

def test_baytrac_device_status_rejects_nullish_datetime():
    with pytest.raises(Exception):
        make_device(dt_tracker="0000-00-00 00:00:00")


def test_baytrac_device_status_adds_utc_when_no_timezone():
    device = make_device(dt_tracker="2024-01-24 09:03:00")
    assert device.dt_tracker.tzinfo == timezone.utc


def test_baytrac_device_status_defaults_loc_valid_to_1():
    device = BaytracDeviceStatus(
        imei="123456789012345",
        dt_tracker=datetime(2024, 1, 24, 9, 3, 0, tzinfo=timezone.utc),
        lat=-51.748, lng=-72.720, altitude=100, angle=45, speed=10,
        name="Vehicle 1", device="FMB120", model="TOYOTA", vin="", odometer=0.0,
    )
    assert device.loc_valid == "1"


# --- _transform ---

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


# --- _transform_route_point ---

def test_transform_route_point_produces_correct_observation(sample_route_point):
    obs = _transform_route_point(sample_route_point)

    assert obs["source"] == "123456789012345"
    assert obs["type"] == "tracking-device"
    assert obs["location"]["lat"] == -51.748
    assert obs["location"]["lon"] == -72.720
    assert obs["additional"]["speed"] == 10
    assert obs["additional"]["altitude"] == 100


# --- action_pull_observations ---

@pytest.mark.asyncio
async def test_action_pull_observations_sends_to_gundi(mocker, integration, pull_config, sample_device_status):
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", AsyncMock(return_value=[sample_device_status]))
    mock_send = AsyncMock(return_value={})
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_observations(integration, pull_config)

    assert result["observations_extracted"] == 1
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["observations"][0]["source"] == sample_device_status.imei


@pytest.mark.asyncio
async def test_action_pull_observations_empty_list(mocker, integration, pull_config):
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", AsyncMock(return_value=[]))
    mock_send = AsyncMock()
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_observations(integration, pull_config)

    assert result["observations_extracted"] == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_action_pull_observations_filters_invalid_gps_by_default(mocker, integration, pull_config, sample_device_status, invalid_gps_device):
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", AsyncMock(return_value=[sample_device_status, invalid_gps_device]))
    mock_send = AsyncMock(return_value={})
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_observations(integration, pull_config)

    assert result["observations_extracted"] == 1
    sent_obs = mock_send.call_args.kwargs["observations"]
    assert sent_obs[0]["source"] == sample_device_status.imei


@pytest.mark.asyncio
async def test_action_pull_observations_includes_invalid_gps_when_disabled(mocker, integration, invalid_gps_device):
    config = PullObservationsConfiguration(endpoint=BAYTRAC_ENDPOINT, token=BAYTRAC_TOKEN, filter_invalid_gps=False)
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", AsyncMock(return_value=[invalid_gps_device]))
    mock_send = AsyncMock(return_value={})
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_observations(integration, config)

    assert result["observations_extracted"] == 1


# --- action_pull_historical_observations ---

@pytest.mark.asyncio
async def test_action_pull_historical_observations_sends_to_gundi(mocker, integration, historical_config, sample_device_status, sample_route_point):
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", AsyncMock(return_value=[sample_device_status]))
    mocker.patch("app.actions.handlers.BaytracClient.get_historical_positions", AsyncMock(return_value=[sample_route_point]))
    mock_send = AsyncMock(return_value={})
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_historical_observations(integration, historical_config)

    assert result["observations_extracted"] == 1
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["observations"][0]["source"] == sample_route_point.imei


@pytest.mark.asyncio
async def test_action_pull_historical_observations_no_points(mocker, integration, historical_config, sample_device_status):
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", AsyncMock(return_value=[sample_device_status]))
    mocker.patch("app.actions.handlers.BaytracClient.get_historical_positions", AsyncMock(return_value=[]))
    mock_send = AsyncMock()
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_historical_observations(integration, historical_config)

    assert result["observations_extracted"] == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_action_pull_historical_observations_single_imei(mocker, integration, sample_route_point):
    config = PullHistoricalObservationsConfiguration(hours=14, end_hours_ago=10, imei="123456789012345")
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mock_get_positions = AsyncMock()
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", mock_get_positions)
    mocker.patch("app.actions.handlers.BaytracClient.get_historical_positions", AsyncMock(return_value=[sample_route_point]))
    mock_send = AsyncMock(return_value={})
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_historical_observations(integration, config)

    mock_get_positions.assert_not_called()
    assert result["observations_extracted"] == 1


@pytest.mark.asyncio
async def test_action_pull_historical_observations_fetches_all_devices_regardless_of_loc_valid(mocker, integration, historical_config, sample_device_status, invalid_gps_device, sample_route_point):
    mocker.patch("app.services.activity_logger.publish_event", AsyncMock())
    mocker.patch("app.actions.handlers.BaytracClient.get_positions_list", AsyncMock(return_value=[sample_device_status, invalid_gps_device]))
    mock_get_historical = AsyncMock(return_value=[sample_route_point])
    mocker.patch("app.actions.handlers.BaytracClient.get_historical_positions", mock_get_historical)
    mock_send = AsyncMock(return_value={})
    mocker.patch("app.actions.handlers.send_observations_to_gundi", mock_send)

    result = await action_pull_historical_observations(integration, historical_config)

    assert result["observations_extracted"] == 2
    called_imeis = [c.kwargs["imei"] for c in mock_get_historical.call_args_list]
    assert sample_device_status.imei in called_imeis
    assert invalid_gps_device.imei in called_imeis
