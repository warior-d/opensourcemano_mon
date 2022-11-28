# -*- coding: utf-8 -*-

# This file is part of OSM Monitoring module

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at

#         http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import pymongo
import time
import socket
import logging
import kafka


def wait_till_commondb_is_ready(config, process_name="osm-mon", commondb_wait_time=5):

    logging.debug("wait_till_commondb_is_ready")

    while True:
        commondb_url = config.conf["database"].get("uri")
        try:
            commondb = pymongo.MongoClient(commondb_url)
            commondb.server_info()
            break
        except Exception:
            logging.info(
                "{} process is waiting for commondb to come up...".format(process_name)
            )
            time.sleep(commondb_wait_time)


def wait_till_kafka_is_ready(config, process_name="osm-mon", kafka_wait_time=5):

    logging.debug("wait_till_kafka_is_ready")

    while True:
        kafka_ready = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                # Verify is kafka port is up
                if (
                    s.connect_ex(
                        (
                            config.conf.get("message", {}).get("host", "kafka"),
                            int(config.conf["message"].get("port")),
                        )
                    )
                    == 0
                ):
                    # Get the list of topics. If kafka is not ready exception will be thrown.
                    consumer = kafka.KafkaConsumer(
                        group_id=config.conf["message"].get("group_id"),
                        bootstrap_servers=[
                            config.conf.get("message", {}).get("host", "kafka")
                            + ":"
                            + config.conf["message"].get("port")
                        ],
                    )
                    all_topics = consumer.topics()
                    logging.debug("Number of topics found: %s", len(all_topics))

                    # Send dummy message in kafka topics. If kafka is not ready exception will be thrown.
                    producer = kafka.KafkaProducer(
                        bootstrap_servers=[
                            config.conf.get("message", {}).get("host", "kafka")
                            + ":"
                            + config.conf["message"].get("port")
                        ]
                    )
                    mon_topics = ["alarm_request", "users", "project"]
                    for mon_topic in mon_topics:
                        producer.send(mon_topic, key=b"echo", value=b"dummy message")

                    # Kafka is ready now
                    kafka_ready = True
        except Exception as e:
            logging.info("Error when trying to get kafka status.")
            logging.debug("Exception when trying to get kafka status: %s", str(e))
        finally:
            if kafka_ready:
                break
            else:
                logging.info(
                    "{} process is waiting for kafka to come up...".format(process_name)
                )
                time.sleep(kafka_wait_time)


def wait_till_core_services_are_ready(
    config, process_name="osm-mon", commondb_wait_time=5, kafka_wait_time=5
):

    logging.debug("wait_till_core_services_are_ready")

    if not config:
        logging.info("Config information is not available")
        return False

    # Check if common-db is ready
    wait_till_commondb_is_ready(config, process_name, commondb_wait_time)

    # Check if kafka is ready
    wait_till_kafka_is_ready(config, process_name, kafka_wait_time)

    return True
