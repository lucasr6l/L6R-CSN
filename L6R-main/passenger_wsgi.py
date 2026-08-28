import sys
import os

def application(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/plain; charset=utf-8')])
    message = 'PASSENGER ESTA FUNCIONANDO PERFEITAMENTE!\n'
    version = 'Versão do Python: %s\n' % sys.version.split()[0]
    return [(message + version).encode('utf-8')]
