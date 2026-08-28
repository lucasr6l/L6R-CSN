import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from server import app as fastapi_app
from a2wsgi import ASGIMiddleware

# Adaptador que garante que o SCRIPT_NAME seja tratado corretamente pela HostGator
def application(environ, start_response):
    path_info = environ.get('PATH_INFO', '')
    
    # Se a HostGator enviar a rota completa com /api-geoportal, nós removemos para o FastAPI entender
    if path_info.startswith('/api-geoportal'):
        environ['PATH_INFO'] = path_info[len('/api-geoportal'):]
        environ['SCRIPT_NAME'] = '/api-geoportal'
        
    wsgi_app = ASGIMiddleware(fastapi_app)
    return wsgi_app(environ, start_response)
