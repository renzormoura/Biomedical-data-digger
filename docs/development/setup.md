# Preparar o ambiente de desenvolvimento

## Pré-requisitos
- **Python 3.10 ou 3.11** (produção usa 3.11.9; o CI roda 3.10 e 3.11).
- **Git** e **Node.js 20** (somente para os testes de JavaScript com `node --test`).
- Conta na Groq (opcional) para o Laboratório de IA, ou Ollama local. Sem nenhum dos dois, tudo funciona, exceto o Laboratório.

## Passo a passo
```bash
git clone <URL do repositório privado>
cd Biomedical_data_digger

python -m venv .venv_local
# Windows (PowerShell):  .venv_local\Scripts\Activate.ps1
# Linux/Mac:             source .venv_local/bin/activate

pip install -r requirements-dev.txt        # inclui as dependências do servidor
```

Configuração local (opcional): crie `biomedical-article-summariser/.env`:
```
DATABASE_PATH=accounts.sqlite3
GROQ_API_KEY=<sua chave>
```
Sem `DATABASE_URL`, o produto usa SQLite local (`accounts.sqlite3`, ignorado pelo Git). Todas as variáveis estão em [Configuração](../operacao/configuracao.md).

## Executar
```bash
cd biomedical-article-summariser
python biomedical_data_digger.py
```
Abra `http://localhost:7860`. **Depois de editar JS ou CSS, reinicie o servidor**: os arquivos estáticos levam um hash de versão calculado na subida.

Para testar o Laboratório de IA sem chave da Groq, instale o [Ollama](https://ollama.com) e escolha o modelo "Llama (local)".

## Verificações antes de commitar
```bash
ruff check biomedical-article-summariser tests evals scripts
mypy
pytest                      # cobertura mínima de 80% no CI
node --test tests/js/browse-lib.test.js
```
Os mesmos passos rodam no CI. Há um `.pre-commit-config.yaml` (ruff, mypy e pytest) se quiser automatizar.

## Atualizar dados e fontes
- Dados do Brasil: [Atualização dos dados do Brasil](../operacao/dados-brasil.md).
- Fontes do feed: `python scripts/verificar_feeds.py`.

## Problemas comuns
| Sintoma | Causa e solução |
|---|---|
| Alterei o CSS/JS e nada mudou | Reinicie o servidor (hash dos assets) e recarregue com cache limpo |
| `ModuleNotFoundError` ao rodar testes | Rode `pytest` na raiz (o `pyproject.toml` define o `pythonpath`) |
| Falha ao gerar o instantâneo da Rename | Falta `pypdf` (está em `requirements-dev.txt`) |
| Busca lenta localmente | A OpenAIRE é lenta; é esperado ver o aviso "demorou demais" |
| Erro de banco em produção | Veja o [Runbook](../operacao/runbook.md#banco-de-dados) |
