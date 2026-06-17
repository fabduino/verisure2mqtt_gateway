# Verisure sensors packets capture to mqtt gateway
# ESP-WROOM-32 and CC1101 E07-M1101D

# Original version (cc1101): Copyright (c) 2025 Adam Kuczyński
# Original version (mqtt): https://randomnerdtutorials.com/micropython-mqtt-esp32-esp8266/
# Merged version and Verisure parameters: Copyright 2026 (c) Pierre Serrier
# Released under MIT license

import time
import gc
import machine
import network
import ubinascii
import ujson
import esp

from machine import Pin
from cc1101 import CC1101
from umqttsimple import MQTTClient
from veri_mqtt_parameters import (
    ssid, password, mqtt_server, mqtt_user, mqtt_pass,
    pub_topic, sub_topic, verisure_id, debug_flag
)

# Configuration constants
WIFI_TIMEOUT_MS = 20000
MQTT_RECONNECT_DELAY_S = 10
EXPECTED_PACKET_SIZE = 13
RF_POLL_INTERVAL_MS = 10
GARBAGE_COLLECT_INTERVAL = 100

# Disable debug output
esp.osdebug(None)
gc.collect()

# Global state
led = None
rf = None
client = None
loop_count = 0


################## FUNCTIONS ##############################

def crc_verisure(data):
    """Calculate Verisure CRC: sum of all bytes + length."""
    crc = 0
    size = data[0] - 1
    for i in range(1, size + 1):
        crc += data[i]
    crc += size
    return crc % 256


def check_crc_verisure(data):
    """Verify Verisure packet CRC."""
    size = data[0]
    return crc_verisure(data) == data[size]


def check_network_verisure(data):
    """Verify packet belongs to configured Verisure network."""
    return (data[1] == verisure_id[0] and 
            data[2] == verisure_id[1] and 
            data[3] == verisure_id[2])


def parse_pkt_verisure(data):
    """Parse Verisure packet and return JSON string or empty string on error."""
    if data[0] != 10:
        return ""
    
    packet_dict = {}
    
    if data[7] == 3 or data[7] == 2:
        packet_dict["sensorType"] = "SWITCH"
        packet_dict["values"] = [data[4], "OPEN" if data[7] == 3 else "CLOSED"]
    elif data[7] == 16:
        packet_dict["sensorType"] = "PIR"
        packet_dict["values"] = [data[4], "TRIG"]
    else:
        return ""  # Unknown sensor type
    
    return ujson.dumps(packet_dict)


def sub_cb(topic, msg):
    """MQTT subscription callback."""
    if debug_flag == "ON":
        print(f"MQTT received on {topic}: {msg}")


def connect_wifi():
    """Connect to WiFi network with timeout."""
    print("Connecting to WiFi...")
    station = network.WLAN(network.STA_IF)
    station.active(True)
    station.connect(ssid, password)
    
    blink = True
    start_time = time.ticks_ms()
    
    while not station.isconnected():
        if time.ticks_diff(time.ticks_ms(), start_time) > WIFI_TIMEOUT_MS:
            print("WiFi connection timeout!")
            return False
        
        blink = not blink
        led(blink)
        time.sleep_ms(200)
    
    led(0)
    print(f"WiFi connected: {station.ifconfig()}")
    return True


def init_rf():
    """Initialize CC1101 RF module."""
    global rf
    print("Initializing RF module...")
    
    rf = CC1101()
    rf.reset()
    
    # Wait for CC1101 to respond
    timeout = 0
    while rf.read_register(CC1101.VERSION, CC1101.STATUS_REGISTER) < 20:
        timeout += 1
        if timeout > 100:
            print("RF module failed to respond!")
            return False
        time.sleep_ms(10)
    
    print("RF module detected")
    
    # Configure CC1101 registers for Verisure
    verisure_config = bytearray(
        b'\x0B\x2E\x06\x07\x45\x53\x3D\x64\x01\x00\x00\x06\x49\x21\x65\x6C'
        b'\x5A\x83\x02\x02\xF8\x32\x07\x30\x18\x16\x1C\xC7\x00\xB2\x87\x6B'
        b'\xF8\x56\x10\xE9\x2A\x00\x1F\x41\x00\x59\x7F'
    )
    rf.write_burst(0, verisure_config)
    rf.write_command(CC1101.SRX)
    print("RF module configured and in RX mode")
    return True


def connect_mqtt():
    """Connect to MQTT broker and subscribe to topic."""
    global client
    print("Connecting to MQTT broker...")
    
    try:
        client_id = ubinascii.hexlify(machine.unique_id())
        client = MQTTClient(client_id, mqtt_server, user=mqtt_user, password=mqtt_pass)
        client.set_callback(sub_cb)
        client.connect()
        client.subscribe(sub_topic)
        print(f"Connected to MQTT broker: {mqtt_server}")
        return True
    except Exception as e:
        print(f"MQTT connection failed: {e}")
        return False


def process_rf_packet(rxdata):
    """Process received RF packet and publish to MQTT if valid."""
    if debug_flag == "ON":
        print(f"RF data: {rxdata}")
    
    if not check_crc_verisure(rxdata):
        if debug_flag == "ON":
            print("CRC check failed")
        return False
    
    if not check_network_verisure(rxdata):
        if debug_flag == "ON":
            print("Network ID mismatch")
        return False
    
    msg = parse_pkt_verisure(rxdata)
    if not msg:
        if debug_flag == "ON":
            print("Failed to parse packet")
        return False
    
    try:
        client.publish(pub_topic, msg)
        print(f"Published: {msg}")
        return True
    except Exception as e:
        print(f"MQTT publish failed: {e}")
        return False


def init():
    """Initialize all hardware and connections."""
    global led
    
    print("*** VERISURE sensors to MQTT Gateway ***")
    led = Pin(2, Pin.OUT)
    led(0)
    
    if not connect_wifi():
        print("Restarting due to WiFi failure...")
        time.sleep(5)
        machine.reset()
    
    if not init_rf():
        print("Restarting due to RF initialization failure...")
        time.sleep(5)
        machine.reset()
    
    if not connect_mqtt():
        print("Restarting due to MQTT connection failure...")
        time.sleep(MQTT_RECONNECT_DELAY_S)
        machine.reset()


def main():
    """Main loop."""
    global loop_count
    
    init()
    
    print("Entering main loop...")
    
    while True:
        try:
            # Check MQTT messages
            client.check_msg()
            
            # Set RF to RX mode
            rf.write_command(CC1101.SRX)
            
            # Check for incoming RF data
            size = rf.read_register(CC1101.RXBYTES, CC1101.STATUS_REGISTER) & CC1101.BITS_RX_BYTES_IN_FIFO
            
            if size == EXPECTED_PACKET_SIZE:
                led(1)
                rxdata = rf.recv()
                success = process_rf_packet(rxdata)
                led(0 if success else 1)
                time.sleep_ms(100)
            else:
                time.sleep_ms(RF_POLL_INTERVAL_MS)
            
            # Periodic garbage collection
            loop_count += 1
            if loop_count >= GARBAGE_COLLECT_INTERVAL:
                gc.collect()
                loop_count = 0
                
        except OSError as e:
            print(f"Error in main loop: {e}")
            print("Attempting MQTT reconnection...")
            time.sleep(MQTT_RECONNECT_DELAY_S)
            try:
                if not connect_mqtt():
                    machine.reset()
            except Exception as reconnect_err:
                print(f"Reconnection failed: {reconnect_err}")
                machine.reset()


if __name__ == "__main__":
    main()
