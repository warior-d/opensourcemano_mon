# -*- coding: utf-8 -*-

# Copyright 2018 Whitestack, LLC
# *************************************************************

# This file is part of OSM Monitoring module
# All Rights Reserved to Whitestack, LLC

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at

#         http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
# For those usages not covered by the Apache License, Version 2.0 please
# contact: bdiaz@whitestack.com or glavado@whitestack.com
##
"""
MON component in charge of CRUD operations for vim_accounts and alarms. It uses the message bus to communicate.
"""
import asyncio
import json
import logging
import time

from osm_mon.core.config import Config
from osm_mon.core.message_bus_client import MessageBusClient
from osm_mon.core.response import ResponseBuilder
from osm_mon.server.service import ServerService

log = logging.getLogger(__name__)


class Server:
    def __init__(self, config: Config, loop=None):
        self.conf = config
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.msg_bus = MessageBusClient(config)
        self.service = ServerService(config)
        self.service.populate_prometheus()

    def run(self):
        self.loop.run_until_complete(self.start())

    async def start(self, wait_time=5):
        topics = ["alarm_request"]
        while True:
            try:
                await self.msg_bus.aioread(topics, self._process_msg)
                break
            except Exception as e:
                # Failed to subscribe to kafka topic
                log.error("Error when subscribing to topic(s) %s", str(topics))
                log.exception("Exception %s", str(e))
                # Wait for some time for kaka to stabilize and then reattempt to subscribe again
                time.sleep(wait_time)
                log.info("Retrying to subscribe the kafka topic(s) %s", str(topics))

    async def _process_msg(self, topic, key, values):
        log.info("Message arrived: %s", values)
        try:

            if topic == "alarm_request":
                if key == "create_alarm_request":
                    alarm_details = values["alarm_create_request"]
                    cor_id = alarm_details["correlation_id"]
                    response_builder = ResponseBuilder()
                    try:
                        alarm = self.service.create_alarm(
                            alarm_details["alarm_name"],
                            alarm_details["threshold_value"],
                            alarm_details["operation"].lower(),
                            alarm_details["severity"].lower(),
                            alarm_details["statistic"].lower(),
                            alarm_details["metric_name"],
                            alarm_details["action"],
                            alarm_details["tags"],
                        )
                        response = response_builder.generate_response(
                            "create_alarm_response",
                            cor_id=cor_id,
                            status=True,
                            alarm_id=alarm.uuid,
                        )
                    except Exception:
                        log.exception("Error creating alarm: ")
                        response = response_builder.generate_response(
                            "create_alarm_response",
                            cor_id=cor_id,
                            status=False,
                            alarm_id=None,
                        )
                    await self._publish_response(
                        "alarm_response_" + str(cor_id),
                        "create_alarm_response",
                        response,
                    )

                if key == "delete_alarm_request":
                    alarm_details = values["alarm_delete_request"]
                    alarm_uuid = alarm_details["alarm_uuid"]
                    response_builder = ResponseBuilder()
                    cor_id = alarm_details["correlation_id"]
                    try:
                        self.service.delete_alarm(alarm_uuid)
                        response = response_builder.generate_response(
                            "delete_alarm_response",
                            cor_id=cor_id,
                            status=True,
                            alarm_id=alarm_uuid,
                        )
                    except Exception:
                        log.exception("Error deleting alarm: ")
                        response = response_builder.generate_response(
                            "delete_alarm_response",
                            cor_id=cor_id,
                            status=False,
                            alarm_id=alarm_uuid,
                        )
                    await self._publish_response(
                        "alarm_response_" + str(cor_id),
                        "delete_alarm_response",
                        response,
                    )

        except Exception:
            log.exception("Exception processing message: ")

    async def _publish_response(self, topic: str, key: str, msg: dict):
        log.info(
            "Sending response %s to topic %s with key %s", json.dumps(msg), topic, key
        )
        await self.msg_bus.aiowrite(topic, key, msg)
