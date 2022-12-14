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

FROM ubuntu:20.04

LABEL authors="Benjamín Díaz"

ENV TZ=Europe/Moscow \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get --yes update \
 && apt-get --yes install git python3 python3-pip libssl-dev libffi-dev mlocate mc vim \
 && python3 -m pip install -U pip

COPY requirements.txt /mon/requirements.txt

COPY requirements-dev.txt /mon/requirements-dev.txt

RUN pip3 install -r /mon/requirements.txt

RUN pip3 install -r /mon/requirements-dev.txt

COPY . /mon

RUN pip3 install /mon

ENV OSMMON_MESSAGE_DRIVER kafka
ENV OSMMON_MESSAGE_HOST kafka
ENV OSMMON_MESSAGE_PORT 9092

ENV OSMMON_DATABASE_DRIVER mongo
ENV OSMMON_DATABASE_URI mongodb://mongo:27017

ENV OSMMON_SQL_DATABASE_URI sqlite:///mon_sqlite.db
ENV OSMMON_GLOBAL_REQUEST_TIMEOUT 10
ENV OSMMON_GLOBAL_LOGLEVEL INFO
ENV OSMMON_VCA_HOST localhost
ENV OSMMON_VCA_SECRET secret
ENV OSMMON_VCA_USER admin
ENV OSMMON_VCA_CACERT cacert
ENV OSMMON_DATABASE_COMMONKEY changeme
ENV OSMMON_COLLECTOR_INTERVAL 30
ENV OSMMON_EVALUATOR_INTERVAL 30
ENV OSMMON_PROMETHEUS_URL http://prometheus:9090
ENV OSMMON_PROMETHEUS_USER admin
ENV OSMMON_PROMETHEUS_PASSWORD admin
ENV OSMMON_GRAFANA_URL http://grafana:3000
ENV OSMMON_GRAFANA_USER admin
ENV OSMMON_GRAFANA_PASSWORD admin

COPY metric.py /usr/local/lib/python3.8/dist-packages/gnocchiclient/v1/metric.py

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=2s --retries=12 \
  CMD osm-mon-healthcheck || exit 1

CMD /bin/bash mon/docker/scripts/start.sh
