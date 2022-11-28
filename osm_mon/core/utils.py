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
# contact: fbravo@whitestack.com or agarcia@whitestack.com
##


def find_in_list(the_list, condition_lambda):
    for item in the_list:
        if condition_lambda(item):
            return item
    else:
        return None


def create_filter_from_nsr(the_nsr):
    p_filter = {}

    if "projects_read" in the_nsr["_admin"]:
        p_filter["_admin.projects_read.cont"] = the_nsr["_admin"]["projects_read"]
    if "projects_write" in the_nsr["_admin"]:
        p_filter["_admin.projects_write.cont"] = the_nsr["_admin"]["projects_write"]

    return p_filter
