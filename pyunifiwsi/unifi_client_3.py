#!/usr/bin/env python3
#
# unifi_client.py
#
# Copyright (c) 2019,202 Nick Waterton <nick.waterton@med.ge.com>
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

#need to install aiohttp (pip install aiohttp) - python 3 only!

from __future__ import print_function

import json
import sys
import time
import threading
from queue import Queue
from collections import OrderedDict
import asyncio
import aiohttp

import logging
from logging.handlers import RotatingFileHandler

#import other modules here depending on which websocket you want to use. this is dome in the 
#routines below for testing, but normally you would do it here.

log = logging.getLogger('Main')

from unifi_client import UnifiClient
        
class UnifiClient3(UnifiClient):
    '''
    Python 3 websocket class
    '''
    def __init__(self, username, password, host='localhost', port=8443, ssl_verify=False, q=None, timeout=10.0, unifi_os=None):
        super().__init__(username, password, host, port, ssl_verify, q, timeout, unifi_os)
        
    def connect_websocket(self):
        t=threading.Thread(target=self.start_websocket)
        t.daemon = True
        t.start()

    def start_websocket(self):
        '''
        Python 3 only!
        '''
        log.debug('Python 3 websocket')
        
        self.loop = asyncio.new_event_loop()
        while True:
            self.loop.run_until_complete(self.async_websocket())
            time.sleep(30)
            log.warn('Reconnecting websocket')
            
    def api(self, command):
        if self.session is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(self._api(command), self.loop)
                return future.result(2) #timeout 2 seconds
            except asyncio.TimeoutError:
                log.error('The api command %s took too long, cancelling the task...' % command)
                future.cancel()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error('API coroutine error: %s' % e)
        return None
            
    async def _api(self, command):
        if self.session is not None:
            try:
                async with self.session.get(self.base_url+command, ssl=self.ssl_verify, timeout=self.timeout) as response:
                    assert response.status == 200
                    json_response = await response.json()
                    log.debug('Received json response to command:')
                    log.debug(json.dumps(json_response, indent=2))
                    return json_response
            except (AssertionError, aiohttp.client_exceptions.ClientConnectorError) as e:
                log.error('API call %s failed: %s' % (command,e))
            except Exception as e:
                log.exception("API exception: %s" % e)
        return None

    async def async_websocket(self):
        '''
        By default ClientSession uses strict version of aiohttp.CookieJar. RFC 2109 explicitly forbids cookie accepting from URLs
        with IP address instead of DNS name (e.g. http://127.0.0.1:80/cookie).
        It’s good but sometimes for testing we need to enable support for such cookies. It should be done by passing unsafe=True
        to aiohttp.CookieJar constructor:
        '''
        
        #enable support for unsafe cookies
        jar = aiohttp.CookieJar(unsafe=True)
        
        log.info('login() %s as %s' % (self.url,self.username))

        json_request = {    'username': self.username,
                            'password': self.password,
                            'strict': True
                       }
                       
        try:
            
            async with aiohttp.ClientSession(cookie_jar=jar) as session:
                self.session = session
                async with session.post(
                        self.login_url,json=json_request, ssl=self.ssl_verify, timeout=self.timeout) as response:
                        assert response.status == 200
                        json_response = await response.json()
                        log.debug('Received json response to login:')
                        log.debug(json.dumps(json_response, indent=2))

                async with session.get(
                        self.initial_info_url,json=self.params, ssl=self.ssl_verify, timeout=self.timeout) as response:
                        assert response.status == 200
                        json_response = await response.json()
                        log.debug('Received json response to initial data:')
                        log.debug(json.dumps(json_response, indent=2))
                        self.update_unifi_data(json_response)
       
                async with session.ws_connect(self.ws_url, ssl=self.ssl_verify, timeout=self.timeout) as ws:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            log.debug('received: %s' % json.dumps(json.loads(msg.data),indent=2))
                            self.update_unifi_data(msg.json(loads=json.loads))
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            log.info('WS closed: %s' % msg.extra)
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            log.error('WS closed with Error')
                            break
                            
        except (AssertionError, aiohttp.client_exceptions.ClientConnectorError) as e:
            log.error('failed to connect: %s' % e)
        except Exception as e:
            log.exception("unknown exception: %s" % e)
            
        self.session = None       
        log.info('Exited')    
        
if __name__ == '__main__':
    pass
