# lametric-exoscale-status
Use LaMetric Time to display the status of all services provided by [exoscale, a public cloud provider](https://www.exoscale.com).
This code is largely inspired from the work of [@baracudaz](https://github.com/baracudaz/netatmo-lametric-proxy).

For users interested in exoscale status, you only need to install the app [**exoscale statuts**](https://apps.lametric.com/apps/exoscale_status/5807) on your devivce.

In case of interest, you can duplicate this by following these steps:

1. Create your own app at [developer.lametric.com](https://developer.lametric.com/)
2. Type : *Indicator App*
3. Select : *Push App* (you get an URL to push your updates)
4. Choose an icon, name, etc
5. Decide if you need a public available app (listed in the store) or a private one.

Once the application is created, on your server, execute:
```
git clone <this repo>
cd lametric-exoscale-status
virtualenv venv
pip install -r requirements.txt
```

Finally :
1. Update the *config.ini* and save your ACCESS_TOKEN and PUSH_URL
2. schedule the execution of this code
