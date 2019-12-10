from __future__ import division
from webthing import (Action, Event, Property, SingleThing, Thing, Value,
                      WebThingServer)
import logging
import time
import uuid
from datetime import datetime
import socket
from pprint import pprint
import ctypes
import threading
import asyncio
import time
from queue import Queue

class myProperty(Property):

    def __init__(self, thing, name, value, metadata=None, msgq=None, msgprefix=None):
        super().__init__(thing, name, value, metadata)
        self.msgq = msgq
        self.msgprefix = msgprefix

    def set_value(self, value):
        if self.msgq is not None:
            self.msgq.put('%s: %s %s %s' % (self.msgprefix, self.href, self.name, value))
        return super().set_value(value)

    def get_value(self):
        ret = super().get_value()
        return ret

class testThing():

    def __init__(self, port, propertyclass=myProperty, msgq=None):
        self.port = port
        self.hostname = '%s.local' % socket.gethostname()
        self.tid = 'http---%s-%s' % (self.hostname, self.port)
        self.thing = Thing(
            'urn:dev:ops:my-testthing-%s' % port,
            'a testThing on port %s' % port,
            ['testThing'],
            'A native webthing for testing'
        )
        self.msgq = msgq

        self.thing.add_property(
            propertyclass(self.thing,
                          'on',
                          Value(True),
                          metadata={
                              '@type': 'OnOffProperty',
                              'title': 'On/Off',
                              'type': 'boolean',
                              'description': 'A boolean property of the thing',
                          },
                          msgq=msgq, msgprefix=self.tid))

        self.thing.add_property(
            propertyclass(self.thing,
                          'idx',
                          Value(0),
                          metadata={
                              '@type': 'IndexProperty',
                              'title': 'Index',
                              'type': 'integer',
                              'description': 'A numerical index of the thing',
                              'minimum': 0,
                              'maximum': 1000,
                              'unit': 'bar',
                          },
                          msgq=msgq, msgprefix=self.tid))

    def to_thing_POST_body(self):

        properties = {}
        for prop in self.thing.properties:
            properties[prop] = self.thing.properties[prop].get_metadata()
            properties[prop]['links'] = [{'rel': 'property', 'href': '/properties/%s' % prop, 'proxy': True}]

        json = {
            'id' : self.tid,
            'title' : 'testThing on %s:%s' % (self.hostname, self.port),
            '@context' : self.thing.context,
            '@type' : self.thing.type,
            'properties' : properties,
            'links' : [],
            'baseHref' : 'http://%s:%s' % (self.hostname, self.port),
            'pin': {'required': False, 'pattern': 0},
            'credentialsRequired': False,
            'description': self.thing.description,
            'actions': {},
            'events': {},
            'selectedCapability': 'Light',
            }

        return json

    def get_thing(self):
        return self.thing

    def get_tid(self):
        return self.tid

import tornado
from tornado.platform.asyncio import AnyThreadEventLoopPolicy
asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())

class testWebThingServer(threading.Thread):

    def __init__(self, name, thing, port):
        threading.Thread.__init__(self)
        self.name = name
        self.thing = thing
        self.port = port

    def run(self):
        self.ioloop = tornado.ioloop.IOLoop.instance()
        self.server = WebThingServer(SingleThing(self.thing.get_thing()), port=self.port)
        self.server.start()

    def stop_loop(self):
        self.ioloop.add_callback(self.ioloop.stop)
        self.server.stop()

if __name__ == '__main__':
    port=8800
    logging.basicConfig(
        level=20,
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s %(message)s"
    )
    thing = testThing(port, propertyclass=myProperty)

    print('Starting webthing server')
    ws = testWebThingServer('name', thing, port)
    ws.start()

    try:
        ws.join()
    except KeyboardInterrupt:
        print ('Stopping webthing server')
        ws.stop_loop()
        print ('Stopped webthing server')


