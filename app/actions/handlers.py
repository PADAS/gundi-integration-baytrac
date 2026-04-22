import logging
from datetime import datetime, timezone, timedelta

from app.services.action_scheduler import crontab_schedule
from app.services.activity_logger import activity_logger
from app.services.gundi import send_observations_to_gundi
from .baytrac_client import BaytracClient, BaytracDeviceStatus, BaytracRoutePoint
from .configurations import PullObservationsConfiguration, PullHistoricalObservationsConfiguration


logger = logging.getLogger(__name__)

HISTORICAL_BATCH_SIZE = 200
LOC_VALID = "1"


def _filter_valid_gps(devices: list) -> tuple:
    valid, invalid = [], []
    for d in devices:
        (valid if d.loc_valid == LOC_VALID else invalid).append(d)
    for d in invalid:
        logger.warning("Skipping device %s (%s) — loc_valid=%s", d.imei, d.name, d.loc_valid)
    return valid, len(invalid)


@activity_logger()
@crontab_schedule("* * * * *")
async def action_pull_observations(integration, action_config: PullObservationsConfiguration):

    async with BaytracClient(
        endpoint=action_config.endpoint,
        token=action_config.token.get_secret_value(),
    ) as client:
        devices = await client.get_positions_list()

    skipped = 0
    if action_config.filter_invalid_gps:
        devices, skipped = _filter_valid_gps(devices)

    observations = [_transform(device) for device in devices]

    if observations:
        await send_observations_to_gundi(observations=observations, integration_id=integration.id)

    return {"observations_extracted": len(observations), "skipped_invalid_gps": skipped}


@crontab_schedule("0 * * * *")
@activity_logger()
async def action_pull_historical_observations(integration, action_config: PullHistoricalObservationsConfiguration):
    pull_config = integration.get_action_config("pull_observations")
    if not pull_config:
        raise ValueError("pull_observations action config not found — configure endpoint and token on the live action first.")
    endpoint = pull_config.data.get("endpoint", "https://advantage.baytrac.co.za/api/api.php")
    token = pull_config.data.get("token")
    if not token:
        raise ValueError("token not found in pull_observations action config.")

    end_dt = datetime.now(tz=timezone.utc) - timedelta(hours=action_config.end_hours_ago)
    start_dt = end_dt - timedelta(hours=action_config.hours)

    total_observations = 0
    batch = []
    async with BaytracClient(endpoint=endpoint, token=token) as client:
        if action_config.imei:
            imeis = [action_config.imei]
        else:
            devices = await client.get_positions_list()
            imeis = [d.imei for d in devices]

        for imei in imeis:
            points = await client.get_historical_positions(
                imei=imei,
                start_dt=start_dt,
                end_dt=end_dt,
            )
            batch.extend(_transform_route_point(p) for p in points)
            if len(batch) >= HISTORICAL_BATCH_SIZE:
                await send_observations_to_gundi(observations=batch, integration_id=integration.id)
                total_observations += len(batch)
                batch = []

    if batch:
        await send_observations_to_gundi(observations=batch, integration_id=integration.id)
        total_observations += len(batch)

    return {"observations_extracted": total_observations}


def _transform_route_point(point: BaytracRoutePoint) -> dict:
    return {
        "source": point.imei,
        "type": "tracking-device",
        "subject_type": "car",
        "recorded_at": point.dt_tracker.isoformat(),
        "location": {
            "lat": point.lat,
            "lon": point.lng,
        },
        "additional": {
            "altitude": point.altitude,
            "angle": point.angle,
            "speed": point.speed,
        },
    }


def _transform(device: BaytracDeviceStatus) -> dict:
    return {
        "source": device.imei,
        "type": "tracking-device",
        "subject_type": "car",
        "source_name": device.name,
        "recorded_at": device.dt_tracker.isoformat(),
        "location": {
            "lat": device.lat,
            "lon": device.lng,
        },
        "additional": {
            "altitude": device.altitude,
            "angle": device.angle,
            "device": device.device,
            "model": device.model,
            "odometer": device.odometer,
            "speed": device.speed,
            "vin": device.vin,
            "name": device.name,
        },
    }
