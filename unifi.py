#!/usr/bin/env python3
#
# boxes.py
#
# Copyright (c) 2017 David Lechner <david@lechnology.com>
# This file is part of the GRX graphics library.
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

__VERSION__ = '1.0.0'

import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib
gi.require_version('Grx', '3.0')
from gi.repository import Grx

import random, time
import json
import sys, os
from multiprocessing import Process, Value, Queue
from subprocess import check_output
from collections import OrderedDict

#from controller import Controller
from unifi_client import UnifiClient

import logging
from logging.handlers import RotatingFileHandler     
        
class UnifiApp(Grx.Application):
    """Base class for simple (non-interactive) demo apps"""
    def __init__(self):
        super(Grx.Application, self).__init__()
        self.init()
        self.hold()
        Grx.mouse_set_cursor(None)
        
        #set default colors and fonts
        global white, black, green, yellow, cyan, blue, red, magenta, dark_gray, default_text_opt, text_height, text_width
        colors = Grx.color_get_ega_colors()
        white = colors[int(Grx.EgaColorIndex.WHITE)]
        black = colors[Grx.EgaColorIndex.BLACK]
        green = colors[Grx.EgaColorIndex.GREEN]
        yellow = Grx.color_get(204,204,0)#colors[Grx.EgaColorIndex.YELLOW] #use darker yellow
        cyan = colors[Grx.EgaColorIndex.CYAN]
        blue = colors[Grx.EgaColorIndex.BLUE]
        magenta = colors[Grx.EgaColorIndex.MAGENTA]
        red = colors[Grx.EgaColorIndex.RED]
        dark_gray = colors[Grx.EgaColorIndex.DARK_GRAY]
        self.set_default_text_size(14)
        
        self.port_size=0

        self.draw_devices = []
        self.redraw_all = False #causes redraw after creation if set to True
        
    def set_default_text_size(self, size=14):
        global default_text_opt, text_height, text_width
        default_text_opt = Grx.TextOptions.new_full(
                        # Don't want to use the dpi-aware font here so we can cram info on to small screens (font size, 8,10,12,14 etc)
                        Grx.Font.load_full('LucidaTypewriter', size, -1, Grx.FontWeight.REGULAR,
                                           Grx.FontSlant.REGULAR, Grx.FontWidth.REGULAR, True, None),
                                           white, black,
                                           Grx.TextHAlign.LEFT, Grx.TextVAlign.TOP)
        #text height/width
        text_height = default_text_opt.get_font().get_text_height('0')
        text_width = default_text_opt.get_font().get_text_width('0')
        
    def set_default_positions(self):
        self.draw_devices = []
        self.redraw_all = True
        self.port_size=0        #min port size
        self.y_update_pos = self.default_update_position #where the key etc is displayed (y pos)
        self.x_pos = self.default_left_margin
        self.text_lines = self.default_text_lines.copy()
    
    def duplicate_text_opts(self, text_object):
        return Grx.TextOptions.new_full(text_object.get_font(),
                                        text_object.get_fg_color(), text_object.get_bg_color(),
                                        text_object.get_h_align(), text_object.get_v_align())

    def do_event(self, event):
        """called when an input event occurs
        overrides Grx.Application.do_event
        """
        if Grx.Application.do_event(self, event):
            return True

        if event.type in (Grx.EventType.KEY_DOWN, Grx.EventType.BUTTON_PRESS,
                          Grx.EventType.TOUCH_DOWN):
                          
            if not self.check_touch_device(event):
                self.quit()
            return True

        return False
        
    def check_touch_device(self, event):
        log.info('event type is: %s' % event.type)
        if event.type == Grx.EventType.TOUCH_DOWN:
            x = event.touch.x
            y = event.touch.y
        elif event.type == Grx.EventType.BUTTON_PRESS:
            x = event.button.x
            y = event.button.y
        else:
            return False
            
        draw_devices = False
        
        if self.zoomed:
            #reset from zoomed
            self.zoomed = False
            for devices in self.all_devices:
                for id in devices.copy().keys():
                    for current_id in self.draw_devices:
                        if id == current_id:
                            devices.pop(id) #force recreation of device with new size parameters
                            
            self.set_default_positions()
            draw_devices = True
        
        if not draw_devices:
            for devices in self.all_devices:
                for id, device in devices.items():
                    if x >= device.x and x <= device.device_right and y >= device.y and y <= device.device_bottom:
                        log.info('touched device: %s' % device.name)
                        self.draw_devices =[id]
                        devices.pop(id) #force recreation of device with new size parameters
                        if device.type == 'usw':
                            self.port_size=55
                            self.text_lines['usw'] = 2
                        elif device.type == 'ugw':
                            self.port_size=140
                            self.text_lines['ugw'] = 8
                            self.x_pos = None
                        else:   #uap
                            self.port_size=140
                            self.text_lines['uap'] = 7
                            self.x_pos = None
                        self.y_update_pos = 460 #where the key etc is displayed (y pos)
                        self.zoomed = True
                        draw_devices = True
                        break
   
        if draw_devices:
            Grx.clear_context(self.black)
            #self.network_switches = {}
            #self.usg = {}
            #self.uap = {}
            self.redraw_key = True
            self.draw_all_devices(True)
            return True
            
        self.exit.value = True
        while not self.q.empty():
            log.info('Waiting for queue to empty')
            self.devices = self.q.get()
        #self.worker.terminate()
        #self.worker.join()
        log.info('Program Exit')
        kill_text = '/usr/bin/sudo kill -9 %s' % self.worker.pid
        check_output(kill_text.split())
        sys.exit(0)
        return False

    # GLib.Application requires that we implement (override) the activate
    # method.
    def do_activate(self):
        Grx.user_set_window(0,0,799,479)    #set for 800X480 screen size (but does not seem to do anything).

        self.white = white
        self.black = black
        self.green = green
        self.yellow = yellow
        self.cyan = cyan
        self.red = red
        self.blue = blue
        self.magenta = magenta
        self.dark_gray = dark_gray

        self.default_text_opt = default_text_opt
        
        #text height/width
        self.text_height = text_height
        self.text_width = text_width
        
        self.x = Grx.get_width()
        self.y = Grx.get_height()
        
        self.default_text_lines = { 'usw':1,
                                    'ugw':6,
                                    'uap':3
                                  }
        self.text_lines = self.default_text_lines.copy()
        self.default_update_position = 330 #where the key etc is displayed (y pos)
        self.default_left_margin = 10   #not used for switches, switches always display 10 in from the right
        self.default_top_margin = 10
        
        self.network_switches = {}
        self.usg = {}
        self.uap = {}
        
        self.all_devices = [self.network_switches, self.usg, self.uap]
        
        self.device_locations = {}

        '''
        self.line_opts = Grx.LineOptions()
        self.line_opts.color = self.white
        self.line_opts.width = 3
        self.line_opts.n_dash_patterns = 2
        self.line_opts.dash_pattern0 = 6
        self.line_opts.dash_pattern1 = 4
        self.line_opts0 = Grx.LineOptions()
        '''
        self.update = Value('i', 0) #for multiprocess
        self.last_update = time.time()
        self.last_update_text = time.ctime()
        self.blink = True
        self.devices = []
        self.x_update_pos = 15
        self.y_update_pos = self.default_update_position
        self.x_pos = 10
        self.redraw_key = True
        self.zoomed = False
        
        #multiprocess stuff
        self.exit = Value('i', 0)   #False
        self.q = Queue()
            
        self.worker = Process(target=self.get_unifi_data)
        self.worker.daemon=True
        self.worker.start()

        GLib.timeout_add_seconds(1,self.draw_update)
        GLib.timeout_add_seconds(1,self.draw_all_devices)
        #GLib.idle_add(self.draw_all_devices)
        
    def draw_key(self, x=30, y=182):
        #x = 30
        #y = 182
        box_size = 20
        spacing = 5
        key = OrderedDict( [('= 2000 MBps', {'shape': 'square', 'color':self.magenta}),
                            ('= 1000 MBps', {'shape': 'square', 'color':self.green}),
                            ('= 100 MBps', {'shape': 'square', 'color':self.yellow}),
                            ('= 10 MBps', {'shape': 'square', 'color':self.cyan}),
                            ('= Up/DownLink', {'shape': 'circle', 'color':self.green})]
                          )
        
        x+=spacing*2
        for text, color in key.items():
            y+= box_size + spacing
            Grx.draw_filled_rounded_box(x, y, x+box_size, y+box_size, 3, color['color'])
            if color['shape'] == 'circle':
                Grx.draw_filled_circle(x+box_size//2, y+box_size//2, box_size//4, self.blue)
            Grx.draw_text(text, x+30, y, self.default_text_opt)
            
        self.redraw_key = False
    
    def draw_update(self):
        if self.exit.value:
            return False
        x = self.x_update_pos
        y = self.y_update_pos
        min_pos = y-130
        
        if self.redraw_key:
            self.draw_key(x+15, y-143)
        
        line_opts = Grx.LineOptions()
        line_opts.width = 5
        offset = 10
        height = 15
        
        if y-((offset+height)*self.update.value) <= min_pos:
            line_opts.color = self.black
            Grx.draw_line_with_options(x,y,x,min_pos,line_opts)
            self.update.value = 1
            
        if self.blink:
            if time.time() - self.last_update < 60:
                line_opts.color = self.green
            else:
                line_opts.color = self.red
        else:
            line_opts.color = self.black
        
        start = y
        end = y-height
        
        for seg in range(self.update.value):
            Grx.draw_line_with_options(x,start,x,end,line_opts)
            start= end-offset
            end=start-height
            if end < min_pos:
                end = min_pos

        self.blink = not self.blink
        
        Grx.draw_text(self.last_update_text, max(0,x-10), y-140, self.default_text_opt)
        
        return True

    def get_unifi_data(self):
        client = UnifiClient(arg.username, arg.password, arg.IP, arg.port, ssl_verify=arg.ssl_verify)
        while not self.exit.value:
            try:
                with self.update.get_lock():
                    self.update.value+=1
                log.info('Refreshing Data')
                devices = client.devices()
                self.q.put(devices)
                log.info('Data Updated')
            except Exception as e:
                log.info('Error getting data: %s' % e)
                self.last_update = 0
                time.sleep(5)
            if log.getEffectiveLevel() == logging.DEBUG:
                with open('data.json', 'w') as f:
                    f.write(json.dumps(devices, indent=2))
        self.q.close()
        
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

            log.debug('Total Number of Devices: %d' % len(base_list))
        except Exception as e:
            log.info('ERROR: %s' % e)
        return base_list         
        
    def draw_all_devices(self, override=False):
        if not override:
            if self.q.empty():
                return GLib.SOURCE_CONTINUE
            devices =[]
            while not self.q.empty():
                devices+=self.q.get()
            self.devices = self.update_list(self.devices, devices)
        else:
            devices = self.devices

        switches = []
        usgs = []
        uaps=[]
        
        for device in devices:
            if device["type"]=='usw':
                switches.append(device)
            elif device["type"]=='ugw':
                usgs.append(device)
            elif device["type"]=='uap':
                uaps.append(device)
                      
        last_switch_pos = self.create_devices(-10, self.default_top_margin, self.network_switches, switches) #auto 10 in from the right, 10 down
        self.create_devices(self.x_pos, self.default_top_margin, self.usg, usgs)
        if self.x_pos is not None:
            x_pos = self.x_pos - 4 #normally 6 from left side
        else:
            x_pos = self.x_pos
        self.create_devices(x_pos, last_switch_pos+5, self.uap, uaps)
        
        self.update_device(self.network_switches, switches)
        self.update_device(self.usg, usgs)
        self.update_device(self.uap, uaps)
 
        self.last_update = time.time()
        self.last_update_text = time.ctime()
        log.debug('Updated time to: %s' % self.last_update_text)
        self.redraw_all = False
            
        return GLib.SOURCE_CONTINUE
        
    def create_devices(self, x, y, devices, data):
        last_switch_pos = y
        if len(data) > 0:
            #create devices
            for device in data:
                id = device["device_id"]
                name = device["name"]
                model = device["model"]
                type = device["type"]
                device['zoomed']=self.zoomed    #add 'zoomed' property into data
                #save locations for redrawing
                if not self.zoomed:
                    try:
                        x = self.device_locations[id].get('x', x)
                        y = self.device_locations[id].get('y', y)
                    except KeyError:
                        self.device_locations[id] = {'x':x,'y':y}

                if len(self.draw_devices) > 0 and id not in self.draw_devices:
                    continue
                if id not in devices:
                    ports = 0
                    for port in device["ethernet_table"]:   #no easy way to figure out the actual number of ports (but not really needed anyway)...
                        ports+=port.get("num_port",0)
                    if type == 'usw':
                        log.info('creating switch: %s' % name)
                        devices[id]=(NetworkSwitch(x,y, ports, device, model=model, port_size=self.port_size, text_lines=self.text_lines[type]))
                        #Vertical spacing of switches increment next switch this many down
                        last_switch_pos = y = devices[id].device_bottom + 10
                    elif type == 'ugw':
                        log.info('creating usg: %s' % name)
                        devices[id]=(USG(x,y, ports, device, model=model, port_size=self.port_size, text_lines=self.text_lines[type]))
                        #Vertical spacing of usg's increment next switch this many down (of course should only be one...)
                        y = devices[id].device_bottom + 10
                    elif type == 'uap':
                        log.info('creating uap: %s' % name)
                        devices[id]=(UAP(x,y, ports, device, model=model, port_size=self.port_size, text_lines=self.text_lines[type]))
                        #horizontal spacing of AP's
                        x = devices[id].device_right + 2
                    
        return last_switch_pos
        
    def update_device(self, devices, data):
        for id, device in devices.items():
            if len(self.draw_devices) > 0 and id not in self.draw_devices:
                continue
            if self.redraw_all:
                device.commit_changes(forced=True)
            for device_data in data:
                type = device_data["type"]
                if id == device_data["device_id"]:  #"device_id" is the same as "_id"
                    log.info('updating device: %s' % device.name)
                    device.store_data(device_data)
        
class NetworkPort():
    def __init__(self, x, y, port_number=1, SFP=False, POE=False, port_width=30, port_height=30, initial_data={}, parent=None):
    
        #colors and fonts
        self.white = white
        self.black = black
        self.green = green
        self.yellow = yellow
        self.cyan = cyan
        self.red = red
        self.blue = blue
        self.magenta = magenta
        self.dark_gray = dark_gray
        
        self.parent = parent

        self.default_text_opt = self.duplicate_text_opts(default_text_opt)
        self.default_text_opt.set_h_align(Grx.TextHAlign.CENTER)
        self.default_text_opt.set_v_align(Grx.TextVAlign.MIDDLE)
        
        #text height/width
        self.text_height = text_height
        self.text_width = text_width
    
        self.x = x
        self.y = y
        
        #fixed things
        self.port_number = port_number
        self.port_width = port_width
        self.port_height = port_height
        self.sfp = SFP
        self.sfp_offset = 0
        if self.sfp:
            self.sfp_offset = 10
        self.poe = POE
        
        #things which may be updated (stored in port_params)
        self.port_params=initial_data
        self.clean = False
        self.commit = {}

        self.draw_port()
        
    def duplicate_text_opts(self, text_object):
        return Grx.TextOptions.new_full(text_object.get_font(),
                                        text_object.get_fg_color(), text_object.get_bg_color(),
                                        text_object.get_h_align(), text_object.get_v_align())
        
    def draw_port(self):
        if self.clean:
            return
        if not self.parent.enabled:
            self.enabled = False
        log.info('Drawing Port : %d, %s, speed:%s, power:%s as %s' % (self.port_number, self.name, self.speed, self.power, 'ENABLED' if self.enabled else 'DISABLED'))
        port_number_text_opts = self.duplicate_text_opts(self.default_text_opt)
        port_number_text_opts.set_fg_color(self.white)
        port_number_text_opts.set_bg_color(self.parent.bg_color)
        port_number_text_opts.set_v_align(Grx.TextVAlign.TOP)
        port_text_opts = self.duplicate_text_opts(self.default_text_opt)
        color = self.get_color()
        port_text_opts.set_bg_color(color)
        port_text_opts.set_fg_color(self.white)
        port_text_opts.set_v_align(Grx.TextVAlign.MIDDLE)

        Grx.draw_text(str(self.port_number), self.x+self.port_width//2, self.y-self.text_height, port_number_text_opts)
        Grx.draw_filled_rounded_box(self.x, self.y, self.x+self.port_width, self.y+self.port_height, 3, color)
        if color == self.black:
            port_color = self.white
            if not self.enabled:
                port_color = self.red
            Grx.draw_rounded_box(self.x, self.y, self.x+self.port_width, self.y+self.port_height, 3, port_color)
        else:
            if self.is_downlink == -1:
                self.draw_downlink()
            elif self.is_downlink == 1:
                self.draw_uplink()
                
            text = [self.name[:self.port_width//self.text_width]]
            poe_offset = 0

            if self.poe:
                if float(self.power)!=0:
                    text = [self.power,
                            self.name[:self.port_width//self.text_width]]
                    poe_offset = self.text_height//2
            
            y_text = self.y+self.port_height/2 - len(text)*self.text_height + poe_offset
            for line, txt in enumerate(text,1):
                Grx.draw_text(txt, self.x+self.port_width/2, y_text+(line*self.text_height), port_text_opts)
                
        self.clean = True
                
    def draw_downlink(self):
        #Downwards triangle
        pt_1 = Grx.Point()
        pt_2 = Grx.Point()
        pt_3 = Grx.Point()
        pt_1.x = self.x+self.port_width//6
        pt_1.y = self.y+self.port_height//6
        pt_2.x = self.x+5*self.port_width//6
        pt_2.y = self.y+self.port_height//6
        pt_3.x = self.x+self.port_width//2
        pt_3.y = self.y+5*self.port_height//6
        
        points = [pt_1, pt_2, pt_3, pt_1]
        Grx.draw_filled_polygon(points, self.blue)
        
    def draw_uplink(self):
        #Upwards triangle
        pt_1 = Grx.Point()
        pt_2 = Grx.Point()
        pt_3 = Grx.Point()
        pt_1.x = self.x+self.port_width//2
        pt_1.y = self.y+self.port_height//6
        pt_2.x = self.x+5*self.port_width//6
        pt_2.y = self.y+5*self.port_height//6
        pt_3.x = self.x+self.port_width//6
        pt_3.y = self.y+5*self.port_height//6

        points = [pt_1, pt_2, pt_3, pt_1]
        Grx.draw_filled_polygon(points, self.blue)
                
    def get_color(self):
        if self.speed == 0 or not self.enabled:
            return self.black
        elif self.speed == 10:
            return self.cyan
        elif self.speed == 100:
            return self.yellow
        elif self.speed == 1000:
            return self.green
        elif self.speed == 2000:
            return self.magenta
        else:
            return self.red
            
    @property      
    def speed(self):
        return self.port_params.get('speed', 0)
        
    @speed.setter      
    def speed(self, value):
        self.port_params['speed'] = value
        
    @property      
    def power(self):
        return self.port_params.get('power', 0)
        
    @power.setter      
    def power(self, value):
        self.port_params['power'] = value
        
    @property      
    def name(self):
        return self.port_params.get('name', '')
        
    @name.setter      
    def name(self, value):
        self.port_params['name'] = value
        
    @property      
    def org_name(self):
        return self.port_params.get('org_name', '')
        
    @org_name.setter      
    def org_name(self, value):
        self.port_params['org_name'] = value
        
    @property      
    def iface_name(self):
        return self.port_params.get('iface_name', '')
        
    @iface_name.setter      
    def iface_name(self, value):
        self.port_params['iface_name'] = value
        
    @property      
    def is_downlink(self):
        return self.port_params.get('is_downlink', 0)
        
    @is_downlink.setter      
    def is_downlink(self, value):
        self.port_params['is_downlink'] = value
        
    @property      
    def enabled(self):
        return self.port_params.get('enabled', False)
        
    @enabled.setter      
    def enabled(self, value):
        self.port_params['enabled'] = value
            
    def commit_changes(self):
        for item, value in self.commit.items():
            if self.port_params.get(item, None) != value:
                log.info('%s: Updating Port: %s(%s) %s to %s ' % (self.parent.name, self.port_number, self.name, item, value))
                self.port_params[item] = value
                self.clean = False
        self.commit = {}
        if not self.clean:
            self.draw_port()
      
    def set_port_speed(self, speed=0):
        self.commit['speed'] = speed
            
    def set_port_power(self, power=0):
        self.commit['power'] = power
            
    def set_port_name(self, name):
        self.commit['name'] = name
        
    def set_port_org_name(self, name):
        self.commit['org_name'] = name
            
    def set_iface(self, name):
        self.commit['iface_name'] = name
            
    def set_downlink(self, downlink):
        self.commit['is_downlink'] = downlink
            
    def set_port_enabled(self, enabled):
        self.commit['enabled'] = enabled   
        
class NetworkDevice():
    '''
    default class for network devices, must be subclassed for specific devices
    default device is a switch...
    '''

    models = {}
    
    states={0:{'text':['Off','Line','','','','',''], 'enabled':False},
            1:{'text':None, 'enabled':True},
            4:{'text':['Upgrading','','','','','',''], 'enabled':True},
            5:{'text':['Provisioning','','','','','',''], 'enabled':True},
            6:{'text':['Heartbeat', 'Missed','','','','',''], 'enabled':True},
            }
            
    type='usw'  #default switch type

    def __init__(self, x, y, ports=24, data=None, model=None, SFP=False, POE=False, port_size=0, text_lines=1):
        
        self.init(x, y, data, model, ports, SFP, POE, port_size, 8, 14, text_lines) #x,y offset of ports, number or lines of text above ports

        #of rows of ports
        rows = 1
        if self.num_ports > 12 or self.sfp:
            rows = 2
               
        self.init_rows(rows)
        self.update_from_data()
        self.draw_device()
        
    def init(self,x, y, data, model, ports, SFP, POE, port_size, x_offset=8, y_offset=14, y_lines_text=1):
        #colors and fonts
        self.white = white
        self.black = black
        self.green = green
        self.yellow = yellow
        self.cyan = cyan
        self.blue = blue
        self.red = red
        self.magenta = magenta
        self.dark_gray = dark_gray
        
        self.bg_color = self.dark_gray
        self.outline = self.white

        self.default_text_opt = self.duplicate_text_opts(default_text_opt)
        self.default_text_opt.set_h_align(Grx.TextHAlign.CENTER)
        self.default_text_opt.set_v_align(Grx.TextVAlign.MIDDLE)
        
        #zoomed or not (if we are zoomed display extra data box)
        self.zoomed = data.get('zoomed', False)
        
        #text height/width
        self.text_height = text_height
        self.text_width = text_width
        #log.info('text width: %s, text height: %s' % (self.text_width, self.text_height))
        
        self.x = x
        self.y = y
        
        #number of text lines above ports
        self.y_lines_text = y_lines_text
        #distance from outline to text
        self.text_offset = 8
        #distance from outline to ports
        self.x_offset = x_offset
        self.y_offset = y_offset + (y_lines_text+1)*self.text_height 
        #horizontal offset of sfp ports
        self.sfp_offset = 0
        #port width
        self.port_width = max(port_size, self.text_width*5) #5 characters wide min for ports
        self.port_height = max(port_size, self.text_width*5) # square ports
        #port spacing
        self.v_spacing = self.text_height + 2
        self.h_spacing = 3
        
        self.name = ''
        self.data = data
        self.model = model
        if not self.check_model():
            self.num_ports = ports
            self.sfp=SFP
            self.poe=POE
            
        self.org_num_ports = self.num_ports
        self.total_ports = ports    #reported total number of ports including sfp ports
            
        if self.sfp:
            self.num_ports+=2
            self.sfp_offset = 10
            
        if self.port_width > 100 and self.num_ports == 1:
            #if we only have 1 large port increase overall width
            self.x_offset+=self.port_width//2
            
        self.new=False   #indicate this is a newly created device, set to false as we are not created yet, will be set later when we have been created
  
    def init_rows(self, rows=1):
        if self.num_ports != self.total_ports:
            log.info('WARNING: number of ports configured: %d, does not match number of ports reported: %d' % (self.num_ports, self.total_ports))
    
        self.rows = rows
        if self.x is None:
            self.x = max(0, Grx.get_width()//2 - (self.num_ports//self.rows * (self.port_width+self.h_spacing) + self.sfp_offset+(2*self.x_offset))//2)
        if self.x < 0:  #auto position x from right edge
            self.x_right_margin = -self.x
            self.x = max(0, Grx.get_width() - (self.num_ports//self.rows * (self.port_width+self.h_spacing) + self.sfp_offset+(2*self.x_offset)+self.x_right_margin))
            
        #port position   
        self.port_x = self.x+self.x_offset
        self.port_y = self.y+self.y_offset
        
        #device parameters
        self.device_bottom = self.y+self.y_offset-self.text_height//2+(self.port_height+self.v_spacing)*self.rows
        self.device_right = self.x+self.sfp_offset+self.x_offset*2+(self.port_width+self.h_spacing)*(self.num_ports//self.rows)
        while self.device_right >= Grx.get_width() or self.device_bottom >= Grx.get_height():
            self.port_width-=1
            self.port_height-=1
            self.device_bottom = self.y+self.y_offset-self.text_height//2+(self.port_height+self.v_spacing)*self.rows
            self.device_right = self.x+self.sfp_offset+self.x_offset*2+(self.port_width+self.h_spacing)*(self.num_ports//self.rows)
        self.device_width = self.device_right - self.x
        self.box_width = self.device_width//self.text_width

        self.ports = {}
        
        #metrics
        self.device_params={}
        self.set_uptime_format()
        self.ip=''
        self.short_ip=''
        
        self.text_override = False
        self.text = ['']
        self.previous_settings = {}
        self.enabled = False
        self.clean = False
        
        self.initial_port_data = {}
        
    def human_size(self,size_bytes):
        """
        format a size in bytes into a 'human' file size, e.g. bytes, KB, MB, GB, TB, PB
        Note that bytes/KB will be reported in whole numbers but MB and above will have greater precision
        e.g. 1 byte, 43 bytes, 443 KB, 4.3 MB, 4.43 GB, etc
        """
        if size_bytes == 1:
            # because I really hate unnecessary plurals
            return "1 byte"

        suffixes_table = [('bytes',0),('KB',0),('MB',1),('GB',2),('TB',2), ('PB',2)]

        num = float(size_bytes)
        for suffix, precision in suffixes_table:
            if num < 1024.0:
                break
            num /= 1024.0

        if precision == 0:
            formatted_size = "%d" % num
        else:
            formatted_size = str(round(num, ndigits=precision))

        return "%s %s" % (formatted_size, suffix)
        
    def set_uptime_format(self):
        long_uptime_format='%.3d days %.2d:%.2d:%.2d'
        short_uptime_format = '%dd%.2d:%.2d:%.2d'
        self.uptime_format=long_uptime_format
        if self.box_width < 16:
            self.uptime_format=short_uptime_format
        
    def duplicate_text_opts(self, text_object):
        return Grx.TextOptions.new_full(text_object.get_font(),
                                        text_object.get_fg_color(), text_object.get_bg_color(),
                                        text_object.get_h_align(), text_object.get_v_align())
                                        
    def check_model(self):
        if self.model in self.models.keys():
            model = self.models[self.model]
            self.description =  model['name']
            self.num_ports = model['ports']
            self.poe =  model.get('poe', False)
            self.sfp =  model.get('sfp', False)
            return True
        else:
            self.description = self.name
            return False
        
    def draw_device(self):
        if self.draw_outline(): #if true, ports already exist, so just draw outline
            return

        if self.sfp:
            if self.model == 'UGWXG':
                pass
            else:
                num_ports = self.num_ports - 1
        else:
            num_ports = self.num_ports + 1  #because range does not include the last value

        for port in range(1,num_ports):
            log_nr.info('creating port: %d, ' % port)
            x_pos = port-1
            row = 1
            if port % 2 == 0 and self.rows > 1:    #even ports
                row = 2
                
            x = self.port_x +((x_pos//self.rows)*(self.port_width+self.h_spacing))
            y = self.port_y + (self.v_spacing + self.port_height) * (row-1)

            self.ports[port] = NetworkPort(x, y, port, SFP= True if self.model == 'UGWXG' else False, POE=self.poe, port_width=self.port_width, port_height=self.port_height, initial_data=self.initial_port_data.get(port, {}), parent=self)
                
        if self.sfp:
            if 'UGW' in self.model:  #if it's a usg
                if self.model == 'UGWXG':
                    #one more port
                    x += self.sfp_offset+self.port_width+self.h_spacing
                    log.info('creating sfp port: %d, %d' % (self.num_ports-1, self.num_ports))
                    self.ports[self.num_ports-1] = NetworkPort(x, self.port_y + (self.v_spacing + self.port_height), self.num_ports-1, SFP=False, POE=False, port_width=self.port_width, port_height=self.port_height, initial_data=self.initial_port_data.get(self.num_ports-1, {}), parent=self)
                else:
                    #Two more ports
                    x += self.sfp_offset+self.port_width+self.h_spacing
                    log.info('creating sfp port: %d, %d' % (self.num_ports-1, self.num_ports))
                    self.ports[self.num_ports-1] = NetworkPort(x, self.port_y, self.num_ports-1, SFP=True, POE=False, port_width=self.port_width, port_height=self.port_height, initial_data=self.initial_port_data.get(self.num_ports-1, {}), parent=self)
                    x += self.port_width+self.h_spacing
                    self.ports[self.num_ports] = NetworkPort(x, self.port_y, self.num_ports, SFP=True, POE=False, port_width=self.port_width, port_height=self.port_height, initial_data=self.initial_port_data.get(self.num_ports, {}), parent=self)
            else:   #else it's a switch
                #Two more ports
                x += self.sfp_offset+self.port_width+self.h_spacing
                log.info('creating sfp port: %d, %d' % (self.num_ports-1, self.num_ports))
                self.ports[self.num_ports-1] = NetworkPort(x, self.port_y, self.num_ports-1, SFP=True, POE=False, port_width=self.port_width, port_height=self.port_height, initial_data=self.initial_port_data.get(self.num_ports-1, {}), parent=self)
                self.ports[self.num_ports] = NetworkPort(x, self.port_y + self.v_spacing + self.port_height, self.num_ports, SFP=True, POE=False, port_width=self.port_width, port_height=self.port_height, initial_data=self.initial_port_data.get(self.num_ports, {}), parent=self)
        
        if self.zoomed:
            self.draw_extra_data()
        self.new = True   #indicate this is a newly created device (so we don't immediately redraw...)
    
    def draw_outline(self):
        if self.clean:
            return
        log.info('%s: Drawing outline' % self.name)
        device_text_opts = self.duplicate_text_opts(self.default_text_opt)
        name = self.name
        long_name = '%s (%s)'%(self.name, self.description)
        if self.box_width > len(long_name): #use long description if we can 
            name = long_name
        #draw bounding box
        self.bg_color = self.dark_gray
        self.outline = self.white
        if not self.enabled:
            log.info('%s: is DISABLED' % name)
            self.bg_color = self.black
            self.outline = self.red  
        else:
            log.info('%s: is ENABLED' % name)
        
        Grx.draw_filled_box(self.x, self.y, self.device_right, self.device_bottom, self.bg_color)
        Grx.draw_box(self.x, self.y, self.device_right, self.device_bottom, self.outline)
        #title
        if self.device_params.get('upgrade', False):
            self.outline = self.yellow
        device_text_opts.set_fg_color(self.outline)
        device_text_opts.set_bg_color(self.bg_color)
        name = name[:self.box_width]
        text_width = device_text_opts.get_font().get_text_width(name)
        self.device_center = self.x+(self.device_right-self.x)//2
        Grx.draw_filled_box(self.device_center-text_width//2, self.y-self.text_height//2, self.device_center+text_width//2, self.y+self.text_height//2, self.black)
        Grx.draw_text(name, self.x//2+self.device_right//2, self.y, device_text_opts)
        
        port_exists = False
        for port in self.ports.values():
            port.clean = False  #force redraw of port
            port_exists = True
            
        return port_exists
        
    def draw_extra_data(self):
        '''
        can override this for devices that aren't switches if you like
        '''
        log.info('%s: Drawing Extra data outline' % self.name)
        device_text_opts = self.duplicate_text_opts(self.default_text_opt)
        name = 'Extra data'
        offset = 10
        left = 220
        #height = Grx.get_height()-self.device_bottom
        #draw bounding box
        Grx.draw_filled_box(left, self.device_bottom+offset, Grx.get_width()-offset, Grx.get_height()-offset, self.bg_color)
        Grx.draw_box(left, self.device_bottom+offset, Grx.get_width()-offset, Grx.get_height()-offset, self.outline)
        #data
        device_text_opts.set_fg_color(self.outline)
        device_text_opts.set_bg_color(self.bg_color)
        device_text_opts.set_h_align(Grx.TextHAlign.LEFT)
        device_text_opts.set_v_align(Grx.TextVAlign.TOP)
        text_top = self.device_bottom+offset
        
        #text
        columns = 1
        text_lines = (Grx.get_height()-offset-self.device_bottom-offset)//self.text_height
        text = self.extra_text()
        
        next_column = False #end line of text in '\n' to trigger new column manually

        for line, txt in enumerate(text, 1):
            if line%text_lines == 0 or next_column:
                next_column = False
                text_top+=self.text_height
                left+= 280
                columns+=1
                if columns > 2:
                    break
                    
            if txt.endswith('\n'):
                txt = txt[:-1]
                if line%text_lines != 0:
                    next_column = True
                    
            next_line = text_top+self.text_height*(line%text_lines)
            #log.info('%s: drawing line: %d, %s' % (self.name, line, txt))
            Grx.draw_filled_box(left+self.text_offset, next_line, Grx.get_width()-offset-2, next_line+self.text_height, self.bg_color) #2 is the border line width
            Grx.draw_text(txt[:Grx.get_width()-offset-2-left-2*self.text_offset], left+self.text_offset, next_line, device_text_opts)
            
    def extra_text(self):
        '''
        can override this for devices that aren't switches if you like
        '''
        text = []
        for port in self.ports.values():
            name = port.org_name
            if port.is_downlink==1:
                name+=(' (uplink)')
            elif port.is_downlink==-1:
                name+=(' (downlink)')
            text.append('%-2s: %s' % (port.port_number, name))
            
        return text
            
    def update_data(self, **kwargs):
        if self.text_override:
            return
            
        for key, value in kwargs.items():
            if value is None:
                self.device_params[key] = value
            if value != self.device_params.get(key,None):
                self.clean = False
                if key=='uptime':
                    self.device_params['uptime_text'] = self.secondsToText(value)
                if key=='upgrade':
                    self.draw_outline()
                self.device_params[key] = value
            
        if not self.clean:
            self.set_text()
            
    def secondsToText(self, secs):
        days = secs//86400
        hours = (secs - days*86400)//3600
        minutes = (secs - days*86400 - hours*3600)//60
        seconds = secs - days*86400 - hours*3600 - minutes*60
        result = self.uptime_format % (days,hours,minutes,seconds)
        return result
        
    def set_text(self, text=None): 
        #override this with each devices metrics text
        #this is the default for a switch
        if text is not None:
            self.text = [''.join(text)]
            self.clean = False
            self.text_override = True
            return
        self.text_override = False
        try:
            if self.poe:
                text = '%-2d°C Fan:%-3d%% Pwr:%-3d%% Load:%-14s Mem:%-3d%%' % ( self.device_params['temp'], 
                                                                                self.device_params['fan'], 
                                                                                self.device_params['power'], 
                                                                                self.device_params['load'], 
                                                                                self.device_params['mem'])
            else:
                text='%-2d°C Fan:%-3d%% Load:%-14s Mem:%-3d%%' % ( self.device_params['temp'], 
                                                                   self.device_params['fan'], 
                                                                   self.device_params['load'], 
                                                                   self.device_params['mem'])
            uptime = 'UP:%-16s' % self.device_params['uptime_text']
            text+= '%*s%s' % (self.box_width-len(text)-len(uptime)-1,'',uptime)
            self.text = [text, 'IP: %s.  MAC: %s, FW_VER: %s Available: %s' % (self.ip,self.device_params['mac'],self.device_params['fw_ver'], self.device_params['upgrade'])]
        except KeyError:
            self.text = []
        
    def update_metrics(self):
        if self.clean:
            return
        log.info('%s: updating metrics' % self.name)
        device_text_opts = self.duplicate_text_opts(self.default_text_opt)
        device_text_opts.set_fg_color(self.white)
        device_text_opts.set_bg_color(self.bg_color)
        device_text_opts.set_h_align(Grx.TextHAlign.LEFT)
        device_text_opts.set_v_align(Grx.TextVAlign.TOP)
        
        for line, txt in enumerate(self.text, 1):
            if line > self.y_lines_text:
                break
            next_line = self.text_height*line
            text_top = self.y-self.text_height//4+next_line
            if txt != self.previous_settings.get(line,None):
                #log.info('%s: drawing line: %d, %s' % (self.name, line, txt))
                Grx.draw_filled_box(self.x+self.text_offset, text_top, self.x+self.device_width-2, text_top+self.text_height, self.bg_color) #2 is the border line width
                Grx.draw_text(txt[:self.box_width], self.x+self.text_offset, text_top, device_text_opts)
                self.previous_settings[line] = txt
            
        self.clean = True
        
    def update_from_data(self):
        if self.data is None:
            return
        total_power = 0.0
        downlinks_list = []
        self.radio_info = ''
        try:
            self.set_device_name(self.data.get("name", ''))
            self.set_device_enabled(self.data["state"])
            #log.info('updating device IP : %s ' % (self.data.get("ip", None)))
            self.set_ip(self.data.get("ip", None))

            downlinks = self.data.get("downlink_table",[])
            for downlink in downlinks:
                downlinks_list.append(downlink["port_idx"])
                    
            for port in self.data["port_table"]:
                total_power+= float(port.get('poe_power', 0))
                port_number = self.get_port_number(port)
                
                if port_number in downlinks_list:
                    self.set_downlink(port_number, -1)
                else:
                    self.set_downlink(port_number, 0)
                    
                #log.info('updating port: %s, name: %s ' % (port_number,port["name"]))
                self.set_port_name(port_number, port["name"])
                self.set_port_org_name(port_number, port["name"])   #save original port name
                #log.info('updating port: %s, speed: %s ' % (port_number,port.get("speed",0)))
                self.set_port_speed(port_number, port.get("speed",0))
                self.set_port_power(port_number, port.get('poe_power', '0'))
                self.set_port_enabled(port_number, port.get("enable", port["up"]))
         
                if port.get("is_uplink",False):
                    #log.info('updating port as uplink : %s, name: %s ' % (port_number,'UP'))
                    self.set_port_name(port_number, 'UP')
                    self.set_downlink(port_number, 1)
                    
                if port.get("lag_member", False):   #aggregated port
                    #port is aggregated
                    if port.get("aggregated_by", False):
                        #port is secondary port
                        self.set_port_name(port_number, 'AG:%d' % port["aggregated_by"])
                    else:
                        #port is primary port   
                        if port.get("lacp_state", False):
                            speed = 0
                            for agg_port in port["lacp_state"]:
                                if agg_port["active"]:
                                    #mem_port = agg_port["member_port"]
                                    speed+=agg_port["speed"]
                            #log.info('updating Agg port: %s, speed: %s ' % (port_number,speed))
                            self.set_port_speed(port_number, speed)
                    
            port = self.data["uplink"]   #uplink is not there if not online
            uplink_port = self.get_port_number(port)

            if port.get("lag_member", False):
                for lag_port in port["lacp_state"]:
                    #log.info('updating lag port: %s, speed: %s ' % (lag_port["member_port"],lag_port["speed"]))
                    self.set_port_speed(lag_port["member_port"], lag_port["speed"])
                    self.set_port_enabled(lag_port["member_port"], lag_port["active"])
                    self.set_downlink(lag_port["member_port"], 1)
                    to_uplink_port = port.get("uplink_remote_port",None)  #uplink_remote_port is not there if heatbeat missing
                    if to_uplink_port is not None:
                        self.set_port_name(lag_port["member_port"], 'To:%s' % to_uplink_port)

            #log.info('updating uplink port: %s, speed: %s ' % (uplink_port,port["speed"]))
            self.set_port_speed(uplink_port, port["speed"])
            to_uplink_port = port.get("uplink_remote_port",None)  #uplink_remote_port is not there if heatbeat missing (this is an AP thing, but including it here)
            if to_uplink_port is not None:
                self.set_port_name(uplink_port, 'To:%s' % to_uplink_port)
            else:
                self.set_port_name(uplink_port, 'P-UP')
            self.set_downlink(uplink_port, 1)
            self.set_port_enabled(uplink_port, port.get("enable", port["up"]))

            self.update_from_data_device_specific()
            
            #log.info('mem: %s, total mem: %s' % (self.data['sys_stats'].get("mem_used", 0),self.data['sys_stats'].get("mem_total", 1)))
            mem_percent = self.data['sys_stats'].get("mem_used", 0)*100//max(1,self.data['sys_stats'].get("mem_total", 0))
            self.update_data(    temp=self.data.get("general_temperature", None),
                                 fan=self.data.get("fan_level", None),
                                 power=total_power*100//max(1,self.data.get("total_max_power", 0)),
                                 load=self.data['sys_stats'].get("loadavg_1", '-') + ','+self.data['sys_stats'].get("loadavg_5", '-')+ ','+self.data['sys_stats'].get("loadavg_15", '-'),
                                 mem=mem_percent,
                                 uptime=self.data.get("uptime", None),
                                 mac=self.data["mac"].upper(),
                                 fw_ver=self.data.get("version", None),
                                 upgrade=self.data.get("upgrade_to_firmware", None),
                                 radio_info=self.radio_info if self.radio_info != '' else None)

        except KeyError as e:
            log.info('Key error: %s' % e)
            self.set_device_enabled(self.data["state"])
            
        self.commit_changes()
        
    def update_from_data_device_specific(self):
        '''
        Override this with specific data for devices other than switches
        '''
        pass
        
            
    def commit_changes(self, forced=False):
        if self.new:    #if we are a new device, don't redraw immediately
            self.new = False
            return
        if forced:
            log.info('%s: FORCED Redraw' % self.name)
            self.previous_settings = {}
            
        if self.enabled != self.previous_settings.get('enabled', None):
            log.info('redrawing device: %s' % self.name)
            self.clean = False
            self.draw_outline()
            self.set_text()
            self.previous_settings = {}   #force redraw of all parameters
            self.previous_settings['enabled'] = self.enabled
        self.update_metrics()
        for port in self.ports.values():
            port.commit_changes()
        
            
    def get_port_number(self, port):
        port_number = port.get("port_idx", None)
        if port_number is None:
            port_number = port.get("ifname",None)  #USG
        #if it's an AP, have to try harder to find the uplink port
        if port_number is None:
            for port in self.data["port_table"]:
                if port['name'] in ['Main', 'PoE In + Data' ]:
                    port_number = port.get("port_idx",None)  #USG
                    break
            else:
                port_number = 1
        return self.get_port_from_string(port_number)
            
    def get_port_from_string(self, port):
        if isinstance(port, str):
            iface_name = port
            port = int(port[-1:])+1
            if port in self.ports:
                self.ports[port].set_iface(iface_name)
            else:
                self.update_port_initial_data(port, {'iface_name':iface_name})
        return port
        
    def set_device_name(self, name=''):
        if name != self.name:
            self.name = name
            
    def update_port_initial_data(self, port, data):
        if not self.initial_port_data.get(port, False):
            self.initial_port_data[port]={}
        self.initial_port_data[port].update(data)
    
    def set_port_speed(self, port, speed=0):
        port = self.get_port_from_string(port)
        if port in self.ports:
            self.ports[port].set_port_speed(speed)
        else:
            self.update_port_initial_data(port, {'speed':speed}) 
            
    def set_port_power(self, port, power=0):
        port = self.get_port_from_string(port)
        if port in self.ports:
            self.ports[port].set_port_power(power)
        else:
            self.update_port_initial_data(port,  {'power':power})
        
    def set_port_name(self, port, name=None):
        port = self.get_port_from_string(port)
        if port in self.ports:
            self.ports[port].set_port_name(name)
        else:
            self.update_port_initial_data(port, {'name':name})
            
    def set_port_org_name(self, port, name=None):
        port = self.get_port_from_string(port)
        if port in self.ports:
            self.ports[port].set_port_org_name(name)
        else:
            self.update_port_initial_data(port, {'org_name':name})
            
    def set_downlink(self, port, downlink=0):
        port = self.get_port_from_string(port)
        if port in self.ports:
            self.ports[port].set_downlink(downlink)
        else:
            self.update_port_initial_data(port, {'is_downlink':downlink})
            
    def set_port_enabled(self, port, enabled=False):
        port = self.get_port_from_string(port)
        if port in self.ports:
            self.ports[port].set_port_enabled(enabled)
        else:
            self.update_port_initial_data(port, {'enabled':enabled})
        
    def set_ip(self, ip=None, port=None):
        if isinstance(self.ip, dict):   #usg uses raw port name (eg 'wan' as key)
            if port is not None:
                if self.ip.get(port, '') != ip:
                    log.info('%s: setting port: %s, IP: %s' % (self.name, port, ip))
                    self.ip[port] = ip
                    self.update_metrics()
        elif self.ip != ip:
            log.info('%s: setting IP: %s' % (self.name, ip))
            self.ip = ip
            self.short_ip = ip.split('.')[-1]
            self.update_metrics()
            
    def get_port(self, port):
        port = self.get_port_from_string(port)
        if port in self.ports:
            return self.ports[port].speed, self.ports[port].power
        return None
        
    def get_port_name(self, port):
        port = self.get_port_from_string(port)
        if port in self.ports:
            return self.ports[port].name
        return None
        
    def store_data(self, data):
        self.data = data
        self.update_from_data()
        #self.new = False
        
    def set_device_enabled(self, state):
        '''
        0 = disconnected
        1 = connected
        4 = upgrading
        5 = provisioning
        6 = heartbeat missed
        
        others probably disabled, downloading, booting?
        '''
        try:        
            current_state = self.states[state]
            self.enabled = current_state['enabled']
            log.info('%s: %s' % (self.name, ''.join(current_state['text']) if current_state['text'] is not None else 'Online'))
            self.set_text(current_state['text'])
        
        except KeyError:
            log.info('Unknown status: %d' % state)
            self.set_text(['state', str(state)])

class NetworkSwitch(NetworkDevice):

    models = {  'US8' : {'ports':8, 'poe':False, 'sfp':False, 'name':'Unifi Switch 8'},
                'US8P60' : {'ports':8, 'poe':True, 'sfp':False, 'name': 'Unifi Switch 8 POE-60W'},
                'US8P150' : {'ports':8, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 8 POE-150W'},
                'S28150' : {'ports':8, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 8 AT-150W'},
                'USC8' : {'ports':8, 'poe':False, 'sfp':False, 'name': 'Unifi Switch 8'},
                'US16P150' : {'ports':16, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 16 POE-150W'},
                'S216150' : {'ports':16, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 16 AT-150W'},
                'US24' : {'ports':24, 'poe':False, 'sfp':True, 'name': 'Unifi Switch 24'},
                'US24P250' : {'ports':24, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 24 POE-250W'},
                'US24PL2' : {'ports':24, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 24 L2 POE'},
                'US24P500' : {'ports':24, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 24 POE-500W'},
                'S224250' : {'ports':24, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 24 AT-250W'},
                'S224500' : {'ports':24, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 24 AT-500W'},
                'US48' : {'ports':48, 'poe':False, 'sfp':True, 'name': 'Unifi Switch 48'},
                'US48P500' : {'ports':48, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 48 POE-500W'},
                'US48PL2' : {'ports':48, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 48 L2 POE'},
                'US48P750' : {'ports':48, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 48 POE-750W'},
                'S248500' : {'ports':48, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 48 AT-500W'},
                'S248750' : {'ports':48, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 48 AT-750W'},
                'US6XG150' : {'ports':4, 'poe':True, 'sfp':True, 'name': 'Unifi Switch 6XG POE-150W'},
                'USXG' : {'ports':12, 'poe':False, 'sfp':True, 'name': 'Unifi Switch 16XG'},
                }

    def __init__(self, x, y, ports=24, data=None, model=None, SFP=False, POE=False, port_size=0, text_lines=1):
        super().__init__(x, y, ports=ports, data=data, model=model, SFP=SFP, POE=POE, port_size=port_size, text_lines=text_lines)

class USG(NetworkDevice):

    models = {  'UGW3'  : {'ports':3, 'poe':False, 'sfp':False, 'name': 'UniFi Security Gateway 3P'},
                'UGW4'	: {'ports':4, 'poe':False, 'sfp':True, 'name': 'UniFi Security Gateway 4P'},     #4 RJ45's and 2 side by side SFP+
                'UGWHD4' : {'ports':4, 'poe':False, 'sfp':False, 'name': 'UniFi Security Gateway HD'},   #unknown for now
                'UGWXG'	: {'ports':8, 'poe':False, 'sfp':True, 'name': 'UniFi Security Gateway XG-8'},   #8 SFP+ 4x2 and 1 RJ45 9lower)
             }
             
    type='ugw'  #USG (gateway) type

    def __init__(self, x, y, ports=3, data=None, model=None, port_size=0, text_lines=5):
        self.init(x, y, data, model, ports, False, False, port_size, 24, 14, text_lines)
   
        if self.sfp:
            if self.model == 'UGWXG':
                self.num_ports=self.org_num_ports+1
            else:
                self.num_ports=self.org_num_ports+2
            
        #of rows of ports
        rows = 1
        if self.model == 'UGWXG':
            rows = 2
            
        self.init_rows(rows)
        self.ip = OrderedDict()
        self.update_from_data()
        self.draw_device()
   
    def set_text(self, text=None): 
        #override this with each devices metrics text
        if text is not None:
            self.text = text
            self.clean = False
            self.text_override = True
            return
        self.text_override = False
        try:
            self.text= [ 'Load:%-14s' % (self.device_params['load']),
                         'Mem:%-3d%%' % self.device_params['mem'],
                         'UP:%-16s' % (self.device_params['uptime_text']),
                       ]
            if self.y_lines_text > 6:
                self.text.append('MAC: %s' % self.device_params['mac'])
                self.text.append('FW_VER: %s Available: %s' % (self.device_params['fw_ver'], self.device_params['upgrade']))
            for name, ip  in self.ip.items():
                self.text.append('%-4s: %s' % (name.upper(), ip if ip != '0.0.0.0' else 'DISABLED'))
        except KeyError:
            self.text = []
            
    def update_from_data_device_specific(self):
        '''
        Override this with specific data for devices other than switches
        '''
        for port in self.data["port_table"]:
            port_number = self.get_port_number(port)
            self.set_port_name(port_number, port["name"].upper()) #usg port names in upper case...
            self.set_ip(port.get("ip", ''),port["name"])
            if 'lan' in port["name"] or port_number > 1:
                self.set_downlink(port_number, -1)    #set as downlink
                
    def extra_text(self):
        '''
        can override this for devices that aren't switches if you like
        '''
        text = []
        data_table=[    "full_duplex",
                        "gateways",
                        "latency",
                        "nameservers",
                        "netmask",  
                    ]
        bytes_table = [ "rx_bytes",
                        "rx_dropped",
                        "rx_errors",
                        "rx_multicast",
                        "tx_bytes",
                        "tx_dropped",
                        "tx_errors",
                      ]
                    
        text.append('--WAN')
        for key, value in sorted(self.data["uplink"].items()):
            if key in data_table+bytes_table:
                if isinstance(value, list):
                    for item in value:
                        text.append('%-12s : %s' % (key, item))
                else:
                    if key in bytes_table: 
                        value = self.human_size(value)
                    text.append('%-12s : %s' % (key, value))
        return text
        
class UAP(NetworkDevice):

    models = {  'BZ2'  : {'ports':1, 'name': 'UniFi AP'},
                'BZ2LR'  : {'ports':1, 'name': 'UniFi AP-LR'},
                'U2HSR'  : {'ports':1, 'name': 'UniFi AP-Outdoor+'},
                'U2IW'  : {'ports':2, 'name': 'UniFi AP-In Wall'},
                'U2L48'  : {'ports':1, 'name': 'UniFi AP-LR'},
                'U2Lv2'  : {'ports':1, 'name': 'UniFi AP-LR v2'},
                'U2M'  : {'ports':1, 'name': 'UniFi AP-Mini'},
                'U2O'  : {'ports':1, 'name': 'UniFi AP-Outdoor'},
                'U2S48'  : {'ports':1, 'name': 'UniFi AP'},
                'U2Sv2'  : {'ports':1, 'name': 'UniFi AP v2'},
                'U5O'  : {'ports':1, 'name': 'UniFi AP-Outdoor 5G'},
                'U7E'  : {'ports':1, 'name': 'UniFi AP-AC'},
                'U7EDU'  : {'ports':2, 'name': 'UniFi AP-AC-EDU'},
                'U7Ev2'  : {'ports':2, 'name': 'UniFi AP-AC v2'},
                'U7HD'  : {'ports':2, 'name': 'UniFi AP-AC-HD'},
                'U7SHD'  : {'ports':2, 'name': 'UniFi AP-AC-SHD'},
                'U7NHD'  : {'ports':2, 'name': 'UniFi AP-nanoHD'},
                'UCXG'  : {'ports':2, 'name': 'UniFi AP-XG'},
                'UXSDM'  : {'ports':2, 'name': 'UniFi AP-BaseStationXG'},
                'UCMSH'  : {'ports':2, 'name': 'UniFi AP-MeshXG'},
                'U7IW'  : {'ports':3, 'name': 'UniFi AP-AC-In Wall'},
                'U7IWP'  : {'ports':3, 'name': 'UniFi AP-AC-In Wall Pro'},
                'U7MP'  : {'ports':2, 'name': 'UniFi AP-AC-Mesh-Pro'},
                'U7LR'  : {'ports':1, 'name': 'UniFi AP-AC-LR'},
                'U7LT'  : {'ports':1, 'name': 'UniFi AP-AC-Lite'},
                'U7O'  : {'ports':1, 'name': 'UniFi AP-AC Outdoor'},
                'U7P'  : {'ports':1, 'name': 'UniFi AP-Pro'},
                'U7MSH'  : {'ports':1, 'name': 'UniFi AP-AC-Mesh'},
                'U7PG2'  : {'ports':2, 'name': 'UniFi AP-AC-Pro'},
                'p2N'  : {'ports':1, 'name': 'PicoStation M2'},
             }
             
    type='uap'  #AP type

    def __init__(self, x, y, ports=2, data=None, model=None, port_size=0, text_lines=3):  
        log.info('AP: %s, ports = %d' % (model,ports))
        
        self.init(x, y, data, model, ports, False, False, port_size, 8, 14, text_lines)
 
        #distance from outline to text
        self.text_offset = 5
        #of rows of ports
        self.init_rows(1)
        self.update_from_data()
        self.draw_device()
        
    def set_text(self, text=None): 
        #override this with each devices metrics text
        description = self.description
        if len(self.description) >= self.box_width:
            description = self.description.replace('UniFi AP-','')[:self.box_width-1]
        if text is not None:
            self.text = text
            self.clean = False
            self.text_override = True
            return
        self.text_override = False
        try:
            ip = 'IP:%s' % (self.ip)
            if len(ip) >= self.box_width:
                ip = 'IP:%s' % (self.short_ip)
                
            self.text= ['%s' % description,
                        '%s' % (ip),
                        '%s' % (self.device_params['uptime_text'][:self.box_width-1]),
                        'Load:%-14s Mem:%-3d%%' % (self.device_params['load'], self.device_params['mem']),
                        'MAC: %s' % self.device_params['mac'],
                        'FW_VER: %s (%s)' % (self.device_params['fw_ver'], self.device_params['upgrade']),
                        '%s' % self.device_params['radio_info']]
        except KeyError:
            self.text = []
            
    def update_from_data_device_specific(self):
        '''
        Override this with specific data for devices other than switches
        '''
        self.radio_info = ''
        radio_table = self.data.get("radio_table", [])
        for radio in radio_table:
            self.radio_info+= '%s: CH:%s, Tx:%s ' % ('2G' if int(radio["channel"]) < 13 else '5G', radio["channel"], radio["tx_power_mode"][:3].upper())

    def extra_text(self):
        '''
        can override this for devices that aren't switches if you like
        '''
        text = []
        radio_data=[    "channel",
                        "radio",
                        "tx_power",
                        "min_rssi",
                        "tx_power_mode",
                        "ht",
                        "min_rssi_enabled",
                    ]
        
        for data in self.data["radio_table"]:
            text.append('--%s' % data["name"])
            for key, value in sorted(data.items()):
                if key in radio_data:
                    text.append('%-21s : %s' % (key, value))
            text[-1]=text[-1]+'\n'  #start new column
        return text

            
            
def setup_logger(logger_name, log_file, level=logging.DEBUG, console=False, no_return=False):
    try: 
        l = logging.getLogger(logger_name)
        formatter = logging.Formatter('[%(levelname)1.1s %(asctime)s] (%(threadName)-10s) %(message)s')
        if log_file is not None:
            fileHandler = logging.handlers.RotatingFileHandler(log_file, mode='a', maxBytes=2000000, backupCount=5)
            fileHandler.setFormatter(formatter)
        if console == True:
            streamHandler = logging.StreamHandler()
            if no_return:
                streamHandler.terminator = ""

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
    global log_nr
    import argparse
    global arg
    parser = argparse.ArgumentParser(description='Unifi Status Screen')
    parser.add_argument('IP', action="store", default=None, help="IP Address of Unifi Controller. (default: None)")
    parser.add_argument('-p','--port', action="store", type=int, default=8443, help='unifi port (default=8443)')
    parser.add_argument('username', action="store", default=None, help='Unifi username. (default=None)')
    parser.add_argument('password', action="store", default=None, help='unifi password. (default=None)')
    parser.add_argument('-s','--ssl_verify', action='store_true', help='Verify Certificates (Default: False)', default = False)
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
    setup_logger('Main_No_Return',log_file,level=log_level,console=True,no_return=True)
    
    log = logging.getLogger('Main')
    log_nr = logging.getLogger('Main_No_Return')
    
    log.debug('Debug mode')
    
    GLib.set_prgname('unifi.py')
    GLib.set_application_name('Unifi Status Screen')
    app = UnifiApp()
    app.run()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log.info('Program Exit')
    sys.exit(0)
