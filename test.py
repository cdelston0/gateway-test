#!/usr/bin/env python3

'''This file contains the main program for the Mozilla IoT gateway
command line interface.
'''

import argparse
import json
import logging
import os
import pathlib
import sys
import unittest
from copy import deepcopy
from testthing import testThing, testWebThingServer
import threading
import time
from pprint import pprint
from datetime import datetime, timedelta
from queue import Queue
import asyncio

from gateway.gateway import GatewayConfig, Gateway

GATEWAY_URL='http://beaglebone.local:8080'
GATEWAY_USER='testuser@email.com'
GATEWAY_PASS='testpass'

NUM_THINGS=50

PORT_START=8800

class GatewayTest(unittest.TestCase):

    @classmethod
    def setUpClass(self, num_things=1):

        self.config = GatewayConfig()
        self.config.set_root('gateways', 'testgateway')
        self.gw = Gateway(GATEWAY_URL, self.config)
        self.gw.login(GATEWAY_USER, GATEWAY_PASS)
        self.msgq = Queue()
        self.tws = {}
        self.things = []

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def newthing(thing):
            thingdata = json.loads(thing)
            port = thingdata['id'].split('-')[-1]
            self.things.append(int(port))

        async def all_things(ports):
            ports = set(ports)
            waiting = len(ports)
            while ports != set(self.things):
                still_waiting = len(ports.difference(set(self.things)))
                if still_waiting != waiting:
                    waiting = still_waiting
                    print('{} Waiting for {} webthings'.format(datetime.now(), waiting))
                await asyncio.sleep(1)
            return True

        # Register websocket on /new_things and wait for connection
        future = self.gw.newThings(newthing)
        result = loop.run_until_complete(future)

        # Start num_things native webthing instances on localhost
        port_end = PORT_START + num_things
        for port in range(PORT_START, port_end):
            tt = testThing(port, msgq=self.msgq)
            tws = testWebThingServer('native webthing on port %s' % port, tt, port)
            tws.start()
            self.tws[port] = (tt, tws)

        # Wait for gateway websocket to indicate that all things are ready
        print('{} Waiting for {} webthings'.format(datetime.now(), len(list(self.tws.keys()))))
        loop.run_until_complete(all_things(list(self.tws.keys())))
        print('{} All webthings added'.format(datetime.now()))

    @classmethod
    def tearDownClass(self):

        # Delete things from gateway, if they're in the list of things we added
        print('Deleting webthings')
        things = self.gw.things()
        for thing in things:
            port = int(thing.split('-')[-1])
            if port in self.tws:
                if thing == self.tws[port][0].get_tid():
                    self.gw.deleteThing(thing)

        # Stop native webthing instances
        print('Stopping webthings')
        for port, (tt, tws) in self.tws.items():
            tws.stop_loop()

        print('Waiting for webthing threads to exit')
        # Wait for native webthing instances to join
        for port, (tt, tws) in self.tws.items():
            tws.join()


class SingleThingProvisioning(GatewayTest):

    @classmethod
    def setUpClass(self):
        super().setUpClass(num_things=1)

    def test_0_add_thing(self):
        '''Add a webthing to the gateway'''
        thing = self.tws[PORT_START][0]
        response = self.gw.addThing(thing.to_thing_POST_body())
        self.assertTrue(response.status_code in [200, 201])

    def test_1_check_thing_added(self):
        '''Check a webthing has been added'''
        thing = self.tws[PORT_START][0]
        self.assertTrue(thing.get_tid() in self.gw.things())

    def test_2_check_thing_property(self):
        '''Retrieve 'on' property for webthing from gateway'''
        thing = self.tws[PORT_START][0]
        prop = self.gw.property(thing.get_tid(), 'on')
        self.assertTrue('on' in list(prop.keys()))

    def test_3_thing_property_changed(self):
        '''Set 'on' property of webthing from the webthing'''
        thing = self.tws[PORT_START][0]

        thing.get_thing().set_property('on', True)
        # FIXME: RACE
        prop = self.gw.property(thing.get_tid(), 'on')
        self.assertTrue(prop['on'])

        thing.get_thing().set_property('on', False)
        # FIXME: RACE
        prop = self.gw.property(thing.get_tid(), 'on')
        self.assertFalse(prop['on'])

    def test_4_change_thing_property(self):
        '''Set 'on' property of webthing from the gateway'''
        thing = self.tws[PORT_START][0]

        self.gw.property(thing.get_tid(), 'on', { 'on' : False })
        # FIXME: RACE
        self.assertFalse(thing.get_thing().get_property('on'))

        self.gw.property(thing.get_tid(), 'on', { 'on' : True })
        # FIXME: RACE
        self.assertTrue(thing.get_thing().get_property('on'))

    def test_5_reset_thing_property(self):
        '''Set 'on' property of webthing to current value (i.e.: no change) from the gateway'''
        thing = self.tws[PORT_START][0]

        prop = self.gw.property(thing.get_tid(), 'on')
        self.assertTrue('on' in list(prop.keys()))

        prop = self.gw.property(thing.get_tid(), 'on', { 'on' : prop['on'] })
        self.assertTrue(prop is not None)

    def test_6_delete_thing(self):
        '''Delete the webthing from the gateway'''
        thing = self.tws[PORT_START][0]
        response = self.gw.deleteThing(thing.get_tid())
        self.assertTrue(response.status_code in [200, 204])

    def test_7_check_thing_deleted(self):
        '''Check the webthing is deleted'''
        thing = self.tws[PORT_START][0]
        self.assertFalse(thing.get_tid() in self.gw.things())
            

