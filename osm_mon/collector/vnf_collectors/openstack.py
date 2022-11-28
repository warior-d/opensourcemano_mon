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
from enum import Enum
import logging
import time
from typing import List
import osm_mon.core.sql_work as sql

from ceilometerclient import client as ceilometer_client
from ceilometerclient.exc import HTTPException
import gnocchiclient.exceptions
from gnocchiclient.v1 import client as gnocchi_client
from keystoneauth1.exceptions.catalog import EndpointNotFound
from keystoneclient.v3 import client as keystone_client
from neutronclient.v2_0 import client as neutron_client
from prometheus_api_client import PrometheusConnect as prometheus_client

from osm_mon.collector.metric import Metric
from osm_mon.collector.utils.openstack import OpenstackUtils
from osm_mon.collector.vnf_collectors.base_vim import BaseVimCollector
from osm_mon.collector.vnf_metric import VnfMetric
from osm_mon.core.common_db import CommonDbClient
from osm_mon.core.config import Config


log = logging.getLogger(__name__)

METRIC_MAPPINGS = {
    "average_memory_utilization": "memory.usage",
    "disk_read_ops": "disk.read.requests.rate",
    "disk_write_ops": "disk.write.requests.rate",
    "disk_read_bytes": "disk.read.bytes.rate",
    "disk_write_bytes": "disk.write.bytes.rate",
    "packets_in_dropped": "network.outgoing.packets.drop",
    "packets_out_dropped": "network.incoming.packets.drop",
    "packets_received": "network.incoming.packets.rate",
    "packets_sent": "network.outgoing.packets.rate",
    "cpu_utilization": "cpu",
}

# Metrics which have new names in Rocky and higher releases
METRIC_MAPPINGS_FOR_ROCKY_AND_NEWER_RELEASES = {
    "disk_read_ops": "disk.device.read.requests",
    "disk_write_ops": "disk.device.write.requests",
    "disk_read_bytes": "disk.device.read.bytes",
    "disk_write_bytes": "disk.device.write.bytes",
    "packets_received": "network.incoming.packets",
    "packets_sent": "network.outgoing.packets"
}

METRIC_MULTIPLIERS = {"cpu": 0.0000001}

METRIC_AGGREGATORS = {"cpu": "rate:mean"}

INTERFACE_METRICS = [
    "packets_in_dropped",
    "packets_out_dropped",
    "packets_received",
    "packets_sent",
]

INSTANCE_DISK = [
    "disk_read_ops",
    "disk_write_ops",
    "disk_read_bytes",
    "disk_write_bytes",
]

REQUIRE_METRICS = [
    "packets_received",
    "packets_sent",
]


class MetricType(Enum):
    INSTANCE = "instance"
    INTERFACE_ALL = "interface_all"
    INTERFACE_ONE = "interface_one"
    INSTANCEDISK = 'instancedisk'


