"""
Fetch Exoscale status page and return a JSON with the status of all services.

Data structure of the JSON returned by the Exoscale Status page (example):

/
├── incidents
│   ├── id:1
│   └── id:2
├── maintenances
└── services
    ├── Portal
    ├── DNS
    ├── Global
    │   ├── API
    │   ├── Compute
    │   ├── Managed Kubernetes SKS
    │   ├── Network Load Balancer NLB
    │   └── Object Storage SOS
    ├── CH-GVA-2
    │   ├── API
    │   ├── Compute
    │   ├── Managed Kubernetes SKS
    │   ├── Network Load Balancer NLB
    │   └── Object Storage SOS
    ├── CH-DK-2
    │   ├── API
    │   ├── Compute
    │   ├── Managed Kubernetes SKS
    │   ├── Network Load Balancer NLB
    │   └── Object Storage SOS
    └── ...
        ├── ...
        └── ...

"""

from requests import get
from requests.exceptions import HTTPError


def fetch_ExoscaleStatus(StatusURL: str = "https://statuspal.eu/api/v2/status_pages/exoscalestatus/summary") -> dict:
    # Requests the status of Exoscale Services and
    # returns a JSON with the status.
    try:
        r = get(StatusURL).json()

    except HTTPError as http_err:
        # invalid HTTP response, bail.
        print(f"HTTP error occurred: {http_err}")
        exit()
    return r


def addParentSrv(services, parentName=None, parentId=None):
    # rework the services
    # add the parent name in every service
    nodes = []

    for service in services:
        serviceId = service["id"]
        serviceName = service["name"]
        serviceCurrentIncidentType = service["current_incident_type"]
        serviceDescription = service["description"]
        serviceChildren = service["children"]

        if service["children"]:
            # it's a parent, recurse with parentname
            node = {
                "id": serviceId,
                "name": serviceName,
                "current_incident_type": serviceCurrentIncidentType,
                "description": serviceDescription,
                "children": serviceChildren,
                "parent": "Exoscale",
                "parentId": None,
            }
            nodes.append(node)
            nodes.extend(addParentSrv(service["children"], serviceName, serviceId))
        else:
            # base case, for children/leafs
            node = {
                "id": serviceId,
                "name": serviceName,
                "current_incident_type": serviceCurrentIncidentType,
                "description": serviceDescription,
                "children": serviceChildren,
                "parent": parentName,
                "parentId": parentId,
            }
            nodes.append(node)
    return nodes
