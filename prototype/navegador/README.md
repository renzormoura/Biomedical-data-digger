# Navegador de artigos — maquete navegável

Maquete para **testar a ideia com pessoas** antes de construir (ver `docs/roadmap/navegador-de-artigos-descoberta.md`).
É independente do app atual: HTML, CSS e JavaScript puros, **sem servidor, sem rede e sem IA**.

> **Todos os artigos são fictícios** (títulos, autores, periódicos, DOIs e números inventados, sempre marcados com
> "(exemplo)"). Nada aqui serve para pesquisar de verdade.

## Como abrir

```bash
cd prototype/navegador
python -m http.server 7880
```

Abra `http://127.0.0.1:7880/index.html`. (Abrir o `index.html` direto no navegador também funciona, mas a cópia para a
área de transferência pode ser bloqueada em `file://`.)

## O que dá para testar

| Tela | O que mostra |
|---|---|
| **Início** | Busca e quatro entradas por perfil (estudante, professor, pesquisador, profissional) |
| **Busca** | Filtros por ano, tipo de estudo, acesso aberto, área e idioma; ordenação; contagem por filtro; termos destacados; paginação; o estado fica na URL |
| **Artigo** | Selos, citação ABNT/APA/Vancouver, resumo organizado com o texto original, números com a frase de origem (sem IA), metadados, palavras-chave clicáveis, artigos semelhantes, etiquetas e listas |
| **Biblioteca** | Artigos salvos, filtro por etiqueta, exportação BibTeX e RIS, cópia das referências ABNT, listas de leitura |
| **Lista compartilhada** | Link que carrega a lista na própria URL (na versão real seria um endereço curto) |
| **Modo teste** | Cinco tarefas por perfil, cronômetro, resultado (conseguiu/desistiu), registro de ações e exportação em JSON |

O botão "Resumir com IA" aparece **desativado** de propósito: a ideia é que, na versão real, a IA seja opcional.

## Conduzindo um teste de usabilidade

1. Abra **Modo teste**, peça à pessoa que leia a tarefa em voz alta e clique em **Iniciar**.
2. Deixe-a navegar sem ajuda; observe onde hesita. Ao terminar, clique em **Conseguiu** ou **Desistiu**.
3. Ao final, **Exportar JSON** (resultados e ações) e **Apagar dados do teste** antes da próxima pessoa.

Os dados (biblioteca, listas, registro do teste) ficam **só no navegador** (`localStorage`).

## Testes automatizados da lógica

```bash
node --test tests/lib.test.js
```

Cobrem busca, filtros, ordenação, extração sem IA, citações, BibTeX/RIS, listas por URL (entrada não confiável) e a
integridade dos dados fictícios. A interface foi verificada manualmente no navegador (desktop e celular, tema claro e escuro).

## Limites da maquete

- 14 artigos fixos; a busca é por texto simples, não representa a qualidade de uma busca real.
- Sem contas, sem sincronização entre dispositivos, sem acesso aberto real (os links são simulados).
- A extração por palavras-chave pode errar; na versão real teria os mesmos avisos do app principal.

## Como isto vira o produto real (se a descoberta validar)

A lógica de `lib.js` tem equivalentes já existentes no app (`extraction.py`, `citations.py`, `article_services.py`).
O que seria novo: fonte principal de busca por consulta, detecção de acesso aberto, e armazenamento de bibliotecas e listas
por conta no PostgreSQL.
