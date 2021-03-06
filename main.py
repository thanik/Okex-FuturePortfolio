import requests
import json
import hmac
import base64
import argparse
import sqlite3
import logging.config
import os
import time
from datetime import datetime
from mako.template import Template
from mako.exceptions import RichTraceback

CONTENT_TYPE = 'Content-Type'
OK_ACCESS_KEY = 'OK-ACCESS-KEY'
OK_ACCESS_SIGN = 'OK-ACCESS-SIGN'
OK_ACCESS_TIMESTAMP = 'OK-ACCESS-TIMESTAMP'
OK_ACCESS_PASSPHRASE = 'OK-ACCESS-PASSPHRASE'
APPLICATION_JSON = 'application/json'
COINS_WHITELIST = ['btc', 'btg', 'etc', 'bch', 'xrp', 'eth', 'eos', 'ltc']

OKEX_URL = 'https://www.okex.com'
REQUEST_TIME_PATH = '/api/general/v3/time'
REQUEST_PATH = '/api/futures/v3/accounts/'
BX_URL = 'https://bx.in.th/api/'
description = "This is Okex.com Future Trading Daily Portfolio Report Generator. " \
              "This tool help gathering and calculating daily profit in your Okex.com future portfolio into a local database. " \
              "It can also generate HTML report for easier viewing."

# setup command line argument
parser = argparse.ArgumentParser(add_help=True, description=description)
parser.add_argument('--generate-html', action='store_true', help='Generate HTML report for all data gathered')
parser.add_argument('--force-add', action='store_true',
                    help='Force retrieve data and add into database (if there\'s today entry in database, it won\'t add a new one by default)')
parser.add_argument('--generate-summary', action='store_true', help='Generate summary equity for each coin in all accounts')
args = parser.parse_args()


# okex functions
# signature
def signature(timestamp, method, request_path, body, secret_key):
    if str(body) == '{}' or str(body) == 'None':
        body = ''
    message = str(timestamp) + str.upper(method) + request_path + str(body)
    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d)


# set request header
def get_header(api_key, sign, timestamp, passphrase):
    header = dict()
    header[CONTENT_TYPE] = APPLICATION_JSON
    header[OK_ACCESS_KEY] = api_key
    header[OK_ACCESS_SIGN] = sign
    header[OK_ACCESS_TIMESTAMP] = str(timestamp)
    header[OK_ACCESS_PASSPHRASE] = passphrase
    return header


def parse_params_to_str(params):
    url = '?'
    for key, value in params.items():
        url = url + str(key) + '=' + str(value) + '&'

    return url[0:-1]


def verify_config(config):
    has_key_check = all(k in config for k in (
        'accounts', 'html_template_file', 'reports_folder', 'enable_bx', 'database_filename',
        'generate_only_current_month', 'decimal_points'))

    if not isinstance(config['accounts'], list):
        logger.error('Accounts config is not an array.')
        return False

    for account in config['accounts']:
        if not all(k in account for k in ('name', 'apiKey', 'secretKey', 'passphrase', 'coins')):
            logger.error('Some required fields in accounts config are not found. Please check accounts config.')
            return False

        if ' ' in account['name']:
            logger.error('Whitespace is not allowed in account\'s name.')
            return False

        if account['name'].lower() == 'summary':
            logger.error('summary is a reserved name for summary report. Please change the account\' name')
            return False

        if not isinstance(account['coins'], list):
            logger.error('Coins settings for account "' + account['name'] + '" is not an array.')
            return False

        for coin in account['coins']:
            if coin not in COINS_WHITELIST:
                logger.error('Coins settings is not in the market.')
                return False

    if not isinstance(config['decimal_points'], int):
        logger.error('decimal_points is not a number. (' + str(type(config['decimal_points'])) + ')')
        return False
    if not os.path.exists(config['html_template_file']):
        logger.error('HTML Template file doesn\'t exist.')
        return False
    return has_key_check


def init_db(cursor, config):
    cursor.execute('SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'db_info\';')
    data = cursor.fetchone()
    if data is None:
        logger.info('No db_info. Generating database (and migrating data if exist...')
        for coin in COINS_WHITELIST:
            cursor.execute('SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'' + coin + '\';')
            coin_table = cursor.fetchone()
            if coin_table is not None:
                cursor.execute('ALTER TABLE ' + coin + ' ADD COLUMN account TEXT')
                cursor.execute('UPDATE ' + coin + ' SET account=?', (config['accounts'][0]['name'],))

        cursor.execute('CREATE TABLE \'db_info\' (version INTEGER PRIMARY KEY)')
        cursor.execute('INSERT INTO db_info (version) VALUES (2)')

    for coin in COINS_WHITELIST:
        cursor.execute('CREATE TABLE IF NOT EXISTS ' + coin + ' ('
                                                              'id INTEGER PRIMARY KEY AUTOINCREMENT,'
                                                              'time DATETIME,'
                                                              'equity DECIMAL(10,8),'
                                                              'thbprice_per_unit DECIMAL(10,2),'
                                                              'account TEXT'
                                                              ')')


