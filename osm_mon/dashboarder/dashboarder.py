# -*- coding: utf-8 -*-

# Copyright 2021 Whitestack, LLC
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
# contact: fbravo@whitestack.com or glavado@whitestack.com
##

import logging
import time
import socket
import asyncio
from urllib.parse import urlparse

from osm_mon.dashboarder.service import DashboarderService
from osm_mon.core.config import Config
from osm_mon.core.message_bus_client import MessageBusClient

log = logging.getLogger(__name__)


class Dashboarder:
    def __init__(self, config: Config, loop=None):
        self.conf = config
        self.service = DashboarderService(config)
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.msg_bus = MessageBusClient(config)

    # run consumer for grafana user management
    def run(self):
        self.loop.run_until_complete(self.start())

    async def start(self, wait_time=5):
        topics = ["users", "project"]
        while True:
            try:
                await self.msg_bus.aioread(topics, self._user_msg)
                break
            except Exception as e:
                # Failed to subscribe to kafka topics
                log.error("Error when subscribing to topic(s) %s", str(topics))
                log.exception("Exception %s", str(e))
                # Wait for some time for kaka to stabilize and then reattempt to subscribe again
                time.sleep(wait_time)
                log.info("Retrying to subscribe the kafka topic(s) %s", str(topics))

    async def _user_msg(self, topic, key, values):
        log.debug(
            "Message from kafka bus received: topic: %s and values: %s and key: %s",
            topic,
            values,
            key,
        )
        try:
            if topic == "users" and key == "created":
                log.debug("Received message from kafka for creating user")
                if values.get("username"):
                    user = values["username"]
                else:
                    user = values["changes"]["username"]
                self.service.create_grafana_user(user)
                # user-created and mapping is done with osm cli
                if values.get("changes"):
                    # user-project-role mapping is included in change
                    if values["changes"].get("project_role_mappings"):
                        user_id = values["_id"]
                        project_data = values["changes"]["project_role_mappings"]
                        project_list = values["changes"].get("projects")
                        self.service.create_grafana_team_member(
                            project_data, user_id, project_list
                        )
                elif values.get("project_role_mappings"):
                    # for fresh project-role-mapping
                    user_id = values.get("_id")
                    project_data = values["project_role_mappings"]
                    if user_id:
                        self.service.create_grafana_team_member(project_data, user_id)
                    else:
                        # for keystone we will get username
                        self.service.create_grafana_team_member(
                            project_data, user=values["username"]
                        )
            elif topic == "users" and key == "deleted":
                log.debug("Received message from kafka for deleting user")
                user = values["username"]
                self.service.delete_grafana_user(user)
            elif topic == "users" and key == "edited":
                log.debug("Received message from kafka for associating user to team")
                user_id = values["_id"]
                if values["changes"].get("remove_project_role_mappings") and not values[
                    "changes"
                ].get("add_project_role_mappings"):
                    # Removing user-project role mapping
                    self.service.remove_grafana_team_members(
                        user_id, values["changes"].get("remove_project_role_mappings")
                    )
                else:
                    # Changing user project role mapping
                    if values["changes"].get("project_role_mappings"):
                        project_data = values["changes"]["project_role_mappings"]
                    else:
                        project_data = values["changes"]["add_project_role_mappings"]
                    self.service.create_grafana_team_member(project_data, user_id)
            elif topic == "project" and key == "created":
                log.debug("Received message from kafka for creating team")
                team_name = values["name"]
                self.service.create_grafana_team(team_name)
            elif topic == "project" and key == "deleted":
                log.debug("Received message from kafka for deleting team")
                project_name = values["name"]
                self.service.delete_grafana_team(project_name)
            elif topic == "project" and key == "edited":
                log.debug("Received message from kafka for team name update")
                project_old_name = values["original"]["name"]
                project_new_name = values["changes"]["name"]
                self.service.update_grafana_team(project_new_name, project_old_name)
        except Exception:
            log.exception("Exception processing message: ")

    def dashboard_forever(self):
        log.debug("dashboard_forever")
        grafana_parsed_uri = urlparse(self.conf.get("grafana", "url"))
        while True:
            try:
                socket.gethostbyname(grafana_parsed_uri.hostname)
                log.debug("Dashboard backend is running")
            except socket.error:
                log.debug("Dashboard backend is not available")
                time.sleep(int(self.conf.get("dashboarder", "interval")))
                continue
            try:
                self.grafana_cleanup()
                self.create_dashboards()
                time.sleep(int(self.conf.get("dashboarder", "interval")))
            except Exception:
                log.exception("Error creating dashboards")

    def create_dashboards(self):
        self.service.create_dashboards()
        log.debug("Dashboarder Service > create_dashboards called!")

    def grafana_cleanup(self):
        # Cleaning up non existing users from grafana
        self.service.delete_non_existing_users()
        # TODO
        # Cleanup of teams from grafana
        log.debug("Deleted non existing users from dashbaorder service")
