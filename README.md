# Okex-FuturePortfolio
Okex.com Future Trading Daily Portfolio Report Generator

This tool help gathering and calculating daily profit in your Okex.com future portfolio into a local database. It can also generate HTML report for easier viewing. This is my first project in Python so any code improvements and pull requests are very welcome. This script requires API access to your Okex account with Trade permisssion only.

HTML reports will be organized like this: reports/_[name of coin]_/_[year]_/_[month]_.html

For example, the BTC profit report for October 2018 will be in reports/btc/2018/10.html


This is an open-source project. If you don't trust my code, you can see them in main.py. I would be very appreciate if you can improve them.

# Report Screenshot
![alt text](https://i.imgur.com/W4ZvrFL.png "Screenshot1")
![alt text](https://i.imgur.com/w9N3iN1.png "Screenshot2")


# Getting Started
(Install Python 3 if you don't have)
Clone this repository and copy config.sample.json as config.json then edit this file.

## config.json

Config Key| Type | Description
--- | --- |---
apiKey | string | API Key for Okex.com
secretKey | string | Secret Key for Okex.com
coins | array of strings | Cryptocurrency coin to gather data in lower case
html_template_file | string | HTML Template file's name to generate reports
reports_folder | string | Generated reports folder name
database_filename | string | Database file's name to store your portfolio
enable_bx | boolean | Enable getting cryptocurrency to fiat price in BX.in.th
moving_average | integer | Number of data entries to calculate moving average
generate_only_current_month | boolean | Generate (and overwrite) HTML report for current month only
decimal_points | integer | Number of decimal points in reports
month_name | array of strings | Name of each month (for localization)

Run `pip install -r requirements.txt` and set cron (or Task Scheduler in Windows) to run main.py every day

# Command Line Arguments

Arguments|Description
--- | ---
--generate-html | Generate HTML report after retrieving data
--force-add | Force retrieve data and add into database (if there's today entry in database, it won't add a new one by default)