def write_month_file(coin_name, account_name, month_number, data):
    # keep temporary data
    equity_stack = []
    month_data = []
    current_index = 0
    moving_average_str = ''
    old_equity = 0
    old_fiat_price = 0
    current_year = ''
    change_redtext = False
    fiat_price_change_redtext = False
    number_format = '{:.' + str(config['decimal_points']) + 'f}'
    number_format_percentage = '{:.' + str(config['decimal_points']) + 'f}%'

    if not data:
        logger.info('No data to generate for month ' + str(month_number) + '. Skipping.')
    else:
        logger.info('Building data for month ' + str(month_number) + '...')
        for entry in data:
            logger.debug('Queried Entry: ' + str(entry))

            if account_name == 'summary':
                datetime_obj = time.strptime(entry[1], '%Y-%m-%d')
            else:
                datetime_obj = time.strptime(entry[1], '%Y-%m-%d %H:%M:%S')
            current_year = str(datetime_obj.tm_year)
            equity_stack.append(entry[2])
            if current_index >= config['moving_average'] - 1:
                if current_index >= config['moving_average']:
                    equity_stack.pop(0)
                moving_average_sum = 0

                for equ in equity_stack:
                    moving_average_sum += equ

                moving_average_sum /= config['moving_average']
                moving_average_str = number_format.format(moving_average_sum)

            if old_equity == 0:
                change_percentage = 0
            else:
                change_percentage = ((entry[2] / old_equity) * 100) - 100
                change_redtext = entry[2] < old_equity

            if old_fiat_price == 0:
                fiat_price_change = 0
                fiat_price_change_percentage = 0
            else:
                fiat_price_change = (entry[3] * entry[2]) - old_fiat_price
                fiat_price_change_percentage = (((entry[3] * entry[2]) / old_fiat_price) * 100) - 100
                fiat_price_change_redtext = (entry[3] * entry[2]) < old_fiat_price

            month_data.append({
                'time': entry[1],
                'equity': number_format.format(entry[2]),
                'change': number_format.format(entry[2] - old_equity),
                'change_percentage': number_format_percentage.format(change_percentage),
                'change_redtext': change_redtext,
                'moving_average': moving_average_str,
                'fiat_unit_price': number_format.format(entry[3]),
                'fiat_price': number_format.format(entry[3] * entry[2]),
                'fiat_price_change': number_format.format(fiat_price_change),
                'fiat_price_change_redtext': fiat_price_change_redtext,
                'fiat_price_change_percentage': number_format_percentage.format(fiat_price_change_percentage)
            })
            old_equity = entry[2]
            old_fiat_price = entry[3] * entry[2]
            current_index += 1

        year_directory_name = config['reports_folder'] + '/' + account_name + '/' + coin_name + '/' + current_year
        month_file_name = str(month_number) + '.html'

        logger.debug('Start writing file...')
        try:
            if not os.path.exists(year_directory_name):
                os.makedirs(year_directory_name)

            html_template = Template(filename=config['html_template_file'])
            output = html_template.render_unicode(month_name=config['month_name'][month_number - 1], year=current_year,
                                                  month_data=month_data, coin_name=coin_name.upper(), account_name=account_name)
            f = open(year_directory_name + '/' + month_file_name, 'w')
            f.write(output)
            f.close()
        except:
            traceback = RichTraceback()
            logger.error('Error while writing HTML file:')
            for (filename, lineno, function, line) in traceback.traceback:
                logger.error("File %s, line %s, in %s" % (filename, lineno, function))
                logger.error(line, "\n")
            logger.error("%s: %s" % (str(traceback.error.__class__.__name__), traceback.error))


def generate_html():
    logger.info('Generating HTML reports for each account...')
    for account in config['accounts']:
        for coin in account['coins']:
            if config['generate_only_current_month']:
                logger.debug('Generate for month ' + str(datetime.now().month))
                cursor.execute(
                    'SELECT * FROM ' + coin + ' WHERE strftime(\'%m\',time)=strftime(\'%m\',\'now\') AND account=? ORDER BY datetime(time)', (account['name'],))
                all_data = cursor.fetchall()
                write_month_file(coin, account['name'], datetime.now().month, all_data)
            else:
                for month in range(1, 13):
                    logger.debug('Generate for month ' + str(month))
                    cursor.execute(
                        'SELECT * FROM ' + coin + ' WHERE strftime(\'%m\',time)=\'{:02}\' AND account=? ORDER BY datetime(time)'.format(
                            month), (account['name'],))
                    all_data = cursor.fetchall()
                    write_month_file(coin, account['name'], month, all_data)

    if args.generate_summary:
        logger.info('Generating HTML reports for summary...')
        coins = set()
        for account in config['accounts']:
            for coin in account['coins']:
                coins.add(coin)

        for coin in coins:
            if config['generate_only_current_month']:
                logger.debug('Generate for month ' + str(datetime.now().month))
                cursor.execute(
                    'SELECT id,strftime(\'%Y-%m-%d\',time) AS time, SUM(equity) AS equity, thbprice_per_unit FROM ' + coin + ' WHERE strftime(\'%m\',time)=strftime(\'%m\',\'now\') GROUP BY strftime("%Y-%m-%d", time) ORDER BY time',
                )
                all_data = cursor.fetchall()
                write_month_file(coin, 'summary', datetime.now().month, all_data)
            else:
                for month in range(1, 13):
                    logger.debug('Generate for month ' + str(month))
                    cursor.execute(
                        'SELECT id,strftime(\'%Y-%m-%d\',time) AS time, SUM(equity) AS equity, thbprice_per_unit FROM ' + coin + ' WHERE strftime(\'%m\',time)=\'{:02}\' GROUP BY strftime("%Y-%m-%d", time) ORDER BY time'.format(
                            month))
                    all_data = cursor.fetchall()
                    write_month_file(coin, 'summary', month, all_data)


