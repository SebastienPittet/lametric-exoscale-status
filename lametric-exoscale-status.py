#!/usr/bin/python3
# encoding=utf-8

# Use LaMetric to display exoscale status
# Author : Sebastien Pittet, https://sebastien.pittet.org
#          Inspired from @baracudaz / netatmo-lametric-proxy

import requests
import sys
import os
import configparser
from library import lametric

_CONFIG_FILE = 'config.ini'

# Load the configuration from config.ini file
try:
    # Get the path of configuration file
    configFile = os.path.join(os.getcwd(), _CONFIG_FILE)

    # Parse the config file content
    config = configparser.ConfigParser()
    config.read(configFile)

    # Get params from config.ini file
    exoscale_status_api = config.get('exoscale', 'exoscale_status_api')
    lametric_push_url = config.get('lametric', 'push_url')
    app_id = config.get('lametric', 'app_id')
    access_token = config.get('lametric', 'access_token')
except:
    print('Cannot read configuration file. Exit.')
    sys.exit(1)

# Icons definition
icon = {
    'app-icon': 'a17776',
    'up': 'i120',
    'down': 'i124',
    'stable': 'a13526',
    'tool': 'i93',
    'smile': 'i4907',
    'redcross': 'i654'
    }

# Get exoscale status from public API (json format)
try:
    exoscaleStatus = requests.get(exoscale_status_api).json()

except requests.exceptions.Timeout:
    print('Exit on a timeout. Cannot get exoscale status.')
    sys.exit(1)

except requests.exceptions.ConnectionError:
    print('Connection Error. Is your DNS well configured?')
    sys.exit(1)

except requests.exceptions.HTTPError:
    print('Invalid HTTP response from exoscale.')
    sys.exit(1)

except requests.exceptions.RequestException as e:
    print(e)
    sys.exit(1)

lametric = lametric.Setup()
lametric.addTextFrame(icon['app-icon'], 'Exoscale')

# Parse exoscale status
for service in exoscaleStatus['status']:
    # print(service, ':', exoscaleStatus['status'][service]['state'])

    # Generate a frame per service
    if exoscaleStatus['status'][service]['state'] == 'operational':
        lametric.addTextFrame(icon['up'], service)
    else:
        lametric.addTextFrame(icon['down'], service)

# If any, display a list of upcoming maintenances
if len(exoscaleStatus['upcoming_maintenances']) < 1:
    lametric.addTextFrame(icon['tool'],
                          'No maintenance planned on exoscale.')
else:
    lametric.addTextFrame(icon['app-icon'],
                          'Upcoming maintenances on exoscale')
    for maintenance in iter(exoscaleStatus['upcoming_maintenances']):
        lametric.addTextFrame(icon['tool'],
                              maintenance['date'][:10] + ': ' +
                              maintenance['title'] + ' : ' +
                              maintenance['description'])

# Finally, push to LaMetric
lametric.push(app_id, access_token)
