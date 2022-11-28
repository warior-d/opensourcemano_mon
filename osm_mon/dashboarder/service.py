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
# contact: glavado@whitestack.com or fbravo@whitestack.com
##
import logging

from osm_mon.core.common_db import CommonDbClient
from osm_mon.core.config import Config
from osm_mon.core.keystone import KeystoneConnection
from osm_mon.dashboarder.backends.grafana import GrafanaBackend
from osm_mon import __path__ as mon_path
from osm_mon.core.utils import find_in_list, create_filter_from_nsr
import re

log = logging.getLogger(__name__)


class DashboarderService:
    def __init__(self, config: Config):
        self.conf = config
        self.common_db = CommonDbClient(self.conf)
        self.grafana = GrafanaBackend(self.conf)

        if bool(self.conf.get("keystone", "enabled")):
            self.keystone = KeystoneConnection(self.conf)
        else:
            self.keystone = None

    def create_dashboards(self):
        # TODO lavado: migrate these methods to mongo change streams
        # Lists all dashboards and OSM resources for later comparisons
        datasource_name_substr = self.conf.get("prometheus-operator", "ds_name_substr")
        prom_operator_port = self.conf.get("prometheus-operator", "port")
        dashboard_uids = self.grafana.get_all_dashboard_uids()
        datasource_names = self.grafana.get_all_datasource_names(datasource_name_substr)
        osm_resource_uids = []
        osm_datasource_names = []
        projects = []

        # Check if keystone is the auth/projects backend and get projects from there
        if self.keystone:
            try:
                projects.extend(
                    map(
                        lambda project: {"_id": project.id, "name": project.name},
                        self.keystone.getProjects(),
                    )
                )
            except Exception:
                log.error("Cannot retrieve projects from keystone")
        else:
            projects.extend(self.common_db.get_projects())

        # Reads existing project list and creates a dashboard for each
        for project in projects:
            project_id = project["_id"]
            # Collect Project IDs for periodical dashboard clean-up
            osm_resource_uids.append(project_id)
            dashboard_path = "{}/dashboarder/templates/project_scoped.json".format(
                mon_path[0]
            )
            cnf_dashboard_path = "{}/dashboarder/templates/cnf_scoped.json".format(
                mon_path[0]
            )
            if project_id not in dashboard_uids:
                project_name = project["name"]
                if project_name != "admin":
                    # Create project folder in Grafana only if user is not admin.
                    # Admin user's dashboard will be created in default folder
                    self.grafana.create_grafana_folders(project_name)
                self.grafana.create_dashboard(project_id, project_name, dashboard_path)
                log.debug("Created dashboard for Project: %s", project_id)
            else:
                log.debug("Dashboard already exists")

            # Read existing k8s cluster list and creates a dashboard for each
            k8sclusters = self.common_db.get_k8sclusters()
            for k8scluster in k8sclusters:
                k8scluster_id = k8scluster["_id"]
                k8scluster_name = k8scluster["name"]
                osm_resource_uids.append(k8scluster_id)
                osm_datasource_names.append("{}-{}".format(datasource_name_substr, k8scluster_name))
                if k8scluster_id not in dashboard_uids:
                    projects_read = k8scluster["_admin"]["projects_read"]
                    if len(projects_read) and projects_read[0] == project_id:
                        # Collect K8S Cluster IDs for periodical dashboard clean-up
                        k8scluster_address = k8scluster["credentials"]["clusters"][0]["cluster"]["server"]
                        # Extract K8S Cluster ip from url
                        k8scluster_ip = re.findall(r'://([\w\-\.]+)', k8scluster_address)[0]

                        # prometheus-operator url
                        datasource_url = "http://{}:{}".format(k8scluster_ip, prom_operator_port)

                        # Create datsource for prometheus-operator in grafana
                        datasource_type = "prometheus"
                        datasource_name = "{}-{}".format(datasource_name_substr, k8scluster_name)
                        if datasource_name not in datasource_names:
                            self.grafana.create_datasource(datasource_name, datasource_type, datasource_url)
                            log.debug("Created datasource for k8scluster: %s", k8scluster_id)

                        if project["name"] != "admin":
                            self.grafana.create_dashboard(
                                k8scluster_id, k8scluster_name, cnf_dashboard_path, project_name=project["name"],
                                datasource_name=datasource_name)
                        else:
                            self.grafana.create_dashboard(
                                k8scluster_id, k8scluster_name, cnf_dashboard_path, datasource_name=datasource_name)
                        log.debug("Created dashboard for k8scluster: %s", k8scluster_id)
                else:
                    log.debug("Dashboard already exist for k8scluster: %s", k8scluster_id)

        # Reads existing NS list and creates a dashboard for each
        # TODO lavado: only create for ACTIVE NSRs
        nsrs = self.common_db.get_nsrs()
        for nsr in nsrs:
            nsr_id = nsr["_id"]
            dashboard_path = "{}/dashboarder/templates/ns_scoped.json".format(
                mon_path[0]
            )
            # Collect NS IDs for periodical dashboard clean-up
            osm_resource_uids.append(nsr_id)
            # Check if the NSR's VNFDs contain metrics
            # Only one DF at the moment, support for this feature is comming in the future
            vnfds_profiles = nsr["nsd"]["df"][0]["vnf-profile"]
            for vnf_profile in vnfds_profiles:
                try:
                    vnfd = self.common_db.get_vnfd_by_id(
                        vnf_profile["vnfd-id"], create_filter_from_nsr(nsr)
                    )
                    # If there are metrics, create dashboard (if exists)
                    if vnfd.get("vdu"):
                        vdu_found = find_in_list(
                            vnfd.get("vdu"), lambda a_vdu: "monitoring-parameter" in a_vdu
                        )
                    else:
                        vdu_found = None
                    if vdu_found:
                        if nsr_id not in dashboard_uids:
                            nsr_name = nsr["name"]
                            project_id = nsr["_admin"]["projects_read"][0]
                            try:
                                # Get project details from commondb
                                project_details = self.common_db.get_project(project_id)
                                project_name = project_details["name"]
                            except Exception as e:
                                # Project not found in commondb
                                if self.keystone:
                                    # Serach project in keystone
                                    for project in projects:
                                        if project_id == project["_id"]:
                                            project_name = project["name"]
                                else:
                                    log.info("Project %s not found", project_id)
                                    log.debug("Exception %s" % e)
                            self.grafana.create_dashboard(
                                nsr_id, nsr_name, dashboard_path, project_name=project_name
                            )
                            log.debug("Created dashboard for NS: %s", nsr_id)
                        else:
                            log.debug("Dashboard already exists")
                        break
                    else:
                        log.debug("NS does not has metrics")
                except Exception:
                    log.exception("VNFD is not valid or has been renamed")
                    continue

        # Delete obsolete dashboards
        for dashboard_uid in dashboard_uids:
            if dashboard_uid not in osm_resource_uids:
                self.grafana.delete_dashboard(dashboard_uid)
                log.debug("Deleted obsolete dashboard: %s", dashboard_uid)
            else:
                log.debug("All dashboards in use")

        # Delete obsolute datasources
        for datasource_name in datasource_names:
            if datasource_name not in osm_datasource_names:
                self.grafana.delete_datasource(datasource_name)
                log.debug("Deleted obsolete datasource: %s", datasource_name)
            else:
                log.debug("All dashboards in use")

    def create_grafana_user(self, user):
        self.grafana.create_grafana_users(user)

    def delete_non_existing_users(self):
        if self.keystone:
            # Get users from keystone
            users = self.keystone.getUsers()
            usernames = []
            for user in users:
                usernames.append(user.name)
            grafana_users = self.grafana.get_grafana_users()
            users_to_be_deleted = list(set(grafana_users) - set(usernames))
            for grafana_user in users_to_be_deleted:
                self.grafana.delete_grafana_users(grafana_user)

    def create_grafana_team_member(
        self, project_data, userid=None, project_list=None, user=None
    ):
        if user:
            user_name = user
        else:
            try:
                # Get user details from  commondb
                user = self.common_db.get_user_by_id(userid)
                user_name = user["username"]
            except Exception as e:
                # User not found in commondb
                if self.keystone:
                    # Search user in keystone
                    user = self.keystone.getUserById(userid)
                    user_name = user.name
                else:
                    log.info("User %s not found", userid)
                    log.debug("Exception %s" % e)
        if project_list:
            # user-project mapping is done by osm cli
            for proj in project_data:
                project = self.common_db.get_project(proj["project"])
                proj_name = project["name"]
                role_obj = self.common_db.get_role_by_id(proj["role"])
                is_admin = role_obj["permissions"].get("admin")
                self.grafana.create_grafana_teams_members(
                    proj_name, user_name, is_admin, project_list
                )
        else:
            # user-project mapping is done by osm ui
            proj_list = []
            if self.keystone:
                users_proj_list = self.keystone.getProjectsById(userid)
                for project in users_proj_list:
                    proj_list.append(project.name)
            else:
                users_proj_list = user.get("project_role_mappings")
                for project in users_proj_list:
                    proj_data = self.common_db.get_project(project["project"])
                    proj_list.append(proj_data["name"])
            for proj in project_data:
                if self.keystone:
                    # Backend authentication type is keystone
                    try:
                        # Getting project and role objects from keystone using ids
                        role_obj = self.keystone.getRoleById(proj["role"])
                        proj_data = self.keystone.getProjectsByProjectId(
                            proj["project"]
                        )
                        log.info(
                            "role object {} {}".format(
                                role_obj.permissions, proj_data.name
                            )
                        )
                        is_admin = role_obj.permissions["admin"]
                    except Exception:
                        # Getting project and role objects from keystone using names
                        role_obj = self.keystone.getRoleByName(proj["role"])[0]
                        proj_data = self.keystone.getProjectsByProjectName(
                            proj["project"]
                        )[0]
                        is_admin = role_obj.to_dict().get("permissions").get("admin")
                        log.info(
                            "role object {} {}".format(
                                role_obj.to_dict(), proj_data.name
                            )
                        )
                    proj_name = proj_data.name
                else:
                    # Backend authentication type is internal
                    try:
                        # Getting project and role object from commondb using names
                        role_obj = self.common_db.get_role_by_name(proj["role"])
                        proj_name = proj["project"]
                    except Exception:
                        # Getting project and role object from commondb using ids
                        role_obj = self.common_db.get_role_by_id(proj["role"])
                        proj_data = self.common_db.get_project(proj["project"])
                        proj_name = proj_data["name"]
                    is_admin = role_obj["permissions"].get("admin")
                self.grafana.create_grafana_teams_members(
                    proj_name, user_name, is_admin, proj_list
                )

    def create_grafana_team(self, team_name):
        self.grafana.create_grafana_teams(team_name)

    def delete_grafana_user(self, user_name):
        self.grafana.delete_grafana_users(user_name)

    def delete_grafana_team(self, project_name):
        self.grafana.delete_grafana_team(project_name)

    def update_grafana_team(self, project_new_name, project_old_name):
        self.grafana.update_grafana_teams(project_new_name, project_old_name)

    def remove_grafana_team_members(self, user_id, proj_data):
        try:
            # Get user details from  commondb
            user = self.common_db.get_user_by_id(user_id)
            user_name = user["username"]
        except Exception as e:
            # User not found in commondb
            if self.keystone:
                # Find user in keystone
                user = self.keystone.getUserById(user_id)
                user_name = user.name
            else:
                log.info("User %s not found", user_id)
                log.debug("Exception %s" % e)
        self.grafana.remove_grafana_team_member(user_name, proj_data)