class MultipleThingProfiling(GatewayTest):

    @classmethod
    def setUpClass(self):
        super().setUpClass(num_things=NUM_THINGS)

    def test_0_add_all_webthings(self):
        '''Add all of the webthings, make sure we get a response from the gateway'''
        for port, (tt, tws) in self.tws.items():
            response = self.gw.addThing(tt.to_thing_POST_body())
            self.assertTrue(response.status_code in [200, 201])

    def test_1_strobe_all_webthings(self):
        '''Not a good test - just causes webthings to flip status, no checking or asserts'''
        for i in range(0,10):

            for port, (tt, tws) in self.tws.items():
                thing = tt.get_thing()
                thing.set_property('on', True)

            for port, (tt, tws) in self.tws.items():
                thing = tt.get_thing()
                thing.set_property('on', False)

    def wait_for_instance_property_changes(self):
        '''Thread to dequeue property set_value messages back from testThings'''

        # FIXME: Need timeout in case something loses messages

        while sum(list(self.count.values())) != 0:
            msg = self.msgq.get()

            msgparts = msg.split(':')
            thingid = msgparts[0]
            value = int(msgparts[1].split(' ')[-1])

            # Record the timestamp that the message was recieved
            self.changed[thingid].append((value, 'r', datetime.now()))
            self.count[thingid] -= 1

    def gateway_property_change_propagation_time(self, changes=1, wait=True):

        num_changes = changes

        print('Sending {} property changes to {} webthings,{} waiting for gateway response'.format(
            num_changes, len(self.tws), "" if wait else " not"))

        self.changed = {}
        self.count = {}
        for port, (tt, tws) in self.tws.items():
            self.changed[tt.get_tid()] = []
            self.count[tt.get_tid()] = changes

        # Spawn thread to listen for messages from webthing property set_value 
        msgthread = threading.Thread(target=self.wait_for_instance_property_changes)
        msgthread.start()

        # Fire off bunch of status changes

        # For each message...
        for idx in range(0, num_changes):

            # ...send to each webthing
            for port, (tt, tws) in self.tws.items():

                thingid = tt.get_tid()

                # Record the timestamp the message was submitted to the gateway
                self.changed[thingid].append((idx, 's', datetime.now()))

                # Write index property via gateway
                future = self.gw.property(thingid, 'idx', { 'idx' : idx }, futures=wait)
                if wait:
                    future.result()

        msgthread.join()

        intervals = {}
        total = timedelta()
        maximum = timedelta()

        for port, (tt, tws) in self.tws.items():
            thingid = tt.get_tid()
            times = self.changed[thingid]

            # Check sequence of received property changes
            recseq = [ r[0] for r in times if r[1] is 'r' ]
            print(thingid, 'sequence correct:', all(recseq[i] <= recseq[i+1] for i in range(len(recseq)-1)))

            # Calculate propagtion times (time between send to gateway and thing property change)
            times.sort(key=lambda x: x[0])
            intervals[thingid] = [ (r[0], r[2] - s[2]) for s, r in zip(times[::2], times[1::2]) ]
            deltas = [ x[1] for x in intervals[thingid] ]

            # Calculate maximum and total propagation
            newmax = max(deltas)
            if newmax > maximum:
                maximum = newmax
            total += sum(deltas, timedelta(0))

        #pprint(intervals)
        print('Mean propagation time: {}'.format(total/(num_changes * len(self.tws))))
        print('Longest propagation time: {}'.format(maximum))
        #pprint(self.changed)

    def test_3_property_change_wait_for_gateway(self):
        self.gateway_property_change_propagation_time(10, wait=True)

    def test_4_property_change_no_wait_for_gateway(self):
        self.gateway_property_change_propagation_time(10, wait=False)

def cleanup_all_webthings():

    config = GatewayConfig()
    config.set_root('gateways', 'testgateway')
    gw = Gateway(GATEWAY_URL, config)
    gw.login(GATEWAY_USER, GATEWAY_PASS)

    things = gw.things()
    for thing in things:
        gw.deleteThing(thing)

if __name__ == '__main__':
    unittest.main()
