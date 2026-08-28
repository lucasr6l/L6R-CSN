import sys
import os

# Adiciona o diretório atual no path do Python
sys.path.insert(0, os.path.dirname(__file__))

# Importa a aplicação FastAPI
from server import app as fastapi_app

# Usa o adaptador a2wsgi para converter de ASGI para WSGI (padrão da HostGator)
from a2wsgi import ASGIMiddleware

# A HostGator sempre procura pela variável "application"
application = ASGIMiddleware(fastapi_app)
