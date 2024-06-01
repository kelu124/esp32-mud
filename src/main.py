import network
network.WLAN(network.AP_IF).active(False)
wlan = network.WLAN(network.STA_IF)
#wlan.config(pm=wlan.PM_NONE)
wlan.active(True)

wlan.config(txpower=18)

wlan.connect('SFR_9770', 'gkk33ckmf4qay57jnhe2')

while not wlan.isconnected():
    pass

print('Network config:', wlan.ifconfig())

import simplemud