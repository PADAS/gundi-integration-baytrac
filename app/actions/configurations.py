from pydantic import Field, HttpUrl, SecretStr

from app.actions.core import PullActionConfiguration


class PullObservationsConfiguration(PullActionConfiguration):
    endpoint: HttpUrl = Field(
        "https://advantage.baytrac.co.za/api/api.php",
        description="Base URL of the Baytrac API.",
    )
    token: SecretStr = Field(
        ...,
        description="Secret API key. Obtain this from Baytrac.",
    )
