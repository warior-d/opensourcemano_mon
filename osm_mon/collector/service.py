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

# This version uses a ProcessThreadPoolExecutor to limit the number of processes launched

import logging
from typing import List
import concurrent.futures
import time
import keystoneauth1.exceptions

from osm_mon.collector.infra_collectors.onos import OnosInfraCollector
from osm_mon.collector.infra_collectors.openstack import OpenstackInfraCollector
from osm_mon.collector.infra_collectors.vio import VIOInfraCollector
from osm_mon.collector.infra_collectors.vmware import VMwareInfraCollector
from osm_mon.collector.metric import Metric
from osm_mon.collector.vnf_collectors.juju import VCACollector
from osm_mon.collector.vnf_collectors.openstack import OpenstackCollector
from osm_mon.collector.vnf_collectors.vio import VIOCollector
from osm_mon.collector.vnf_collectors.vmware import VMwareCollector
from osm_mon.core.common_db import CommonDbClient
from osm_mon.core.config import Config

log = logging.getLogger(__name__)

VIM_COLLECTORS = {
    "openstack": OpenstackCollector,
    "vmware": VMwareCollector,
    "vio": VIOCollector,
}
VIM_INFRA_COLLECTORS = {
    "openstack": OpenstackInfraCollector,
    "vmware": VMwareInfraCollector,
    "vio": VIOInfraCollector,
}
SDN_INFRA_COLLECTORS = {"onosof": OnosInfraCollector, "onos_vpls": OnosInfraCollector}

# Map to store vim ids and corresponding vim session objects
vim_sess_map = {}


# Invoked from process executor to initialize the vim session map
def init_session(session_map: dict):
    global vim_sess_map
    vim_sess_map = session_map


