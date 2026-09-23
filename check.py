#!/usr/bin/env python3
from typing import Dict, Any, List, TypedDict
from urllib.request import Request, urlopen
from xml.etree import ElementTree as etree
from argparse import ArgumentParser
from pathlib import Path
from io import BytesIO
import zipfile
import tomllib
import logging
import json
import enum
import sys
import re

logging.basicConfig(level=logging.INFO)

Alerts = TypedDict('Alerts', {'available': List[str], 'unavailable': List[str]})


@enum.unique
class Fuel(enum.StrEnum):
    Diesel = 'Gazole'
    E85 = 'E85'
    Lpg = 'GPLc'
    Unleaded95E10 = 'E10'
    Unleaded95E5 = 'SP95'
    Unleaded98E5 = 'SP98'


def load_config() -> Dict[str, Any]:
    logging.info('Chargement de la configuration...')

    try:
        with open(Path(__file__).parent / 'config.toml', 'rb') as f:
            config = tomllib.load(f)
    except FileNotFoundError:
        logging.critical('config.toml introuvable, abandon.')

        sys.exit(1)

    try:
        if not isinstance(config.get('smspartner_api_key'), str):
            raise ValueError('Pas d\'entrée "smspartner_api_key" dans la configuration')
        elif not isinstance(config.get('recipients'), list):
            raise ValueError('Pas d\'entrée "recipients" dans la configuration')
        elif not isinstance(config.get('locations'), dict):
            raise ValueError('Pas d\'entrées "locations" dans la configuration')
        elif isinstance(config.get('sender'), str) and re.fullmatch(r'[a-z0-9]{3,11}', config['sender']) is None:
            raise ValueError('"sender" invalide dans la configuration : doit être composé de 3 à 11 caractères exclusivement alphanumériques')
    except ValueError as e:
        logging.critical(f'{e} (abandon)')

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


def create_alerts(locations_config: Dict[str, Any]) -> Dict[str, Alerts]:
    locations_status = load_locations_status()
    xml = fetch_feed()
    alerts = {}

    for location_node in xml.iter('pdv'):
        location_id = location_node.get('id')

        if not location_id:
            continue

        if location_id not in locations_config:
            try:
                del locations_status[location_id]
            except KeyError:
                pass

            continue

        logging.info(f'Vérification de {location_id}...')

        location = locations_config[location_id]
        statuses = locations_status.get(location_id, {})

        if location_id not in locations_status:
            locations_status[location_id] = {}

        for available_fuel_node in location_node.iter('prix'):
            fuel = available_fuel_node.get('nom', '')

            if fuel not in location['fuels']:
                try:
                    del locations_status[location_id][fuel]
                except KeyError:
                    pass

                continue

            if not statuses.get(fuel, True): # Le carburant était indisponible, et est maintenant disponible
                logging.info(f'  {fuel} devenu disponible')

                if location['label'] not in alerts:
                    alerts[location['label']] = {}

                if 'available' not in alerts[location['label']]:
                    alerts[location['label']]['available'] = []

                alerts[location['label']]['available'].append(fuel)
                alerts[location['label']]['available'].sort()

            locations_status[location_id][fuel] = True

        for unavailable_fuel_node in location_node.iter('rupture'):
            fuel = unavailable_fuel_node.get('nom', '')

            if unavailable_fuel_node.get('type') == 'definitive' or fuel not in location['fuels']:
                try:
                    del locations_status[location_id][fuel]
                except KeyError:
                    pass

                continue

            if statuses.get(fuel, True): # Le carburant était disponible, et est maintenant indisponible
                logging.info(f'  {fuel} devenu indisponible')

                if location['label'] not in alerts:
                    alerts[location['label']] = {}

                if 'unavailable' not in alerts[location['label']]:
                    alerts[location['label']]['unavailable'] = []

                alerts[location['label']]['unavailable'].append(fuel)
                alerts[location['label']]['unavailable'].sort()

            locations_status[location_id][fuel] = False

    save_locations_status(locations_status)

    return dict(
        sorted(alerts.items())
    )


def load_locations_status() -> Dict[str, Dict[str, bool]]:
    logging.info('Chargement des statuts...')

    try:
        with open(Path(__file__).parent / 'locstatus.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.info('  Inexistant pour l\'instant')

        return {}


def fetch_feed() -> etree.ElementTree:
    logging.info('Récupération du flux...')

    request = Request(
        'https://donnees.roulez-eco.fr/opendata/instantane_ruptures',
        headers={
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0',
        },
        method='GET'
    )

    with urlopen(request) as response:
        with zipfile.ZipFile(BytesIO(response.read())) as zf:
            return etree.parse(zf.open('PrixCarburants_instantane_ruptures.xml'))


def save_locations_status(statuses: Dict[str, Dict[str, bool]]) -> None:
    logging.info('Sauvegarde des statuts...')

    with open(Path(__file__).parent / 'locstatus.json', 'w') as f:
        json.dump(statuses, f)


def alerts_to_message(alerts: Dict[str, Alerts]) -> str:
    message = []

    for location_name, availabilities in alerts.items():
        location_message = f'- {location_name} ::br:'

        if 'unavailable' in availabilities:
            location_message += 'Indispo : {}'.format(
                ', '.join(availabilities['unavailable'])
            )

        if 'available' in availabilities:
            location_message += 'Dispo : {}'.format(
                ', '.join(availabilities['available'])
            )

        message.append(location_message)

    return ':br::br:'.join(message)


def send_sms(config: Dict[str, Any], message: str, dry_run: bool = True) -> None:
    logging.info('Envoi du SMS...')

    urlopen(Request(
        'https://api.smspartner.fr/v1/send',
        data=json.dumps({
            'apiKey': config['smspartner_api_key'],
            'phoneNumbers': ','.join(config['recipients']),
            'message': message,
            'sender': config.get('sender', 'AlerteCarbu'),
            'sandbox': int(dry_run),
            '_format': 'json',
        }).encode('utf-8'),
        method='POST'
    ))


def run() -> None:
    arg_parser = ArgumentParser(
        description='Script Python qui alerte via SMS des disponibilités de carburants'
    )

    arg_parser.add_argument(
        '--dry-run',
        help='Ne pas vraiment envoyer de SMS (mode sandbox)',
        action='store_true'
    )

    args = arg_parser.parse_args()

    if args.dry_run:
        logging.info('Mode sandbox activé')

    config = load_config()

    alerts = create_alerts(config.get('locations'))

    if alerts:
        send_sms(
            config,
            alerts_to_message(alerts),
            args.dry_run
        )

        logging.info('Effectué.')
    else:
        logging.info('Aucune alerte à envoyer.')

if __name__ == '__main__':
    run()
