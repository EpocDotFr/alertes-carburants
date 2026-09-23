# Alertes carburants

Script Python qui alerte via SMS des disponibilités de carburants.

Seulement pour la France, désolé. [Article de blog associé](https://epoc.fr)

## Prérequis

  - Python >= 3.11
  - Un compte [SMS Partner](https://www.smspartner.fr/) avec suffisamment de crédits SMS, ainsi qu'une [clef API](https://www.docpartner.dev/api/sms-partner) valide

## Installation

Clonez ce dépôt quelque part.

Aussi, vous pourriez télécharger seulement `check.py` si vous ne voulez pas vous embêter avec Git car tout est intégré
dans ce script (regarde maman, sans dépendances !).

## Configuration

La configuration se passe via le fichier `config.toml`, qui **doit** être situé à côté de `check.py`. Vous trouverez
un fichier de configuration d'exemple (`config.example.toml`) pour commencer, tout y est expliqué.

## Utilisation

### Vérifier les disponibilités

Ce projet consiste en un seul script Python, `check.py`, qui doit être invoqué à interval régulier (typiquement en
utilisant un planificateur de tâches comme cron). Il va télécharger, analyser et déclencher les alertes SMS à partir du
[flux temps réel officiel](https://www.prix-carburants.gouv.fr/rubrique/opendata/) des prix des carburants en France.

Par exemple, vérifier les disponibilités toutes les deux heures :

```
0 */2 * * * ./chemin/vers/check.py
```

Ne le programmez pas plus fréquemment que toutes les 10 minutes : il s'agit de l'intervalle d'actualisation du flux
susmentionné.

Le fichier `locstatus.json` est créé automatiquement et ne devrait jamais être modifié ni supprimé. Il sert à persister
l'état de l'approvisionnement pour chaque point de vente et chaque carburant configuré.

### Mode simulation (dry-run / sandbox)

```bash
./check.py --dry-run
```

Si le mode simulation est activé, les SMS ne sont pas réellement envoyés. Vous les trouverez tout de même dans la boîte
d'envoi de votre tableau de bord SMS Partner (marqués comme "Sandbox").
