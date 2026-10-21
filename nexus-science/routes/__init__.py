"""Rotas JSON do navegador de artigos, uma por dominio (descoberta, biblioteca, relatorios, avisos, feed...).

Cada modulo expoe `register_<dominio>_routes(app, ctx)`; `ctx` e o `ApiContext` com as dependencias.
"""
