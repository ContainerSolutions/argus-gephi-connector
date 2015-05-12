#!/usr/bin/env python
import time
from threading import Thread, Condition, RLock, Timer
import pygephi
import sys
import json
import pprint
import socket
import mock
from ipwhois import IPWhois
import operator
from cachetools import LRUCache, cachedmethod


def synchronized(method):
    # from http://stackoverflow.com/a/4625483/1314907
    def new_method(self, *arg, **kws):
        with self.lock:
            return method(self, *arg, **kws)
    return new_method


class MyGephiClient(pygephi.GephiClient):
    # needed because pygephi.GephiClient misses "change edge" command

    def change_edge(self, id, flush=True, **attributes):
        self.data += json.dumps(self.peh({"ce": {id: attributes}})) + '\r\n'
        if(self.autoflush):
            self.flush()


class NetworkGraphModel:

    class WhoisProvider(Thread):

        cache = LRUCache(maxsize=150)
        lock = RLock()
        queue = []  # TODO limit the size by condition
        daemon = True

        def __init__(self, producer):
            self.producer = producer
            super(NetworkGraphModel.WhoisProvider, self).__init__()

        @synchronized
        def process(self, ipAddress):
            self.queue.append(ipAddress)

        @cachedmethod(operator.attrgetter('cache'))
        def _getWhoisData(self, ipAddress):
            result = {}
            try:
                data = IPWhois(ipAddress).lookup()
                if 'nets' in data and data['nets']:
                    result = data['nets'][0]
            except Exception as ex:
                if "Private-Use Networks" in str(ex):
                    pass
            return result

        def run(self):
            while True:
                with self.lock:
                    if self.queue:
                        ipAddress = self.queue.pop(0)
                    else:
                        time.sleep(1)
                        continue

                if self.producer.nodeExists(ipAddress):
                    try:
                        data = self._getWhoisData(ipAddress)
                        if len(data):
                            self.producer.changeNode(ipAddress, **data)
                    except Exception as ex:
                        print ex
                        with self.lock:
                            self.queue.append(ipAddress)  # return to queue
                        time.sleep(1)
                        pass
                time.sleep(.2)

    lock = RLock()
    nodeCounter = 0
    edgeCounter = 0
    nodes = {}
    edges = {}
    dnsCache = LRUCache(maxsize=150)

    def __init__(self, gephiAPI, maxAgeInSec):
        self.gephiAPI = gephiAPI
        self.maxAgeInSec = maxAgeInSec
        self.whoisProvider = NetworkGraphModel.WhoisProvider(self)

    @cachedmethod(operator.attrgetter('dnsCache'))
    def _getHostname(self, ipAddress):
        host, alias, addresslist = socket.gethostbyaddr(ipAddress)
        return host

    @synchronized
    def clear(self):
        self.gephiAPI.clean()

    @synchronized
    def changeNode(self, ipAddress, **node_attributes):
        print "updating node for", ipAddress
        if self.nodeExists(ipAddress):
            self.gephiAPI.change_node(
                str(self.nodes[ipAddress]["id"]), **node_attributes)

    @synchronized
    def nodeExists(self, ipAddress):
        return ipAddress in self.nodes

    @synchronized
    def addNode(self, ipAddress):
        if ipAddress not in self.nodes:
            print "adding node", ipAddress
            try:
                label = self._getHostname(ipAddress)
            except:
                label = ipAddress

            node_attributes = {
                "ip": ipAddress,
                "label": label,
                "size": 10,
                'r': 1.0,
                'g': 0.0,
                'b': 0.0,
                'x': 1}

            self.gephiAPI.add_node(str(self.nodeCounter), **node_attributes)
            self.whoisProvider.process(ipAddress)
            self.nodes[ipAddress] = {
                "counter": 0,
                "unique": 0,
                "id": self.nodeCounter}
            self.nodeCounter += 1

        return self.nodes[ipAddress]["id"]

    @synchronized
    def delNode(self, ipAddress):
        self.gephiAPI.delete_node(str(self.addNode(ipAddress)))
        del self.nodes[ipAddress]

    @synchronized
    def addEdge(
            self,
            fromIpAddress,
            toIpAddress,
            fromPort,
            toPort,
            weight=0,
            **edge_attributes):
        pair = fromIpAddress + "-" + toIpAddress
        reversePair = toIpAddress + "-" + fromIpAddress
        pairPort = fromPort + "-" + toPort
        if pair not in self.edges:
            self.edges[pair] = {}
        edge_attributes['Weight'] = weight
        if pairPort not in self.edges[pair]:
            print "adding edge", pair
            self.gephiAPI.add_edge(str(self.edgeCounter),
                                   str(self.addNode(fromIpAddress)),
                                   str(self.addNode(toIpAddress)),
                                   False,
                                   **edge_attributes)
            if len(self.edges[pair]) == 0 and reversePair not in self.edges:
                self.incUniqueCounter(fromIpAddress)
                self.incUniqueCounter(toIpAddress)
            self.incCounter(fromIpAddress)
            self.incCounter(toIpAddress)
            self.edges[pair][pairPort] = {
                'id': self.edgeCounter,
                'from': fromIpAddress,
                'to': toIpAddress,
                'fromPort': fromPort,
                "toPort": toPort}
            self.edgeCounter += 1
            self.edges[pair][pairPort]['lastSeen'] = time.time()
        else:
            if weight > 0:
                print "changing edge", pair
                self.gephiAPI.change_edge(
                    str(self.edges[pair][pairPort]['id']), True, **edge_attributes)
                self.edges[pair][pairPort]['lastSeen'] = time.time()
        return self.edges[pair][pairPort]['id']

    @synchronized
    def decCounter(self, ipAddress):
        self.nodes[ipAddress]["counter"] -= 1
        if self.nodes[ipAddress]["counter"] == 0:
            print "deleting node", ipAddress
            self.delNode(ipAddress)

    @synchronized
    def incCounter(self, ipAddress):
        self.nodes[ipAddress]["counter"] += 1

    @synchronized
    def decUniqueCounter(self, ipAddress):
        if ipAddress in self.nodes:
            self.nodes[ipAddress]["unique"] -= 1
            self.updateSize(ipAddress)

    @synchronized
    def incUniqueCounter(self, ipAddress):
        self.nodes[ipAddress]["unique"] += 1
        self.updateSize(ipAddress)

    @synchronized
    def updateSize(self, ipAddress):
        print ipAddress, ":", self.nodes[ipAddress]["unique"]
        data = {"size": 8 + self.nodes[ipAddress]["unique"]}
        self.changeNode(ipAddress, **data)

    def startJobs(self):
        self.whoisProvider.start()
        self.installCleanupJob(self.maxAgeInSec)

    @synchronized
    def installCleanupJob(self, maxAgeInSec):
        try:
            print "cleanupJob called"
            for pair in self.edges.keys():
                # print "checking if {0} was seen last {1} secs".format(pair,
                # maxAgeInSec)
                for pairPort in self.edges[pair].keys():
                    if time.time() - \
                            self.edges[pair][pairPort]['lastSeen'] > maxAgeInSec:
                        self.delEdge(
                            self.edges[pair][pairPort]['from'],
                            self.edges[pair][pairPort]['to'],
                            self.edges[pair][pairPort]['fromPort'],
                            self.edges[pair][pairPort]['toPort'])
        finally:
            Timer(
                5, NetworkGraphModel.installCleanupJob, [
                    self, maxAgeInSec]).start()

    @synchronized
    def delEdge(self, fromIpAddress, toIpAddress, fromPort, toPort):
        self.gephiAPI.delete_edge(
            str(self.addEdge(fromIpAddress, toIpAddress, fromPort, toPort)))
        pair = fromIpAddress + "-" + toIpAddress
        reversePair = toIpAddress + "-" + fromIpAddress
        print "deleting edge", pair
        self.decCounter(fromIpAddress)
        self.decCounter(toIpAddress)
        pairPort = fromPort + "-" + toPort
        del self.edges[pair][pairPort]
        if len(self.edges[pair]) == 0:
            del self.edges[pair]
            if reversePair not in self.edges:
                self.decUniqueCounter(fromIpAddress)
                self.decUniqueCounter(toIpAddress)

noop = False
model = NetworkGraphModel(mock.Mock() if noop else MyGephiClient(
    'http://localhost:8080/workspace0',
    autoflush=True),
    60)
model.clear()
model.startJobs()
firstLine = True
keys = ()

while True:
    line = sys.stdin.readline().rstrip()
    if firstLine:
        keys = line.split('\t')
        firstLine = False
        continue
    else:
        print "processing new input line"
        values = dict(zip(keys, line.split('\t')))
    if values['State'] == 'CLO':
        model.delEdge(
            values['SrcAddr'],
            values['DstAddr'],
            values['Sport'],
            values['Dport'])
    else:
        attrs = {'proto': values['Proto']}
        if values['Proto'] == 'udp': # a hack to reduce number of edges, otherewise gephi had problems
            values['Sport'] = 'port'
            values['Dport'] = 'port'
        model.addEdge(
            values['SrcAddr'],
            values['DstAddr'],
            values['Sport'],
            values['Dport'],
            values['TotPkts'],
            **attrs)
