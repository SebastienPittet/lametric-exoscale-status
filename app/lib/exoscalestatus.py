import tomli
from requests import get
from requests.exceptions import HTTPError
import os

directory = os.getcwd()
CONFIG_FILE = directory + "/" + "config.toml"


def loadconfig(Confile=CONFIG_FILE):
    # Reads the Configuration file and return the content as JSON
    toml_dict = {}

    with open(Confile, "rb") as f:
        try:
            toml_dict = tomli.load(f)
        except tomli.TOMLDecodeError:
            print("Invalid configuration file. Please check TOML Synthax.")
            exit()
    return toml_dict


def getExoscaleStatus(StatusURL):
    # Requests the status of Exoscale Services and
    # returns a JSON with the status.
    try:
        r = get(StatusURL).json()

    except HTTPError as http_err:
        # invalid HTTP response, bail.
        print(f'HTTP error occurred: {http_err}')
        exit()
    return r


def init_frames(configuration):
    # initialize the content for LAMETRIC
    APP_NAME = configuration['lametric-app']['name']
    APP_LOGO = configuration['lametric-app']['logo']

    default_frame = {
        "frames": [
            {
                "icon": APP_LOGO,
                "text": APP_NAME,
            }
        ]
    }

    frames = {}
    frames = default_frame
    return frames


def addParentSrv(services, parentName=None, parentId=None):
    # rework the services
    # add the parent name in every service
    nodes = []

    for service in services:
        serviceId = service['id']
        serviceName = service['name']
        serviceCurrentIncidentType = service['current_incident_type']
        serviceDescription = service['description']
        serviceChildren = service['children']

        if service['children']:
            # it's a parent, recurse with parentname
            node = {
                "id": serviceId,
                "name": serviceName,
                "current_incident_type": serviceCurrentIncidentType,
                "description": serviceDescription,
                "children": serviceChildren,
                "parent": "Exoscale",
                "parentId": None
            }
            nodes.append(node)
            nodes.extend(addParentSrv(service['children'],
                                      serviceName,
                                      serviceId))
        else:
            # base case, for children/leafs
            node = {
                "id": serviceId,
                "name": serviceName,
                "current_incident_type": serviceCurrentIncidentType,
                "description": serviceDescription,
                "children": serviceChildren,
                "parent": parentName,
                "parentId": parentId
            }
            nodes.append(node)
    return nodes


def append_frame(frames, logo, text):
    # Add a new frame to display

    # create new frame
    frame = {
        "icon": logo,
        "text": text,
    }

    frames['frames'].append(frame)
    return frames


def addServiceFrames(services, incidents, frames, ICONS):
    # parse the incidents and add status frames

    # filter on impacted services AND children
    # The parent (Exoscale root service) has an parentId == None
    # So, the 2nd condition belwo filters out the root + the zones,
    # as they have a parentId == None
    impacted_services = [service for service in services if service['current_incident_type'] and service['parentId']]

    for service in impacted_services:
        # aggregate the parentName + childName
        serviceFullName = service['parent'] + " " + service['name']

        if service['current_incident_type'] == 'minor':
            frames = append_frame(frames, ICONS['down-minor'], serviceFullName)
        elif service['current_incident_type'] == 'major':
            frames = append_frame(frames, ICONS['down-fire'], serviceFullName)
        elif service['current_incident_type'] == 'scheduled':
            frames = append_frame(frames, ICONS['scheduled'], serviceFullName)
        else:
            frames = append_frame(frames, ICONS['no-status'], service['name'])
    return frames
