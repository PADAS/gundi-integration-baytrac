import logging

import httpx
from datetime import datetime, timezone
from pydantic import BaseModel, validator, ValidationError


logger = logging.getLogger(__name__)


class BaytracException(Exception):
    pass


class BaytracUnauthorizedException(BaytracException):
    def __init__(self, error: Exception, message: str, status_code=401):
        self.status_code = status_code
        self.message = message
        self.error = error
        super().__init__(f"'{self.status_code}: {self.message}, Error: {self.error}'")


class BaytracDeviceStatus(BaseModel):
    imei: str
    dt_tracker: datetime
    lat: float
    lng: float
    altitude: int
    angle: int
    speed: int
    name: str
    device: str
    model: str
    vin: str
    odometer: float

    @validator("dt_tracker")
    def ensure_timezone(cls, v):
        if not v.tzinfo:
            return v.replace(tzinfo=timezone.utc)
        return v


class BaytracClient:
    BAYTRAC_RESPONSE_WRONG_API = "ERROR: wrong API key"
    BAYTRAC_ERROR_RESPONSES = {BAYTRAC_RESPONSE_WRONG_API: 401}

    def __init__(self, endpoint: str, token: str):
        self._endpoint = endpoint
        self._token = token

    async def get_positions_list(self) -> list:
        params = {
            "api": "user",
            "ver": 1.0,
            "key": self._token,
            "cmd": "USER_GET_OBJECTS",
        }
        async with httpx.AsyncClient(timeout=120) as session:
            try:
                response = await session.get(url=self._endpoint, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                msg = f"Baytrac API returned HTTP error: {e}"
                logger.exception(msg)
                if e.response.status_code == 401:
                    raise BaytracUnauthorizedException(e, message=msg)
                raise
            except httpx.HTTPError as e:
                msg = f"Baytrac API request failed: {e}"
                logger.exception(msg)
                raise

        if "ERROR" in response.text:
            error_code = self.BAYTRAC_ERROR_RESPONSES.get(response.text.strip(), 500)
            if error_code == 401:
                raise BaytracUnauthorizedException(
                    BaytracException(error_code), message=response.text.strip()
                )
            msg = f"Baytrac API returned error response: {response.text}"
            logger.error(msg)
            raise httpx.HTTPError(msg)

        devices = []
        for item in response.json():
            try:
                devices.append(BaytracDeviceStatus.parse_obj(item))
            except ValidationError as e:
                logger.warning("Skipping invalid device record: %s", e, extra={"item": item})
        return devices
