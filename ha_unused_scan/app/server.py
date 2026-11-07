# -*- coding: utf-8 -*-
"""Serveur web (Ingress Home Assistant) — bibliothèque standard uniquement."""
import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive  # noqa: E402
import scanner  # noqa: E402

PORT = int(os.environ.get('PORT', '8099'))
DEV = os.environ.get('DEV') == '1'
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
INGRESS_IP = '172.30.32.2'


def options():
    try:
        with open('/data/options.json', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ha_api():
    """(url, jeton) de l'API Home Assistant : via le Supervisor, ou HA_URL/HA_TOKEN en test."""
    tok = os.environ.get('SUPERVISOR_TOKEN')
    if tok:
        return 'http://supervisor/core/api', tok
    if os.environ.get('HA_URL') and os.environ.get('HA_TOKEN'):
        return os.environ['HA_URL'].rstrip('/') + '/api', os.environ['HA_TOKEN']
    return None, None


def check_config():
    url, tok = ha_api()
    if not url:
        return {'ok': None, 'message': "API Home Assistant indisponible dans ce mode."}
    req = urllib.request.Request(url + '/config/core/check_config', data=b'{}', method='POST',
                                 headers={'Authorization': 'Bearer ' + tok,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        ok = d.get('result') == 'valid'
        return {'ok': ok, 'message': 'Configuration valide.' if ok else (d.get('errors') or 'Configuration invalide.')}
    except Exception as e:  # noqa
        return {'ok': None, 'message': 'Vérification impossible : %s' % e}


def recharger_automations():
    url, tok = ha_api()
    if not url:
        return False
    req = urllib.request.Request(url + '/services/automation/reload', data=b'{}', method='POST',
                                 headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True
    except Exception:  # noqa
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = 'HAUnusedScan/0.1'

    def log_message(self, fmt, *args):
        sys.stderr.write('[%s] %s\n' % (self.address_string(), fmt % args))

    def _autorise(self):
        if DEV or self.client_address[0] in (INGRESS_IP, '127.0.0.1'):
            return True
        self.send_error(403, 'Accès uniquement via Home Assistant (Ingress).')
        return False

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._autorise():
            return
        u = urlparse(self.path)
        path = u.path.rstrip('/') or '/'
        try:
            if path in ('/', '/index.html'):
                with open(os.path.join(STATIC, 'index.html'), 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == '/api/scan':
                q = parse_qs(u.query)
                jours = int((q.get('jours') or [options().get('jours_inactifs', 60)])[0])
                url, tok = ha_api()
                self._json(scanner.scan(jours, url, tok))
            elif path == '/api/archive':
                self._json({'archives': archive.liste()})
            elif path == '/api/autos/archive':
                self._json({'autos': archive.liste_autos()})
            else:
                self.send_error(404)
        except Exception as e:  # noqa
            self._json({'erreur': str(e)}, 500)

    def do_POST(self):
        if not self._autorise():
            return
        path = urlparse(self.path).path.rstrip('/')
        try:
            n = int(self.headers.get('Content-Length') or 0)
            data = json.loads(self.rfile.read(n).decode() or '{}') if n else {}
            noms = data.get('fichiers') or []
            if path == '/api/archive':
                self._json(archive.archiver(noms))
            elif path == '/api/restore':
                self._json(archive.restaurer(noms))
            elif path == '/api/autos/archive':
                r = archive.archiver_autos(data.get('ids') or [], data.get('noms') or {})
                r['recharge'] = recharger_automations() if r['archives'] else False
                self._json(r)
            elif path == '/api/autos/restore':
                r = archive.restaurer_autos(data.get('ids') or [])
                r['recharge'] = recharger_automations() if r['restaures'] else False
                self._json(r)
            elif path == '/api/check':
                self._json(check_config())
            else:
                self.send_error(404)
        except Exception as e:  # noqa
            self._json({'erreur': str(e)}, 500)


if __name__ == '__main__':
    print('Nettoyeur de configuration : http://0.0.0.0:%d  (dossier : %s)' % (PORT, scanner.config_dir()), flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
