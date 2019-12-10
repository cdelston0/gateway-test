#!/usr/bin/env python3

'''This file contains the main program for the Mozilla IoT gateway
command line interface.
'''

from datetime import datetime, timedelta
from gateway.gateway import GatewayConfig, Gateway
# from pprint import pprint
from queue import Queue
from testthing import testThing, testWebThingServer
import argparse
import asyncio
import json
import sys
import threading
import unittest

CONFIG = {
    'gateway': {
        'url': 'http://localhost:8080',
        'user': '',
        'password': '',
    },
    'things': {
        'quantity': 5,
        'port_start': 8800,
    },
}


class GatewayTest(unittest.TestCase):

    @classmethod
    def setUpClass(self, num_things=1):

        self.config = GatewayConfig()
        self.config.set_root('gateways', 'testgateway')
        self.gw = Gateway(CONFIG['gateway']['url'], self.config)
        self.gw.login(CONFIG['gateway']['user'], CONFIG['gateway']['password'])
        self.msgq = Queue()
        self.tws = {}
        self.things = []

        self.loop = loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Callback when ws message is received from the /new_thing socket
        def newthing(thing):
            thingdata = json.loads(thing)
            port = thingdata['id'].split('-')[-1]
            self.things.append(int(port))

        # Tracks
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
        future = self.gw.newThingsWebsocket(newthing)
        result = loop.run_until_complete(future)

        # Start num_things native webthing instances on localhost
        port_end = CONFIG['things']['port_start'] + num_things
        for port in range(CONFIG['things']['port_start'], port_end):
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
        thing = self.tws[CONFIG['things']['port_start']][0]
        response = self.gw.addThing(thing.to_thing_POST_body())
        self.assertTrue(response.status_code in [200, 201])

    def test_1_check_thing_added(self):
        '''Check a webthing has been added'''
        thing = self.tws[CONFIG['things']['port_start']][0]
        self.assertTrue(thing.get_tid() in self.gw.things())

    def test_2_check_thing_property(self):
        '''Retrieve 'on' property for webthing from gateway'''
        thing = self.tws[CONFIG['things']['port_start']][0]
        prop = self.gw.property(thing.get_tid(), 'on')
        self.assertTrue('on' in list(prop.keys()))

    def test_3_thing_property_changed(self):
        '''Set 'on' property of webthing from the webthing'''
        thing = self.tws[CONFIG['things']['port_start']][0]

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
        thing = self.tws[CONFIG['things']['port_start']][0]

        self.gw.property(thing.get_tid(), 'on', { 'on' : False })
        # FIXME: RACE
        self.assertFalse(thing.get_thing().get_property('on'))

        self.gw.property(thing.get_tid(), 'on', { 'on' : True })
        # FIXME: RACE
        self.assertTrue(thing.get_thing().get_property('on'))

    def test_5_reset_thing_property(self):
        '''Set 'on' property of webthing to current value (i.e.: no change) from the gateway'''
        thing = self.tws[CONFIG['things']['port_start']][0]

        prop = self.gw.property(thing.get_tid(), 'on')
        self.assertTrue('on' in list(prop.keys()))

        prop = self.gw.property(thing.get_tid(), 'on', { 'on' : prop['on'] })
        self.assertTrue(prop is not None)

    def test_6_delete_thing(self):
        '''Delete the webthing from the gateway'''
        thing = self.tws[CONFIG['things']['port_start']][0]
        response = self.gw.deleteThing(thing.get_tid())
        self.assertTrue(response.status_code in [200, 204])

    def test_7_check_thing_deleted(self):
        '''Check the webthing is deleted'''
        thing = self.tws[CONFIG['things']['port_start']][0]
        self.assertFalse(thing.get_tid() in self.gw.things())


