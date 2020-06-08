#!/usr/bin/env python3
#
# unifi_client.py
#
# Copyright (c) 2019,2020 Nick Waterton <nick.waterton@med.ge.com>
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

# N Waterton 10th September 2019 V1.1.2: added "sta:sync" message type found in controller 5.11.39
# N Waterton 13th February  2020 V 1.1.3: added basic support for UDM Pro
# N Waterton 15th February  2020 V 1.1.4: added enhanced support for UDM Pro
# N Waterton 21st February  2020 V 1.1.5: added api call feature
# N Waterton 4th  June      2020 V 1.1.6: reduced logging from device:update and sta:sync messages (now debug only)     

'''
Not all of these work, but good starting point...
apps: "/api/apps",
system: "/api/system",
firmwareUpdate: "/api/firmware/update",
firmwareSchedule: "/api/firmware/schedule",
device: {
    general: "/api/device/general"
},
controller: "/api/controllers",
status: "/status",
login: "/auth/login",
logout: "/auth/logout",
rebootDevice: "/api/system/reboot",
powerOff: "/api/system/poweroff",
factoryReset: "/api/system/reset",
eraseAndFormat: "/api/storage/eraseAndFormat",
sshEnable: "/api/system/ssh/enable",
sshPassword: "/api/system/ssh/setpassword",
location: "/api/system/location",
timezone: "/api/system/timezone",
systemWS: "/api/ws/system",
downloadSupportFile: "/api/support/generate"
'''

from __future__ import print_function

import json
import sys
import time
import threading
import requests
try:
    from queue import Queue
except ImportError:
    from Queue import Queue
from collections import OrderedDict

import logging
from logging.handlers import RotatingFileHandler

__VERSION__ = '1.1.6'

log = logging.getLogger('Main')

class UnifiClient(object):

    def __init__(self, username, password, host='localhost', port=8443, ssl_verify=False, q=None, timeout=10.0, unifi_os=None):
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.ssl_verify = ssl_verify
        self.timeout = timeout
        self.unifi_os = unifi_os
        self.client = None
        self.session = None
        
        if self.unifi_os is None:
            self.unifi_os = self.is_unifi_os()
        
        if unifi_os:
            # do not use port for unifi os based devices (UDM)
            self.url = 'https://{}/proxy/network/'.format(self.host)
            self.ws_url= 'wss://{}/proxy/network/wss/s/default/events'.format(self.host)
            self.login_url = 'https://{}/api/auth/login'.format(self.host)
        else:
            self.url = 'https://{}:{}/'.format(self.host, self.port)
            self.ws_url= 'wss://{}:{}/wss/s/default/events'.format(self.host, self.port)
            self.login_url = self.url + 'api/login'
        self.base_url = 'https://{}:{}/'.format(self.host, self.port)
        self.initial_info_url = self.url + 'api/s/default/stat/device'
        self.params = {'_depth': 4, 'test': 0}
        
        
        #dictionary for storing unifi data
        self.unifi_data = OrderedDict()
        #keep track of unknown message types
        self.message_types = {}
        #keep track of mac to id's, if id missing
        self.mac_id = {}

        #pass queues to child classes
        if q is None:
            self.sync_q = Queue()
            self.event_q = Queue(10)
            self.queues = [self.sync_q, self.event_q]
        else:
            self.sync_q = q[0]
            self.event_q = q[1]  
            
        log.debug('Python: %s' % repr(sys.version_info))
        
        self.connect_websocket()
        
    def is_unifi_os(self):
        '''
        check for Unifi OS controller eg UDM, UDM Pro.
        HEAD request will return 200 id Unifi OS,
        if this is a Standard controller, we will get 302 (redirect) to /manage
        '''
        if self.ssl_verify is False:
            # Disable insecure warnings - our server doesn't have root certs
            from requests.packages.urllib3.exceptions import InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    
        r = requests.head('https://{}:{}'.format(self.host, self.port), verify=self.ssl_verify, timeout=self.timeout)
        if r.status_code == 200:
            log.info('Unifi OS controller detected')
            return True
        if r.status_code == 302:
            log.info('Unifi Standard controller detected')
            return False
        log.warning('Unable to determine controller type - using Unifi Standard controller')
        return False
        
    def api(self, command):
        if self.client is None:
            log.error('no client connected')
        else:
            try:
                return self.client.api(command)
            except Exception as e:
                log.error('Error in API call: %s' % e)
            
        return None
        
    def connect_websocket(self):
        '''
        connect python 2 or 3 websocket
        Would need to be fixed for python 4.x...
        '''
        if sys.version_info[0] == 3 and sys.version_info[1] > 3:
            from unifi_client_3 import UnifiClient3 #has to be in separate module to prevent python2 syntax errors
            self.client = UnifiClient3(self.username,self.password,self.host,self.port,self.ssl_verify,self.queues,self.timeout,self.unifi_os)
        else:
            self.client = UnifiClient2(self.username,self.password,self.host,self.port,self.ssl_verify,self.queues,self.timeout,self.unifi_os)
        
    def update_unifi_data(self, data):
        '''
        takes data from the websocket, splits device sync updates and events out,
        puts sync events in the output queue
        Uses OrderDict to preserve the order for repeatable output.
        '''
        unifi_data = OrderedDict()
        
        meta = data['meta']
        update_type = meta.get("message", "device:sync")   #"events", "device:sync", "device:update", "speed-test:update", "user:sync", "sta:sync", possibly others
        data_list = data['data']
        
        if update_type == "device:sync":
            for update in data_list:
                new_data={update["_id"]:update}
                unifi_data.update(new_data)
                log.info('Updating: %s (%s)' % (update["_id"], unifi_data[update["_id"]].get("name",'Unknown')))
                #log.info('data: %s' % json.dumps(unifi_data, indent=2))
            self.sync_q.put(unifi_data)
            
        elif update_type == "events":
            if self.event_q.full():
                #discard oldest event
                self.event_q.get()
                self.event_q.task_done()
            self.event_q.put(data['data'])
            
        elif update_type == "device:update":
            log.debug('received device:update: message')
            log.debug('received update: %s' % json.dumps(data, indent=2))
            #do something with updates here
            #note now receive temperature readings from udmp here (but also in device:sync, so ignore here).
        elif update_type == "user:sync":
            log.info('received user:sync: message')
            log.debug('received sync: %s' % json.dumps(data, indent=2))
            #do something with user syncs here
        elif update_type == "speed-test:update":
            log.debug('received speedtest: %s' % json.dumps(data, indent=2))
            #do something with speed tests here
        elif update_type == "sta:sync":
            log.debug('received sta:sync: message')
            log.debug('\n: %s' % json.dumps(data, indent=2))
            #do something with station sync here
            
        else:
            log.warn('Unknown message type: %s, data: %s' % (update_type, json.dumps(data, indent=2)))
            self.message_types.update({update_type:data})
     
        if len(self.message_types) > 0:
            log.warn('previously received unknown message types: %s' % self.message_types.keys())
            
        log.debug('%d events in event queue%s' % (self.event_q.qsize(),'' if not self.event_q.full() else ' event queue is FULL' ))
        log.debug('%d events in sync queue' % (self.sync_q.qsize()))
            
        if log.getEffectiveLevel() == logging.DEBUG:    
            with open('raw_data.json', 'w') as f:
                f.write(json.dumps(unifi_data, indent=2))
            
    def deduplicate_list(self, base_list):
        '''
        takes list of dicts, and returns list of deduplicated dicts
        based on _id value
        '''
        temp=OrderedDict()
        for d in base_list:
            temp[d['_id']] = d
        return list(temp.values())
        
    def update_list(self, base_list, update_list):
        '''
        operates on list of dicts, updates base_list with new values from update_list
        '''
        try:
            #eliminate earlier duplicates
            base_list = self.deduplicate_list(base_list)
            update_list = self.deduplicate_list(update_list)
            for item in update_list:
                for id, device in enumerate(list(base_list)):   #copy list so that we can change it while iterating on it
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

