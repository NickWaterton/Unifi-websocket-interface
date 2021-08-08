from pyunifiwsi import UnifiClient

unifi_username = ''
unifi_password = ''
IP = '192.168.1.2'
unifi_port = 443

client = UnifiClient(unifi_username, unifi_password, IP, unifi_port, ssl_verify=False)

data = client.devices()

print(data)