## Resumidor de Resumos de Artigos Biomédicos usando Europe PMC + Ollama

Este é um aplicativo simples que demonstra um resumidor de resumos de artigos, utilizando a API do Europe PMC e LLMs do Ollama para gerar resumos concisos da literatura biomédica.

## 🔍 Sobre o Europe PMC (EPMC)
O Europe PMC é um banco de dados gratuito e de acesso aberto que disponibiliza milhões de artigos, artigos científicos e preprints das ciências da vida e da biomedicina. Faz parte da rede PubMed Central International (PMCI).

## Funcionalidades

Esta solução apresenta 2 métodos:
1. Uma demonstração simples via notebook Jupyter
2. Uma demonstração interativa via Gradio, executada no seu computador local.

**Funcionalidades principais:**
- Buscar metadados e resumo de um artigo via API do Europe PMC (usando um PMCID fornecido).
- Pré-processar e limpar o texto do resumo, removendo tags desnecessárias, por exemplo tags de referência ou fórmulas matemáticas.
- Resumir os abstracts em tópicos (bullet points) + um parágrafo curto usando modelos do Ollama.

## 📌 Como usar

- Acesse o [site do Europe PMC](https://europepmc.org/).
- Use a barra de pesquisa para encontrar um artigo de acesso aberto por palavras-chave, nomes de entidades, revista ou autor. Ex.: Genes, Diseases, nutrition etc.
- Como o app atualmente funciona apenas com artigos de acesso aberto, você precisará restringir os resultados a artigos `open-access`: adicione filtros como `HAS_FT:Y` ou `IN_EPMC:Y` à sua sintaxe de busca. Ex.: `"Genes: HAS_FT:Y"`
- Selecione o artigo de interesse e copie o PMCID dele (ex.: PMC1234567).

- Execute o resumidor:
  - via notebook: Cole o `PMCID` como string na função `display_response`, após executar todas as outras células.
  - via Gradio:
    - execute o script Python via CLI:
    ```python
    python article_summariser-gradio.py
    ```
    - Cole o `PMCID` que você copiou no campo de texto `Enter a **EuropePMC Article ID`.
    - Clique no botão `Fetch Article Abstract and generate Summary`.
    **Obs.:** Observei que usar `llama3.2` roda mais rápido no meu PC. Você pode experimentar alguns atrasos com os outros modelos. Também certifique-se de já ter o Ollama em execução via `ollama serve` no seu terminal antes de rodar o script.


c:\Users\renzo\OneDrive\Desktop\teste\venv\Scripts\python.exe "c:\Users\renzo\OneDrive\Desktop\teste\biomedical-article-summariser\article_summariser-gradio.py"