class UnifiClient2(UnifiClient):
    '''
    Python 2 websocket class
    '''
    def __init__(self, username, password, host='localhost', port=8443, ssl_verify=False, q=None, timeout=10.0, unifi_os=None):
        super(UnifiClient2, self).__init__(username, password, host, port, ssl_verify, q, timeout, unifi_os)
   
    def connect_websocket(self):
        t=threading.Thread(target=self.start_websocket)
        t.daemon = True
        t.start()
   
    def start_websocket(self):
        log.debug('Python 2 websocket')
        while True:
            self.simple_websocket()
            time.sleep(30)
            log.warn('Reconnecting websocket')
            
    def api(self, command):
        if self.session is not None:
            try:
                r = self.session.get(self.base_url+command, verify=self.ssl_verify, timeout=self.timeout)
                assert r.status_code == 200

                data = r.json()
                
                log.debug('received API response: %s' % json.dumps(data, indent=2))
                return data
            except (AssertionError, requests.ConnectionError, requests.Timeout) as e:
                log.error('API call %s failed: %s' % (command,e))
            except Exception as e:
                log.exception("API command exception: %s" % e)
        return None      

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
        self.session = session
        
        try:
        
            # We Authenticate with one session to get a session ID and other validation cookies
            r = session.post(self.login_url, json=json_request, verify=self.ssl_verify, timeout=self.timeout)
            assert r.status_code == 200

            r = session.get(self.initial_info_url, json=self.params, verify=self.ssl_verify, timeout=self.timeout)
            assert r.status_code == 200

            data = r.json()
            
            log.debug('received initial data: %s' % json.dumps(data, indent=2))
            self.update_unifi_data(data)
            
            #login successful, get cookies
            cookies = requests.utils.dict_from_cookiejar(session.cookies)
            log.debug('cookies: %s' % cookies)
            #cookies example: {'csrf_token': 'icIkv3tcVjwlJ4TQbgyeCuEZiJGErAUy', 'unifises': 'nutupuMKrLC4eA6CRmS6yWcldWowJRT2'
            if self.unifi_os:
                SESSIONID = cookies.get('TOKEN')
                ws_cookies = "TOKEN=%s" % (SESSIONID)
            else:
                csrf_token = cookies.get('csrf_token')
                SESSIONID = cookies.get('unifises')
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

        except (AssertionError, requests.ConnectionError, requests.Timeout) as e:
            log.error("Connection failed error: %s" % e)
        except Exception as e:
            log.exception("unknown exception: %s" % e)
            
        self.session = None       
        log.info('Exited')
        
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
