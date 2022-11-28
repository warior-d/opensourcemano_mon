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
import logging

from osm_mon.core.common_db import CommonDbClient
from osm_mon.core.config import Config
from osm_mon.core.models import Alarm

log = logging.getLogger(__name__)


class ServerService:
    def __init__(self, config: Config):
        self.common_db = CommonDbClient(config)

    def create_alarm(
        self,
        name: str,
        threshold: float,
        operation: str,
        severity: str,
        statistic: str,
        metric_name: str,
        action: str,
        tags: dict,
    ) -> Alarm:
        log.debug("create_alarm")
        alarm = Alarm(
            name, severity, threshold, operation, statistic, metric_name, action, tags
        )
        self.common_db.create_alarm(alarm)
        log.info("Alarm %s created", alarm.name)
        return alarm

    def delete_alarm(self, alarm_uuid: str) -> None:
        log.debug("delete_alarm")
        self.common_db.delete_alarm(alarm_uuid)
        log.info("Alarm %s is deleted", alarm_uuid)

    def populate_prometheus(self):
        # This method can be executed infinite number of times
        # without side-effects.
        log.info("Setting up MON Exporter in prometheus")
        result = self.common_db.common_db.set_one(
            "prometheus_jobs", {"job_name": "mon_exporter"}, {
                "job_name": "mon_exporter",
                "static_configs": [
                    {
                        "targets": [
                            "mon:8000"
                        ]
                    }
                ]
            },
            fail_on_empty=False,
            upsert=True
        )
        log.info("Prometheus Jobs added > {}".format(result))
