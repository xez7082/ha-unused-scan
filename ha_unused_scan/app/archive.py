# -*- coding: utf-8 -*-
"""Archivage réversible : on DÉPLACE les fichiers packages/*.yaml dans _archive/,
on ne supprime jamais rien."""
import json
import os
import re
import shutil
from datetime import datetime

from scanner import config_dir

NOM_OK = re.compile(r'^[A-Za-z0-9_.\-]+\.ya?ml$')


def _dirs():
    base = config_dir()
    if not base:
        raise RuntimeError('Dossier de configuration introuvable.')
    return os.path.join(base, 'packages'), os.path.join(base, '_archive')


def _manifest(arc):
    p = os.path.join(arc, '_manifeste.json')
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_manifest(arc, data):
    with open(os.path.join(arc, '_manifeste.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def liste():
    pk, arc = _dirs()
    if not os.path.isdir(arc):
        return []
    man = {m['fichier']: m for m in _manifest(arc)}
    out = []
    for n in sorted(os.listdir(arc)):
        if NOM_OK.match(n):
            out.append({'fichier': n, 'date': man.get(n, {}).get('date', ''),
                        'taille': os.path.getsize(os.path.join(arc, n))})
    return out


def archiver(noms):
    pk, arc = _dirs()
    os.makedirs(arc, exist_ok=True)
    man = _manifest(arc)
    faits, erreurs = [], []
    for n in noms:
        if not NOM_OK.match(n or ''):
            erreurs.append({'fichier': n, 'raison': 'nom invalide'})
            continue
        src = os.path.join(pk, n)
        if not os.path.isfile(src):
            erreurs.append({'fichier': n, 'raison': 'introuvable'})
            continue
        dst = os.path.join(arc, n)
        if os.path.exists(dst):
            dst = os.path.join(arc, datetime.now().strftime('%Y%m%d-%H%M%S-') + n)
        shutil.move(src, dst)
        man = [m for m in man if m.get('fichier') != os.path.basename(dst)]
        man.append({'fichier': os.path.basename(dst), 'origine': n,
                    'date': datetime.now().strftime('%d/%m/%Y %H:%M')})
        faits.append(n)
    _save_manifest(arc, man)
    return {'archives': faits, 'erreurs': erreurs}


def restaurer(noms):
    pk, arc = _dirs()
    man = _manifest(arc)
    faits, erreurs = [], []
    for n in noms:
        if not NOM_OK.match(n or ''):
            erreurs.append({'fichier': n, 'raison': 'nom invalide'})
            continue
        src = os.path.join(arc, n)
        if not os.path.isfile(src):
            erreurs.append({'fichier': n, 'raison': 'introuvable dans _archive'})
            continue
        origine = next((m.get('origine') for m in man if m.get('fichier') == n), n)
        if not NOM_OK.match(origine or ''):
            origine = n
        dst = os.path.join(pk, origine)
        if os.path.exists(dst):
            erreurs.append({'fichier': n, 'raison': 'un fichier du même nom existe déjà dans packages'})
            continue
        shutil.move(src, dst)
        man = [m for m in man if m.get('fichier') != n]
        faits.append(origine)
    _save_manifest(arc, man)
    return {'restaures': faits, 'erreurs': erreurs}


# ---------------------------------------------------------------- automatisations
# Les automatisations créées dans l'interface vivent dans automations.yaml.
# « Archiver » = DÉPLACER leur bloc vers _archive/automations_archivees.yaml
# (avec une sauvegarde complète de automations.yaml avant chaque changement).
AUTO_FILE = 'automations.yaml'
AUTO_ARC = 'automations_archivees.yaml'
AUTO_MAN = '_autos_manifeste.json'


def _blocs(txt):
    lignes = txt.splitlines(keepends=True)
    deb = [i for i, l in enumerate(lignes) if l.startswith('- ')]
    if not deb:
        return '', []
    entete = ''.join(lignes[:deb[0]])
    blocs = []
    for s, e in zip(deb, deb[1:] + [len(lignes)]):
        b = ''.join(lignes[s:e])
        blocs.append(b if b.endswith('\n') else b + '\n')
    return entete, blocs


def _uid(bloc):
    m = re.search(r"^(?:- |  )id:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", bloc, re.M)
    return m.group(1) if m else None


def _alias(bloc):
    m = re.search(r"^(?:- |  )alias:\s*['\"]?(.+?)['\"]?\s*$", bloc, re.M)
    return m.group(1) if m else '(sans nom)'


def _lire(p):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def _ecrire(p, txt):
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(txt)
    os.replace(tmp, p)


def _ecrire_liste(p, entete, blocs):
    _ecrire(p, (entete + ''.join(blocs)) if blocs else '[]\n')


def archiver_autos(uids, noms=None):
    base = config_dir()
    arc = os.path.join(base, '_archive')
    os.makedirs(arc, exist_ok=True)
    src = os.path.join(base, AUTO_FILE)
    txt = _lire(src)
    entete, blocs = _blocs(txt)
    voulus = set(u for u in uids if u)
    garde, deplaces = [], []
    noms = noms or {}
    # repli : si l'identifiant n'est pas dans le fichier, on cherche l'alias (seulement s'il est unique)
    alias_de = {}
    for b in blocs:
        alias_de.setdefault(_alias(b), []).append(b)
    par_alias = {}
    for u in voulus:
        if not any(_uid(b) == u for b in blocs) and noms.get(u) and len(alias_de.get(noms[u], [])) == 1:
            par_alias[id(alias_de[noms[u]][0])] = u
    trouves = set()
    for b in blocs:
        if _uid(b) in voulus:
            deplaces.append(b)
            trouves.add(_uid(b))
        elif id(b) in par_alias and _uid(b):
            deplaces.append(b)
            trouves.add(par_alias[id(b)])
        else:
            garde.append(b)
    erreurs = [{'id': noms.get(u, u), 'raison': 'introuvable dans automations.yaml (définie ailleurs ?)'} for u in sorted(voulus - trouves)]
    if not deplaces:
        return {'archives': [], 'erreurs': erreurs}
    _ecrire(os.path.join(arc, 'automations_%s.sauvegarde.yaml' % datetime.now().strftime('%Y%m%d-%H%M%S')), txt)
    dst = os.path.join(arc, AUTO_ARC)
    ancien = _lire(dst)
    e2, b2 = _blocs(ancien)
    _ecrire_liste(dst, e2, b2 + deplaces)
    try:
        man = json.loads(_lire(os.path.join(arc, AUTO_MAN)) or '{}')
    except ValueError:
        man = {}
    for b in deplaces:
        man[_uid(b)] = datetime.now().strftime('%d/%m/%Y %H:%M')
    _ecrire(os.path.join(arc, AUTO_MAN), json.dumps(man, ensure_ascii=False, indent=1))
    _ecrire_liste(src, entete, garde)
    return {'archives': [_alias(b) for b in deplaces], 'erreurs': erreurs}


def liste_autos():
    base = config_dir()
    if not base:
        return []
    arc = os.path.join(base, '_archive')
    _, blocs = _blocs(_lire(os.path.join(arc, AUTO_ARC)))
    try:
        man = json.loads(_lire(os.path.join(arc, AUTO_MAN)) or '{}')
    except ValueError:
        man = {}
    return [{'uid': _uid(b), 'nom': _alias(b), 'date': man.get(_uid(b), '')} for b in blocs if _uid(b)]


def restaurer_autos(uids):
    base = config_dir()
    arc = os.path.join(base, '_archive')
    src = os.path.join(base, AUTO_FILE)
    entete, blocs = _blocs(_lire(src))
    present = {_uid(b) for b in blocs}
    dst = os.path.join(arc, AUTO_ARC)
    e2, b2 = _blocs(_lire(dst))
    voulus = set(uids)
    reste, retour, erreurs = [], [], []
    for b in b2:
        u = _uid(b)
        if u in voulus:
            if u in present:
                erreurs.append({'id': u, 'raison': 'déjà présente dans automations.yaml'})
                reste.append(b)
            else:
                retour.append(b)
        else:
            reste.append(b)
    if retour:
        _ecrire(os.path.join(arc, 'automations_%s.sauvegarde.yaml' % datetime.now().strftime('%Y%m%d-%H%M%S')), _lire(src))
        _ecrire_liste(src, entete, blocs + retour)
        _ecrire_liste(dst, e2, reste)
    return {'restaures': [_alias(b) for b in retour], 'erreurs': erreurs}