class OpenstackCollector(BaseVimCollector):
    def __init__(self, config: Config, vim_account_id: str, vim_session: object):
        super().__init__(config, vim_account_id)
        self.common_db = CommonDbClient(config)
        vim_account = self.common_db.get_vim_account(vim_account_id)
        self.backend = self._get_backend(vim_account, vim_session)

    def _build_keystone_client(self, vim_account: dict) -> keystone_client.Client:
        sess = OpenstackUtils.get_session(vim_account)
        return keystone_client.Client(session=sess)

    def _get_resource_uuid(
        self, nsr_id: str, vnf_member_index: str, vdur_name: str
    ) -> str:
        vdur = self.common_db.get_vdur(nsr_id, vnf_member_index, vdur_name)
        return vdur["vim-id"]

    def collect(self, vnfr: dict) -> List[Metric]:
        nsr_id = vnfr["nsr-id-ref"]
        vnf_member_index = vnfr["member-vnf-index-ref"]
        vnfd = self.common_db.get_vnfd(vnfr["vnfd-id"])
        # Populate extra tags for metrics
        tags = {}
        tags["ns_name"] = self.common_db.get_nsr(nsr_id)["name"]
        if vnfr["_admin"]["projects_read"]:
            tags["project_id"] = vnfr["_admin"]["projects_read"][0]
        else:
            tags["project_id"] = ""

        metrics = []

        for vdur in vnfr["vdur"]:
            # This avoids errors when vdur records have not been completely filled
            if "name" not in vdur:
                continue
            vdu = next(filter(lambda vdu: vdu["id"] == vdur["vdu-id-ref"], vnfd["vdu"]))
            if "monitoring-parameter" in vdu:
                for param in vdu["monitoring-parameter"]:
                    metric_name = param["performance-metric"]
                    log.debug(f"Using an {type(self.backend)} as backend")
                    if type(self.backend) is PrometheusTSBDBackend:
                        openstack_metric_name = self.backend.map_metric(metric_name)
                    else:
                        openstack_metric_name = METRIC_MAPPINGS[metric_name]
                    metric_type = self._get_metric_type(metric_name)
                    try:
                        resource_id = self._get_resource_uuid(
                            nsr_id, vnf_member_index, vdur["name"]
                        )
                    except ValueError:
                        log.warning(
                            "Could not find resource_uuid for vdur %s, vnf_member_index %s, nsr_id %s. "
                            "Was it recently deleted?",
                            vdur["name"],
                            vnf_member_index,
                            nsr_id,
                        )
                        continue
                    try:
                        log.info(
                            "Collecting metric type: %s and metric_name: %s and resource_id %s and ",
                            metric_type,
                            metric_name,
                            resource_id,
                        )
                        value = self.backend.collect_metric(
                            metric_type, openstack_metric_name, resource_id
                        )

                        if value is None and metric_name in METRIC_MAPPINGS_FOR_ROCKY_AND_NEWER_RELEASES and type(self.backend) is not PrometheusTSBDBackend:
                            # Reattempting metric collection with new metric names.
                            # Some metric names have changed in newer Openstack releases
                            log.info(
                                "Reattempting metric collection for type: %s and name: %s and resource_id %s",
                                metric_type,
                                metric_name,
                                resource_id
                            )
                            openstack_metric_name = METRIC_MAPPINGS_FOR_ROCKY_AND_NEWER_RELEASES[metric_name]
                            value = self.backend.collect_metric(
                                metric_type, openstack_metric_name, resource_id
                            )

                        if value is not None:
                            # Transform commulate parameter -> delta
                            if metric_name in REQUIRE_METRICS:
                                current_val = value
                                row = sql.sql_select(metric_name, resource_id)
                                if row is not None:
                                    metrica = row[0]
                                    oldtime = row[1]
                                    oldpackets = row[2]
                                    resid = row[3]
                                    log.info("LOGS process: metrica: %s | current_val: %d | old_val: %d | resource_id: %s",
                                        metrica, 
                                        current_val, 
                                        oldpackets, 
                                        resource_id
                                    )
                                    dif_time = time.time() - oldtime
                                    if dif_time > 0:
                                        metic_rate = (value - oldpackets) / dif_time
                                        value = metic_rate
                                    log.info(row)
                                else:
                                    log.info("LOGS no row data: metrica: %s value: %d resource_id: %s", metric_name, value, resource_id)
                                sql.sql_insert(metric_name, time.time(), current_val, resource_id)

                            log.info("value: %s", value)
                            metric = VnfMetric(
                                nsr_id,
                                vnf_member_index,
                                vdur["name"],
                                metric_name,
                                value,
                                tags,
                            )
                            metrics.append(metric)
                        else:
                            log.info("metric value is empty")
                    except Exception as e:
                        log.exception(
                            "Error collecting metric %s for vdu %s"
                            % (metric_name, vdur["name"])
                        )
                        log.info("Error in metric collection: %s" % e)
        return metrics

    def _get_backend(self, vim_account: dict, vim_session: object):
        if vim_account.get("prometheus-config"):
            try:
                tsbd = PrometheusTSBDBackend(vim_account)
                log.debug("Using prometheustsbd backend to collect metric")
                return tsbd
            except Exception as e:
                log.error(f"Can't create prometheus client, {e}")
                return None
        try:
            gnocchi = GnocchiBackend(vim_account, vim_session)
            gnocchi.client.metric.list(limit=1)
            log.debug("Using gnocchi backend to collect metric")
            return gnocchi
        except (HTTPException, EndpointNotFound):
            ceilometer = CeilometerBackend(vim_account, vim_session)
            ceilometer.client.capabilities.get()
            log.debug("Using ceilometer backend to collect metric")
            return ceilometer

    def _get_metric_type(self, metric_name: str) -> MetricType:
        if metric_name not in INTERFACE_METRICS:
            if metric_name not in INSTANCE_DISK:
                return MetricType.INSTANCE
            else:
                return MetricType.INSTANCEDISK
        else:
            return MetricType.INTERFACE_ALL


