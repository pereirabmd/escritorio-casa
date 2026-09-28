"""Ponto de entrada de produção: `uvicorn pulse.asgi:app`. Separado para que importar `pulse.main` nos testes
não leia o ambiente nem abra bases de dados."""

from pulse.main import create_app

app = create_app()
