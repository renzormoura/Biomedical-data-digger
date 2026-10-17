# Maquete do redesign visual

Maquete estática (HTML, CSS e um script mínimo de tema) que acompanha `docs/roadmap/plano-redesign-visual.md`.
Dados fictícios; não faz chamadas de rede nem usa o back-end.

- `index.html`: página inicial.
- `artigo.html`: página do artigo, com painel de confiabilidade recolhível e seletor de citação.
- `styles.css`: tokens e componentes. O tema segue o sistema (`prefers-color-scheme`); o botão do cabeçalho alterna e lembra a escolha.

Para ver, sirva a pasta (o navegador não carrega o CSS em visualizações `data:`):

```bash
cd prototype/redesign && python -m http.server 7870
```

Sem emoji, sem fontes ou scripts externos; ícones em SVG de traço embutidos.
