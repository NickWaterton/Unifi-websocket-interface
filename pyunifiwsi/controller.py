import json
import logging
import requests
import shutil
import time
import warnings

'''
see https://ubntwiki.com/products/software/unifi-controller/api for api details
'''


"""For testing purposes:
logging.basicConfig(filename='pyunifi.log', level=logging.WARN,
                    format='%(asctime)s %(message)s')
"""
log = logging.getLogger(__name__)


class APIError(Exception):
    pass


def retry_login(func, *args, **kwargs):
    """To reattempt login if requests exception(s) occur at time of call"""
    def wrapper(*args, **kwargs):
        try:
            try:
                return func(*args, **kwargs)
            except (requests.exceptions.RequestException,
                    APIError) as err:
                log.warning("Failed to perform %s due to %s" % (func, err))
                controller = args[0]
                controller._login()
                return func(*args, **kwargs)
        except Exception as err:
            raise APIError(err)
    return wrapper


class Controller(object):

    """Interact with a UniFi controller.

    Uses the JSON interface on port 8443 (HTTPS) to communicate with a UniFi
    controller. Operations will raise unifi.controller.APIError on obvious
    problems (such as login failure), but many errors (such as disconnecting a
    nonexistant client) will go unreported.

    >>> from unifi.controller import Controller
    >>> c = Controller('192.168.1.99', 'admin', 'p4ssw0rd')
    >>> for ap in c.get_aps():
    ...     print 'AP named %s with MAC %s' % (ap.get('name'), ap['mac'])
    ...
    AP named Study with MAC dc:9f:db:1a:59:07
    AP named Living Room with MAC dc:9f:db:1a:59:08
    AP named Garage with MAC dc:9f:db:1a:59:0b
    

    """
    
    DPI_Category = {0	:{'cat':'Instant messaging', 'apps': {}},
                    1	:{'cat':'P2P', 'apps': {}},
                    3	:{'cat':'File Transfer', 'apps': {}},
                    4	:{'cat':'Streaming Media', 'apps': {}},
                    5	:{'cat':'Mail and Collaboration', 'apps': {}},
                    6	:{'cat':'Voice over IP', 'apps': {}},
                    7	:{'cat':'Database', 'apps': {}},
                    8	:{'cat':'Games', 'apps': {}},
                    9	:{'cat':'Network Management', 'apps': {}},
                    10	:{'cat':'Remote Access Terminals', 'apps': {}},
                    11	:{'cat':'Bypass Proxies and Tunnels', 'apps': {}},
                    12	:{'cat':'Stock Market', 'apps': {}},
                    13	:{'cat':'Web', 'apps': {}},
                    14	:{'cat':'Security Update', 'apps': {}},
                    15	:{'cat':'Web IM', 'apps': {}},
                    17	:{'cat':'Business', 'apps': {}},
                    18	:{'cat':'Network Protocols', 'apps': {}},
                    19	:{'cat':'Network Protocols', 'apps': {}},
                    20	:{'cat':'Network Protocols', 'apps': {}},
                    23	:{'cat':'Private Protocol', 'apps': {}},
                    24	:{'cat':'Social Network', 'apps': {}},
                    255	:{'cat':'Unknown', 'apps': {}},
                    }
               
    Device_Codes = {    'BZ2' : {'type' : 'uap', 'name' : 'UniFi AP'},
                        'BZ2LR' : {'type' : 'uap', 'name' : 'Unifi AP-LR'},
                        'U2HSR' : {'type' : 'uap', 'name' : 'Unifi AP-Outdoor+'},
                        'U2IW' : {'type' : 'uap', 'name' : 'Unifi AP-In Wall'},
                        'U2L48' : {'type' : 'uap', 'name' : 'Unifi AP-LR'},
                        'U2Lv2' : {'type' : 'uap', 'name' : 'Unifi AP-LR v2'},
                        'U2M' : {'type' : 'uap', 'name' : 'Unifi AP-Mini'},
                        'U2O' : {'type' : 'uap', 'name' : 'Unifi AP-Outdoor'},
                        'U2S48' : {'type' : 'uap', 'name' : 'Unifi AP'},
                        'U2Sv2' : {'type' : 'uap', 'name' : 'Unifi AP v2'},
                        'U5O' : {'type' : 'uap', 'name' : 'Unifi AP-Outdoor 5G'},
                        'U7E' : {'type' : 'uap', 'name' : 'Unifi AP-AC'},
                        'U7EDU' : {'type' : 'uap', 'name' : 'Unifi AP-AC-EDU'},
                        'U7Ev2' : {'type' : 'uap', 'name' : 'Unifi AP-AC v2'},
                        'U7HD' : {'type' : 'uap', 'name' : 'Unifi AP-HD'},
                        'U7SHD' : {'type' : 'uap', 'name' : 'Unifi AP-SHD'},
                        'U7NHD' : {'type' : 'uap', 'name' : 'Unifi AP-nanoHD'},
                        'UCXG' : {'type' : 'uap', 'name' : 'Unifi AP-XG'},
                        'UXSDM' : {'type' : 'uap', 'name' : 'Unifi AP-BaseStationXG'},
                        'UCMSH' : {'type' : 'uap', 'name' : 'Unifi AP-MeshXG'},
                        'U7IW' : {'type' : 'uap', 'name' : 'Unifi AP-AC-In Wall'},
                        'U7IWP' : {'type' : 'uap', 'name' : 'Unifi AP-AC-In Wall Pro'},
                        'U7MP' : {'type' : 'uap', 'name' : 'Unifi AP-AC-Mesh-Pro'},
                        'U7LR' : {'type' : 'uap', 'name' : 'Unifi AP-AC-LR'},
                        'U7LT' : {'type' : 'uap', 'name' : 'Unifi AP-AC-Lite'},
                        'U7O' : {'type' : 'uap', 'name' : 'Unifi AP-AC Outdoor'},
                        'U7P' : {'type' : 'uap', 'name' : 'Unifi AP-Pro'},
                        'U7MSH' : {'type' : 'uap', 'name' : 'Unifi AP-AC-Mesh'},
                        'U7PG2' : {'type' : 'uap', 'name' : 'Unifi AP-AC-Pro'},
                        'p2N' : {'type' : 'uap', 'name' : 'PicoStation M2'},
                        'US8' : {'type' : 'usw', 'name' : 'Unifi Switch 8'},
                        'US8P60' : {'type' : 'usw', 'name' : 'Unifi Switch 8 POE-60W'},
                        'US8P150' : {'type' : 'usw', 'name' : 'Unifi Switch 8 POE-150W'},
                        'S28150' : {'type' : 'usw', 'name' : 'Unifi Switch 8 AT-150W'},
                        'USC8' : {'type' : 'usw', 'name' : 'Unifi Switch 8'},
                        'US16P150' : {'type' : 'usw', 'name' : 'Unifi Switch 16 POE-150W'},
                        'S216150' : {'type' : 'usw', 'name' : 'Unifi Switch 16 AT-150W'},
                        'US24' : {'type' : 'usw', 'name' : 'Unifi Switch 24'},
                        'US24P250' : {'type' : 'usw', 'name' : 'Unifi Switch 24 POE-250W'},
                        'US24PL2' : {'type' : 'usw', 'name' : 'Unifi Switch 24 L2 POE'},
                        'US24P500' : {'type' : 'usw', 'name' : 'Unifi Switch 24 POE-500W'},
                        'S224250' : {'type' : 'usw', 'name' : 'Unifi Switch 24 AT-250W'},
                        'S224500' : {'type' : 'usw', 'name' : 'Unifi Switch 24 AT-500W'},
                        'US48' : {'type' : 'usw', 'name' : 'Unifi Switch 48'},
                        'US48P500' : {'type' : 'usw', 'name' : 'Unifi Switch 48 POE-500W'},
                        'US48PL2' : {'type' : 'usw', 'name' : 'Unifi Switch 48 L2 POE'},
                        'US48P750' : {'type' : 'usw', 'name' : 'Unifi Switch 48 POE-750W'},
                        'S248500' : {'type' : 'usw', 'name' : 'Unifi Switch 48 AT-500W'},
                        'S248750' : {'type' : 'usw', 'name' : 'Unifi Switch 48 AT-750W'},
                        'US6XG150' : {'type' : 'usw', 'name' : 'Unifi Switch 6XG POE-150W'},
                        'USXG' : {'type' : 'usw', 'name' : 'Unifi Switch 16XG'},
                        'UGW3' : {'type' : 'ugw', 'name' : 'Unifi Security Gateway 3P'},
                        'UGW4' : {'type' : 'ugw', 'name' : 'Unifi Security Gateway 4P'},
                        'UGWHD4' : {'type' : 'ugw', 'name' : 'Unifi Security Gateway HD'},
                        'UGWXG' : {'type' : 'ugw', 'name' : 'Unifi Security Gateway XG-8'},
                        'UP4' : {'type' : 'uph', 'name' : 'Unifi Phone-X'},
                        'UP5' : {'type' : 'uph', 'name' : 'Unifi Phone'},
                        'UP5t' : {'type' : 'uph', 'name' : 'Unifi Phone-Pro'},
                        'UP7' : {'type' : 'uph', 'name' : 'Unifi Phone-Executive'},
                        'UP5c' : {'type' : 'uph', 'name' : 'Unifi Phone'},
                        'UP5tc' : {'type' : 'uph', 'name' : 'Unifi Phone-Pro'},
                        'UP7c' : {'type' : 'uph', 'name' : 'Unifi Phone-Executive'},
                    }
    
                    
    def __init__(self, host, username, password, port=8443,
                 version='v5', site_id='default', ssl_verify=False):
        """
        :param host: the address of the controller host; IP or name
        :param username: the username to log in with
        :param password: the password to log in with
        :param port: the port of the controller host
        :param version: the base version of the controller API [v4|v5]
        :param site_id: the site ID to connect to
        :param ssl_verify: Verify the controllers SSL certificate,
            can also be "path/to/custom_cert.pem"
        """
        if float(version[1:]) < 4:
            raise APIError("%s controllers no longer supported" % version)

        self.host = host
        self.port = port
        self.version = version
        self.username = username
        self.password = password
        self.site_id = site_id
        self.url = 'https://' + host + ':' + str(port) + '/'
        self.ssl_verify = ssl_verify

        if ssl_verify is False:
            warnings.simplefilter("default", category=requests.packages.
                                  urllib3.exceptions.InsecureRequestWarning)
                                  
        self.unifi_os = self.is_unifi_os()

        self.session = requests.Session()
        self.session.verify = ssl_verify
        
        self.load_dpi_from_file()

        log.debug('Controller for %s', self.url)
        self._login()

    @staticmethod
    def _jsondec(data):
        obj = json.loads(data)
        if 'meta' in obj:
            if obj['meta']['rc'] != 'ok':
                raise APIError(obj['meta']['msg'])
        if 'data' in obj:
            return obj['data']
        else:
            return obj

    def _api_url(self):
        if self.unifi_os:
            return self.url + 'proxy/network/api/s/' + self.site_id + '/'
        else:
            return self.url + 'api/s/' + self.site_id + '/'

    @retry_login
    def _read(self, url, params=None):
        # Try block to handle the unifi server being offline.
        r = self.session.get(url, params=params)
        return self._jsondec(r.text)

    def _api_read(self, url, params=None):
        return self._read(self._api_url() + url, params)

    @retry_login
    def _write(self, url, params=None):
        r = self.session.post(url, json=params)
        return self._jsondec(r.text)

    def _api_write(self, url, params=None):
        return self._write(self._api_url() + url, params)

    @retry_login
    def _update(self, url, params=None):
        r = self.session.put(url, json=params)
        return self._jsondec(r.text)

    def _api_update(self, url, params=None):
        return self._update(self._api_url() + url, params)

    def _login(self):
        log.debug('login() as %s', self.username)

        # XXX Why doesn't passing in the dict work?
        params = {'username': self.username, 'password': self.password}
        if self.unifi_os:
            login_url = self.url + 'api/auth/login'
        else:
            login_url = self.url + 'api/login'

        r = self.session.post(login_url, json=params)
        if r.status_code is not 200:
            raise APIError("Login failed - status code: %i" % r.status_code)

    def _logout(self):
        log.debug('logout()')
        self._api_write('logout')
        
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
    
        r = requests.head('https://{}:{}'.format(self.host, self.port), verify=self.ssl_verify, timeout=10.0)
        if r.status_code == 200:
            log.info('Unifi OS controller detected')
            return True
        if r.status_code == 302:
            log.info('Unifi Standard controller detected')
            return False
        log.warning('Unable to determine controller type - using Unifi Standard controller')
        return False
        
    def update_dpi(self):
        try:
            url = 'https://fw-update.ubnt.com/api/firmware?filter=eq~~product~~usg-dpi&sort=-version&limit=1'
            resp = requests.get(url=url)
            data = resp.json() # Check the JSON Response Content documentation below
            dpi_url = data['_embedded']["firmware"][0]["_links"]["data"]["href"]
            resp = requests.get(url=dpi_url)
            import tarfile, io
            file_like_object = io.BytesIO(resp.content)
            tar = tarfile.open(mode='r', fileobj=file_like_object)
            #save the files for later if needed
            tar.extract('cats.xml')
            tar.extract('rule.xml')
            cats = tar.extractfile('cats.xml').read()
            rule = tar.extractfile('rule.xml').read()
            self.update_dpi_from_xml(cats, rule)
        except Exception as e:
            print('error updating DPI categories: %s' %e)
            
    def load_dpi_from_file(self):
        try:
            cats = rule = None
            with open('cats_default.xml', 'r') as f:
                cats = f.read()
            with open('rule_default.xml', 'r') as f:
                rule = f.read()
                
            self.update_dpi_from_xml(cats, rule)
        except Exception as e:
            print('error reading DPI categories: %s' %e)
        
    def update_dpi_from_xml(self, cats=None, rule=None):
        import xmltodict
        cats_dict = rule_dict ={}
        if cats:
            cat_dict = xmltodict.parse(cats)
        if rule:
            rule_dict = xmltodict.parse(rule)

        try:
            catagories = cat_dict["data"]["app_categories"]["app_category"]
            for cat in catagories:
                self.DPI_Category[int(cat["@id"])] = {}
                self.DPI_Category[int(cat["@id"])]['cat'] = cat["@name"]
        except keyError:
            pass
            
        try:
            catagories = rule_dict["data"]["app_categories"]["app_category"]
            for cat in catagories:
                self.DPI_Category[int(cat["@id"])] = {}
                self.DPI_Category[int(cat["@id"])]['cat'] = cat["@name"]
            applications = rule_dict["data"]["applications"]["application"]
            for app in applications:
                if self.DPI_Category[int(app["@cat_id"])].get('apps',None) is None:
                    self.DPI_Category[int(app["@cat_id"])]['apps'] = {}
                self.DPI_Category[int(app["@cat_id"])]['apps'][int(app["@app_id"])]= app["@name"]
        except KeyError:
            pass
        #print(json.dumps(self.DPI_Category, indent=2))
        #print(json.dumps(rule_dict, indent=2))
        #print(self.DPI_Category)

    def switch_site(self, name):
        """
        Switch to another site

        :param name: Site Name
        :return: True or APIError
        """
        for site in self.get_sites():
            if site['desc'] == name:
                self.site_id = site['name']
                return True
        raise APIError("No site %s found" % name)
        
    def get_site_test(self):
        return self._read(self.url+'api/device/general')
        
    def get_system_info(self):
        return self._read(self.url+'api/system')
        
    def get_site_stats(self):
        """Return a list of all Sites and stats."""
        return self._read(self.url+'api/stat/sites')

    def get_alerts(self):
        """Return a list of all Alerts."""
        return self._api_read('stat/alarm')
        
    def get_site_dpi_stats(self, type=True):
        """Return a list of site DPI stats"""
        params = {
            'type': 'by_app' if type else 'by_cat' }
        result_list = self._api_write('stat/sitedpi', params)
        for result in result_list:
            if type:
                apps = result['by_app']
            else:
                apps = result['by_cat']
            for app in apps:
                try:
                    cat_id = app.get('cat',255)
                    app['cat_name'] = self.DPI_Category[cat_id]['cat']
                    if cat_id < 128:
                        cat_id+=128
                        app['cat_name_ext'] = self.DPI_Category[cat_id]['cat']
                    else:
                        app['cat_name_ext'] = app['cat_name']
                    if type:
                        app_id = int(app.get('app',65535))
                        for appid in self.DPI_Category[cat_id]['apps'].keys():
                            if app_id == appid:
                                app['app_name'] = self.DPI_Category[cat_id]['apps'][app_id]
                                break
                        else:
                            app['app_name'] = str(app.get('app', '?'))+'_unknown'
                except KeyError:
                    app['cat_name'] = str(app.get('cat', '?'))+'_unknown'
                    app['cat_name_ext'] = str(app.get('cat', '?'))+'_unknown'
                    if type:
                        app['app_name'] = str(app.get('app', '?'))+'_unknown'
        return result_list
        
    def get_sta_dpi_stats(self, type=True):
        """Return a list of station DPI stats"""
        params = {
            'type': 'by_app' if type else 'by_cat' }
        result_list = self._api_write('stat/stadpi', params)
        for result in result_list:
            if type:
                apps = result['by_app']
            else:
                apps = result['by_cat']
            for app in apps:
                try:
                    cat_id = app.get('cat',255)
                    app['cat_name'] = self.DPI_Category[cat_id]['cat']
                    if cat_id < 128:
                        cat_id+=128
                        app['cat_name_ext'] = self.DPI_Category[cat_id]['cat']
                    else:
                        app['cat_name_ext'] = app['cat_name']
                    if type:
                        app_id = int(app.get('app',65535))
                        for appid in self.DPI_Category[cat_id]['apps'].keys():
                            if app_id == appid:
                                app['app_name'] = self.DPI_Category[cat_id]['apps'][app_id]
                                break
                        else:
                            app['app_name'] = str(app.get('app', '?'))+'_unknown'
                except KeyError:
                    app['cat_name'] = str(app.get('cat', '?'))+'_unknown'
                    app['cat_name_ext'] = str(app.get('cat', '?'))+'_unknown'
                    if type:
                        app['app_name'] = str(app.get('app', '?'))+'_unknown'
        return result_list
        
    def get_roaugeaps(self):
        """Return a list of neighbouring APs"""
        return self._api_read('stat/rogueap')
        
    def get_roaugeaps_since(self, since=1):
        """Return a list of neighbouring APs seen withing "since" hours"""
        params = {
            'within': int(since) }
        return self._api_write('stat/rogueap', params)
        
    def get_stats_dyndns(self):
        """Return a list of dyndns configuration and stats"""
        return self._api_read('stat/dynamicdns')
        
    def get_switch_ports(self):
        """Return a list of (usg)? switch port configuration"""
        return self._api_read('rest/portconf')

    def get_alerts_unarchived(self):
        """Return a list of Alerts unarchived."""
        return self._api_write('stat/alarm', params={'archived': False})

    def get_statistics_last_24h(self):
        """Returns statistical data of the last 24h"""
        return self.get_statistics_24h(time.time())

    def get_statistics_24h(self, endtime):
        """Return statistical data last 24h from time"""

        params = {
            #'attrs': ["bytes", "num_sta", "time"],
            'attrs': ['bytes', 'wan-tx_bytes', 'wan-rx_bytes', 'wlan_bytes', 'num_sta', 'lan-num_sta', 'wlan-num_sta', 'time', 'rx_bytes', 'tx_bytes'],
            'start': int(endtime - 86400) * 1000,
            'end': int(endtime - 3600) * 1000}
        return self._write(self._api_url() + 'stat/report/hourly.site', params)

    def get_events(self):
        """Return a list of all Events."""
        return self._api_read('stat/event')
        
    def get_devices(self):
        """Return a list of all devices
        """
        return self._api_read('stat/device-basic')

    def get_aps(self):
        """Return a list of all devices (inc switches),
        with significant information about each.
        """
        # Set test to 0 instead of NULL
        params = {'_depth': 2, 'test': 0}
        return self._api_read('stat/device', params)

    def get_client(self, mac):
        """Get details about a specific client"""

        # stat/user/<mac> works better than stat/sta/<mac>
        # stat/sta seems to be only active clients
        # stat/user includes known but offline clients
        return self._api_read('stat/user/' + mac)[0]

    def get_clients(self):
        """Return a list of all active clients,
        with significant information about each.
        """
        return self._api_read('stat/sta')

    def get_users(self):
        """Return a list of all known clients,
        with significant information about each.
        """
        return self._api_read('list/user')

    def get_user_groups(self):
        """Return a list of user groups with its rate limiting settings."""
        return self._api_read('list/usergroup')

    def get_sysinfo(self):
        """Return basic system informations."""
        return self._api_read('stat/sysinfo')

    def get_healthinfo(self):
        """Return health information."""
        return self._api_read('stat/health')

    def get_sites(self):
        """Return a list of all sites,
        with their UID and description"""
        return self._read(self.url + 'api/self/sites')

    def get_wlan_conf(self):
        """Return a list of configured WLANs
        with their configuration parameters.
        """
        return self._api_read('list/wlanconf')

    def _run_command(self, command, params={}, mgr='stamgr'):
        log.debug('_run_command(%s)', command)
        params.update({'cmd': command})
        return self._write(self._api_url() + 'cmd/' + mgr, params=params)

    def _mac_cmd(self, target_mac, command, mgr='stamgr', params={}):
        log.debug('_mac_cmd(%s, %s)', target_mac, command)
        params['mac'] = target_mac
        return self._run_command(command, params, mgr)

    def create_site(self, desc='desc'):
        """Create a new site.

        :param desc: Name of the site to be created.
        """
        return self._run_command('add-site', params={"desc": desc},
                                 mgr='sitemgr')

    def block_client(self, mac):
        """Add a client to the block list.

        :param mac: the MAC address of the client to block.
        """
        return self._mac_cmd(mac, 'block-sta')

    def unblock_client(self, mac):
        """Remove a client from the block list.

        :param mac: the MAC address of the client to unblock.
        """
        return self._mac_cmd(mac, 'unblock-sta')

    def disconnect_client(self, mac):
        """Disconnect a client.

        Disconnects a client, forcing them to reassociate. Useful when the
        connection is of bad quality to force a rescan.

        :param mac: the MAC address of the client to disconnect.
        """
        return self._mac_cmd(mac, 'kick-sta')

    def restart_ap(self, mac):
        """Restart an access point (by MAC).

        :param mac: the MAC address of the AP to restart.
        """
        return self._mac_cmd(mac, 'restart', 'devmgr')

    def restart_ap_name(self, name):
        """Restart an access point (by name).

        :param name: the name address of the AP to restart.
        """
        if not name:
            raise APIError('%s is not a valid name' % str(name))
        for ap in self.get_aps():
            if ap.get('state', 0) == 1 and ap.get('name', None) == name:
                return self.restart_ap(ap['mac'])

    def archive_all_alerts(self):
        """Archive all Alerts"""
        return self._run_command('archive-all-alarms', mgr='evtmgr')

    def create_backup(self):
        """Ask controller to create a backup archive file

        ..warning:
            This process puts significant load on the controller
            and may render it partially unresponsive for other requests.

        :return: URL path to backup file
        """
        res = self._run_command('backup', mgr='system')
        return res[0]['url']

    def get_backup(self, download_path=None, target_file='unifi-backup.unf'):
        """
        :param download_path: path to backup; if None is given
            one will be created
        :param target_file: Filename or full path to download the
            backup archive to, should have .unf extension for restore.
        """
        if not download_path:
            download_path = self.create_backup()

        r = self.session.get(self.url + download_path, stream=True)
        with open(target_file, 'wb') as _backfh:
            return shutil.copyfileobj(r.raw, _backfh)

    def authorize_guest(self, guest_mac, minutes, up_bandwidth=None,
                        down_bandwidth=None, byte_quota=None, ap_mac=None):
        """
        Authorize a guest based on his MAC address.

        :param guest_mac: the guest MAC address: 'aa:bb:cc:dd:ee:ff'
        :param minutes: duration of the authorization in minutes
        :param up_bandwidth: up speed allowed in kbps
        :param down_bandwidth: down speed allowed in kbps
        :param byte_quota: quantity of bytes allowed in MB
        :param ap_mac: access point MAC address
        """
        cmd = 'authorize-guest'
        params = {'mac': guest_mac, 'minutes': minutes}

        if up_bandwidth:
            params['up'] = up_bandwidth
        if down_bandwidth:
            params['down'] = down_bandwidth
        if byte_quota:
            params['bytes'] = byte_quota
        if ap_mac:
            params['ap_mac'] = ap_mac
        return self._run_command(cmd, params=params)

    def unauthorize_guest(self, guest_mac):
        """
        Unauthorize a guest based on his MAC address.

        :param guest_mac: the guest MAC address: 'aa:bb:cc:dd:ee:ff'
        """
        cmd = 'unauthorize-guest'
        params = {'mac': guest_mac}
        return self._run_command(cmd, params=params)

    def get_firmware(self, cached=True, available=True,
                     known=False, site=False):
        """
        Return a list of available/cached firmware versions

        :param cached: Return cached firmwares
        :param available: Return available (and not cached) firmwares
        :param known: Return only firmwares for known devices
        :param site: Return only firmwares for on-site devices
        :return: List of firmware dicts
        """
        res = []
        if cached:
            res.extend(self._run_command('list-cached', mgr='firmware'))
        if available:
            res.extend(self._run_command('list-available', mgr='firmware'))

        if known:
            res = [fw for fw in res if fw['knownDevice']]
        if site:
            res = [fw for fw in res if fw['siteDevice']]
        return res

    def cache_firmware(self, version, device):
        """
        Cache the firmware on the UniFi Controller

        .. warning:: Caching one device might very well cache others,
            as they're on shared platforms

        :param version: version to cache
        :param device: device model to cache (e.g. BZ2)
        :return: True/False
        """
        return self._run_command(
            'download', mgr='firmware',
            params={'device': device, 'version': version})[0]['result']

    def remove_firmware(self, version, device):
        """
        Remove cached firmware from the UniFi Controller

        .. warning:: Removing one device's firmware might very well remove
            others, as they're on shared platforms

        :param version: version to cache
        :param device: device model to cache (e.g. BZ2)
        :return: True/false
        """
        return self._run_command(
            'remove', mgr='firmware',
            params={'device': device, 'version': version})[0]['result']

    def get_tag(self):
        """Get all tags and their member MACs"""
        return self._api_read('rest/tag')

    def upgrade_device(self, mac, version):
        """
        Upgrade a device's firmware to verion
        :param mac: MAC of dev
        :param version: version to upgrade to
        """
        self._mac_cmd(mac, 'upgrade', mgr='devmgr',
                      params={'upgrade_to_firmware': version})

    def provision(self, mac):
        """
        Force provisioning of a device
        :param mac: MAC of device
        """
        self._mac_cmd(mac, 'force-provision', mgr='devmgr')

    def get_setting(self, section=None, super=False):
        """
        Return settings for this site or controller

        :param super: Return only controller-wide settings
        :param section: Only return this/these section(s)
        :return: {section:settings}
        """
        res = {}
        settings = self._api_read('get/setting')
        if section and not isinstance(section, (list, tuple)):
            section = [section]

        for s in settings:
            s_sect = s['key']
            if (super and 'site_id' in s) or \
               (not super and 'site_id' not in s) or \
               (section and s_sect not in section):
                continue
            for k in ('_id', 'site_id', 'key'):
                s.pop(k, None)
            res[s_sect] = s
        return res

    def update_setting(self, settings):
        """
        Update settings

        :param settings: {section:{settings}}
        :return: resulting settings
        """
        res = []
        for sect, setting in settings.items():
            res.extend(self._api_write('set/setting/' + sect, setting))
        return res

    def update_user_group(self, group_id, down_kbps=-1, up_kbps=-1):
        """
        Update user group bandwidth settings

        :param group_id: Group ID to modify
        :param down_kbps: New bandwidth in KBPS for download
        :param up_kbps: New bandwidth in KBPS for upload
        """

        res = None
        groups = self.get_user_groups()

        for group in groups:
            if group["_id"] == group_id:
                # Apply setting change
                res = self._api_update("rest/usergroup/{0}".format(group_id), {
                    "qos_rate_max_down": down_kbps,
                    "qos_rate_max_up": up_kbps,
                    "name": group["name"],
                    "_id": group_id,
                    "site_id": self.site_id
                })
                return res

        raise ValueError("Group ID {0} is not valid.".format(group_id))

    def set_client_alias(self, mac, alias):
        """
        Set the client alias. Set to "" to reset to default
        :param mac: The MAC of the client to rename
        :param alias: The alias to set
        """
        client = self.get_client(mac)['_id']
        return self._api_update('rest/user/' + client, {'name': alias})
