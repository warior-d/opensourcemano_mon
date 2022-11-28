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
# contact: glavado@whitestack.com or fbravo@whitestack.com
##
import logging
import requests
import base64
import json
from osm_mon.core.config import Config

log = logging.getLogger(__name__)


class GrafanaBackend:
    def __init__(self, config: Config):
        self.conf = config
        self.url = config.get("grafana", "url")
        grafana_user = config.get("grafana", "user")
        grafana_password = config.get("grafana", "password")
        self.headers = {
            "content-type": "application/json",
            "authorization": "Basic %s"
            % base64.b64encode(
                (grafana_user + ":" + grafana_password).encode("utf-8")
            ).decode(),
        }

    def get_all_dashboard_uids(self):
        # Gets only dashboards that were automated by OSM (with tag 'osm_automated')
        response = requests.request(
            "GET", self.url + "/api/search?tag=osm_automated", headers=self.headers
        )
        dashboards = response.json()
        dashboard_uids = []
        for dashboard in dashboards:
            dashboard_uids.append(dashboard["uid"])
        log.debug("Searching for all dashboard uids: %s", dashboard_uids)
        return dashboard_uids

    def get_all_datasource_names(self, datasource_name_substr):
        # Gets only dashboards that were created for prom-operator
        response = requests.request(
            "GET", self.url + "/api/datasources", headers=self.headers
        )
        datasources = response.json()
        datasource_names = []
        for datasource in datasources:
            if datasource["name"].startswith(datasource_name_substr):
                datasource_names.append(datasource["name"])
        log.debug("Searching for all datasource names: %s", datasource_names)
        return datasource_names

    def get_dashboard_status(self, uid):
        response = requests.request(
            "GET", self.url + "/api/dashboards/uid/" + uid, headers=self.headers
        )
        log.debug("Searching for dashboard result: %s", response.text)
        return response

    def create_dashboard(self, uid, name, json_file, project_name=None, datasource_name=None):
        try:
            with open(json_file) as f:
                dashboard_data = f.read()

            dashboard_data = dashboard_data.replace("OSM_ID", uid).replace(
                "OSM_NAME", name
            )
            if datasource_name:
                dashboard_data = dashboard_data.replace("OSM_DATASOURCE_NAME", datasource_name)
            dashboard_json_data = json.loads(dashboard_data)
            # Get folder id
            if project_name:
                folder_name = project_name
            else:
                folder_name = name
            response_folder_id = requests.request(
                "GET",
                self.url + "/api/folders/{}".format(folder_name),
                headers=self.headers,
            )
            if response_folder_id.status_code == 200:
                folder_id = json.loads(response_folder_id.text)["id"]
                dashboard_json_data["folderId"] = folder_id
                dashboard_json_data["overwrite"] = False

            response = self.send_request_for_creating_dashboard(dashboard_json_data)

            # Admin dashboard will be created if already exists. Rest will remain same.
            if json.loads(response.text).get("status") == "name-exists":
                # Delete any previous project-admin dashboard if it already exist.
                if name == "admin":
                    self.delete_admin_dashboard()
                    response = self.send_request_for_creating_dashboard(
                        dashboard_json_data
                    )
                else:
                    return

            # Get team id
            if project_name is not None:
                name = project_name
            response_team = requests.request(
                "GET",
                self.url + "/api/teams/search?name={}".format(name),
                headers=self.headers,
            )

            # Remove default permissions of admin user's dashboard so that it is not visible to non-admin users
            if len(json.loads(response_team.text)["teams"]) == 0:
                # As team information is not available so it is admin user
                dahboard_id = json.loads(response.text)["id"]
                requests.request(
                    "POST",
                    self.url + "/api/dashboards/id/{}/permissions".format(dahboard_id),
                    headers=self.headers,
                )

            log.info("Dashboard %s is created in Grafana", name)
            return response
        except Exception:
            log.exception("Exception processing message: ")

    def create_datasource(self, datasource_name, datasource_type, datasource_url):
        try:
            datasource_data = {
                "name": datasource_name,
                "type": datasource_type,
                "url": datasource_url,
                "access": "proxy",
                "readOnly": False,
                "basicAuth": False
            }
            response = requests.request(
                "POST",
                self.url + "/api/datasources",
                data=json.dumps(datasource_data),
                headers=self.headers,
            )
            log.info("Datasource %s is created in Grafana", datasource_name)
            log.info("************* response: {}".format(response.__dict__))
            return response
        except Exception:
            log.exception("Exception processing request for creating datasource: ")

    def send_request_for_creating_dashboard(self, dashboard_data):
        response = requests.request(
            "POST",
            self.url + "/api/dashboards/db/",
            data=json.dumps(dashboard_data),
            headers=self.headers,
        )
        return response

    def delete_dashboard(self, uid):
        response = requests.request(
            "DELETE", self.url + "/api/dashboards/uid/" + uid, headers=self.headers
        )
        log.debug("Dashboard %s deleted from Grafana", uid)
        return response

    def delete_datasource(self, datasource_name):
        response = requests.request(
            "DELETE", self.url + "/api/datasources/name/" + datasource_name, headers=self.headers
        )
        log.debug("Datasource %s deleted from Grafana", datasource_name)
        return response

    def delete_admin_dashboard(self):
        requests.request(
            "DELETE",
            self.url + "/api/dashboards/db/osm-project-status-admin",
            headers=self.headers,
        )
        log.debug("Dashboard osm-project-status-admin deleted from Grafana")

    def create_grafana_users(self, user):
        email = "{}@osm.etsi.org".format(user)
        user_payload = {
            "name": user,
            "email": email,
            "login": user,
            "password": user,
        }
        response_users = requests.request(
            "POST",
            self.url + "/api/admin/users/",
            json=user_payload,
            headers=self.headers,
        )
        json_data = json.loads(response_users.text)
        url = "/api/org/users/{}/".format(json_data["id"])
        permission_payload = {
            "role": "Editor",
        }
        requests.request(
            "PATCH", self.url + url, json=permission_payload, headers=self.headers
        )
        log.info("New user %s created in Grafana", user)
        return response_users

    # Get Grafana users
    def get_grafana_users(self):
        response_users = requests.request(
            "GET",
            self.url + "/api/users",
            headers=self.headers,
        )
        user_list = []
        users = json.loads(response_users.text)
        for user in users:
            if user["name"] and user["name"] != "admin":
                user_list.append(user["name"])
        return user_list

    # Create Grafana team with member
    def create_grafana_teams_members(
        self, project_name, user_name, is_admin, proj_list
    ):
        # Check if user exist in Grafana
        user_response = requests.request(
            "GET",
            self.url + "/api/users/lookup?loginOrEmail={}".format(user_name),
            headers=self.headers,
        )
        user_obj = json.loads(user_response.text)
        if user_response.status_code != 200:
            user_response = self.create_grafana_users(user_name)
            user_obj = json.loads(user_response.text)

        user_id = user_obj["id"]

        # Get teams for user
        team_objs = requests.request(
            "GET",
            self.url + "/api/users/{}/teams".format(user_id),
            headers=self.headers,
        )
        team_obj = json.loads(team_objs.text)
        team_list = []
        if len(team_obj):
            for team in team_obj:
                team_list.append(team["name"])

        proj_unlink = set(team_list) - set(proj_list)
        for prj in proj_unlink:
            response_team = requests.request(
                "GET",
                self.url + "/api/teams/search?name={}".format(prj),
                headers=self.headers,
            )
            team_id = json.loads(response_team.text)["teams"][0]["id"]
            requests.request(
                "DELETE",
                self.url + "/api/teams/{}/members/{}".format(team_id, user_id),
                headers=self.headers,
            )
        if project_name != "admin":
            # Add member to team
            response_team = requests.request(
                "GET",
                self.url + "/api/teams/search?name={}".format(project_name),
                headers=self.headers,
            )

            # Search if team in Grafana corresponding to the project already exists
            if not json.loads(response_team.text)["teams"]:
                self.create_grafana_teams(project_name)
                response_team = requests.request(
                    "GET",
                    self.url + "/api/teams/search?name={}".format(project_name),
                    headers=self.headers,
                )
            team_id = json.loads(response_team.text)["teams"][0]["id"]
            if project_name not in team_list:
                # Create a team in Grafana corresponding to the project as it doesn't exist
                member_payload = {"userId": user_id}
                requests.request(
                    "POST",
                    self.url + "/api/teams/{}/members".format(team_id),
                    json=member_payload,
                    headers=self.headers,
                )
        # Check if user role or project name is admin
        if is_admin or project_name == "admin":
            # Give admin righsts to user
            url = "/api/org/users/{}/".format(user_id)
            permission_payload = {
                "role": "Admin",
            }
            requests.request(
                "PATCH", self.url + url, json=permission_payload, headers=self.headers
            )
            log.info("User %s is assigned Admin permission", user_name)
        else:
            # Give editor rights to user
            url = "/api/org/users/{}/".format(user_id)
            permission_payload = {
                "role": "Editor",
            }
            requests.request(
                "PATCH", self.url + url, json=permission_payload, headers=self.headers
            )
            log.info("User %s is assigned Editor permission", user_name)

    # Create team in Grafana
    def create_grafana_teams(self, team_name):
        team_payload = {
            "name": team_name,
        }
        requests.request(
            "POST", self.url + "/api/teams", json=team_payload, headers=self.headers
        )
        log.info("New team %s created in Grafana", team_name)

    # Create folder in Grafana
    def create_grafana_folders(self, folder_name):
        folder_payload = {"uid": folder_name, "title": folder_name}
        requests.request(
            "POST", self.url + "/api/folders", json=folder_payload, headers=self.headers
        )
        log.info("Dashboard folder %s created", folder_name)

        response_team = requests.request(
            "GET",
            self.url + "/api/teams/search?name={}".format(folder_name),
            headers=self.headers,
        )
        # Create team if it doesn't already exists
        if len(json.loads(response_team.text)["teams"]) == 0:
            self.create_grafana_teams(folder_name)
            response_team = requests.request(
                "GET",
                self.url + "/api/teams/search?name={}".format(folder_name),
                headers=self.headers,
            )
        # Assign required permission to the team's folder
        team_id = json.loads(response_team.text)["teams"][0]["id"]
        permission_data = {
            "items": [
                {"teamId": team_id, "permission": 2},
            ]
        }
        requests.request(
            "POST",
            self.url + "/api/folders/{}/permissions".format(folder_name),
            json=permission_data,
            headers=self.headers,
        )

    # delete user from grafana
    def delete_grafana_users(self, user_name):
        # Get user id
        response_id = requests.request(
            "GET",
            self.url + "/api/users/lookup?loginOrEmail={}".format(user_name),
            headers=self.headers,
        )
        try:
            user_id = json.loads(response_id.text)["id"]
        except Exception:
            log.exception("Exception processing message: ")
        # Delete user
        response = requests.request(
            "DELETE",
            self.url + "/api/admin/users/{}".format(user_id),
            headers=self.headers,
        )
        log.info("User %s deleted in Grafana", user_name)
        return response

    # delete team from grafana
    def delete_grafana_team(self, project_name):
        # Delete Grafana folder
        requests.request(
            "DELETE",
            self.url + "/api/folders/{}".format(project_name),
            headers=self.headers,
        )
        # Delete Grafana team
        team_obj = requests.request(
            "GET",
            self.url + "/api/teams/search?name={}".format(project_name),
            headers=self.headers,
        )
        team_id = json.loads(team_obj.text)["teams"][0]["id"]
        response = requests.request(
            "DELETE", self.url + "/api/teams/{}".format(team_id), headers=self.headers
        )
        log.info("Team %s deleted in Grafana", project_name)
        return response

    # update grafana team
    def update_grafana_teams(self, project_new_name, project_old_name):
        team_obj = requests.request(
            "GET",
            self.url + "/api/teams/search?name={}".format(project_old_name),
            headers=self.headers,
        )
        team_id = json.loads(team_obj.text)["teams"][0]["id"]
        data = {
            "name": project_new_name,
        }
        response = requests.request(
            "PUT",
            self.url + "/api/teams/{}".format(team_id),
            json=data,
            headers=self.headers,
        )
        log.info("Grafana team updated %s", response.text)
        return response

    # remove member from grafana team
    def remove_grafana_team_member(self, user_name, project_data):
        # Get user id
        response_id = requests.request(
            "GET",
            self.url + "/api/users/lookup?loginOrEmail={}".format(user_name),
            headers=self.headers,
        )
        user_id = json.loads(response_id.text)["id"]
        for project in project_data:
            # Get team id
            team_obj = requests.request(
                "GET",
                self.url + "/api/teams/search?name={}".format(project["project"]),
                headers=self.headers,
            )
            team_id = json.loads(team_obj.text)["teams"][0]["id"]
            response = requests.request(
                "DELETE",
                self.url + "/api/teams/{}/members/{}".format(team_id, user_id),
                headers=self.headers,
            )
        return response
