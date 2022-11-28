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
import argparse
import logging
import sys

from osm_mon.core.config import Config
from osm_mon.evaluator.evaluator import Evaluator
from osm_mon.cmd.mon_utils import wait_till_core_services_are_ready


def main():
    parser = argparse.ArgumentParser(prog="osm-mon-evaluator")
    parser.add_argument("--config-file", nargs="?", help="MON configuration file")
    args = parser.parse_args()
    cfg = Config(args.config_file)

    root = logging.getLogger()
    root.setLevel(logging.getLevelName(cfg.get("global", "loglevel")))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.getLevelName(cfg.get("global", "loglevel")))
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", "%m/%d/%Y %I:%M:%S %p"
    )
    ch.setFormatter(formatter)
    root.addHandler(ch)

    log = logging.getLogger(__name__)
    if wait_till_core_services_are_ready(cfg, "osm-mon-evaluator"):
        log.info("Starting MON Evaluator...")
        log.debug("Config: %s", cfg.conf)
        log.info("Initializing database...")
        try:
            evaluator = Evaluator(cfg)
            evaluator.evaluate_forever()
        except Exception as e:
            log.error("Failed to start MON Evaluator")
            log.exception("Exception: %s", str(e))
    else:
        log.error("Failed to start MON Evaluator")


if __name__ == "__main__":
    main()
