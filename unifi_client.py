#!/usr/bin/env python3
#
# unifi_client.py
#
# Copyright (c) 2019 Nick Waterton <nick.waterton@med.ge.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

#need to install websockets-client (pip install websocket-client)
#or aiohttp (pip install aiohttp) - python 3 only!

from __future__ import print_function

import json
import sys
import threading
import queue
from collections import OrderedDict

import logging
from logging.handlers import RotatingFileHandler

__VERSION__ = '1.0.0'

#import other modules here depending on which websocket you want to use. this is dome in the 
#routines below for testing, but normally you would do it here.
'''
import asyncio
import aiohttp

import requests
import websocket
'''

log = logging.getLogger('Main')

class UnifiClient():

    def __init__(self, username, password, host='localhost', port=8443, ssl_verify=False):
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.ssl_verify = ssl_verify
        
        self.url = 'https://' + self.host + ':' + str(port) + '/'
        self.login_url = self.url + 'api/login'
        self.initial_info_url = self.url + 'api/s/default/stat/device'
        self.params = {'_depth': 4, 'test': 0}
        self.ws_url= 'wss://{}:{}/wss/s/default/events'.format(self.host, self.port)
        
        #dictionary for storing unifi data
        self.unifi_data = OrderedDict()
        #keep track of unknown message types
        self.message_types = {}
        
        self.python2 = False
        if sys.version_info[0] < 3:
            self.python2 = True
            
        log.debug('Python: %s' % repr(sys.version_info))
        
        #self.python2 = True    #debugging

        self.sync_q = queue.Queue()
        self.event_q = queue.Queue(10)
        
        if self.python2:
            t = threading.Thread(target=self.connect_websocket)
        else:
            t = threading.Thread(target=self.asyncio_websocket)
            
        t.daemon = True
        t.start()
    
    def asyncio_websocket(self):
        '''
        Python 3 only!
        '''
        import asyncio
        
        loop = asyncio.new_event_loop()
        while True:
            loop.run_until_complete(self.async_websocket())
            time.sleep(30)
            log.warn('Reconnecting websocket')
        
    async def async_websocket(self):
        '''
        By default ClientSession uses strict version of aiohttp.CookieJar. RFC 2109 explicitly forbids cookie accepting from URLs
        with IP address instead of DNS name (e.g. http://127.0.0.1:80/cookie).
        It’s good but sometimes for testing we need to enable support for such cookies. It should be done by passing unsafe=True
        to aiohttp.CookieJar constructor:
        '''
        import asyncio
        import aiohttp
        
        #enable support for unsafe cookies
        jar = aiohttp.CookieJar(unsafe=True)
        
        log.info('login() %s as %s' % (self.url,self.username))

        json_request = {    'username': self.username,
                            'password': self.password,
                            'strict': True
                       }
                       
        try:

            async with aiohttp.ClientSession(cookie_jar=jar) as session:
                async with session.post(
                        self.login_url,json=json_request, ssl=self.ssl_verify) as response:
                        assert response.status == 200
                        json_response = await response.json()
                        log.debug('Received json response to login:')
                        log.debug(json.dumps(json_response, indent=2))

                async with session.get(
                        self.initial_info_url,json=self.params, ssl=self.ssl_verify) as response:
                        assert response.status == 200
                        json_response = await response.json()
                        log.debug('Received json response to initial data:')
                        log.debug(json.dumps(json_response, indent=2))
                        self.update_unifi_data(json_response)

                async with session.ws_connect(self.ws_url, ssl=self.ssl_verify) as ws:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            log.debug('received: %s' % json.dumps(json.loads(msg.data),indent=2))
                            self.update_unifi_data(msg.json(loads=json.loads))
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            log.info('WS closed')
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            log.error('WS closed with Error')
                            break
                            
        except AssertionError as e:
            log.error('failed to connect: %s' % e)
               
        log.info('Exited')
    
    def connect_websocket(self):
        while True:
            self.simple_websocket()
            time.sleep(30)
            log.warn('Reconnecting websocket')

    def simple_websocket(self):
        import requests
        import websocket
        
        log.info('login() %s as %s' % (self.url,self.username))
        
        json_request = {    'username': self.username,
                            'password': self.password,
                            'strict': True
                       }    
        
        if self.ssl_verify is False:
            # Disable insecure warnings - our server doesn't have root certs
            from requests.packages.urllib3.exceptions import InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        
        session = requests.Session()# This session is used to login and obtain a session ID
        session.verify = self.ssl_verify # not really needed as we disable checking in the post anyway
        
        try:
        
            # We Authenticate with one session to get a session ID and other validation cookies
            r = session.post(self.login_url, json=json_request, verify=self.ssl_verify)
            assert r.status_code == 200

            r = session.get(self.initial_info_url, json=self.params, verify=self.ssl_verify)
            assert r.status_code == 200

            data = r.json()
            
            log.debug('received initial data: %s' % json.dumps(data, indent=2))
            self.update_unifi_data(data)
            
            #login successful, get cookies
            cookies = requests.utils.dict_from_cookiejar(session.cookies)
            log.debug('cookies: %s' % cookies)
            #cookies example: {'csrf_token': 'icIkv3tcVjwlJ4TQbgyeCuEZiJGErAUy', 'unifises': 'nutupuMKrLC4eA6CRmS6yWcldWowJRT2'
            csrf_token = cookies['csrf_token']
            SESSIONID = cookies['unifises']
            ws_cookies = "unifises=%s; csrf_token=%s" % (SESSIONID, csrf_token)
            
            #optional debugging on
            if log.getEffectiveLevel() == logging.DEBUG:
                websocket.enableTrace(True)
            import ssl  #so that we can disable checking
            # Disable insecure warnings - our server doesn't have root certs
            if self.ssl_verify:
                ws = websocket.WebSocket()
            else:
                ws = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_NONE})
            ws.connect(   self.ws_url,
                          cookie = ws_cookies
                      )
                      
            while True:
                msg=ws.recv()
                if len(msg) == 0:
                    log.info('WS closed')
                    break
                log.debug('received: %s' % json.dumps(json.loads(msg), indent=2))
                self.update_unifi_data(json.loads(msg))
            log.info('WS disconnected')

        except AssertionError as e:
            log.error("Connection failed error: %s" % e)
               
        log.info('Exited')
            
    def update_unifi_data(self, data):
        '''
        takes data from the websocket, splits device sync updates and events out,
        puts sync events in the output queue
        Uses OrderDict to preserve the order for repeatable output.
        '''
        unifi_data = OrderedDict()
        
        meta = data['meta']
        update_type = meta.get("message", "device:sync")   #"events" or "device:sync"
        if update_type == "device:sync":
            data_list = data['data']
            for update in data_list:
                new_data={update["_id"]:update}
                unifi_data.update(new_data)
                log.info('Updating: %s (%s)' % (update["_id"], unifi_data[update["_id"]].get("name",'Unknown')))
            self.sync_q.put(unifi_data)
        elif update_type == "events":
            if self.event_q.full():
                #discard oldest event
                self.event_q.get()
                self.event_q.task_done()
            self.event_q.put(data['data'])
        elif update_type == "device:update":
            log.info('received update; %s' % json.dumps(data, indent=2))
        else:
            log.warn('Unknown message type: %s, data: %s' % (update_type, json.dumps(data, indent=2)))
            self.message_types.update({update_type:data})
     
        if len(self.message_types) > 0:
            log.warn('unknown message types: %s' % self.message_types.keys())
            
        log.debug('%d events in event queue%s' % (self.event_q.qsize(),'' if not self.event_q.full() else ' event queue is FULL' ))
            
        if log.getEffectiveLevel() == logging.DEBUG:    
            with open('raw_data.json', 'w') as f:
                f.write(json.dumps(unifi_data, indent=2))
            
    def deduplicate_list(self, base_list):
        temp=OrderedDict()
        for d in base_list:
            temp[d['_id']] = d
        return list(temp.values())
        
    def update_list(self, base_list, update_list):
        try:
            #eliminate earlier duplicates
            base_list = self.deduplicate_list(base_list)
            update_list = self.deduplicate_list(update_list)
            for item in update_list:
                for id, device in enumerate(base_list.copy()):
                    if device['_id'] == item['_id']:
                        base_list.remove(device)
                        base_list.insert(id,item)
                        break
                else:
                    base_list.append(item)

            log.debug('number of devices updated: %d' % len(base_list))
        except Exception as e:
            log.error('update_list: ERROR: %s' % e)
        return base_list
        
    def events(self, blocking=False):
        '''
        returns a list of event updates
        if blocking, waits for a new update, then returns it as a list
        if not blocking, returns any updates in the queue, or an empty list if there are none
        '''
        if blocking:
            unifi_events=self.event_q.get()
            self.event_q.task_done()
        else:
            unifi_events = []
            while not self.event_q.empty():
                unifi_events+=self.event_q.get()
                self.event_q.task_done()
        return unifi_events
        
    def devices(self, blocking=True):
        '''
        returns a list of device updates
        if blocking, waits for a new update, then returns it as a list
        if not blocking, returns any updates in the queue, or a list with an empty dict if there are none
        '''
        if blocking:
            unifi_data=self.sync_q.get()
            self.sync_q.task_done()
        else:
            unifi_data = {}
            while not self.sync_q.empty():
                unifi_data.update(self.sync_q.get())
                self.sync_q.task_done()
        devices_list = list(unifi_data.values())
        #update master list
        self.update_list(self.unifi_data, devices_list)
        return devices_list
        
    def get_devices(self, type, blocking=True):
        '''
        updates master list from any data waiting in the queue, and returns any matching 'type'
        '''
        self.devices(blocking)
        for device in self.unifi_data:
            if type in [device['_id'], device['mac'], device['name'], device['ip'], device['type']]:
                return device
        return None
        
    def get_devices_types(self, types, blocking=True):
        '''
        types is a list of types, eg
        ['ugw', 'usw', 'uap']
        updates master list from any data waiting in the queue
        returns a dictionary of devices with the keys of 'type'
        '''
        devices_dict = {}
        devices_list = []

        self.devices(blocking)
        for device in self.unifi_data:
            for type in types:
                if device['type'] == types:
                    devices_list.append(device)
            devices_dict[type] = devices_list
        return devices_dict
        
        
