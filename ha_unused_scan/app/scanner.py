# -*- coding: utf-8 -*-
"""Moteur d'analyse : repère les fichiers packages/*.yaml et les automatisations
Home Assistant qui ne semblent plus servir. Lecture seule (sauf archive.py)."""
import json
import os
import re
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

SKIP_DIRS = {'_archive', 'custom_components', '.git', 'deps', '__pycache__', 'backups',
             'blueprints', 'tts', 'image', 'media', 'node_modules', '.cloud'}
TEXT_EXT = ('.yaml', '.yml', '.html', '.js', '.json', '.jinja', '.txt')
STORAGE_WANTED = ('lovelace', 'energy', 'homeassistant.exposed_entities')
BLOCK_DOMAINS = ('input_number', 'input_boolean', 'input_select', 'input_text',
                 'input_datetime', 'input_button', 'counter', 'timer', 'utility_meter')
ENTITY_RE = re.compile(r'\b([a-z_]+)\.([a-z0-9_]+)\b')
MAX_SIZE = 6 * 1024 * 1024


def config_dir():
    env = os.environ.get('HA_CONFIG')
    if env and os.path.isdir(env):
        return os.path.realpath(env)
    for p in ('/homeassistant', '/config'):
        if os.path.isfile(os.path.join(p, 'configuration.yaml')) or os.path.isdir(os.path.join(p, 'packages')):
            return os.path.realpath(p)
    return None


def slug(text):
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', t.lower()).strip('_')


def _read(path):
    try:
        if os.path.getsize(path) > MAX_SIZE:
            return ''
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def _walk(base):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            p = os.path.join(root, name)
            rel = os.path.relpath(p, base)
            if rel.startswith('.storage' + os.sep):
                if name.startswith(STORAGE_WANTED):
                    yield p, rel
                continue
            if name.startswith('rapport_inutilises'):
                continue
            if name.lower().endswith(TEXT_EXT):
                yield p, rel


def _definitions(texte):
    ids, noms, courant = set(), [], ''
    lignes = texte.splitlines()
    for i, ligne in enumerate(lignes):
        top = re.match(r'^([A-Za-z_]\w*):', ligne)
        if top:
            courant = top.group(1)
        m = re.match(r'^(\w+):\s*$', ligne)
        if m and m.group(1) in BLOCK_DOMAINS:
            dom = 'sensor' if m.group(1) == 'utility_meter' else m.group(1)
            for l2 in lignes[i + 1:]:
                if l2.strip() and not l2.startswith((' ', '#')):
                    break
                k = re.match(r'^  ([a-z0-9_]+):\s*(#.*)?$', l2)
                if k:
                    ids.add(dom + '.' + k.group(1))
        mn = re.match(r'^\s*(?:-\s+)?name:\s*["\']?(.+?)["\']?\s*(#.*)?$', ligne)
        if mn and 'alias' not in ligne and courant not in BLOCK_DOMAINS:
            nom = mn.group(1).strip()
            if nom and not nom.startswith(('{', '!')):
                noms.append(nom)
    return ids, noms


ACTIFS = {'automation': 'automatisation', 'alert': 'alerte', 'script': 'script',
          'rest_command': 'commande REST', 'shell_command': 'commande shell', 'scene': 'scène',
          'notify': 'notification', 'alexa': 'exposition Alexa', 'google_assistant': 'Google Assistant',
          'homekit': 'HomeKit', 'emulated_hue': 'Hue émulé', 'light': 'lumières', 'switch': 'interrupteurs'}


def _actif(texte):
    """Ce que le fichier FAIT tout seul (même si aucune entité n'est citée ailleurs)."""
    cles = set(re.findall(r'^([A-Za-z_]\w*):', texte, re.M))
    out = [v for k, v in ACTIFS.items() if k in cles]
    if re.search(r'^\s*-?\s*(service|action):\s*\S', texte, re.M) and 'automatisation' not in out:
        out.append('appels de service')
    if re.search(r'^\s*-?\s*(trigger|triggers):', texte, re.M) and 'automatisation' not in out:
        out.append('déclencheurs')
    return out


def ha_states(url, token):
    req = urllib.request.Request(url.rstrip('/') + '/states',
                                 headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=20) as r:
        return {s['entity_id']: s for s in json.loads(r.read().decode())}


