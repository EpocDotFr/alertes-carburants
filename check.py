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


def fetch_feed() -> etree.ElementTree:
    logging.info('Récupération du flux...')

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
    logging.info('Chargement de la configuration...')

    try:
        with open(Path(__file__).parent / 'config.toml', 'rb') as f:
            config = tomllib.load(f)
    except FileNotFoundError:
        logging.critical('config.toml introuvable, abandon.')

        sys.exit(1)

    if 'alerts' not in config or not config['alerts']:
        logging.critical('Pas d\'entrée "alerts" dans la configuration, abandon.')

        sys.exit(1)
    elif 'smspartner_api_key' not in config['alerts'] or not config['alerts']['smspartner_api_key']:
        logging.critical('Pas d\'entrée "smspartner_api_key" dans la section "alerts" de la configuration, abandon.')

        sys.exit(1)
    elif 'recipients' not in config['alerts'] or not config['alerts']['recipients']:
        logging.critical('Pas d\'entrée "api_key" dans la section "alerts" de la configuration, abandon.')

        sys.exit(1)
    elif 'locations' not in config or not config['locations']:
        logging.critical('Pas d\'entrées "locations" dans la configuration, abandon.')

        sys.exit(1)

    for location_id, location in config['locations'].items():
        label = location.get('label')
        fuels = location.get('fuels')

        try:
            if not isinstance(label, str):
                raise ValueError('"label" manquant ou invalide (doit être un string)')
            elif not isinstance(fuels, list):
                raise ValueError('"fuels" manquant ou invalide (doit être une liste de strings)')

            try:
                location['fuels'] = [Fuel(fuel) for fuel in fuels]
            except ValueError:
                raise ValueError('Une des valeurs de "fuels" est invalide')
        except ValueError as e:
            logging.error(f'Location {location_id}: {e} (sera ignoré)')

            del config['locations'][location_id]

            continue

    return config


def load_locations_status() -> Dict[str, Dict[str, bool]]:
    logging.info('Chargement des statuts...')

    try:
        with open(Path(__file__).parent / 'locstatus.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.info('  Inexistant pour l\'instant')

        return {}


def save_locations_status(statuses: Dict[str, Dict[str, bool]]) -> None:
    logging.info('Sauvegarde des statuts...')

    with open(Path(__file__).parent / 'locstatus.json', 'w') as f:
        json.dump(statuses, f)


def send_sms(alerts_config: Dict[str, Any], message: str) -> None:
    urlopen(Request(
        'https://api.smspartner.fr/v1/send',
        data=json.dumps({
            'apiKey': alerts_config['smspartner_api_key'],
            'phoneNumbers': alerts_config['recipients'].join(','),
            'message': message,
            'sender': alerts_config.get('sender', 'AlertesCarburant'),
            '_format': 'json',
        }).encode('utf-8'),
        method='POST'
    ))


def run() -> None:
    config = load_config()
    locations_status = load_locations_status()
    xml = fetch_feed()

    for location_node in xml.iter('pdv'):
        location_id = location_node.get('id')

        if not location_id:
            continue

        if location_id not in config['locations']:
            try:
                del locations_status[location_id]
            except KeyError:
                pass

            continue

        logging.info(f'Vérification de {location_id}...')

        location = config['locations'][location_id]
        statuses = locations_status.get(location_id, {})

        if location_id not in locations_status:
            locations_status[location_id] = {}

        for available_fuel_node in location_node.iter('prix'):
            fuel = available_fuel_node.get('nom', '')

            if not statuses.get(fuel, True): # Le carburant était indisponible, et est maintenant disponible
                logging.info(f'  {fuel} devenu disponible')

                locations_status[location_id][fuel] = True

        for unavailable_fuel_node in location_node.iter('rupture'):
            if unavailable_fuel_node.get('type') == 'definitive':
                continue

            fuel = unavailable_fuel_node.get('nom', '')

            if statuses.get(fuel, True): # Le carburant était disponible, et est maintenant indisponible
                logging.info(f'  {fuel} devenu indisponible')

                locations_status[location_id][fuel] = False

    save_locations_status(locations_status)

    logging.info('Effectué.')


if __name__ == '__main__':
    run()
