#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

from data import LinkState, MessageHELLO
from dispatch import LOG_INFO

class NeighborEngine(object):
    """
    This module is responsible for maintaining this router's link-state.  It runs the HELLO protocol
    with the router's neighbors and notifies outbound when the list of neighbors-in-good-standing (the
    link-state) changes.
    """
    def __init__(self, container):
        self.container = container
        self.id = self.container.id
        self.area = self.container.area
        self.last_hello_time = 0.0
        self.hello_interval = container.config.helloInterval
        self.hello_max_age = container.config.helloMaxAge
        self.hellos = {}
        self.link_state_changed = False
        self.link_state = LinkState(None, self.id, self.area, 0, [])


    def tick(self, now):
        self._expire_hellos(now)

        if now - self.last_hello_time >= self.hello_interval:
            self.last_hello_time = now
            self.container.send('amqp:/_local/qdhello', 
                                MessageHELLO(None, self.id, self.area, self.hellos.keys(), self.container.instance))

        if self.link_state_changed:
            self.link_state_changed = False
            self.link_state.bump_sequence()
            self.container.local_link_state_changed(self.link_state)


    def handle_hello(self, msg, now, link_id):
        if msg.id == self.id:
            return
        self.hellos[msg.id] = now
        if msg.is_seen(self.id):
            if self.link_state.add_peer(msg.id):
                self.link_state_changed = True
                self.container.new_neighbor(msg.id, link_id, msg.instance)
                self.container.log(LOG_INFO, "New neighbor established: %s on link: %d" % (msg.id, link_id))

    def linkLost(self, link_id):
        node_id = self.container.node_tracker.link_id_to_node_id(link_id)
        if node_id:
            self._delete_neighbor(node_id)

    def _delete_neighbor(self, key):
        self.hellos.pop(key)
        if self.link_state.del_peer(key):
            self.link_state_changed = True
            self.container.lost_neighbor(key)
            self.container.log(LOG_INFO, "Neighbor lost: %s" % key)

    def _expire_hellos(self, now):
        to_delete = []
        for key, last_seen in self.hellos.items():
            if now - last_seen > self.hello_max_age:
                to_delete.append(key)
        for key in to_delete:
            self._delete_neighbor(key)
