from flask import Flask
from lib import exoscalestatus, configuration, lametric
import json

app = Flask(__name__)

# ############## INIT ###############

# Load configuration from config.toml
config = configuration.load_config()

# init LAMETRIC logos
# Country flags and Status logos
FLAGS = config["lametric-country"]
STATUS = config["status-logo"]

# ############ ROUTES ###############


@app.route("/")
def home():
    return "Exoscale Status API is running!"


@app.route("/api/v1/")
def apiv1():
    # Create the Title frame
    frames = lametric.init_frames(config)

    # Request the Exoscale Status page
    r = exoscalestatus.fetch_ExoscaleStatus(config["exoscale"]["status_url"])

    # About the Services
    services = r["services"]
    services = exoscalestatus.addParentSrv(services)

    # About Incidents
    incidents = r["incidents"]

    if not incidents:
        frames = lametric.append_frame(frames, STATUS["up"], "HEALTHY")
    else:
        # Add the frames for all the sub-services
        frames = lametric.addServiceFrames(services,
                                                 incidents,
                                                 frames,
                                                 STATUS)

    # About Maintenances
    maintenances = r["maintenances"]
    if maintenances:
        frames = lametric.append_frame(
            frames,
            STATUS["tool"],
            "Maintenance scheduled: {}".format(len(maintenances)),
        )
    else:
        frames = lametric.append_frame(frames,
                                             STATUS["tool"],
                                             "No maintenance.")

    return json.dumps(frames)


# Testing to check if it works
@app.route("/test")
def test():
    return "OK!"


if __name__ == "__main__":
    app.run()
