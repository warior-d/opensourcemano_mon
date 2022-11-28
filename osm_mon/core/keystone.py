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
# contact: fbravo@whitestack.com
##

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client


class KeystoneConnection:
    """
    Object representing a connection with keystone, it's main use is to collect
    projects and users from the OSM platform stored in keystone instead MongoDB
    """

    def __init__(self, config):
        self.auth_url = config.get("keystone", "url")
        self.username = config.get("keystone", "service_user")
        self.project_name = config.get("keystone", "service_project")
        self.project_domain_name_list = config.get(
            "keystone", "service_project_domain_name"
        ).split(",")
        self.password = config.get("keystone", "service_password")
        self.user_domain_name_list = config.get("keystone", "domain_name").split(",")

        self.auth = v3.Password(
            auth_url=self.auth_url,
            user_domain_name=self.user_domain_name_list[0],
            username=self.username,
            password=self.password,
            project_domain_name=self.project_domain_name_list[0],
            project_name=self.project_name,
        )

        self.keystone_session = session.Session(auth=self.auth)
        self.keystone_client = client.Client(
            session=self.keystone_session, endpoint_override=self.auth_url
        )

    def getProjects(self):
        """
        Grabs projects from keystone using the client and session build in the constructor
        """
        return self.keystone_client.projects.list()

    def getProjectsById(self, user_id):
        """
        Grabs projects filtered by user ID from keystone using the client and session build in the constructor
        """
        return self.keystone_client.projects.list(user=user_id)

    def getUsers(self):
        """
        Grabs users from keystone using the client and session build in the constructor
        """
        domain_list = self.keystone_client.domains.list()
        users = []
        for domain in domain_list:
            users.extend(self.keystone_client.users.list(domain=domain.id))
        return users

    def getUserById(self, user_id):
        """
        Grabs user object from keystone using user id
        """
        return self.keystone_client.users.get(user_id)

    def getRoleById(self, role_id):
        """
        Grabs role object from keystone using id
        """
        return self.keystone_client.roles.get(role_id)

    def getRoleByName(self, role):
        """
        Grabs role object from keystone using name
        """
        return self.keystone_client.roles.list(name=role)

    def getProjectsByProjectId(self, project_id):
        """
        Grabs projects object from keystone using id
        """
        return self.keystone_client.projects.get(project_id)

    def getProjectsByProjectName(self, project):
        """
        Grabs projects object from keystone name
        """
        return self.keystone_client.projects.list(name=project)
