# PythonAPI LaMetric REST data access
# coding=utf-8

# @Baracudaz (https://github.com/baracudaz/netatmo-lametric-proxy)
# @SebastienPittet migrated to 'requests' instead of urllib

import json
import sys
import requests

# Common definitions

_BASE_URL = "https://developer.lametric.com/"
_PUSH_URL = _BASE_URL + "api/V1/dev/widget/update/com.lametric."


class Setup(object):

    def __init__(self):
        self.data = {}
        self.data['frames'] = []
        self.index = 0

    def addTextFrame(self, icon, text):
        frame = {}
        frame['index'] = self.index
        frame['icon'] = icon
        frame['text'] = text
        self.data['frames'].append(frame)
        self.index += 1

    def addGoalFrame(self, icon, start, current, end, unit):
        frame = {}
        frame['index'] = self.index
        frame['icon'] = icon
        frame['goalData'] = {}
        frame['goalData']['start'] = start
        frame['goalData']['current'] = start
        frame['goalData']['end'] = start
        frame['goalData']['unit'] = unit
        self.data['frames'].append(frame)
        self.index += 1

    def addSparklineFrame(self, data):
        frame = {}
        frame['index'] = self.index
        frame['chartData'] = data
        self.data['frames'].append(frame)
        self.index += 1

    def push(self, app_id, access_token):
        # print json.dumps(self.data,ensure_ascii=False)

        headers = {'Accept': 'application/json',
                   'Cache-Control': 'no-cache',
                   'X-Access-Token': access_token
                   }
        try:
            request = requests.post(_PUSH_URL + app_id,
                                    data = json.dumps(self.data,
                                                      ensure_ascii=False),
                                    headers = headers)
            request.raise_for_status()

        except requests.exceptions.Timeout:
            # Maybe set up for a retry, or continue in a retry loop
            print('Timeout from lametric. Exit.')
            sys.exit(1)
        except requests.exceptions.ConnectionError as e:
            # DNS failure, refused connection, etc
            print(e)
            print('Connection Error. Exit.')
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            # invalid HTTP response
            print('Invalid HTTP response: ' + str(request.status_code))
            print(e)
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            # catastrophic error. bail.
            print(e)
            sys.exit(1)
        else:
            # everything is fine
            print('LaMetric updated with exoscale status.')