def setup_logging(
        default_path='logging.json',
        default_level=logging.INFO,
        env_key='LOG_CFG'
):
    """Setup logging configuration

    """
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)


def add_entry_to_database(coin_name, account_name, equity, fiatprice):
    if args.force_add:
        cursor.execute(
            'INSERT INTO ' + coin_name + ' (equity, thbprice_per_unit, time, account) VALUES (?, ?, DATETIME(\'now\',\'localtime\'), ?)',
            (str(equity), str(fiatprice), account_name,))
        logger.debug('Equity value ' + str(equity) + ' added in ' + coin_name + ' for account ' + account_name)
    else:
        cursor.execute('SELECT id FROM ' + coin_name + ' WHERE DATE(time)=DATE(\'now\',\'localtime\') AND account=?', (account_name,))
        data = cursor.fetchone()
        if data is None:
            logger.debug('No data for today. Add a new entry.')
            cursor.execute(
                'INSERT INTO ' + coin_name + ' (equity, thbprice_per_unit, time, account) VALUES (?, ?, DATETIME(\'now\',\'localtime\'), ?)',
                (str(equity), str(fiatprice), account_name,))
            logger.debug('Equity value ' + str(equity) + ' added in ' + coin_name + ' for account ' + account_name)
        else:
            logger.debug('Today data exists for ' + coin_name + ' in ' + account_name + '. Ignoring new data.')


def get_bx_thb_price(bx_response_json, coin_name):
    if bx_response_json is not None:
        for i in bx_response_json:
            if coin_name.upper() == bx_response_json[i]['secondary_currency'] and bx_response_json[i][
                'primary_currency'] == 'THB':
                return bx_response_json[i]['last_price']
    return 0


# setup logger
setup_logging()
logger = logging.getLogger()

# read config file
try:
    with open('config.json') as config_data:
        config = json.load(config_data)
        config_data.close()
except (SystemExit, KeyboardInterrupt):
    raise
except Exception as e:
    logger.exception('Failed to read config.json file')
    exit(0)

if not verify_config(config):
    logger.error('Invalid config.json file, please check that all required fields are there and correct.')
    exit(0)

# database checking
database_conn = sqlite3.connect(config['database_filename'])
cursor = database_conn.cursor()
init_db(cursor, config)
database_conn.commit()

# get data from bx
if config['enable_bx']:
    bx_response = requests.get(BX_URL)
    if bx_response.ok:
        bx_response_json = bx_response.json()
else:
    bx_response_json = None

# get data from okex
for account in config['accounts']:
    for coin in account['coins']:
        # do request
        # get timestamp from okex
        time_response = requests.get(OKEX_URL + REQUEST_TIME_PATH)
        time_response_json = time_response.json()
        if time_response.ok:
            if time_response_json['epoch']:
                timestamp = float(time_response_json['epoch'])
                # set request header
                header = get_header(account['apiKey'],
                                    signature(timestamp, 'GET', REQUEST_PATH + coin, None, account['secretKey']),
                                    timestamp,
                                    account['passphrase'])
                response = requests.get(OKEX_URL + REQUEST_PATH + coin, headers=header)
                if response.ok:
                    response_json = response.json()
                    if response_json['equity']:
                        add_entry_to_database(coin, account['name'], response_json['equity'],
                                                      get_bx_thb_price(bx_response_json, coin))
                        database_conn.commit()
                    else:
                        logger.error('Okex Server sent an API error while getting data for ' + coin + ' in ' + account['name'] + ' (' + str(response_json['error_code']) + ').')
                        logger.error(str(response.json()))
                else:
                    logger.error('Okex Server sent an error while getting data for ' + coin + ' in ' + account['name'] + ' (' + str(response.status_code) + ').')
                    logger.error(str(response.json()))
            else:
                logger.error('Okex Server sent an API error while getting time (' + str(time_response_json['error_code']) + ').')
                logger.debug(str(time_response.json()))
        else:
            logger.error('Okex Server sent an error while getting time (' + str(time_response.status_code) + ').')
            logger.debug(str(time_response.json()))

if args.generate_html:
    generate_html()

database_conn.close()
exit(0)
