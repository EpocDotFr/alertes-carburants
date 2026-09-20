#!/usr/bin/env python3
from urllib.request import Request, urlopen
from xml.etree import ElementTree as etree
from urllib.error import HTTPError
from typing import Dict, Any
from pathlib import Path
from io import BytesIO
import zipfile
import tomllib
import logging
import json
import enum
import sys

logging.basicConfig(level=logging.INFO)


@enum.unique
class Fuel(enum.StrEnum):
    Diesel = 'Gazole'
    E85 = 'E85'
    Lpg = 'GPLc'
    Unleaded95E10 = 'E10'
    Unleaded95E5 = 'SP95'
    Unleaded98E5 = 'SP98'

    @property
    def id(self) -> int:
        match self:
            case self.Diesel:
                return 1
            case self.Unleaded95E5:
                return 2
            case self.E85:
                return 3
            case self.Lpg:
                return 4
            case self.Unleaded95E10:
                return 5
            case self.Unleaded98E5:
                return 6


def fetch_feed() -> etree.ElementTree:
    logging.info('Fetching feed...')

    request = Request(
        'https://donnees.roulez-eco.fr/opendata/instantane_ruptures',
        headers={
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0',
        },
        method='GET'
    )

    try:
        with urlopen(request) as response:
            with zipfile.ZipFile(BytesIO(response.read())) as zf:
                return etree.parse(zf.open('PrixCarburants_instantane_ruptures.xml'))
    except HTTPError as e:
        logging.error(e)

        sys.exit(1)


def load_config() -> Dict[str, Any]:
    logging.info('Loading configuration...')

    try:
        with open(Path(__file__).parent / 'config.toml', 'rb') as f:
            config = tomllib.load(f)
    except FileNotFoundError:
        logging.critical('config.toml not found, aborting.')

        sys.exit(1)

    if 'sms' not in config or not config['sms']:
        logging.critical('No "sms" entry found in config file, aborting.')

        sys.exit(1)
    elif 'api_key' not in config['sms'] or not config['sms']['api_key']:
        logging.critical('No "api_key" entry found in sms section of the config file, aborting.')

        sys.exit(1)
    elif 'recipients' not in config['sms'] or not config['sms']['recipients']:
        logging.critical('No "recipients" entry found in sms section of the config file, aborting.')

        sys.exit(1)
    elif 'locations' not in config or not config['locations']:
        logging.critical('No "locations" entries found in config file, aborting.')

        sys.exit(1)

    for location_id, location in config['locations'].items():
        label = location.get('label')
        fuels = location.get('fuels')

        try:
            if not isinstance(label, str):
                raise ValueError('missing or invalid label attribute (must be a string)')
            elif not isinstance(fuels, list):
                raise ValueError('missing or invalid fuels attribute (must be an array of strings)')

            location['fuels'] = [Fuel(fuel) for fuel in fuels]
        except ValueError as e:
            logging.error(f'Location {location_id}: {e}, will be ignored')

            del config['locations'][location_id]

            continue

    return config


def load_locations_status() -> Dict[str, Dict[int, bool]]:
    logging.info('Loading statuses...')

    try:
        with open(Path(__file__).parent / 'locstatus.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.info('  Unexisting')

        return {}


def save_locations_status(statuses: Dict[str, Dict[int, bool]]) -> None:
    logging.info('Saving statuses...')

    with open(Path(__file__).parent / 'locstatus.json', 'w') as f:
        json.dump(statuses, f)


def send_sms(alerts_config: Dict[str, Any], message: str) -> None:
    urlopen(Request(
        'https://api.smspartner.fr/v1/send',
        data=json.dumps({
            'apiKey': alerts_config['smspartner_api_key'],
            'phoneNumbers': alerts_config['recipients'].join(','),
            'message': message,
            'sender': 'AlertesCarburant',
            '_format': 'json',
        }).encode('utf-8'),
        method='POST'
    ))


def run() -> None:
    config = load_config()
    statuses = load_locations_status()
    xml = fetch_feed()

    for location_node in xml.iter('pdv'):
        location_id = location_node.get('id')

        if location_id not in config['locations']:
            continue

        location = config['locations'][location_id]

        logging.info(f'Checking location {location_id}')

    save_locations_status(statuses)

    logging.info('Done.')


if __name__ == '__main__':
    run()
