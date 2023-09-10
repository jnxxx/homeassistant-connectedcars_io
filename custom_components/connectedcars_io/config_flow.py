"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_NAME, CONF_PATH, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.selector as selector
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DOMAIN, CONF_HEALTH_SENSITIVITY
from .minvw import MinVW

_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required("namespace", default="minvolkswagen"): cv.string,
    }
)

from homeassistant.const import (
    CONF_URL,
    CONF_SCAN_INTERVAL,
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

    data: Optional[dict[str, Any]]

    async def async_step_user(self, user_input: Optional[dict[str, Any]] = None):
        """Invoked when a user initiates a flow via the user interface."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                client = MinVW(
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                    user_input["namespace"],
                )
                token = await client._get_access_token()

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
                # self.data[CONF_REPOS] = []
                # Return the form of the next step.
                # return await self.async_step_repo()

                # User is done, create the config entry.
                return self.async_create_entry(
                    title=user_input["namespace"], data=self.data
                )

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """dabblerdk_powermeterreader options flow."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # _LOGGER.warning(
            #     "User input, selected options: %s",
            #     user_input[CONF_HEALTH_SENSITIVITY],
            # )

            if not errors:
                options = {}
                options[CONF_HEALTH_SENSITIVITY] = user_input[CONF_HEALTH_SENSITIVITY]

                return self.async_create_entry(title="", data=options)

        options_list = ["high", "medium", "low", "all"]
        options_schema = vol.Schema(
            {
                # vol.Required(
                #     CONF_URL, default=self.config_entry.data[CONF_URL]
                # ): cv.string,
                vol.Required(
                    CONF_HEALTH_SENSITIVITY,
                    default=self.config_entry.options.get(
                        CONF_HEALTH_SENSITIVITY, "medium"
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options_list,
                        multiple=False,
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key=CONF_HEALTH_SENSITIVITY,
                    ),
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
