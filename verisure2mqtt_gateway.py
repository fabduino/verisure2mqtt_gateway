# Verisure sensors packets capture to mqtt gateway
# ESP-WROOM-32 and CC1101 E07-M1101D

# Original version (cc1101): Copyright (c) 2025 Adam Kuczyński
# Original version (mqtt): https://randomnerdtutorials.com/micropython-mqtt-esp32-esp8266/
# Merged version and Verisure parameters: Copyright 2026 (c) Pierre Serrier
# Released under MIT license
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import time
from cc1101 import CC1101
from machine import Pin
from veri_mqtt_parameters import verisure_id, debug_flag
import ujson

from umqttsimple import MQTTClient
import ubinascii
import machine
import micropython
import network
import esp
esp.osdebug(None)
import gc
gc.collect()

from veri_mqtt_parameters import ssid, password, mqtt_server, mqtt_user, mqtt_pass, pub_topic, sub_topic

################## FUNCTIONS ##############################
def crc_verisure(data):			#Sum of all bytes + length, apended end of message
  crc = 0
  size = data[0]-1		# La taille utile du packet est en position 0, le CRC reçu est en dernière position de la taille utile
  for i in range (1, size+1):
    crc += data[i]
  crc += size
  crc = crc % 256			# le crc est sur un seul octet
  return crc

def check_crc_verisure(data):
    size = data[0]
    if crc_verisure(data) == data[size]:
        return True
    return False

def check_network_verisure(data):
    if data[1] == verisure_id[0] and data[2] == verisure_id[1] and data[3] == verisure_id[2]:
        return True
    return False

def parse_pkt_verisure(data):
    if  data[0] != 10:
        return 0
    dict = {}
    if data[7] == 3 or data[7] == 2:
      dict["sensorType"] = "SWITCH"
      if data[7] == 3:
        dict["values"] = [data[4],"OPEN"]
      else:
        dict["values"] = [data[4],"CLOSED"]
    if data[7] == 16:
        dict["sensorType"] = "PIR"
        dict["values"] = [data[4],"TRIG"]
    encoded = ujson.dumps(dict)
    return encoded

def sub_cb(topic, msg):
  print(topic, msg)
  if topic == sub_topic:
    print('ESP received message')

def connect_and_subscribe():
  global client_id, mqtt_server, sub_topic
  client = MQTTClient(client_id, mqtt_server, user=mqtt_user, password=mqtt_pass)
  client.set_callback(sub_cb)
  client.connect()
  client.subscribe(sub_topic)
  print('Connected to %s MQTT broker, subscribed to %s topic' % (mqtt_server, sub_topic))
  return client

def restart_and_reconnect():
  print('Failed to connect to MQTT broker. Reconnecting...')
  time.sleep(10)
  machine.reset()
  if topic == sub_topic:
    print('ESP received message')

###################### PROGRAM ###############################
######## Init
print('*** VERISURE sensors to MQTT Gateway ***')
led = Pin(2, Pin.OUT)						# integrated led

# wifi connection
station = network.WLAN(network.STA_IF)
station.active(True)
station.connect(ssid, password)

blink = True
led(blink)				# turn on the in led
while station.isconnected() == False:
  blink = not blink
  led(blink)			# blink the in led
  time.sleep(0.2)
  pass
led(0)					#turn off the in led

print('WIFI connection successful')
print(station.ifconfig())

# Registers configuration
verisure = bytearray(b'\x0B\x2E\x06\x07\x45\x53\x3D\x64\x01\x00\x00\x06\x49\x21\x65\x6C\x5A\x83\x02\x02\xF8\x32\x07\x30\x18\x16\x1C\xC7\x00\xB2\x87\x6B\xF8\x56\x10\xE9\x2A\x00\x1F\x41\x00\x59\x7F\x3F\x81\x31\x09')

# Init CC1101
rf = CC1101()
rf.reset()

# Test SPI and CC1101 responding
while rf.read_register(CC1101.VERSION, CC1101.STATUS_REGISTER) < 20:
  pass
print('Connection RF OK')

# Init CC1101 registers
rf.write_burst(0, verisure)			#initialisation avec les valeurs Verisure
#print (rf.read_burst(0, 47))		# 
print('Init. RF OK')

# Set CC1101 in receive mode
rf.write_command(CC1101.SRX)

# Mqtt connection
client_id = ubinascii.hexlify(machine.unique_id())
try:
  client = connect_and_subscribe()
except OSError as e:
  restart_and_reconnect()

########### Loop
while True:
    try:
      client.check_msg()			# check mqtt sub_topic
      rf.write_command(CC1101.SRX)
      size = rf.read_register(CC1101.RXBYTES, CC1101.STATUS_REGISTER) & CC1101.BITS_RX_BYTES_IN_FIFO # check CC1101 RX FIFO
      if size == 13:
        led(1)					# turn on the in led
        #print ('LEN=',size)
        rxdata = rf.recv()
        if debug_flag == 'ON':
          print ('RF data->',rxdata)
          #print (f'CRC calculated=0x{crc_verisure(rxdata):02x}')
          #print ('Verif.CRC->',check_crc_verisure(rxdata))
          #print ('Verif. Network->', check_network_verisure(rxdata))
          
        if check_crc_verisure(rxdata) and check_network_verisure(rxdata):			# check packet OK
          msg = parse_pkt_verisure(rxdata)										# translate packet in JSON format
          print('Payload MQTT->',msg)   
          client.publish(pub_topic, msg)					# publish JSON on mqtt topic
          led(0)				# turn off the in led
      time.sleep_ms(10)
    except OSError as e:
     restart_and_reconnect()