def setup_logger(logger_name, log_file, level=logging.DEBUG, console=False):
    try: 
        l = logging.getLogger(logger_name)
        formatter = logging.Formatter('[%(levelname)1.1s %(asctime)s] (%(threadName)-10s) %(message)s')
        if log_file is not None:
            fileHandler = logging.handlers.RotatingFileHandler(log_file, mode='a', maxBytes=2000000, backupCount=5)
            fileHandler.setFormatter(formatter)
        if console == True:
          streamHandler = logging.StreamHandler()

        l.setLevel(level)
        if log_file is not None:
            l.addHandler(fileHandler)
        if console == True:
          l.addHandler(streamHandler)
             
    except Exception as e:
        print("Error in Logging setup: %s - do you have permission to write the log file??" % e)
        sys.exit(1)
        
def main():
    global log
    import argparse
    parser = argparse.ArgumentParser(description='Unifi MQTT-WS Client and Data')
    parser.add_argument('IP', action="store", default=None, help="IP Address of Unifi Controller. (default: None)")
    parser.add_argument('-po','--unifi_port', action="store", type=int, default=8443, help='unifi port (default=8443)')
    parser.add_argument('username', action="store", default=None, help='Unifi username. (default=None)')
    parser.add_argument('password', action="store", default=None, help='unifi password. (default=None)')
    parser.add_argument('-s','--ssl_verify', action='store_true', help='Verify Certificates (Default: False)', default = False)
    #parser.add_argument('-cid','--client_id', action="store", default=None, help='optional MQTT CLIENT ID (default=None)')
    parser.add_argument('-b','--broker', action="store", default=None, help='mqtt broker to publish sensor data to. (default=None)')
    parser.add_argument('-p','--port', action="store", type=int, default=1883, help='mqtt broker port (default=1883)')
    parser.add_argument('-u','--user', action="store", default=None, help='mqtt broker username. (default=None)')
    parser.add_argument('-pw','--passwd', action="store", default=None, help='mqtt broker password. (default=None)')
    parser.add_argument('-pt','--pub_topic', action="store",default='/unifi_data/', help='topic to publish unifi data to. (default=/unifi_data/)')
    parser.add_argument('-l','--log', action="store",default="None", help='log file. (default=None)')
    parser.add_argument('-D','--debug', action='store_true', help='debug mode', default = False)
    parser.add_argument('-V','--version', action='version',version='%(prog)s {version}'.format(version=__VERSION__))

    
    arg = parser.parse_args()
    
    if arg.debug:
      log_level = logging.DEBUG
    else:
      log_level = logging.INFO
      
    #setup logging
    if arg.log == 'None':
        log_file = None
    else:
        log_file=os.path.expanduser(arg.log)
    setup_logger('Main',log_file,level=log_level,console=True)
    
    log = logging.getLogger('Main')
    
    log.debug('Debug mode')
    
    broker = arg.broker
    
    if broker:
        try:
            import paho.mqtt.client as paho
        except ImportError:
            log.error("paho mqtt client not found")
            broker = None
    
    try:
        if broker:
            port = arg.port
            user = arg.user
            password = arg.passwd
            mqttc = paho.Client()               #Setup MQTT
            if user is not None and password is not None:
                mqttc.username_pw_set(username=user,password=password)
            mqttc.connect(broker, port, 120)
            mqttc.loop_start()
   
    
        client = UnifiClient(arg.username, arg.password, arg.IP, arg.unifi_port, arg.ssl_verify)
    
        while True:
            data = client.devices()
            log.info('got new data')
            if broker:
                mqttc.publish(arg.pub_topic, json.dumps(data))
            log.debug(json.dumps(data, indent=2))
    except KeyboardInterrupt:
        if broker:
            mqttc.loop_stop()
        log.info('Program Exit')

if __name__ == '__main__':
    '''
    <Cntrl-C> to exit
    '''
    main()
