#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#extract models info from unifi javascript
# N Waterton 4th July 2019 V1.0: initial release
# N Waterton 13th July 2019 V1.0.2 minor fixes.
# N Waterton 10th Sep 2019 V1.0.3 minor fixes

import time, os, sys, json, re
from datetime import timedelta
from collections import OrderedDict
import hjson  #pip3 install hjson
import signal
import logging
from logging.handlers import RotatingFileHandler
supported_devices=['UGW','USW','UAP','UDM']

__VERSION__ = __version__ = '1.0.3'

class progress_bar():
    '''
    create terminal progress bar
    @params:
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        bar_length  - Optional  : character length of bar (Int)
    '''
    
    def __init__(self,total=100, prefix='', suffix='', decimals=1, bar_length=100):
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.decimals = decimals
        self.bar_length = bar_length
        self.prev_output_len = 0
        
    def update(self,iteration):
        iteration = max(min(iteration, self.total), 0)
        str_format = "{0:." + str(self.decimals) + "f}"
        percents = str_format.format(100 * (iteration / float(self.total)))
        filled_length = int(round(self.bar_length * iteration / float(self.total)))
        #bar = b'█'.decode('utf8') * filled_length + '-' * (self.bar_length - filled_length)
        bar = '█' * filled_length + '-' * (self.bar_length - filled_length)
        
        output = '\r%s |%s| %s%s %s' % (self.prefix, bar, percents, '%', self.suffix)
        
        current_output_len = len(output)
        diff = self.prev_output_len - current_output_len
        if diff > 0:    #if output is shorter than previously
            output += ' ' * diff    #pad output with spaces
    
        self.prev_output_len = current_output_len

        sys.stdout.write(output)
        sys.stdout.flush()
        
def newline():
    output = '\n'
    sys.stdout.write(output)
    sys.stdout.flush()

def pprint(obj):
    """Pretty JSON dump of an object."""
    return json.dumps(obj, sort_keys=True, indent=2, separators=(',', ': '))
    
def deduplicate_list(input_list):
    return list(dict.fromkeys(input_list))
    
def get_js_web_urls(url):
    global requests
    import requests #pip3 install requests
    
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    from bs4 import BeautifulSoup #pip3 install bs4
    r = requests.get(url, verify=False, timeout=10)
    soup = BeautifulSoup(r.content,features="html.parser")

    src = [sc["src"] for sc in  soup.select("script[src]")]
    return src
    
def get_js_from_web(base_url,url,tempdir = 'tempDir'+os.sep):
    log.info('retrieving js from: %s' % base_url+url)

    if not os.path.exists(tempdir):
        os.mkdir(tempdir)
    try:
        data = None
        r = requests.get(base_url+url, verify=False, timeout=10)
        assert r.status_code == 200
        data = r.text
        if data:
            os.makedirs(os.path.dirname(tempdir+url), exist_ok=True)
            with open(tempdir+url,'w+') as f:
                f.write(data)
                return tempdir+url

    except (AssertionError, requests.ConnectionError, requests.Timeout) as e:
        log.error("Connection failed error: %s" % e)
    except Exception as e:
        log.exception("unknown exception: %s" % e)
    
    return None
    
def get_js_files(unifi_dir):
    js_files = []
    for root, dir, files in os.walk(unifi_dir):
        for file in files:
            if file.endswith('.js'):
                js_files.append(root+os.sep+file)
    return js_files
    
def find_models_file(files, pattern):
    models_files = []
    pattern = re.compile(pattern)
    for file in files:
        for i, line in enumerate(open(file)):
            for match in re.finditer(pattern, line):
                #log.info('Found in file %s on line %s: %s' % (file, i+1, match.group()))
                models_files.append(file)
                continue
    return models_files
    
def find_json(files, pattern_match, all=False):
    pattern = re.compile(r".*\.exports=(\{.*?\}\}\}\})\}.*")
    json_obj = []
    for file in files:
        size = os.path.getsize(file)
        pos = 0
        progress = progress_bar(100, decimals=0, bar_length=40)
        progress.prefix='%s%s' % ('...' if len(file) > 30 else '', file[max(0,len(file)-27):])
        with open(file) as dataFile:
            for line, data in enumerate(dataFile,1):
                pos += len(data)
                #log.info("searching line: %d, %d%%" % (line, int(pos*100//size)))
                progress.update(pos*100.0/size)
                match_iter = pattern.finditer(data)
                for match in match_iter:
                    if pattern_match in match.group(1):
                        json_string = match.group(1)
                        json_string = json_string.replace("!0", "1").replace("!1", "0").strip()
                        try:
                            jsonObj = hjson.loads(json_string)
                            json_obj.append(jsonObj)
                            progress.suffix="matches: %d" % len(json_obj)
                            log.debug('Found json: %s' % pprint(jsonObj))
                            if not all:
                                newline()
                                log.info("Total Json matches found: %d" % len(json_obj))
                                return json_obj
                        except json.decoder.JSONDecodeError as e:
                            newline()
                            log.error('Json Error: %s' % e)
        newline()                  
    log.info("Total Json matches found: %d" % len(json_obj))
    return json_obj
    
