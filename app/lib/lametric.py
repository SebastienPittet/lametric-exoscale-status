"""
This module contains functions to create the frames for the LAMETRIC display.
"""

def init_frames(configuration: dict) -> dict:
    """
    initialize the content for LAMETRIC (1st frame)
    input: configuraton dictionary
    output: frames dictionary
    """
    # Initialize the frames for LAMETRIC
    APP_NAME = configuration["lametric-app"]["name"]
    APP_LOGO = configuration["lametric-app"]["logo"]

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


def append_frame(frames: dict, logo: str, text: str) -> dict:
    # Add a new frame to display

    # create new frame
    frame = {
        "icon": logo,
        "text": text,
    }

    frames["frames"].append(frame)
    return frames


def addServiceFrames(services, frames: dict, ICONS: dict) -> dict:
    # parse the incidents and add status frames

    # filter on impacted services AND children
    # The parent (Exoscale root service) has an parentId == None
    # So, the 2nd condition belwo filters out the root + the zones,
    # as they have a parentId == None
    impacted_services = [
        service
        for service in services
        if service["current_incident_type"] and service["parentId"]
    ]

    for service in impacted_services:
        # aggregate the parentName + childName
        serviceFullName = service["parent"] + " " + service["name"]

        if service["current_incident_type"] == "minor":
            frames = append_frame(frames, ICONS["down-minor"], serviceFullName)
        elif service["current_incident_type"] == "major":
            frames = append_frame(frames, ICONS["down-fire"], serviceFullName)
        elif service["current_incident_type"] == "scheduled":
            frames = append_frame(frames, ICONS["scheduled"], serviceFullName)
        else:
            frames = append_frame(frames, ICONS["no-status"], service["name"])
    return frames
