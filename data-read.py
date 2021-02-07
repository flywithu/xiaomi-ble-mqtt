#!/usr/bin/python3

from mitemp.mitemp_bt.mitemp_bt_poller import MiTempBtPoller
from mitemp.mitemp_bt.mitemp_bt_poller import MI_TEMPERATURE, MI_HUMIDITY, MI_BATTERY

from mitemp.lywsd03mmc.mitemp_bt_poller import MiTempBtPoller as MiTempBtPoller_03


from btlewrap.bluepy import BluepyBackend
from bluepy.btle import BTLEException
import paho.mqtt.publish as publish
import traceback
import configparser
import os
import json
import datetime
import sys
import psutil
# import logging
# from mitemp.lywsd03mmc.mitemp_bt_poller import _LOGGER

# _LOGGER.setLevel(logging.DEBUG)
# stream_hander = logging.StreamHandler()
# _LOGGER.addHandler(stream_hander)


###################### Remove zombie bluepy-helper pip3 install psutil
##workaround 
PROCNAME = "bluepy-helper"

for proc in psutil.process_iter():
    # check whether the process name matches
    if proc.name() == PROCNAME:
        proc.kill()
##################################################################

workdir = os.path.dirname(os.path.realpath(__file__))
config = configparser.ConfigParser()
config.read("{0}/devices.ini".format(workdir))

devices = config.sections()


# Averages
averages = configparser.ConfigParser()
averages.read("{0}/averages.ini".format(workdir))

messages = []


for device in devices:

    mac = config[device].get("device_mac")
    if config[device].get("device") == "LYWSD03MMC":
        poller = MiTempBtPoller_03(mac, BluepyBackend, ble_timeout=config[device].getint("timeout", 10))
    elif config[device].get("device") == "MJ_HT_V1":
        poller = MiTempBtPoller(mac, BluepyBackend, ble_timeout=config[device].getint("timeout", 10))

    try:

        temperature = poller.parameter_value(MI_TEMPERATURE)
        humidity = poller.parameter_value(MI_HUMIDITY)
        battery = poller.parameter_value(MI_BATTERY)
      
     
        data = json.dumps({
            "temperature": temperature,
            "humidity": humidity,
            "battery": battery
        })



        # Check averages
        avg = []
        average_count = config[device].getint("average")
        if average_count:
            if mac in averages.sections():
                avg = json.loads(averages[mac]["avg"])

            # Add average
            avg.insert(0, data)

            # Strip data
            avg = avg[0:average_count]

            # Calc averages
            temperature = 0
            humidity = 0
            battery = 0

            for a in avg:
                al = json.loads(a)
                temperature += al["temperature"]
                humidity += al["humidity"]
                battery += al["battery"]

            temperature = round(temperature / len(avg), 1)
            humidity = round(humidity / len(avg), 1)
            battery = round(battery / len(avg), 1)

            # Convert averages
            averages[mac] = {}
            averages[mac]["avg"] = json.dumps(avg)

            # Rewrite data
            data = json.dumps({
                "temperature": temperature,
                "humidity": humidity,
                "battery": int(battery),
                "average": len(avg)
            })

        print(datetime.datetime.now(), device, " : ", data)
        i=0
        cal_unit=dict()
        cal_unit['humidity']="%"
        cal_unit['battery']="%"
        cal_unit['temperature']='°C'

        for device_class in config[device].get("device_class").split(":"):
            


            dataconfig=json.dumps(
                {
                "device_class": device_class,
                "name": device_class.capitalize(),
                "state_topic": config[device].get("topic")+"/state",
                "value_template": "{{value_json."+device_class+"}}",        
                "unique_id":config[device].get("device_mac")+"_"+str(i),
                "unit_of_measurement":cal_unit[device_class] ,
                "device":{
                  "identifiers": [config[device].get("device_mac")],
                  "name": device,
                  "model": config[device].get("device"),
                  "manufacturer": "Xiomi",
                  "sw_version" : "0.1",

                }
                }            
            ) 
            messages.append({'topic': "homeassistant/"+config[device].get("topic")+"_"+str(i)+"/config",'payload': dataconfig})
            i=i+1
        messages.append({'topic': config[device].get("topic")+"/state", 'payload': data, 'retain': config[device].getboolean("retain", False)})
        availability = 'online'
    except BTLEException as e:
        availability = 'offline'
        print(datetime.datetime.now(), "Error connecting to device {0}: {1}".format(device, str(e)))
        print(traceback.print_exc())
        #easy way for zombie
        del poller
    except Exception as e:
        availability = 'offline'
        print(datetime.datetime.now(), "Error polling device {0}. Device might be unreachable or offline.".format(device))
        print(traceback.print_exc())
        del poller
        #easy way for zombie
#need to fix below
#  7731 root      20   0    3644    660    576 R  48.5   0.1 260:51.29 bluepy-helper
# 24703 root      20   0    3644    652    568 R  48.2   0.1  65:57.79 bluepy-helper
# 27076 root      20   0    3644    652    568 R  48.2   0.1  38:59.71 bluepy-helper
# 23034 root      20   0    3644    700    616 R  47.9   0.1  89:30.75 bluepy-helper
#  6340 root      20   0    3644   2380   2244 R  47.6   0.3 270:11.43 bluepy-helper
# 32136 root      20   0    3644   2380   2244 R  47.6   0.3 314:38.65 bluepy-helper
# 23342 root      20   0    3644   2232   2096 R  47.2   0.2 374:22.19 bluepy-helper
# 29199 root      20   0    3644   2268   2132 R  46.6   0.2 334:27.28 bluepy-helper

    # finally:
    #      messages.append({'topic': config[device].get("availability_topic"), 'payload': availability, 'retain': config[device].getboolean("retain", False)})



# Init MQTT
mqtt_config = configparser.ConfigParser()
mqtt_config.read("{0}/mqtt.ini".format(workdir))
mqtt_broker_cfg = mqtt_config["broker"]


print("Try MQTT")
try:
    auth = None
    mqtt_username = mqtt_broker_cfg.get("username")
    mqtt_password = mqtt_broker_cfg.get("password")

    if mqtt_username:
        auth = {"username": mqtt_username, "password": mqtt_password}
    # print(messages)
    publish.multiple(messages, keepalive=50,hostname=mqtt_broker_cfg.get("host"), port=mqtt_broker_cfg.getint("port"), client_id=mqtt_broker_cfg.get("client"), auth=auth)
except Exception as ex:
    print(datetime.datetime.now(), "Error publishing to MQTT: {0}".format(str(ex)))

with open("{0}/averages.ini".format(workdir), "w") as averages_file:
    averages.write(averages_file)
