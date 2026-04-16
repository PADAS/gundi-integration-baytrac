import logging
from datetime import datetime, timezone, timedelta

from app.services.action_scheduler import crontab_schedule
from app.services.activity_logger import activity_logger
from app.services.gundi import send_observations_to_gundi
from .baytrac_client import BaytracClient, BaytracDeviceStatus, BaytracRoutePoint
from .configurations import PullObservationsConfiguration, PullHistoricalObservationsConfiguration


logger = logging.getLogger(__name__)


@activity_logger()
@crontab_schedule("* * * * *")
async def action_pull_observations(integration, action_config: PullObservationsConfiguration):

    client = BaytracClient(
        endpoint=action_config.endpoint,
        token=action_config.token.get_secret_value(),
    )
    devices = await client.get_positions_list()

    if action_config.filter_invalid_gps:
        invalid = [d for d in devices if d.loc_valid != "1"]
        for d in invalid:
            logger.debug("Skipping device %s (%s) — loc_valid=%s", d.imei, d.name, d.loc_valid)
        devices = [d for d in devices if d.loc_valid == "1"]

    observations = [_transform(device) for device in devices]

    if observations:
        await send_observations_to_gundi(observations=observations, integration_id=integration.id)

    return {"observations_extracted": len(observations)}


@crontab_schedule("0 */6 * * *")
@activity_logger()
async def action_pull_historical_observations(integration, action_config: PullHistoricalObservationsConfiguration):
    pull_config = integration.get_action_config("pull_observations")
    if not pull_config:
        raise ValueError("pull_observations action config not found — configure endpoint and token on the live action first.")
    endpoint = pull_config.data.get("endpoint", "https://advantage.baytrac.co.za/api/api.php")
    token = pull_config.data.get("token")
    if not token:
        raise ValueError("token not found in pull_observations action config.")

    client = BaytracClient(endpoint=endpoint, token=token)

    end_dt = datetime.now(tz=timezone.utc) - timedelta(hours=action_config.end_hours_ago)
    start_dt = end_dt - timedelta(hours=action_config.hours)

    if action_config.imei:
        imeis = [action_config.imei]
    else:
        devices = await client.get_positions_list()
        if action_config.filter_invalid_gps:
            invalid = [d for d in devices if d.loc_valid != "1"]
            for d in invalid:
                logger.debug("Skipping device %s (%s) — loc_valid=%s", d.imei, d.name, d.loc_valid)
            devices = [d for d in devices if d.loc_valid == "1"]
        imeis = [d.imei for d in devices]

    total_observations = 0
    for imei in imeis:
        points = await client.get_historical_positions(
            imei=imei,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        observations = [_transform_route_point(p) for p in points]
        if observations:
            await send_observations_to_gundi(observations=observations, integration_id=integration.id)
            total_observations += len(observations)

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
