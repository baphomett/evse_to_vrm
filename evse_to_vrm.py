#!/usr/bin/env python

import os
import sys
import json
import logging
import platform
import paho.mqtt.client as mqtt
import _thread as thread   # for daemon = True  / Python 3.x
from gi.repository import GLib as gobject # Python 3.x
from dbus.mainloop.glib import DBusGMainLoop

sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService

path_UpdateIndex = '/UpdateIndex'

# ---------------------------------------------------------
PRODUCT_NAME = "evseCharger1" #name displayed on VenusOS
REFRESH_TIME = 1 #refresh time in seconds
DEVICE_NUM = 101 #device instance on vrm
MAX_CURRENT = 32 #maximum allowed current in A

# MQTT Setup
#HOST_IP = "192.168.68.100" #if using a local mqtt server

# if using APR's server:
HOST_IP = "www.missingbolt.com"
USER = "user"
PASSWORD = "<INSERT PASSWORD HERE>"
MQTTNAME = "evseCharger1"
TOPIC = "user/evse/evse1/from"
connected = 0
# ---------------------------------------------------------

# initial variables
power = 0
current = 0
set_current = 0
time = 0
charged_energy = 0
last_time = 0
stat = 0


def read_json(msg):
    jsonpayload = json.loads(msg.payload)
    logging.debug(jsonpayload)

    p = jsonpayload["P"]
    cur = jsonpayload["I"]
    set_cur = jsonpayload["EVamp"]
    
    # workaround to check if car is charging
    try:
        time = jsonpayload["CHti"]
    except KeyError:
        time = -1

    # calculate charged energy between updates
    en = p/(3600000/REFRESH_TIME)

    if int(jsonpayload["EVsta"])==3:
        stat = 2 #charging
    elif int(jsonpayload["EVsta"])==2:
        stat = 1 #connected
    elif int(jsonpayload["EVsta"])==1 or int(jsonpayload["EVsta"])==254:
        stat = 0 #disconnected
        #stat = 1 #looks better on VRM (shows 0W instead of 'disconnected)
    else:
        stat = 0 #disconnected
        #stat = 1 #looks better on VRM (shows 0W instead of 'disconnected)

    return p, cur, set_cur, time, en, stat

# MQTT functions:
def on_disconnect(client, userdata, rc):
    global connected
    logging.info("Client Got Disconnected")
    if rc != 0:
        logging.info('Unexpected MQTT disconnection. Will auto-reconnect')

    try:
        logging.info("Trying to Reconnect")
        client.username_pw_set(USER, PASSWORD)
        client.connect(HOST_IP)
        connected = 1
    except Exception as e:
        logging.exception(f"Error in Retrying to Connect with Broker. {e}")
        connected = 0

def on_connect(client, userdata, flags, rc):
    global connected
    if rc == 0:
        logging.info("Connected to MQTT Broker!")
        connected = 1
        client.subscribe(TOPIC)
    else:
        logging.info(f"Failed to connect, return code {rc}")


def on_message(client, userdata, msg):
    try:
        global power, current, set_current, time, charged_energy, last_time, stat
        if msg.topic == TOPIC:
            if msg.payload != '{"value": null}' and msg.payload != b'{"value": null}':
                power, current, set_current, time, energy, stat = read_json(msg)
                charged_energy += energy
            else:
                stat = 0 #disconnected
                logging.info("Response from MQTT was null and ignored")

    except Exception as e:
        logging.exception(f"Something failed when reading message: {e}")




class DbusService:
  def __init__(self, servicename, deviceinstance, paths, productname=PRODUCT_NAME, connection='MQTT'):
    self._dbusservice = VeDbusService(servicename)
    self._paths = paths

    logging.debug(f"{servicename} /DeviceInstance = {deviceinstance}")

    # Create the management objects, as specified in the ccgx dbus-api document
    self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
    self._dbusservice.add_path('/Mgmt/ProcessVersion', 'Unknown version, and running on Python ' + platform.python_version())
    self._dbusservice.add_path('/Mgmt/Connection', connection)

    # Create the mandatory objects
    self._dbusservice.add_path('/DeviceInstance', deviceinstance)
    self._dbusservice.add_path('/ProductId', 65535) 
    self._dbusservice.add_path('/ProductName', productname)
    self._dbusservice.add_path('/FirmwareVersion', 0.9)
    self._dbusservice.add_path('/HardwareVersion', 1.0)
    self._dbusservice.add_path('/Connected', 1)

    for path, settings in self._paths.items():
      self._dbusservice.add_path(
        path, settings['initial'], writeable=True, onchangecallback=self._handlechangedvalue)

    # pause before the next request (time in ms)
    gobject.timeout_add(REFRESH_TIME*1000, self._update)   

  def _update(self):
    global power, current, set_current, time, charged_energy, last_time, stat
    
    if time == -1 and last_time != time: #means not charging, so reset charged_energy
        power, current, charged_energy, stat = 0, 0, 0, 1 #stopped charging

    self._dbusservice['/Ac/L1/Power'] = power
    self._dbusservice['/Ac/Power'] = power
    self._dbusservice['/Ac/Energy/Forward'] = charged_energy
    self._dbusservice['/Current'] = current
    self._dbusservice['/SetCurrent'] = set_current
    self._dbusservice['/ChargingTime'] = time if time > 0 else 0
    self._dbusservice['/Status'] = stat
    
    logging.info(f"EVSE status: {stat}, charging power: {power}, actual current: {current}, set current: {set_current}")
    
    # update lasttime
    last_time = time

    # increment UpdateIndex - to show that new data is available
    index = self._dbusservice[path_UpdateIndex] + 1  # increment index
    if index > 255:   # maximum value of the index
      index = 0       # overflow from 255 to 0
    self._dbusservice[path_UpdateIndex] = index
    return True

  def _handlechangedvalue(self, path, value):
    logging.debug("someone else updated %s to %s" % (path, value))
    return True # accept the change


def main():
  logging.basicConfig(level=logging.DEBUG) # use .INFO for less logging
  thread.daemon = True # allow the program to quit

  
  # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
  DBusGMainLoop(set_as_default=True)
  
  evse_service = DbusService(
    servicename='com.victronenergy.evcharger.APR_EVSE1',
    deviceinstance=DEVICE_NUM,
    paths={
      '/Ac/L1/Power': {'initial': 0},
      '/Ac/Energy/Forward': {'initial': 0},
      '/Ac/Power': {'initial': 0},
      '/Current': {'initial': 0.0},
      '/MaxCurrent': {'initial': 32},
      '/SetCurrent': {'initial': 16},
      '/ChargingTime': {'initial': 0},
      '/Mode': {'initial': 0}, #0=manual, 1=auto
      '/Position': {'initial': 1}, #0=AC output, 1=AC input
      '/AutoStart': {'initial': 1}, #0=autostart disabled, 1=autostart enabled
      '/StartStop': {'initial': 1}, #0=disconnected, 1=connected
      '/Model': {'initial': 'APR_EVSE'}, 
      '/Status': {'initial': 0}, #0=disconnected, 1=connected, 2=charging, 3=charged, 4=waiting for sun, etc

      path_UpdateIndex: {'initial': 0},
    })

  logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
  mainloop = gobject.MainLoop()
  mainloop.run()

# MQTT configuration
client = mqtt.Client(MQTTNAME) # create new instance
client.on_disconnect = on_disconnect
client.on_connect = on_connect
client.on_message = on_message
client.username_pw_set(USER, PASSWORD)
client.connect(HOST_IP, port=1883, keepalive=60)  # connect to broker

client.loop_start()

if __name__ == "__main__":
  main()
