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
from typing import List

from keystoneclient.v3 import client as keystone_client
from novaclient import client as nova_client
from cinderclient import client as cinder_client
from neutronclient.neutron import client as neutron_client

from osm_mon.collector.infra_collectors.base_vim import BaseVimInfraCollector
from osm_mon.collector.metric import Metric
from osm_mon.collector.utils.openstack import OpenstackUtils
from osm_mon.core.common_db import CommonDbClient
from osm_mon.core.config import Config

log = logging.getLogger(__name__)


class BaseOpenStackInfraCollector(BaseVimInfraCollector):
    def __init__(self, config: Config, vim_account_id: str):
        super().__init__(config, vim_account_id)
        self.conf = config
        self.common_db = CommonDbClient(config)
        self.vim_account = self.common_db.get_vim_account(vim_account_id)
        # self.keystone = self._build_keystone_client(self.vim_account)
        self.vim_session = None
        self.nova = self._build_nova_client(self.vim_account)
        self.cinder = self._build_cinder_client(self.vim_account)
        self.neutron, self.tenant_id = self._build_neutron_client(self.vim_account)

    def collect(self) -> List[Metric]:
        metrics = []
        vim_status = self.is_vim_ok()
        if vim_status:
            # Updating the resources in mongoDB
            self.update_resources()
        if self.vim_account["_admin"]["projects_read"]:
            vim_project_id = self.vim_account["_admin"]["projects_read"][0]
        else:
            vim_project_id = ""
        vim_tags = {
            "vim_account_id": self.vim_account["_id"],
            "project_id": vim_project_id,
        }
        vim_status_metric = Metric(vim_tags, "vim_status", vim_status)
        metrics.append(vim_status_metric)
        vnfrs = self.common_db.get_vnfrs(vim_account_id=self.vim_account["_id"])
        for vnfr in vnfrs:
            nsr_id = vnfr["nsr-id-ref"]
            ns_name = self.common_db.get_nsr(nsr_id)["name"]
            vnf_member_index = vnfr["member-vnf-index-ref"]
            if vnfr["_admin"]["projects_read"]:
                vnfr_project_id = vnfr["_admin"]["projects_read"][0]
            else:
                vnfr_project_id = ""
            for vdur in vnfr["vdur"]:
                if "vim-id" not in vdur:
                    log.debug("Field vim-id is not present in vdur")
                    continue
                resource_uuid = vdur["vim-id"]
                tags = {
                    "vim_account_id": self.vim_account["_id"],
                    "resource_uuid": resource_uuid,
                    "ns_id": nsr_id,
                    "ns_name": ns_name,
                    "vnf_member_index": vnf_member_index,
                    "vdu_name": vdur.get("name", ""),
                    "project_id": vnfr_project_id,
                }
                try:
                    vm = self.nova.servers.get(resource_uuid)
                    vm_status = (0 if (vm.status == 'ERROR') else 1)
                    vm_status_metric = Metric(tags, "vm_status", vm_status)
                except Exception as e:
                    log.warning("VM status is not OK: %s" % e)
                    vm_status_metric = Metric(tags, "vm_status", 0)
                metrics.append(vm_status_metric)

        return metrics

    def is_vim_ok(self) -> bool:
        try:
            self.nova.servers.list()
            return True
        except Exception as e:
            log.warning("VIM status is not OK: %s" % e)
            return False

    def update_resources(self):
        if "resources" in self.vim_account:
            vimacc_resources = self.vim_account["resources"]
            # Compute resources
            try:
                com_lim = self.nova.limits.get()._info['absolute']
                if ("compute" in vimacc_resources) \
                   and ((vimacc_resources["compute"]["ram"]["total"] != com_lim['maxTotalRAMSize'])
                   or (vimacc_resources["compute"]["vcpus"]["total"] != com_lim['maxTotalCores'])
                   or (vimacc_resources["compute"]["ram"]["used"] != com_lim['totalRAMUsed'])
                   or (vimacc_resources["compute"]["vcpus"]["used"] != com_lim['totalCoresUsed'])
                   or (vimacc_resources["compute"]["instances"]["total"] != com_lim['maxTotalInstances'])
                   or (vimacc_resources["compute"]["instances"]["used"] != com_lim['totalInstancesUsed'])):
                    update_dict = {"resources.compute": {"ram": {"total": com_lim['maxTotalRAMSize'],
                                                                 "used": com_lim['totalRAMUsed']},
                                                         "vcpus": {"total": com_lim['maxTotalCores'],
                                                                   "used": com_lim['totalCoresUsed']},
                                                         "instances": {"total": com_lim['maxTotalInstances'],
                                                                       "used": com_lim['totalInstancesUsed']}}}
                    suc_value = self.common_db.set_vim_account(str(self.vim_account['_id']), update_dict)
                    log.info("Compute resources update in mongoDB  = %s" % suc_value)
            except Exception as e:
                log.warning("Error in updating compute resources: %s" % e)

            # Volume resources
            try:
                vol_lim = self.cinder.limits.get()._info['absolute']
                if ("storage" in vimacc_resources) and\
                   ((vimacc_resources["storage"]["volumes"]["total"] != vol_lim['maxTotalVolumes'])
                   or (vimacc_resources["storage"]["snapshots"]["total"] != vol_lim['maxTotalSnapshots'])
                   or (vimacc_resources["storage"]["volumes"]["used"] != vol_lim['totalVolumesUsed'])
                   or (vimacc_resources["storage"]["snapshots"]["used"] != vol_lim['totalSnapshotsUsed'])
                   or (vimacc_resources["storage"]["storage"]["total"] != vol_lim['maxTotalVolumeGigabytes'])
                   or (vimacc_resources["storage"]["storage"]["used"] != vol_lim['totalGigabytesUsed'])):
                    update_dict = {"resources.storage": {"volumes": {"total": vol_lim['maxTotalVolumes'],
                                                                     "used": vol_lim['totalVolumesUsed']},
                                                         "snapshots": {"total": vol_lim['maxTotalSnapshots'],
                                                                       "used": vol_lim['totalSnapshotsUsed']},
                                                         "storage": {"total": vol_lim['maxTotalVolumeGigabytes'],
                                                                     "used": vol_lim['totalGigabytesUsed']}}}
                    suc_value = self.common_db.set_vim_account(str(self.vim_account['_id']), update_dict)
                    log.info("Volume resources update in mongoDB = %s" % suc_value)
            except Exception as e:
                log.warning("Error in updating volume resources: %s" % e)

            # Network resources
            try:
                net_lim = self.neutron.show_quota_details(self.tenant_id)["quota"]
                if ("network" in vimacc_resources) and\
                   ((vimacc_resources["network"]["networks"]["total"] != net_lim["network"]["limit"])
                   or (vimacc_resources["network"]["networks"]["used"] != net_lim['network']['used'])
                   or (vimacc_resources["network"]["subnets"]["total"] != net_lim['subnet']['limit'])
                   or (vimacc_resources["network"]["subnets"]["used"] != net_lim['subnet']['used'])
                   or (vimacc_resources["network"]["floating_ips"]["total"] != net_lim['floatingip']['limit'])
                   or (vimacc_resources["network"]["floating_ips"]["used"] != net_lim['floatingip']['used'])):
                    update_dict = {"resources.network": {"networks": {"total": net_lim['network']['limit'],
                                                                      "used": net_lim['network']['used']},
                                                         "subnets": {"total": net_lim['subnet']['limit'],
                                                                     "used": net_lim['subnet']['used']},
                                                         "floating_ips": {"total": net_lim['floatingip']['limit'],
                                                                          "used": net_lim['floatingip']['used']}}}
                    suc_value = self.common_db.set_vim_account(str(self.vim_account['_id']), update_dict)
                    log.info("Network resources update in mongoDB = %s" % suc_value)
            except Exception as e:
                log.warning("Error in updating network resources: %s" % e)

    def _build_keystone_client(self, vim_account: dict) -> keystone_client.Client:
        sess = OpenstackUtils.get_session(vim_account)
        return keystone_client.Client(session=sess, timeout=10)

    def _build_nova_client(self, vim_account: dict) -> nova_client.Client:
        sess = OpenstackUtils.get_session(vim_account)
        self.vim_session = sess
        return nova_client.Client("2", session=sess, timeout=10)

    def _build_cinder_client(self, vim_account: dict) -> cinder_client.Client:
        # sess = OpenstackUtils.get_session(vim_account)
        return cinder_client.Client("3", session=self.vim_session, timeout=10)

    def _build_neutron_client(self, vim_account: dict) -> tuple:
        # sess = OpenstackUtils.get_session(vim_account)
        tenant_id = self.vim_session.get_project_id()
        return neutron_client.Client("2", session=self.vim_session, timeout=10), tenant_id
