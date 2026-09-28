from __future__ import annotations

from fastapi import APIRouter, Request

from pulse import VERSION

router = APIRouter(tags=["sistema"])


@router.get("/health")
def health(request: Request):
    """Estado do Pulse e dos serviços de que depende. Uma falha num módulo não derruba o resto (modo degradado)."""
    estado = request.app.state
    try:
        conn = estado.db()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        base = "ok"
    except Exception:
        base = "indisponivel"
    dados = "ok" if estado.dados.saude() else "indisponivel"
    componentes = {"base_de_dados": base, "dados_api": dados}
    return {"estado": "ok" if all(v == "ok" for v in componentes.values()) else "degradado",
            "versao": VERSION, "ambiente": estado.settings.env, "componentes": componentes}


@router.get("/version")
def version():
    return {"versao": VERSION}
