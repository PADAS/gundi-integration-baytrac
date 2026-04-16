from typing import Optional
from pydantic import Field, HttpUrl, SecretStr

from app.actions.core import PullActionConfiguration, ExecutableActionMixin


class PullObservationsConfiguration(PullActionConfiguration):
    endpoint: HttpUrl = Field(
        "https://advantage.baytrac.co.za/api/api.php",
        description="Base URL of the Baytrac API.",
    )
    token: SecretStr = Field(
        ...,
        description="Secret API key. Obtain this from Baytrac.",
    )
    filter_invalid_gps: bool = Field(
        True,
        description="If enabled, positions with an invalid GPS fix (loc_valid != 1) are excluded.",
    )


class PullHistoricalObservationsConfiguration(ExecutableActionMixin, PullActionConfiguration):
    hours: int = Field(
        6,
        description="Number of hours of historical data to fetch per device.",
        ge=1,
        le=48,
    )
    end_hours_ago: int = Field(
        0,
        description="End of the time window, expressed as hours before now. Default 0 means now.",
        ge=0,
    )
    imei: Optional[str] = Field(
        None,
        description="If set, only fetch historical data for this specific device IMEI.",
    )
    filter_invalid_gps: bool = Field(
        True,
        description="If enabled, devices with an invalid current GPS fix (loc_valid != 1) are skipped.",
    )