class OpenstackBackend:
    def collect_metric(
        self, metric_type: MetricType, metric_name: str, resource_id: str
    ):
        pass


class PrometheusTSBDBackend(OpenstackBackend):
    def __init__(self, vim_account: dict):
        self.cred = vim_account["prometheus-config"]["prometheus_cred"]
        self.map = vim_account["prometheus-config"]["prometheus_map"]
        self.client = self._build_prometheus_client(vim_account)

    def _build_prometheus_client(self, vim_account: dict) -> prometheus_client:
        url = vim_account["prometheus-config"]["prometheus_url"]
        return prometheus_client(url, disable_ssl = True)

    def collect_metric(
        self, metric_type: MetricType, metric_name: str, resource_id: str
        ):
        metric = self.query_metric(metric_name, resource_id)
        return metric["value"][1] if metric else None

    def map_metric(self, metric_name: str):
        return self.map[metric_name]

    def query_metric(self, metric_name, resource_id = None):
        metrics = self.client.get_current_metric_value(metric_name = metric_name)
        if resource_id:
            metric = next(filter(lambda x: resource_id in x["metric"]["resource_id"], metrics))
            return metric
        return metrics


class GnocchiBackend(OpenstackBackend):
    def __init__(self, vim_account: dict, vim_session: object):
        self.client = self._build_gnocchi_client(vim_account, vim_session)
        self.neutron = self._build_neutron_client(vim_account, vim_session)

    def _build_gnocchi_client(self, vim_account: dict, vim_session: object) -> gnocchi_client.Client:
        return gnocchi_client.Client(session=vim_session)

    def _build_neutron_client(self, vim_account: dict, vim_session: object) -> neutron_client.Client:
        return neutron_client.Client(session=vim_session)

    def collect_metric(
        self, metric_type: MetricType, metric_name: str, resource_id: str
    ):
        if metric_type == MetricType.INTERFACE_ALL:
            return self._collect_interface_all_metric(metric_name, resource_id)

        elif metric_type == MetricType.INSTANCE:
            return self._collect_instance_metric(metric_name, resource_id)

        elif metric_type == MetricType.INSTANCEDISK:
            return self._collect_instance_disk_metric(metric_name, resource_id)

        else:
            raise Exception("Unknown metric type %s" % metric_type.value)

    def _collect_interface_all_metric(self, openstack_metric_name, resource_id):
        total_measure = None
        interfaces = self.client.resource.search(
            resource_type="instance_network_interface",
            query={"=": {"instance_id": resource_id}},
        )
        for interface in interfaces:
            try:
                #log.warning("STRT_interface_all_metric measures openstack_metric_name %s, resource_id-interface %s",  openstack_metric_name, interface["id"])
                measures = self.client.metric.get_measures(
                    openstack_metric_name, resource_id=interface["id"], limit=1
                )
                if measures:
                    if not total_measure:
                        total_measure = 0.0
                    total_measure += measures[-1][2]
            except (gnocchiclient.exceptions.NotFound, TypeError) as e:
                # Gnocchi in some Openstack versions raise TypeError instead of NotFound
                log.debug(
                    "No metric %s found for interface %s: %s",
                    openstack_metric_name,
                    interface["id"],
                    e,
                )
        return total_measure

    def _collect_instance_disk_metric(self, openstack_metric_name, resource_id):
        value = None
        instances = self.client.resource.search(
            resource_type='instance_disk',
            query={'=': {'instance_id': resource_id}},
        )
        for instance in instances:
            try:
                measures = self.client.metric.get_measures(
                    openstack_metric_name, resource_id=instance['id'], limit=1
                )
                if measures:
                    value = measures[-1][2]

            except gnocchiclient.exceptions.NotFound as e:
                log.debug("No metric %s found for instance disk %s: %s", openstack_metric_name,
                          instance['id'], e)
        return value

    def _collect_instance_metric(self, openstack_metric_name, resource_id):
        value = None
        try:
            aggregation = METRIC_AGGREGATORS.get(openstack_metric_name)

            try:
                #log.warning("STRT_instance_metric measures openstack_metric_name %s, aggregation %s, time %s, resource_id %s ",  openstack_metric_name, aggregation, time.time() - 1200, resource_id)
                measures = self.client.metric.get_measures(
                    openstack_metric_name,
                    aggregation=aggregation,
                    start=time.time() - 1200,
                    resource_id=resource_id,
                )
                #log.warning("STRT_READY measures {}".format(measures))
                if measures:
                    value = measures[-1][2]
            except (
                gnocchiclient.exceptions.NotFound,
                gnocchiclient.exceptions.BadRequest,
                TypeError,
            ) as e:
                # CPU metric in previous Openstack versions do not support rate:mean aggregation method
                # Gnocchi in some Openstack versions raise TypeError instead of NotFound or BadRequest
                if openstack_metric_name == "cpu":
                    log.debug(
                        "No metric %s found for instance %s: %s",
                        openstack_metric_name,
                        resource_id,
                        e,
                    )
                    log.info(
                        "Retrying to get metric %s for instance %s without aggregation",
                        openstack_metric_name,
                        resource_id,
                    )
                    measures = self.client.metric.get_measures(
                        openstack_metric_name, resource_id=resource_id, limit=1
                    )
                else:
                    raise e
                # measures[-1] is the last measure
                # measures[-2] is the previous measure
                # measures[x][2] is the value of the metric
                if measures and len(measures) >= 2:
                    value = measures[-1][2] - measures[-2][2]
            if value:
                # measures[-1][0] is the time of the reporting interval
                # measures[-1][1] is the duration of the reporting interval
                if aggregation:
                    # If this is an aggregate, we need to divide the total over the reported time period.
                    # Even if the aggregation method is not supported by Openstack, the code will execute it
                    # because aggregation is specified in METRIC_AGGREGATORS
                    value = value / measures[-1][1]
                if openstack_metric_name in METRIC_MULTIPLIERS:
                    value = value * METRIC_MULTIPLIERS[openstack_metric_name]
        except gnocchiclient.exceptions.NotFound as e:
            log.debug(
                "No metric %s found for instance %s: %s",
                openstack_metric_name,
                resource_id,
                e,
            )
        return value


class CeilometerBackend(OpenstackBackend):
    def __init__(self, vim_account: dict, vim_session: object):
        self.client = self._build_ceilometer_client(vim_account, vim_session)

    def _build_ceilometer_client(self, vim_account: dict, vim_session: object) -> ceilometer_client.Client:
        return ceilometer_client.Client("2", session=vim_session)

    def collect_metric(
        self, metric_type: MetricType, metric_name: str, resource_id: str
    ):
        if metric_type != MetricType.INSTANCE:
            raise NotImplementedError(
                "Ceilometer backend only support instance metrics"
            )
        measures = self.client.samples.list(
            meter_name=metric_name,
            limit=1,
            q=[{"field": "resource_id", "op": "eq", "value": resource_id}],
        )
        return measures[0].counter_volume if measures else None
