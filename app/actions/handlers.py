import logging

from app.services.action_scheduler import crontab_schedule
from app.services.activity_logger import activity_logger
from app.services.gundi import send_observations_to_gundi
from .baytrac_client import BaytracClient, BaytracDeviceStatus
from .configurations import PullObservationsConfiguration


logger = logging.getLogger(__name__)


@activity_logger()
@crontab_schedule("* * * * *")
async def action_pull_observations(integration, action_config: PullObservationsConfiguration):

    client = BaytracClient(
        endpoint=action_config.endpoint,
        token=action_config.token.get_secret_value(),
    )
    devices = await client.get_positions_list()

    observations = [_transform(device) for device in devices]

    if observations:
        await send_observations_to_gundi(observations=observations, integration_id=integration.id)

    return {"observations_extracted": len(observations)}


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