def merge_dicts(a, b):
    c = a.copy()
    for k,v in b.items():
        if isinstance(v, dict):
            d = a.get(k, None)
            if isinstance(d,dict):
                c[k] = merge_dicts(v, d)
            else:
                c[k]=v
        else:
            c[k]=v
    return c
 
            
    
def consolidate_json(json_list):
    json_obj = {}
    for json in json_list:
        json_obj.update(json)
        
    json_dict = OrderedDict(sorted(json_obj.items(), key=lambda t: t[1]['type']))
    return json_dict
    
def get_summary(data):
    summary = {}
    for device, info in data.items():
        if device in supported_devices: #models.json format data
            summary[device]=len(info)
        else:                           #unifi devices format data
            if info['type'] not in summary:
                summary[info['type']] = 1
            else:
                summary[info['type']] += 1
    return summary
    
def update_models(file, data):
    if os.path.exists(file):
        log.warn('Updating file: %s, press ^C if you want to exit!' % file)
        with open(file) as f:
            models = json.loads(f.read(), object_pairs_hook=OrderedDict)
            
        new_models = OrderedDict()
        #ensure we have an entry for each supported type (even if it's blank)
        for type in supported_devices:
            if not models.get(type):
                models[type] = {}
            new_models[type] = {}
        log.info('NOTE! currently supported devices are: %s' % supported_devices)
        
        for device, info in data.items():
            type = info['type'].upper()
            result = True
            if type in supported_devices and device not in models[type]:
                #check for UDN
                if type == 'UDM':
                    new_models[type][device]=info   #add to models database (even though UDM section isn't currently used)
                elif type == 'UAP':
                    #all that is needed for AP's
                    new_models[type][device]={}
                    new_models[type][device]['name']=info['name']
                    log.info('Added %s device: %s - %s' % (type, device, info['name']))
                    continue
                else:
                    for existing_device, existing_info in models[type].items():
                        if info['name'].upper() in existing_info['name'].upper():
                            log.info('========New Device %s =========' % device)
                            log.info('looks like %s - %s is similar to %s - %s' % (device, info['name'], existing_device, existing_info['name']))
                            if query_yes_no("Do you want to copy it into the database? (if You select No, you can add it as a new device)"):
                                new_models[type][device]=existing_info
                                log.info('Device: %s copied' % new_models[type][device])
                                result = False
                            else:
                                result = query_yes_no("Do you want to add it as a new device to the database?")
                    if not result:
                        continue
                        
                #new device
                log.info('========New Device %s =========' % device)
                log.info('found new device: %s - %s, type: %s' % (device, info['name'], type))
                if not query_yes_no("Do you want to add it to the database?"):
                    continue
                else:
                    #UDM only
                    if type == 'UDM':
                        log.info('This is a %s device, you have to choose what type of device to add it as' % type)
                        while True:
                            try:
                                options = [{option: choice.upper()} for option, choice in enumerate(info['subtypes'])]
                                sel_option = query_number('please select one of the following options: %s' % options, 0)
                                type = info['subtypes'][sel_option].upper()
                                break
                            except exception as e:
                                log.error('error: %s' % e)
                                   
                    #add new device name
                    new_models[type][device]={}
                    new_models[type][device]['name']=info['name']

                    if type != 'UAP':   #only way for UAP to get here is if a UDM was selected as a UAP, this will skip over in that case.
                        if info.get('features'):
                            poe = info['features'].get('poe',0)
                            new_models[type][device]['poe'] = True if poe == 1 else False
                        
                        if info.get('diagram'):
                            diagram = info['diagram']
                            log.info('here is a diagram of the device: %s' % pprint(diagram))
                            rows = len(diagram)
                        
                        standard, sfp, sfp_plus = extract_ports_list(info['ports'])
                        if len(standard) > 0:
                            log.info('ports %s are standard ports' % standard )
                        standard = len(standard)
                        if len(sfp) > 0:
                            log.info('ports %s are sfp ports' % sfp )
                        sfp = len(sfp)
                        if len(sfp_plus) > 0:
                            log.info('ports %s are sfp+ ports' % sfp_plus )
                        sfp_plus = len(sfp_plus)

                        new_models[type][device]['ports']={'number':standard,'rows':0 if standard==0 else 1 if standard <= 8 else 2}
                        new_models[type][device]['sfp']={'number':sfp,'rows': sfp if sfp < 2 else 2}   
                        new_models[type][device]['sfp+']={'number':sfp_plus,'rows':sfp_plus if sfp_plus < 2 else 2}
                        if standard > 0:
                            rows = new_models[type][device]['ports']['rows']
                            new_models[type][device]['ports']['rows'] = query_number('how many ROWS of standard ports are there? (eg, 1,2)', rows)
                        if sfp > 0:
                            rows = new_models[type][device]['sfp']['rows']
                            new_models[type][device]['sfp']['rows'] = query_number('how many ROWS of sfp ports are there? (eg, 1,2)', rows)
                        if sfp_plus > 0:
                            rows = new_models[type][device]['sfp+']['rows']
                            new_models[type][device]['sfp+']['rows'] = query_number('how many ROWS of sfp+ ports are there? (eg, 1,2)', rows)
                        if sfp > 0 or sfp_plus > 0:
                            while not new_models[type][device].get('order'):
                                if query_yes_no("Are the first ports (from the left) standard ports?"):
                                    new_models[type][device]['order'] = [0,1,2]
                                else:
                                    if query_yes_no("Are the first ports (from the left) sfp ports?"):
                                        new_models[type][device]['order'] = [1,0,2]
                                    else:
                                        if query_yes_no("Are the first ports (from the left) sfp+ ports?"):
                                            new_models[type][device]['order'] = [2,0,1]
                                        else:
                                            log.error('OK, the first ports must be standard, sfp, or sfp+ ports. try again')
                                            
                    log.debug('Device: %s added' % new_models[type][device])
                    log.info('Device: %s added' % new_models[type][device]['name'])
                    
        log.debug('The following new devices have been added: %s' % pprint(new_models))
        log.info('New devices: %s' % get_summary(new_models))
        all_models = OrderedDict()
        all_models.update(models)
        if not any([value for value in get_summary(new_models).values()]):
            log.info('No New Models Found')
            #return
        else:
            if query_yes_no("Do you want to add them to the database?"):
                all_models = merge_dicts(models, new_models)
                log.info('database updated')
        if query_yes_no("Do you want to add the full Unifi data to the database (recommended)?"):
            for type, devices in all_models.copy().items():
                for device in devices:
                    if device in data:
                        #log.info("adding : %s to models[%s][%s]['unifi']" % (data[device], type, device))
                        all_models[type][device]['unifi'] = data[device].copy()
        log.debug('The following data will be written to the database: %s' % pprint(all_models))
        log.info('total devices: %s' % get_summary(all_models))
        if query_yes_no("Do you want to overwrite the %s file?" % file, None):
            #backup original file
            from shutil import copyfile
            copyfile(file, file+'.org')
            #write models file out
            with open(file, 'w') as f:
                f.write(pprint(all_models))
            log.info('File: %s Updated' % file)
            log.info('Total devices: %s' % get_summary(all_models))
        else:
            log.info('File: %s NOT updated' % file)
            
