# Copyright 2017 Intel Research and Development Ireland Limited
# *************************************************************

# This file is part of OSM Monitoring module
# All Rights Reserved to Intel Corporation

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
# contact: prithiv.mohan@intel.com or adrian.hoban@intel.com

from setuptools import setup

_name = "osm_mon"
_version_command = ("git describe --match v* --tags --long --dirty", "pep440-git-full")
_description = "OSM Monitoring Module"
_author = "OSM Support"
_author_email = "osmsupport@etsi.org"
_maintainer = "OSM Support"
_maintainer_email = "osmsupport@etsi.org"
_license = "Apache 2.0"
_url = "https://osm.etsi.org/gitweb/?p=osm/MON.git;a=tree"

setup(
    name=_name,
    version_command=_version_command,
    description=_description,
    long_description=open("README.rst", encoding="utf-8").read(),
    author=_author,
    author_email=_author_email,
    maintainer=_maintainer,
    maintainer_email=_maintainer_email,
    url=_url,
    license=_license,
    packages=[_name],
    package_dir={_name: _name},
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "osm-mon-server = osm_mon.cmd.mon_server:main",
            "osm-mon-evaluator = osm_mon.cmd.mon_evaluator:main",
            "osm-mon-collector = osm_mon.cmd.mon_collector:main",
            "osm-mon-dashboarder = osm_mon.cmd.mon_dashboarder:main",
            "osm-mon-healthcheck = osm_mon.cmd.mon_healthcheck:main",
        ]
    },
    setup_requires=["setuptools-version-command"],
)
