import network
network.WLAN(network.AP_IF).active(False)
wlan = network.WLAN(network.STA_IF)
#wlan.config(pm=wlan.PM_NONE)
wlan.active(True)

wlan.config(txpower=18)

wlan.connect('XXX', 'XXX')

while not wlan.isconnected():
    pass

print('Network config:', wlan.ifconfig())

import machine
i2c = machine.I2C(sda=machine.Pin(8), scl=machine.Pin(9))
from ssd1306 import SSD1306_I2C
oled = SSD1306_I2C(128, 32, i2c)
oled.poweron()

oled.text('Network config:', 0, 0)
oled.text("@"+str(wlan.ifconfig()[0]), 0, 15)
oled.show()

import simplemud