def scan(jours_inactifs=60, ha_url=None, ha_token=None):
    base = config_dir()
    if not base:
        raise RuntimeError("Dossier de configuration introuvable (/homeassistant ou /config).")
    etats, avertissement = {}, None
    if ha_url and ha_token:
        try:
            etats = ha_states(ha_url, ha_token)
        except Exception as e:  # noqa
            avertissement = "États HA illisibles (%s) : analyse des fichiers seule." % e

    nom_vers_id = defaultdict(list)
    for eid, s in etats.items():
        fn = (s.get('attributes') or {}).get('friendly_name')
        if fn:
            nom_vers_id[fn.strip().lower()].append(eid)

    contenu = {rel: _read(p) for p, rel in _walk(base)}
    usage = defaultdict(set)
    for rel, txt in contenu.items():
        for m in ENTITY_RE.finditer(txt):
            usage[m.group(1) + '.' + m.group(2)].add(rel)
    slug_usage = defaultdict(set)
    for eid, fs in usage.items():
        slug_usage[eid.split('.', 1)[1]] |= fs

    def cite_par(eid, rel):
        if eid.startswith('~'):
            s = eid[1:]
            fs = set()
            for k, v in slug_usage.items():
                if k == s or (k.startswith(s + '_') and k[len(s) + 1:].isdigit()):
                    fs |= v
        else:
            fs = usage.get(eid, set())
        return sorted(f for f in fs if f != rel)

    # index des entités vivantes par suffixe (pour retrouver les ids approximatifs « ~ »)
    par_suffixe = defaultdict(list)
    for eid in etats:
        par_suffixe[eid.split('.', 1)[1]].append(eid)
    maintenant = datetime.now(timezone.utc)

    def etat_de(eid):
        """(etat, age_en_jours) : vivante | indisponible | absente | inconnu."""
        if not etats:
            return 'inconnu', None
        cands = []
        if eid.startswith('~'):
            sl = eid[1:]
            for k, v in par_suffixe.items():
                if k == sl or (k.startswith(sl + '_') and k[len(sl) + 1:].isdigit()):
                    cands += v
        elif eid in etats:
            cands = [eid]
        if not cands:
            return 'absente', None
        vivante = [c for c in cands if etats[c].get('state') not in ('unavailable', 'unknown')]
        if not vivante:
            return 'indisponible', None
        age = None
        try:
            d = datetime.fromisoformat(etats[vivante[0]]['last_updated'].replace('Z', '+00:00'))
            age = (maintenant - d).days
        except (KeyError, ValueError):
            pass
        return 'vivante', age

    pk = os.path.join(base, 'packages')
    noms = sorted(n for n in os.listdir(pk) if n.endswith(('.yaml', '.yml'))) if os.path.isdir(pk) else []
    base_defs = {}
    for n in noms:
        rel = os.path.join('packages', n)
        txt = contenu.get(rel, '')
        ids, noms_e = _definitions(txt)
        items = [{'label': e, 'id': e} for e in sorted(ids)]
        for nom in noms_e:
            trouves = nom_vers_id.get(nom.lower())
            if trouves:
                items += [{'label': nom, 'id': t} for t in trouves]
            else:
                items.append({'label': nom, 'id': '~' + slug(nom)})
        vus, uniques = set(), []
        for it in items:
            if it['id'] not in vus and it['id'] != '~':
                vus.add(it['id'])
                uniques.append(it)
        if uniques:
            for it in uniques:
                it['etat'], it['age'] = etat_de(it['id'])
            base_defs[n] = (rel, uniques, _actif(txt))

    def mentions(n):
        return sorted(r for r, tx in contenu.items()
                      if n in tx and os.path.basename(r) != n)[:3]

    def evaluer(dead):
        res = {}
        for n, (rel, uniques, actif) in base_defs.items():
            ents = []
            for it in uniques:
                cp = [f for f in cite_par(it['id'], rel) if os.path.basename(f) not in dead]
                ents.append(dict(it, cite_par=cp[:3], utilise=bool(cp)))
            res[n] = ents
        return res

    # Un fichier cité seulement par un autre fichier candidat est lui aussi candidat.
    dead, premier = set(), None
    for _ in range(6):
        res = evaluer(dead)
        nouveau = {n for n, e in res.items() if not any(x['utilise'] for x in e)}
        if premier is None:
            premier = set(nouveau)
        if nouveau == dead:
            break
        dead = nouveau

    fichiers = []
    for n, ents in res.items():
        rel, _, actif = base_defs[n]
        nb_ut = sum(1 for x in ents if x['utilise'])
        statut = 'inutilise' if nb_ut == 0 else ('partiel' if nb_ut < len(ents) else 'ok')
        vivantes = sum(1 for x in ents if x['etat'] == 'vivante')
        mortes = sum(1 for x in ents if x['etat'] in ('absente', 'indisponible'))
        raisons, verdict = [], 'utilise'
        if statut == 'inutilise':
            cite_nom = mentions(n)
            if actif:
                raisons.append('Contient : ' + ', '.join(actif))
            if cite_nom:
                raisons.append('Nom du fichier cité dans ' + cite_nom[0])
            if etats and mortes == len(ents):
                raisons.append('Toutes ses entités sont absentes ou indisponibles')
            elif etats and vivantes:
                raisons.append('%d entité(s) encore actives mais affichées nulle part' % vivantes)
            if not etats:
                raisons.append("États des entités non lus (API indisponible)")
            if actif or cite_nom:
                verdict = 'attention'
            elif etats and mortes == len(ents):
                verdict = 'sur'
            else:
                verdict = 'probable'
        try:
            taille = os.path.getsize(os.path.join(base, rel))
        except OSError:
            taille = 0
        fichiers.append({'fichier': n, 'statut': statut, 'verdict': verdict, 'raisons': raisons,
                         'actif': actif, 'total': len(ents), 'utilisees': nb_ut,
                         'vivantes': vivantes, 'mortes': mortes, 'taille': taille,
                         'entites': [{'nom': x['label'], 'id': x['id'].lstrip('~'),
                                      'utilise': x['utilise'], 'cite_par': x['cite_par'],
                                      'etat': x['etat'], 'age': x['age']} for x in ents]})

    # Automatisations (nécessite l'API HA)
    autos = None
    if etats:
        import archive as _arc
        _, blocs = _arc._blocs(contenu.get('automations.yaml', ''))
        casse_par_uid = {}
        DOMS = ('sensor', 'binary_sensor', 'input_number', 'input_boolean', 'switch', 'light',
                'climate', 'cover', 'select', 'number')
        for bl in blocs:
            u = _arc._uid(bl)
            c = {}
            for m in ENTITY_RE.finditer(bl):
                if m.group(1) in DOMS:
                    eid = m.group(1) + '.' + m.group(2)
                    if eid not in etats:
                        c[eid] = 'absente'
                    elif etats[eid].get('state') in ('unavailable', 'unknown'):
                        c[eid] = 'indisponible'
            if u:
                casse_par_uid[u] = c
        liste, jamais, anciennes, desact, cassees = [], [], [], [], {}
        for eid, s in etats.items():
            if not eid.startswith('automation.'):
                continue
            at = s.get('attributes') or {}
            nom = at.get('friendly_name', eid)
            uid = at.get('id')
            off = s.get('state') == 'off'
            lt = at.get('last_triggered')
            j, never = None, not lt
            if lt:
                try:
                    j = (maintenant - datetime.fromisoformat(lt.replace('Z', '+00:00'))).days
                except ValueError:
                    pass
            cas = casse_par_uid.get(uid, {})
            cassees.update(cas)
            raisons = []
            if never:
                raisons.append('jamais déclenchée')
            elif j is not None and j >= jours_inactifs:
                raisons.append('pas déclenchée depuis %d jours' % j)
            if off:
                raisons.append('désactivée')
            if cas:
                raisons.append('%d entité(s) absente(s)/indisponible(s)' % len(cas))
            item = {'nom': nom, 'id': eid, 'uid': uid, 'desactivee': off, 'jamais': never,
                    'jours': j, 'cassees': sorted(cas), 'raisons': raisons}
            liste.append(item)
            if off:
                desact.append(item)
            if never:
                jamais.append(item)
            elif j is not None and j >= jours_inactifs:
                anciennes.append(item)
        liste.sort(key=lambda x: (not x['raisons'], x['nom'].lower()))
        autos = {'liste': liste,
                 'jamais': sorted(jamais, key=lambda x: x['nom']),
                 'anciennes': sorted(anciennes, key=lambda x: -(x['jours'] or 0)),
                 'desactivees': sorted(desact, key=lambda x: x['nom']),
                 'entites_cassees': [{'id': k, 'etat': v} for k, v in sorted(cassees.items())],
                 'jours': jours_inactifs}

    return {'dossier': base, 'nb_fichiers_analyses': len(contenu), 'fichiers': fichiers,
            'automatisations': autos, 'avertissement': avertissement,
            'date': datetime.now().strftime('%d/%m/%Y %H:%M')}
