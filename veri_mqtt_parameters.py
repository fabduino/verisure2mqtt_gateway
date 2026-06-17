# Configuration file for verisure2mqtt_gateway.py

# wifi credentials 
ssid = 'REPLACE_WITH_YOUR_SSID'		#your wifi ssid
password = 'REPLACE_WITH_YOUR_PASSWORD#'	#your wifi password

# mqtt broker parameters
mqtt_server = 'REPLACE_WITH_YOUR_MQTT_BROKER_IP'	#your mqtt boker ip address 
mqtt_user = 'REPLACE_WITH_YOUR_MQTT_USERNAME'		#your user account on mqtt broker
mqtt_pass = 'REPLACE_WITH_YOUR_MQTT_PASSWORD'		#your user password on mqtt broker

# topics mqtt
pub_topic = b'home/verisure/sensor'	#your plublish topic
sub_topic = b'home/verisure/command'	#your subscribe topic (optionnal)

# Verisure "Network id"
verisure_id = bytearray(b'\xDB\xE7\x14')	#your verisure network id 

# debug indicator
debug_flag = 'Off'							# debug flag, put ON for debug
