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
from typing import List

from osm_common import dbmongo, dbmemory

from osm_mon.core.config import Config
from osm_mon.core.models import Alarm


class CommonDbClient:
    def __init__(self, config: Config):
        if config.get("database", "driver") == "mongo":
            self.common_db = dbmongo.DbMongo()
        elif config.get("database", "driver") == "memory":
            self.common_db = dbmemory.DbMemory()
        else:
            raise Exception(
                "Unknown database driver {}".format(config.get("section", "driver"))
            )
        self.common_db.db_connect(config.get("database"))

    def get_vnfr(self, nsr_id: str, member_index: int):
        vnfr = self.common_db.get_one(
            "vnfrs", {"nsr-id-ref": nsr_id, "member-vnf-index-ref": str(member_index)}
        )
        return vnfr

    def get_vnfrs(self, nsr_id: str = None, vim_account_id: str = None):
        if nsr_id and vim_account_id:
            raise NotImplementedError("Only one filter is currently supported")
        if nsr_id:
            vnfrs = [
                self.get_vnfr(nsr_id, member["member-vnf-index"])
                for member in self.get_nsr(nsr_id)["nsd"]["constituent-vnfd"]
            ]
        elif vim_account_id:
            vnfrs = self.common_db.get_list("vnfrs", {"vim-account-id": vim_account_id})
        else:
            vnfrs = self.common_db.get_list("vnfrs")
        return vnfrs

    def get_vnfd(self, vnfd_id: str):
        vnfd = self.common_db.get_one("vnfds", {"_id": vnfd_id})
        return vnfd

    def get_vnfd_by_id(self, vnfd_id: str, filter: dict = {}):
        filter["id"] = vnfd_id
        vnfd = self.common_db.get_one("vnfds", filter)
        return vnfd

    def get_vnfd_by_name(self, vnfd_name: str):
        # TODO: optimize way of getting single VNFD in shared enviroments (RBAC)
        if self.common_db.get_list("vnfds", {"name": vnfd_name}):
            vnfd = self.common_db.get_list("vnfds", {"name": vnfd_name})[0]
            return vnfd
        else:
            return None

    def get_nsrs(self):
        return self.common_db.get_list("nsrs")

    def get_nsr(self, nsr_id: str):
        nsr = self.common_db.get_one("nsrs", {"id": nsr_id})
        return nsr

    def get_nslcmop(self, nslcmop_id):
        nslcmop = self.common_db.get_one("nslcmops", {"_id": nslcmop_id})
        return nslcmop

    def get_vdur(self, nsr_id, member_index, vdur_name):
        vnfr = self.get_vnfr(nsr_id, member_index)
        for vdur in vnfr["vdur"]:
            if vdur["name"] == vdur_name:
                return vdur
        raise ValueError(
            "vdur not found for nsr-id {}, member_index {} and vdur_name {}".format(
                nsr_id, member_index, vdur_name
            )
        )

    def decrypt_vim_password(self, vim_password: str, schema_version: str, vim_id: str):
        return self.common_db.decrypt(vim_password, schema_version, vim_id)

    def decrypt_sdnc_password(
        self, sdnc_password: str, schema_version: str, sdnc_id: str
    ):
        return self.common_db.decrypt(sdnc_password, schema_version, sdnc_id)

    def get_vim_account_id(self, nsr_id: str, vnf_member_index: int) -> str:
        vnfr = self.get_vnfr(nsr_id, vnf_member_index)
        return vnfr["vim-account-id"]

    def get_vim_accounts(self):
        return self.common_db.get_list("vim_accounts")

    def get_vim_account(self, vim_account_id: str) -> dict:
        vim_account = self.common_db.get_one("vim_accounts", {"_id": vim_account_id})
        vim_account["vim_password"] = self.decrypt_vim_password(
            vim_account["vim_password"], vim_account["schema_version"], vim_account_id
        )
        vim_config_encrypted_dict = {
            "1.1": ("admin_password", "nsx_password", "vcenter_password"),
            "default": (
                "admin_password",
                "nsx_password",
                "vcenter_password",
                "vrops_password",
            ),
        }
        vim_config_encrypted = vim_config_encrypted_dict["default"]
        if vim_account["schema_version"] in vim_config_encrypted_dict.keys():
            vim_config_encrypted = vim_config_encrypted_dict[
                vim_account["schema_version"]
            ]
        if "config" in vim_account:
            for key in vim_account["config"]:
                if key in vim_config_encrypted:
                    vim_account["config"][key] = self.decrypt_vim_password(
                        vim_account["config"][key],
                        vim_account["schema_version"],
                        vim_account_id,
                    )
        return vim_account

    def set_vim_account(self, vim_account_id: str, update_dict: dict) -> bool:
        try:
            # Set vim_account resources in mongo
            self.common_db.set_one('vim_accounts', {"_id": vim_account_id}, update_dict)
            # self.common_db.set_one('vim_accounts', {"name": "test-vim"}, update_dict)
            return True
        except Exception:
            return False

    def get_sdncs(self):
        return self.common_db.get_list("sdns")

    def get_sdnc(self, sdnc_id: str):
        return self.common_db.get_one("sdns", {"_id": sdnc_id})

    def get_projects(self):
        return self.common_db.get_list("projects")

    def get_project(self, project_id: str):
        return self.common_db.get_one("projects", {"_id": project_id})

    def get_k8sclusters(self):
        return self.common_db.get_list("k8sclusters")

    def create_alarm(self, alarm: Alarm):
        action_data = {"uuid": alarm.uuid, "action": alarm.action}
        self.common_db.create("alarms_action", action_data)
        return self.common_db.create("alarms", alarm.to_dict())

    def delete_alarm(self, alarm_uuid: str):
        self.common_db.del_one("alarms_action", {"uuid": alarm_uuid})
        return self.common_db.del_one("alarms", {"uuid": alarm_uuid})

    def get_alarms(self) -> List[Alarm]:
        alarms = []
        alarm_dicts = self.common_db.get_list("alarms")
        for alarm_dict in alarm_dicts:
            alarms.append(Alarm.from_dict(alarm_dict))
        return alarms

    def update_alarm_status(self, alarm_state: str, uuid):
        modified_count = self.common_db.set_one("alarms", {"uuid": uuid}, {"alarm_status": alarm_state})
        return modified_count

    def get_alarm_by_uuid(self, uuid: str):
        return self.common_db.get_one("alarms", {"uuid": uuid})

    def get_user(self, username: str):
        return self.common_db.get_one("users", {"username": username})

    def get_user_by_id(self, userid: str):
        return self.common_db.get_one("users", {"_id": userid})

    def get_role_by_name(self, name: str):
        return self.common_db.get_one("roles", {"name": name})

    def get_role_by_id(self, role_id: str):
        return self.common_db.get_one("roles", {"_id": role_id})
