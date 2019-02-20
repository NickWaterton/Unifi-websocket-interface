# Unifi-websocket-interface
A Websocket client for Unifi Controller and an example RPi based display program.

The websocket client is `unifi_client.py`

You can run it from the command line as an example, but mostly you would import it as a module.

it should run under python 2 or 3, but it's really designed and tested under python 3.5.
It uses asyncio-http so you need to install `aiohttp` for python 3.x. You also need `asyncio` support.

For Python 2 it uses `requests` and `websocket-client`, so you need to have both installed.

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

`unifi.py` is an example program using unifi_client.py to update a network status display on an RPi3 (800x600 size). It uses some obscure graphics libraries, so it's not easy to get working, but it's more of an example of how to get and use the data than anything else.

`controller.py` is a module that gives access to the unifi API, and can be used for simple REST access to unifi data. it's cobbled together from various sources on the web 9thanks to the contributors), I just added to it, it's not my work as such.


All is tested on Unifi 5.10.17, with FW 4.0.21. I have various AP's (UAP-AC-XX) some Unifi Switches and a USG (3 port).

Currently running on an RPi3, Python 3.5.3, but also works in my development environment (Ubuntu 18.04.1, Python 3.6.7).

Hope you find it useful.
There is no warranty...