class CollectorService:
    def __init__(self, config: Config):
        self.conf = config
        self.common_db = CommonDbClient(self.conf)
        return

    # static methods to be executed in the Processes
    @staticmethod
    def _get_vim_type(conf: Config, vim_account_id: str) -> str:
        common_db = CommonDbClient(conf)
        vim_account = common_db.get_vim_account(vim_account_id)
        vim_type = vim_account["vim_type"]
        if "config" in vim_account and "vim_type" in vim_account["config"]:
            vim_type = vim_account["config"]["vim_type"].lower()
            if vim_type == "vio" and "vrops_site" not in vim_account["config"]:
                vim_type = "openstack"
        return vim_type

    @staticmethod
    def _collect_vim_metrics(conf: Config, vnfr: dict, vim_account_id: str):
        # TODO(diazb) Add support for aws
        metrics = []
        vim_type = CollectorService._get_vim_type(conf, vim_account_id)
        log.debug("vim type.....{}".format(vim_type))
        if vim_type in VIM_COLLECTORS:
            collector = VIM_COLLECTORS[vim_type](conf, vim_account_id, vim_sess_map[vim_account_id])
            metrics = collector.collect(vnfr)
            log.debug("Collecting vim metrics.....{}".format(metrics))
        else:
            log.debug("vimtype %s is not supported.", vim_type)
        return metrics

    @staticmethod
    def _collect_vca_metrics(conf: Config, vnfr: dict):
        metrics = []
        vca_collector = VCACollector(conf)
        metrics = vca_collector.collect(vnfr)
        log.debug("Collecting vca metrics.....{}".format(metrics))
        return metrics

    @staticmethod
    def _collect_vim_infra_metrics(conf: Config, vim_account_id: str):
        log.info("Collecting vim infra metrics")
        metrics = []
        vim_type = CollectorService._get_vim_type(conf, vim_account_id)
        if vim_type in VIM_INFRA_COLLECTORS:
            collector = VIM_INFRA_COLLECTORS[vim_type](conf, vim_account_id)
            metrics = collector.collect()
            log.debug("Collecting vim infra metrics.....{}".format(metrics))
        else:
            log.debug("vimtype %s is not supported.", vim_type)
        return metrics

    @staticmethod
    def _collect_sdnc_infra_metrics(conf: Config, sdnc_id: str):
        log.info("Collecting sdnc metrics")
        metrics = []
        common_db = CommonDbClient(conf)
        sdn_type = common_db.get_sdnc(sdnc_id)["type"]
        if sdn_type in SDN_INFRA_COLLECTORS:
            collector = SDN_INFRA_COLLECTORS[sdn_type](conf, sdnc_id)
            metrics = collector.collect()
            log.debug("Collecting sdnc metrics.....{}".format(metrics))
        else:
            log.debug("sdn_type %s is not supported.", sdn_type)
        return metrics

    @staticmethod
    def _stop_process_pool(executor):
        log.info("Shutting down process pool")
        try:
            log.debug("Stopping residual processes in the process pool")
            for pid, process in executor._processes.items():
                if process.is_alive():
                    process.terminate()
        except Exception as e:
            log.info("Exception during process termination")
            log.debug("Exception %s" % (e))

        try:
            # Shutting down executor
            log.debug("Shutting down process pool executor")
            executor.shutdown()
        except RuntimeError as e:
            log.info("RuntimeError in shutting down executer")
            log.debug("RuntimeError %s" % (e))
        return

    def collect_metrics(self) -> List[Metric]:
        vnfrs = self.common_db.get_vnfrs()
        metrics = []

        # Get all vim ids regiestered in osm and create their corresponding vim session objects
        # Vim ids and their corresponding session objects are stored in vim-session-map
        # It optimizes the number of authentication tokens created in vim for metric colleciton
        vim_sess_map.clear()
        vims = self.common_db.get_vim_accounts()
        for vim in vims:
            vim_type = CollectorService._get_vim_type(self.conf, vim["_id"])
            if vim_type in VIM_INFRA_COLLECTORS:
                collector = VIM_INFRA_COLLECTORS[vim_type](self.conf, vim["_id"])
                vim_sess = collector.vim_session if vim_type == "openstack" else None
                # Populate the vim session map with vim ids and corresponding session objects
                # vim session objects are stopred only for vim type openstack
                if vim_sess:
                    vim_sess_map[vim["_id"]] = vim_sess

        start_time = time.time()
        # Starting executor pool with pool size process_pool_size. Default process_pool_size is 20
        # init_session is called to assign the session map to the gloabal vim session map variable
        with concurrent.futures.ProcessPoolExecutor(
            self.conf.get("collector", "process_pool_size"), initializer=init_session, initargs=(vim_sess_map,)
        ) as executor:
            log.info(
                "Started metric collector process pool with pool size %s"
                % (self.conf.get("collector", "process_pool_size"))
            )
            futures = []
            for vnfr in vnfrs:
                nsr_id = vnfr["nsr-id-ref"]
                vnf_member_index = vnfr["member-vnf-index-ref"]
                vim_account_id = self.common_db.get_vim_account_id(
                    nsr_id, vnf_member_index
                )
                futures.append(
                    executor.submit(
                        CollectorService._collect_vim_metrics,
                        self.conf,
                        vnfr,
                        vim_account_id,
                    )
                )
                futures.append(
                    executor.submit(
                        CollectorService._collect_vca_metrics, self.conf, vnfr
                    )
                )

            for vim in vims:
                futures.append(
                    executor.submit(
                        CollectorService._collect_vim_infra_metrics,
                        self.conf,
                        vim["_id"],
                    )
                )

            sdncs = self.common_db.get_sdncs()
            for sdnc in sdncs:
                futures.append(
                    executor.submit(
                        CollectorService._collect_sdnc_infra_metrics,
                        self.conf,
                        sdnc["_id"],
                    )
                )

            try:
                # Wait for future calls to complete till process_execution_timeout. Default is 50 seconds
                for future in concurrent.futures.as_completed(
                    futures, self.conf.get("collector", "process_execution_timeout")
                ):
                    try:
                        result = future.result(
                            timeout=int(
                                self.conf.get("collector", "process_execution_timeout")
                            )
                        )
                        metrics.extend(result)
                        log.debug("result = %s" % (result))
                    except keystoneauth1.exceptions.connection.ConnectionError as e:
                        log.info("Keystone connection error during metric collection")
                        log.debug("Keystone connection error exception %s" % (e))
            except concurrent.futures.TimeoutError as e:
                # Some processes have not completed due to timeout error
                log.info(
                    "Some processes have not finished due to TimeoutError exception"
                )
                log.debug("concurrent.futures.TimeoutError exception %s" % (e))

            # Shutting down process pool executor
            CollectorService._stop_process_pool(executor)

        end_time = time.time()
        log.info("Collection completed in %s seconds", end_time - start_time)

        return metrics
