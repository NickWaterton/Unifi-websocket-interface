# Unifi-websocket-interface
A Websocket client for Unifi Controller and an example RPi based display program.

The websocket client is `unifi_client.py`

You can run it from the command line as an example, but mostly you would import it as a module.

`unify_client.py` is designed for python 3.4 and above, tested under python 3.5, but includes support for python 2.
It uses asyncio-http so you need to install `aiohttp` for python 3.x. You also need `asyncio` support.
`unifi_client_3.py` is the python 3 websocket client class, so it needs to be in the same directory as `unifi_client.py`

The Python 2 websocket uses `requests` and `websocket-client`, so you need to have both installed if you are using python 2.

`unifi_client.py` can also optionally publish data to an mqtt topic, for which you need `paho-mqtt` installed.

here is the help text:

```bash
nick@proliant:~/Scripts/Unifi-websocket-interface$ ./unifi_client.py -h
usage: unifi_client.py [-h] [-po UNIFI_PORT] [-s] [-b BROKER] [-p PORT]
                       [-u USER] [-pw PASSWD] [-pt PUB_TOPIC] [-l LOG] [-D]
                       [-V]
                       IP username password

Unifi MQTT-WS Client and Data

positional arguments:
  IP                    IP Address of Unifi Controller. (default: None)
  username              Unifi username. (default=None)
  password              unifi password. (default=None)

optional arguments:
  -h, --help            show this help message and exit
  -po UNIFI_PORT, --unifi_port UNIFI_PORT
                        unifi port (default=8443)
  -s, --ssl_verify      Verify Certificates (Default: False)
  -b BROKER, --broker BROKER
                        mqtt broker to publish sensor data to. (default=None)
  -p PORT, --port PORT  mqtt broker port (default=1883)
  -u USER, --user USER  mqtt broker username. (default=None)
  -pw PASSWD, --passwd PASSWD
                        mqtt broker password. (default=None)
  -pt PUB_TOPIC, --pub_topic PUB_TOPIC
                        topic to publish unifi data to. (default=/unifi_data/)
  -l LOG, --log LOG     log file. (default=None)
  -D, --debug           debug mode
  -V, --version         show program's version number and exit
```

You have to supply an ip (or FQDN), username and password (your Unifi login credentials), and optionally the port number (default is 8443).

Example command lines:
- `./unifi_client.py 192.168.x.x username password`
- `./unifi_client.py 192.168.x.x username password -D` with debugging output so that you can see the data
- `./unifi_client.py 192.168.x.x username password -po 8444` different default unifi port
- `./unifi_client.py 192.168.x.x username password -b 192.168.x.y` publish data to your mqtt broker at 192.168.x.y (no mqtt user or password)

`unifi.py` is an example __Python 3__ program using unifi_client.py to update a network status display on an RPi3 (800x600 size). It uses some obscure graphics libraries, so it's not easy to get working, but it's more of an example of how to get and use the data than anything else.
I did increase the size of the display to 1024x800 later.

To install the required graphics library for `unifi.py` proceed as follows:
1) Download the keyring file https://github.com/ev3dev/grx/files/2824733/keyring.tar.gz
2) `sudo cp ev3dev-archive-keyring.gpg /etc/apt/trusted.gpg.d/`
3) follow the instructions here https://github.com/ev3dev/grx/wiki/Developing-on-Raspberry-Pi ignoring the non-existent keyring link.

__NOTE__ You do not need console-runner, and I never got it to work anyway.
__NOTE__ Pay attention to the bitmap fonts comment, it is required.

`controller.py` is a module that gives access to the unifi API, and can be used for simple REST access to unifi data. it's cobbled together from various sources on the web (thanks to the contributors), I just added to it, it's not my work as such.

When the client first connects, it pulls the confguration data for __all__ your devices, so the first data hit is large, after that only updates are received from the controller. The data is in the same format as it is received, ie a list of dictionaries (received as json text). The current state is stored in the client in `UnifiClient.unifi_data`, which is only updated when you call `UnifiClient.devices()`. There are methods for accessing this data, all of which call the devices() method internally, so use the methods, rather than accessing unifi_data directly. Only sync and events methods are exposed, other types of updates (speed test and so on) are displayed in debug mode, but otherwise ignored. It would be easy to add handling for these updates though if you need them for something. Feel free to fork your own version.

All is tested on Unifi 5.10.17, with FW 4.0.21. I have various AP's (UAP-AC-XX) some Unifi Switches and a USG (3 port).

Currently running on an RPi3, Python 3.5.3, but also works in my development environment (Ubuntu 18.04.1, Python 3.6.7).

Hope you find it useful.
There is no warranty...
