"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
from typing import Any, Dict, Optional

#from gidgethub import BadRequest
#from gidgethub.aiohttp import GitHubAPI
from homeassistant import config_entries, core
from homeassistant.const import CONF_EMAIL, CONF_NAME, CONF_PATH, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .minvw import MinVW

_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required("namespace", default="minvolkswagen"): cv.string,
    }
)

# async def validate_auth(email: str, password: str, namespace: str, hass: core.HomeAssistant) -> None:

#     session = async_get_clientsession(hass)
#     gh = GitHubAPI(session, "requester", oauth_token=access_token)
#     try:
#         client = await MinVW(email, password, namespace)
#     except BadRequest:
#         raise ValueError


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Github Custom config flow."""

    data: Optional[Dict[str, Any]]

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Invoked when a user initiates a flow via the user interface."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            try:
                client = MinVW(user_input[CONF_EMAIL], user_input[CONF_PASSWORD], user_input['namespace'])
                token = await client._get_access_token()
                _LOGGER.debug(f"Config response: {token}")

            except Exception as err:
                _LOGGER.debug(err)
                if str(err) == "Email is incorrect":
                    errors[CONF_EMAIL] = "email"
                elif str(err) == "Incorrect password":
                    errors[CONF_PASSWORD] = "pw"
                elif str(err) == "Namespace could not be found":
                    errors["namespace"] = "ns"
                else:
                    errors["base"] = "auth"
            if not errors:
                # Input is valid, set data.
                self.data = user_input
                #self.data[CONF_REPOS] = []
                # Return the form of the next step.
                #return await self.async_step_repo()

                # User is done, create the config entry.
                return self.async_create_entry(title=user_input["namespace"], data=self.data)

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )




