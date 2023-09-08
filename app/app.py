from flask import Flask
from lib import exoscalestatus
import json

app = Flask(__name__)

# ############## INIT ###############

# Load configuration from config.toml
configuration = exoscalestatus.loadconfig()

# init LAMETRIC logos
# Country flags and Status logos
FLAGS = configuration['lametric-country']
STATUS = configuration['status-logo']

# ############ ROUTES ###############


@app.route('/')
def home():
    return "OK"


@app.route('/api/v1/')
def apiv1():
    # Create the Title frame
    frames = exoscalestatus.init_frames(configuration)

    # Request the Exoscale Status page
    r = exoscalestatus.getExoscaleStatus(
        configuration['exoscale']['status_url'])

    # About the Services
    services = r['services']
    services = exoscalestatus.addParentSrv(services)

    # About Incidents
    incidents = r['incidents']

    if not incidents:
        frames = exoscalestatus.append_frame(frames, STATUS['up'], "HEALTHY")
    else:
        # Add the frames for all the sub-services
        frames = exoscalestatus.addServiceFrames(
            services, incidents, frames, STATUS)

    # About Maintenances
    maintenances = r['maintenances']
    if maintenances:
        frames = exoscalestatus.append_frame(frames,
                                             STATUS['tool'],
                                             "Maintenance scheduled: {}".format(len(maintenances)))
    else:
        frames = exoscalestatus.append_frame(frames, STATUS['tool'],
                                             "No maintenance.")

    return json.dumps(frames)


# Testing to check if it works
@app.route('/test')
def test():
    return "OK!"


if __name__ == '__main__':
    app.run()
