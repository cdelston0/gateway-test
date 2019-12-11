#!/usr/bin/env python3

'''This file contains the main program for the Mozilla IoT gateway
command line interface.
'''

from datetime import datetime, timedelta
from gateway.gateway import GatewayConfig, Gateway
from pprint import pprint
import queue
from testthing import testThing, testWebThingServer
import argparse
import asyncio
import json
import sys
import threading
import unittest
import time

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
        self.msgq = queue.Queue()
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
        skt = loop.run_until_complete(future)

        # FIXME: RACE here - seem to miss first new_thing message?
        time.sleep(1)

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
        self.add_all_webthings(self)

    def add_all_webthings(self):
        '''Add all of the webthings, make sure we get a response from the gateway'''
        for port, (tt, tws) in self.tws.items():
            response = self.gw.addThing(tt.to_thing_POST_body())
            #self.assertTrue(response.status_code in [200, 201])

    #def test_1_strobe_all_webthings(self):
        #'''Not a good test - just causes webthings to flip status, no checking or asserts'''
        #for i in range(0, 10):

            #for port, (tt, tws) in self.tws.items():
                #thing = tt.get_thing()
                #thing.set_property('on', True)

            #for port, (tt, tws) in self.tws.items():
                #thing = tt.get_thing()
                #thing.set_property('on', False)

    def recieve_webthing_messages(self):
        '''Thread to dequeue property set_value messages from testThing instances'''

        while sum(list(self.msgcnt.values())) != 0:
            timeout=60
            try:
                msg = self.msgq.get(timeout=timeout)
                #print(msg)
            except queue.Empty:
                pprint(f'Timed out waiting for messages from testThings after {timeout}s')
                pprint(self.msgcnt)
                pprint(self.msglog)
                break

            msgparts = msg.split(':')
            thingid = msgparts[0]
            value = int(msgparts[1].split(' ')[-1])

            # Record the timestamp that the message was recieved
            self.msglog[thingid].append((value, 'r', datetime.now()))
            self.msgcnt[thingid] -= 1

    def init_webthing_message_data(self, expectedcount):
        '''Initialise variables used to record messages from the testThing instances'''
        self.msglog = {}
        self.msgcnt = {}
        for port, (tt, tws) in self.tws.items():
            self.msglog[tt.get_tid()] = []
            self.msgcnt[tt.get_tid()] = expectedcount

    def property_change_via_POST(self, thingid, prop, value, wait):
        '''Change a webthing property via POST to the gateway'''
        future = self.gw.property(thingid, prop, { prop : value }, futures=wait)
        if wait:
            future.result()

    def calculate_webthing_property_change_times(self, changes):
        '''Postprocess time differences between messages sent and recieved'''
        intervals = {}
        total = timedelta()
        maximum = timedelta()

        for port, (tt, tws) in self.tws.items():
            thingid = tt.get_tid()
            times = self.msglog[thingid]

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
        print('Mean propagation time: {}'.format(total/(changes * len(self.tws))))
        print('Longest propagation time: {}'.format(maximum))
        #pprint(self.msglog)

    def gateway_send_property_changes_to_webthings(self, changes, changefn, wait=True):
        '''Send property change messages to webthings'''
        self.init_webthing_message_data(changes)

        print('Sending {} property changes to {} webthings,{} waiting for gateway response'.format(
            changes, len(self.tws), "" if wait else " not"))

        # Spawn thread to listen for messages from webthing property set_value
        msgthread = threading.Thread(target=self.recieve_webthing_messages)
        msgthread.start()

        # FIXME: RACE? We seem to lose first property change(s) if we start sending too soon 
        time.sleep(1)

        # For each property change...
        for idx in range(0, changes):

            # ...and each webthing...
            for port, (tt, tws) in self.tws.items():

                thingid = tt.get_tid()
                self.msglog[thingid].append((idx, 's', datetime.now()))

                # ...send a property change to the thing
                changefn(thingid, 'idx', idx, wait)

        # Wait for thread to finish recieving property change messages
        msgthread.join()

        # FIXME: Handle message counts being lower than expected (timeout)


    def test_1_property_change_via_POST_wait_for_gateway(self):
        changes=10
        self.gateway_send_property_changes_to_webthings(changes, changefn=self.property_change_via_POST, wait=True)
        self.calculate_webthing_property_change_times(changes)

    def test_2_property_change_via_POST_no_wait_for_gateway(self):
        changes=10
        self.gateway_send_property_changes_to_webthings(changes, changefn=self.property_change_via_POST, wait=False)
        self.calculate_webthing_property_change_times(changes)

    def init_thing_WS(self):

        def thingWSMsg(msg):
            pass
            #thingdata = json.loads(msg)
            #print('RCV ', msg)

        future = self.gw.thingWebsocket(thingWSMsg)
        return self.loop.run_until_complete(future)

        # FIXME: do we need to wait for <some_ready_condition> before starting to change properties?
        #time.sleep(1)

    def property_change_via_WS(self, thingid, prop, value, wait):
        future = self.skt.write_message(json.dumps(
            {
                "id" : thingid,
                "messageType": "setProperty",
                "data": { prop: value }
            })
        )
        self.loop.run_until_complete(future)

    def test_3_property_change_via_WS_wait_for_gateway(self):
        changes=10
        self.skt = self.init_thing_WS()
        self.gateway_send_property_changes_to_webthings(changes, changefn=self.property_change_via_WS, wait=True)
        self.calculate_webthing_property_change_times(changes)

    def test_4_property_change_via_WS_no_wait_for_gateway(self):
        changes=10
        self.skt = self.init_thing_WS()
        self.gateway_send_property_changes_to_webthings(changes, changefn=self.property_change_via_WS, wait=False)
        self.calculate_webthing_property_change_times(changes)

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
