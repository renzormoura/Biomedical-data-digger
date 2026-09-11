# Roadmap — Biomedical Data Digger

## ✅ Concluído

- Busca direta por PMID, PMCID, DOI, arXiv, OpenAlex, Semantic Scholar e URLs
- Busca por palavras-chave em Europe PMC, OpenAlex, Semantic Scholar, Crossref e arXiv
- Índice de Relevância Bibliográfica com fórmula explicável
- Filtros por áreas médicas e gerais
- Interface Gradio com tema visual
- 11 tipos de análise com prompts especializados
- Sistema de filtros de personalização (público, tom, idioma, detalhe, foco)
- Suporte Groq API (produção) + Ollama (desenvolvimento local)
- Cache de artigos em memória
- Histórico de sessão
- Deploy no Render com CI/CD via GitHub
- Proteção de secrets (.env + .gitignore)

## 🔄 Em andamento

Nenhum item ativo.

## 📋 Próximo

- **Validar fontes em produção** — monitorar disponibilidade de arXiv, Crossref, OpenAlex e Semantic Scholar
- **Avaliação metodológica estruturada** — recurso separado do índice bibliográfico

## 🔮 Futuro

- **Texto completo** — integrar endpoint de full-text da Europe PMC (artigos Open Access)
- **Export PDF/Word** — download do resultado formatado
- **Streaming** — reativar quando migrar para plano pago do Render (mais CPU)
- **Testes automatizados** — cobertura mínima das funções principais
- **Múltiplos artigos** — comparar dois artigos lado a lado
