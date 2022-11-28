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
from unittest import TestCase, mock

from osm_mon.core.common_db import CommonDbClient
from osm_mon.core.config import Config
from osm_mon.core.message_bus_client import MessageBusClient
from osm_mon.evaluator.backends.prometheus import PrometheusBackend
from osm_mon.evaluator.evaluator import AlarmStatus
from osm_mon.evaluator.service import EvaluatorService

vnfr_record_mock = {
    "_id": "0d9d06ad-3fc2-418c-9934-465e815fafe2",
    "ip-address": "192.168.160.2",
    "created-time": 1535392482.0044956,
    "vim-account-id": "be48ae31-1d46-4892-a4b4-d69abd55714b",
    "vdur": [
        {
            "interfaces": [
                {
                    "mac-address": "fa:16:3e:71:fd:b8",
                    "name": "eth0",
                    "ip-address": "192.168.160.2",
                }
            ],
            "status": "ACTIVE",
            "vim-id": "63a65636-9fc8-4022-b070-980823e6266a",
            "name": "cirros_ns-1-cirros_vnfd-VM-1",
            "status-detailed": None,
            "ip-address": "192.168.160.2",
            "vdu-id-ref": "cirros_vnfd-VM",
        }
    ],
    "id": "0d9d06ad-3fc2-418c-9934-465e815fafe2",
    "vnfd-ref": "cirros_vdu_scaling_vnf",
    "vnfd-id": "63f44c41-45ee-456b-b10d-5f08fb1796e0",
    "_admin": {
        "created": 1535392482.0067868,
        "projects_read": ["admin"],
        "modified": 1535392482.0067868,
        "projects_write": ["admin"],
    },
    "nsr-id-ref": "87776f33-b67c-417a-8119-cb08e4098951",
    "member-vnf-index-ref": "1",
    "connection-point": [{"name": "eth0", "id": None, "connection-point-id": None}],
}

vnfd_record_mock = {
    "_id": "63f44c41-45ee-456b-b10d-5f08fb1796e0",
    "id": "cirros_vdu_scaling_vnf",
    "_admin": {},
    "product-name": "cirros_vdu_scaling_vnf",
    "version": "1.0",
    "vdu": [
        {
            "id": "cirros_vnfd-VM",
            "name": "cirros_vnfd-VM",
            "int-cpd": [
                {
                    "virtual-network-interface-requirement": [{"name": "vdu-eth0"}],
                    "id": "vdu-eth0-int",
                }
            ],
            "virtual-compute-desc": "cirros_vnfd-VM-compute",
            "virtual-storage-desc": ["cirros_vnfd-VM-storage"],
            "sw-image-desc": "cirros034",
            "monitoring-parameter": [
                {
                    "id": "cirros_vnfd-VM_memory_util",
                    "name": "cirros_vnfd-VM_memory_util",
                    "performance-metric": "average_memory_utilization",
                }
            ],
        }
    ],
    "virtual-compute-desc": [
        {
            "id": "cirros_vnfd-VM-compute",
            "virtual-cpu": {"num-virtual-cpu": 1},
            "virtual-memory": {"size": 1},
        }
    ],
    "virtual-storage-desc": [{"id": "cirros_vnfd-VM-storage", "size-of-storage": 2}],
    "sw-image-desc": [{"id": "cirros034", "name": "cirros034", "image": "cirros034"}],
    "ext-cpd": [
        {
            "int-cpd": {"vdu-id": "cirros_vnfd-VM", "cpd": "vdu-eth0-int"},
            "id": "vnf-cp0-ext",
        }
    ],
    "df": [
        {
            "id": "default-df",
            "vdu-profile": [{"id": "cirros_vnfd-VM"}],
            "instantiation-level": [
                {
                    "id": "default-instantiation-level",
                    "vdu-level": [{"vdu-id": "cirros_vnfd-VM"}],
                }
            ],
        }
    ],
    "description": "Simple VNF example with a cirros and a scaling group descriptor",
    "mgmt-cp": "vnf-cp0-ext",
}


@mock.patch.object(CommonDbClient, "__init__", lambda *args, **kwargs: None)
@mock.patch.object(MessageBusClient, "__init__", lambda *args, **kwargs: None)
class EvaluatorTest(TestCase):
    def setUp(self):
        super().setUp()
        self.config = Config()

    @mock.patch.object(EvaluatorService, "_get_metric_value")
    def test_evaluate_metric(self, get_metric_value):
        mock_alarm = mock.Mock()
        mock_alarm.operation = "gt"
        mock_alarm.threshold = 50.0
        mock_alarm.metric = "metric_name"
        get_metric_value.return_value = 100.0

        service = EvaluatorService(self.config)
        service.queue = mock.Mock()
        service._evaluate_metric(mock_alarm)
        service.queue.put.assert_called_with((mock_alarm, AlarmStatus.ALARM))
        service.queue.reset_mock()

        mock_alarm.operation = "lt"
        service._evaluate_metric(mock_alarm)
        service.queue.put.assert_called_with((mock_alarm, AlarmStatus.OK))
        service.queue.reset_mock()

        get_metric_value.return_value = None
        service._evaluate_metric(mock_alarm)
        service.queue.put.assert_called_with((mock_alarm, AlarmStatus.INSUFFICIENT))

    @mock.patch("multiprocessing.Process")
    @mock.patch.object(EvaluatorService, "_evaluate_metric")
    @mock.patch.object(CommonDbClient, "get_vnfd")
    @mock.patch.object(CommonDbClient, "get_vnfr")
    @mock.patch.object(CommonDbClient, "get_alarms")
    def test_evaluate_alarms(
        self, alarm_list, get_vnfr, get_vnfd, evaluate_metric, process
    ):
        mock_alarm = mock.Mock()
        mock_alarm.vdur_name = "cirros_ns-1-cirros_vnfd-VM-1"
        mock_alarm.monitoring_param = "cirros_vnf_memory_util"
        mock_alarm.tags = {"name": "value"}
        alarm_list.return_value = [mock_alarm]
        get_vnfr.return_value = vnfr_record_mock
        get_vnfd.return_value = vnfd_record_mock

        evaluator = EvaluatorService(self.config)
        evaluator.evaluate_alarms()

        process.assert_called_with(target=evaluate_metric, args=(mock_alarm,))

    @mock.patch.object(PrometheusBackend, "get_metric_value")
    def test_get_metric_value_prometheus(self, get_metric_value):
        self.config.set("evaluator", "backend", "prometheus")
        evaluator = EvaluatorService(self.config)
        evaluator._get_metric_value("test", {})

        get_metric_value.assert_called_with("test", {})