def extract_ports_list(ports):
    '''
    returns ports list from unifi data as tuple of lists of port number ints
    eg ([0,1,2,3], [4,5],[])
    (standard []. sfp[], sfp_plus[])
    NOTE, USG's start at port 0, but switches start at port 1.
    '''
    standard = []
    sfp = []
    sfp_plus = []
    if isinstance(ports, (list, dict)):
        #standard = [x for x in range(1,len(ports)+1,1)]
        standard = [x for x in range(len(ports))]
    if ports.get('standard'):
        standard = ports_list_decode(ports['standard'])
    if ports.get('sfp'):
        sfp = ports_list_decode(ports['sfp'])
    if ports.get('plus'):
        sfp_plus = ports_list_decode(ports['plus'])

    return standard, sfp, sfp_plus
        
def ports_list_decode(ports):
    ports_list = []
    if isinstance(ports, int):
        ports_list = [x for x in range(1,ports+1,1)]
    if isinstance(ports, list):
        ports_list = ports
    if isinstance(ports, str):
        #log.info('Ports is a string: %s' % ports)
        ports_string_list = ports.split('-')
        ports_list = [x for x in range(int(ports_string_list[0]),int(ports_string_list[-1])+1,1)] 
        
    return ports_list                
                
def query_yes_no(question, default="yes"):
    """Ask a yes/no question via input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n") 

def query_number(question, default=1):
    """Ask a numerical question via input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be a number or None (meaning
        an answer is required of the user).

    The "answer" return value is an int.
    """
    if default is None:
        prompt = " [] "
    else:
        prompt = " [%d] " % default

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return int(default)
        elif choice.isdigit():
            return int(choice)
        else:
            sys.stdout.write("Please respond with a number\n")                              
    
def secondsToStr(elapsed=None):
    if elapsed is None:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    else:
        return str(timedelta(seconds=elapsed))
    
def sigterm_handler(signal, frame):
    log.info('Received SIGTERM signal')
    sys.exit(0)

def setup_logger(logger_name, log_file, level=logging.DEBUG, console=False):
    try: 
        l = logging.getLogger(logger_name)
        formatter = logging.Formatter('[%(levelname)1.1s %(asctime)s] (%(name)-5s) %(message)s')
        if log_file is not None:
            fileHandler = logging.handlers.RotatingFileHandler(log_file, mode='a', maxBytes=2000000, backupCount=5)
            fileHandler.setFormatter(formatter)
        if console == True:
            formatter = logging.Formatter('[%(levelname)1.1s %(name)-5s] %(message)s')
            streamHandler = logging.StreamHandler()
            streamHandler.setFormatter(formatter)

        l.setLevel(level)
        if log_file is not None:
            l.addHandler(fileHandler)
        if console == True:
          l.addHandler(streamHandler)
             
    except Exception as e:
        print("Error in Logging setup: %s - do you have permission to write the log file??" % e)
        sys.exit(1)   
    
    
    
    
def main():
    '''
    Main routine
    '''
    global log
    import argparse
    parser = argparse.ArgumentParser(description='extract model info from Unifi')
    parser.add_argument('-f','--files', action="store", default='/usr/lib/unifi', help='unifi files base location (default: /usr/lib/unifi)')
    parser.add_argument('-u','--url', action="store", default=None, help='unifi url base location eg https://192.168.1.1:8443 (default: None)')
    parser.add_argument('-up','--update', action="store", default=None, help='models file to update eg models.json (default: None)')
    parser.add_argument('-o','--out', action="store", default='models_tmp.json', help='output file name (default: models_tmp.json)')
    parser.add_argument('-p','--pattern', action="store", default='U7HD', help='pattern to search for (default; U7HD)')
    parser.add_argument('-a','--all', action='store_true', help='get all matches (not just first) default: False)', default = False)
    parser.add_argument('-l','--log', action="store",default="None", help='log file. (default: None)')
    #parser.add_argument('-d','--dryrun', action='store_true', help='dry run (no file written)', default = False)
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
    
    log.info("Python Version: %s" % sys.version.replace('\n',''))
    log.info("Unifi Models Extract Version: %s" % __version__)
    
    #register signal handler
    signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        start = time.time()
        js_files = []
        if arg.url:
            log.info("Downloading javascript files, this can take a while...")
            tmpdir = 'tempDir'+os.sep
            if arg.debug and os.path.exists(tmpdir):
                arg.files = tmpdir
            else:
                base_url = arg.url+'/manage/'
                src = get_js_web_urls(base_url)
                for url in src:
                    file = get_js_from_web(base_url,url,tmpdir)
                    if file:
                        js_files.append(file)
        #log.info('found js files : %s' % js_files)
        if len(js_files) == 0:
            if not os.path.exists(arg.files):
                log.warn('This has to be run on the unifi controller, not your display device!')
                lop.warn('please supply a URL for your controller to run from your display device (eg -u https://192.168.1.1:8443)')
                os.exit(1)
            log.warn("Searching for models data in %s, This can take quite a while to run on large files!" % arg.files)
            js_files = get_js_files(arg.files)
        models_files = find_models_file(js_files, arg.pattern)
        models_files = deduplicate_list(models_files)
        json_list = find_json(models_files, arg.pattern, arg.all)
        json_models = consolidate_json(json_list)
        if len(json_models) > 0:
            with open(arg.out,'w+') as dataFile:
                dataFile.write(pprint(json_models))
            
            log.info('Got data for: %s' % get_summary(json_models))
            log.info('Models Data written to: %s' % arg.out)
            if arg.update:
                update_models(arg.update, json_models)
        else:
            log.warn('No Models Data found')
        
    except (KeyboardInterrupt, SystemExit):
        log.info("System exit Received - Exiting program")
        
    finally:
        log.debug("Program Exited")
        if arg.url and not arg.debug:
            if os.path.exists(tmpdir):
                import shutil
                shutil.rmtree(tmpdir)

        log.info("Elapsed time: %s" % secondsToStr(time.time()-start))

if __name__ == '__main__':
    main()
