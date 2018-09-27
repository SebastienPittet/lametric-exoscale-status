#!/usr/bin/python3
# encoding=utf-8

# Use LaMetric to display exoscale status
# Author : Sebastien Pittet, https://sebastien.pittet.org
#          Inspired from @baracudaz / netatmo-lametric-proxy

import logging
import requests
import sys
import os
import configparser
from library import lametric

_CONFIG_FILE = 'config.ini'

# Icons definition
icon = {
    'app-icon': 'a17776',
    'up': 'i120',
    'down': 'i124',
    'stable': 'a13526',
    'fire': '2715',
    'tool': 'i93',
    'smile': 'i4907',
    'redcross': 'i654'
    }

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

    # Configure logging
    loglevel = config.get('general','loglevel')
    logfile = config.get('general','logfile')
    numeric_level = getattr(logging, loglevel.upper(), None)
    logging.basicConfig(filename=logfile,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        level=numeric_level)

except:
    logging.error('Cannot read configuration file. Exit.')
    sys.exit(1)

# Get exoscale status from public API (json format)
try:
    exoscaleStatus = requests.get(exoscale_status_api).json()

except requests.exceptions.Timeout:
    logging.critical('Exit on a timeout. Cannot get exoscale status.')
    sys.exit(1)

except requests.exceptions.ConnectionError:
    logging.critical('Connection Error. Is your DNS well configured?')
    sys.exit(1)

except requests.exceptions.HTTPError:
    logging.critical('Invalid HTTP response from exoscale.')
    sys.exit(1)

except requests.exceptions.RequestException as e:
    logging.critical(e)
    sys.exit(1)

lametric = lametric.Setup()
lametric.addTextFrame(icon['app-icon'], 'Exoscale')

# Parse exoscale status
for service in exoscaleStatus['status']:
    status = service +  ' is ' + exoscaleStatus['status'][service]['state']
    logging.debug(status)

    # Generate a frame per service
    if exoscaleStatus['status'][service]['state'] == 'operational':
        lametric.addTextFrame(icon['up'], service)
    elif exoscaleStatus['status'][service]['state'] == 'degraded_performance':
        lametric.addTextFrame(icon['fire'], service)
    elif exoscaleStatus['status'][service]['state'] == 'partial_outage':
        lametric.addTextFrame(icon['fire'], service)
    elif exoscaleStatus['status'][service]['state'] == 'major_outage':
        lametric.addTextFrame(icon['down'], service)
    else:
        lametric.addTextFrame(icon['down'], service)

# If any, display a list of upcoming maintenances
nb_maintenance = len(exoscaleStatus['upcoming_maintenances'])
logging.debug('nb_maintenance: ' + str(nb_maintenance))

if nb_maintenance < 1:
    lametric.addTextFrame(icon['tool'],
                          'No maintenance planned on exoscale.')
else:
    lametric.addTextFrame(icon['tool'],
                          'Upcoming maintenances on exoscale: '
                          + str(nb_maintenance))

    for maintenance in iter(exoscaleStatus['upcoming_maintenances']):
        logging.debug(maintenance['description'])
        lametric.addTextFrame(icon['tool'],
                              maintenance['date'][:10] + ': ' +
                              maintenance['title'] + ' : ' +
                              maintenance['description'])

# Finally, push to LaMetric
try:
    lametric.push(app_id, access_token)
    logging.info('Lametric updated with status and %s maintenance(s).',
                  nb_maintenance)

except:
    logging.error('Lametric is NOT up to date!')
