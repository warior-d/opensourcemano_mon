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

# pylint: disable=E1101

import datetime
from unittest import TestCase, mock

import gnocchiclient

from osm_mon.collector.vnf_collectors.openstack import GnocchiBackend
from osm_mon.core.config import Config


class CollectorTest(TestCase):
    def setUp(self):
        super().setUp()
        self.config = Config()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(GnocchiBackend, "_build_neutron_client")
    @mock.patch.object(GnocchiBackend, "_build_gnocchi_client")
    def test_collect_gnocchi_rate_instance(self, build_gnocchi_client, _):
        mock_gnocchi_client = mock.Mock()
        mock_gnocchi_client.metric = mock.Mock()
        mock_vim_session = mock.Mock()
        mock_gnocchi_client.metric.get_measures.return_value = [
            (
                datetime.datetime(
                    2019,
                    4,
                    12,
                    15,
                    43,
                    tzinfo=datetime.timezone(datetime.timedelta(0), "+00:00"),
                ),
                60.0,
                0.0345442539,
            ),
            (
                datetime.datetime(
                    2019,
                    4,
                    12,
                    15,
                    44,
                    tzinfo=datetime.timezone(datetime.timedelta(0), "+00:00"),
                ),
                60.0,
                600000000,
            ),
        ]
        build_gnocchi_client.return_value = mock_gnocchi_client

        backend = GnocchiBackend({"_id": "test_uuid"}, mock_vim_session)
        value = backend._collect_instance_metric("cpu", "test_resource_id")
        self.assertEqual(value, 1.0)
        mock_gnocchi_client.metric.get_measures.assert_called_once_with(
            "cpu",
            aggregation="rate:mean",
            start=mock.ANY,
            resource_id="test_resource_id",
        )

    @mock.patch.object(GnocchiBackend, "_build_neutron_client")
    @mock.patch.object(GnocchiBackend, "_build_gnocchi_client")
    def test_collect_gnocchi_non_rate_instance(self, build_gnocchi_client, _):
        mock_gnocchi_client = mock.Mock()
        mock_vim_session = mock.Mock()
        mock_gnocchi_client.metric.get_measures.return_value = [
            (
                datetime.datetime(
                    2019,
                    4,
                    12,
                    15,
                    43,
                    tzinfo=datetime.timezone(datetime.timedelta(0), "+00:00"),
                ),
                60.0,
                0.0345442539,
            ),
            (
                datetime.datetime(
                    2019,
                    4,
                    12,
                    15,
                    44,
                    tzinfo=datetime.timezone(datetime.timedelta(0), "+00:00"),
                ),
                60.0,
                128,
            ),
        ]
        build_gnocchi_client.return_value = mock_gnocchi_client

        backend = GnocchiBackend({"_id": "test_uuid"}, mock_vim_session)
        value = backend._collect_instance_metric("memory.usage", "test_resource_id")
        self.assertEqual(value, 128)
        mock_gnocchi_client.metric.get_measures.assert_called_once_with(
            "memory.usage",
            aggregation=None,
            start=mock.ANY,
            resource_id="test_resource_id",
        )

    @mock.patch.object(GnocchiBackend, "_build_neutron_client")
    @mock.patch.object(GnocchiBackend, "_build_gnocchi_client")
    def test_collect_gnocchi_no_metric(self, build_gnocchi_client, _):
        mock_gnocchi_client = mock.Mock()
        mock_vim_session = mock.Mock()
        mock_gnocchi_client.metric.get_measures.side_effect = (
            gnocchiclient.exceptions.NotFound()
        )
        build_gnocchi_client.return_value = mock_gnocchi_client

        backend = GnocchiBackend({"_id": "test_uuid"}, mock_vim_session)
        value = backend._collect_instance_metric("memory.usage", "test_resource_id")
        self.assertIsNone(value)
        mock_gnocchi_client.metric.get_measures.assert_called_once_with(
            "memory.usage",
            aggregation=None,
            start=mock.ANY,
            resource_id="test_resource_id",
        )

    @mock.patch.object(GnocchiBackend, "_build_neutron_client")
    @mock.patch.object(GnocchiBackend, "_build_gnocchi_client")
    def test_collect_interface_all_metric(
        self, build_gnocchi_client, build_neutron_client
    ):
        mock_gnocchi_client = mock.Mock()
        mock_vim_session = mock.Mock()
        mock_gnocchi_client.resource.search.return_value = [
            {"id": "test_id_1"},
            {"id": "test_id_2"},
        ]
        mock_gnocchi_client.metric.get_measures.return_value = [
            (
                datetime.datetime(
                    2019,
                    4,
                    12,
                    15,
                    43,
                    tzinfo=datetime.timezone(datetime.timedelta(0), "+00:00"),
                ),
                60.0,
                0.0345442539,
            ),
            (
                datetime.datetime(
                    2019,
                    4,
                    12,
                    15,
                    44,
                    tzinfo=datetime.timezone(datetime.timedelta(0), "+00:00"),
                ),
                60.0,
                0.0333070363,
            ),
        ]

        build_gnocchi_client.return_value = mock_gnocchi_client

        backend = GnocchiBackend({"_id": "test_uuid"}, mock_vim_session)
        value = backend._collect_interface_all_metric(
            "packets_received", "test_resource_id"
        )
        self.assertEqual(value, 0.0666140726)
        mock_gnocchi_client.metric.get_measures.assert_any_call(
            "packets_received", resource_id="test_id_1", limit=1
        )
        mock_gnocchi_client.metric.get_measures.assert_any_call(
            "packets_received", resource_id="test_id_2", limit=1
        )

    @mock.patch.object(GnocchiBackend, "_build_neutron_client")
    @mock.patch.object(GnocchiBackend, "_build_gnocchi_client")
    def test_collect_instance_disk_metric(
        self, build_gnocchi_client, build_neutron_client
    ):
        mock_gnocchi_client = mock.Mock()
        mock_vim_session = mock.Mock()
        mock_gnocchi_client.resource.search.return_value = [
            {"id": "test_id"},
        ]
        mock_gnocchi_client.metric.get_measures.return_value = [
            (
                datetime.datetime(
                    2019,
                    4,
                    12,
                    15,
                    43,
                    tzinfo=datetime.timezone(datetime.timedelta(0), "+00:00"),
                ),
                60.0,
                0.0225808,
            ),
            (
                datetime.datetime(
                    2019,
                    4,
                    12,
                    15,
                    44,
                    tzinfo=datetime.timezone(datetime.timedelta(0), "+00:00"),
                ),
                60.0,
                230848,
            ),
        ]

        build_gnocchi_client.return_value = mock_gnocchi_client

        backend = GnocchiBackend({"_id": "test_uuid"}, mock_vim_session)
        value = backend._collect_instance_disk_metric(
            "disk_read_bytes", "test_resource_id"
        )
        self.assertEqual(value, 230848)
        mock_gnocchi_client.metric.get_measures.assert_any_call(
            "disk_read_bytes", resource_id="test_id", limit=1
        )