class MultipleThingProfiling(GatewayTest):

    @classmethod
    def setUpClass(self):
        num_things = CONFIG['things']['quantity']
        super().setUpClass(num_things=num_things)

    def test_0_add_all_webthings(self):
        '''Add all of the webthings, make sure we get a response from the gateway'''
        for port, (tt, tws) in self.tws.items():
            response = self.gw.addThing(tt.to_thing_POST_body())
            self.assertTrue(response.status_code in [200, 201])

    def test_1_strobe_all_webthings(self):
        '''Not a good test - just causes webthings to flip status, no checking or asserts'''
        for i in range(0, 10):

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
            print(msg)

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

    def test_6_webthing_property_change_ws(self):

        wait = False
        num_changes = 10

        print('Sending {} property changes to {} webthings via websocket,{} waiting for gateway response'.format(
            num_changes, len(self.tws), "" if wait else " not"))

        self.changed = {}
        self.count = {}
        for port, (tt, tws) in self.tws.items():
            self.changed[tt.get_tid()] = []
            self.count[tt.get_tid()] = num_changes

        # Spawn thread to listen for messages from webthing property set_value
        msgthread = threading.Thread(target=self.wait_for_instance_property_changes)
        msgthread.start()

        self.msgcount = 0

        def thingWSMsg(msg):
            print('RCV ',msg)
            self.msgcount += 1

        async def all_things(num):
            while self.msgcount != num:
                await asyncio.sleep(1)
            return True

        # Open websocket
        future = self.gw.thingWebsocket(thingWSMsg)
        skt = self.loop.run_until_complete(future)

        # Wait for N messages from WS indicating
        # FIXME: Should wait for 'connected' : 'true' message for each?
        self.loop.run_until_complete(all_things(len(self.count)))

        # Fire off bunch of status changes

        # For each message...
        future = None
        for idx in range(0, num_changes):

            # ...send to each webthing
            for port, (tt, tws) in self.tws.items():

                thingid = tt.get_tid()

                # Record the timestamp the message was submitted to the gateway
                self.changed[thingid].append((idx, 's', datetime.now()))

                # Write index property via websocket
                future = skt.write_message(json.dumps(
                    {
                        "id" : thingid,
                        "messageType": "setProperty",
                        "data": { "idx": idx }
                    })
                )
                self.loop.run_until_complete(future)

        # Wait until last write_message future has completed
        #self.loop.run_until_complete(future)
        #self.loop.run_until_complete(asyncio.sleep(60))
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

    def test_5_webthing_property_change(self):

        self.msgcount = 0

        def thingWSMsg(msg):
            print('RCV ', msg)
            self.msgcount += 1

        async def all_things(num):
            while self.msgcount != num:
                await asyncio.sleep(1)
            return True

        # Open websocket
        future = self.gw.thingWebsocket(thingWSMsg)
        skt = self.loop.run_until_complete(future)

        # Wait for N messages from WS indicating readiness
        # FIXME: Should wait for 'connected' : 'true' message for each?
        self.loop.run_until_complete(all_things(CONFIG['things']['quantity']))

        for port, (tt, tws) in self.tws.items():
            skt.write_message(json.dumps(
                {
                    "id": tt.get_tid(),
                    "messageType": "setProperty",
                    "data": {
                        "idx": 10
                    }
                }))

        self.loop.run_until_complete(asyncio.sleep(60))


def cleanup_all_webthings():

    config = GatewayConfig()
    config.set_root('gateways', 'testgateway')
    gw = Gateway(CONFIG['gateway']['url'], config)
    gw.login(CONFIG['gateway']['user'], CONFIG['gateway']['password'])

    things = gw.things()
    for thing in things:
        gw.deleteThing(thing)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Gateway test client.')
    parser.add_argument('--things-quantity',
                        help='number of things to start',
                        type=int,
                        default=CONFIG['things']['quantity'])
    parser.add_argument('--things-port-start',
                        help='starting port number for things to listen on',
                        type=int,
                        default=CONFIG['things']['port_start'])
    parser.add_argument('--gateway-url',
                        help='URL of gateway',
                        type=str,
                        default=CONFIG['gateway']['url'])
    parser.add_argument('--gateway-user',
                        help='user to log into gateway with',
                        type=str,
                        required=True)
    parser.add_argument('--gateway-password',
                        help='password to log into gateway with',
                        type=str,
                        required=True)
    args, remaining = parser.parse_known_args()

    if args.things_quantity is not None:
        CONFIG['things']['quantity'] = args.things_quantity

    if args.things_port_start is not None:
        CONFIG['things']['port_start'] = args.things_port_start

    if args.gateway_url is not None:
        CONFIG['gateway']['url'] = args.gateway_url

    CONFIG['gateway']['user'] = args.gateway_user
    CONFIG['gateway']['password'] = args.gateway_password

    sys.argv = sys.argv[:1] + remaining
    unittest.main()
