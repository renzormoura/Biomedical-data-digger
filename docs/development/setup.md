# Setup de Desenvolvimento

## Pré-requisitos
- Python 3.11.9
- Git
- Conta Groq (para obter API key): https://console.groq.com

## Configuração local

### 1. Clonar o repositório
```bash
git clone https://github.com/renzormoura/Biomedical-data-digger.git
cd Biomedical-data-digger
```

### 2. Criar e ativar ambiente virtual
```bash
python -m venv venv

# Windows PowerShell
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Instalar dependências
```bash
pip install -r biomedical-article-summariser/requirements.txt
```

### 4. Configurar variáveis de ambiente
Criar arquivo `biomedical-article-summariser/.env`:
```
GROQ_API_KEY=sua_chave_aqui
DATABASE_PATH=accounts.sqlite3
```

A chave é obtida em: https://console.groq.com/keys

### 5. Executar
```bash
cd biomedical-article-summariser
python biomedical_data_digger.py
```

Acesse: http://localhost:7860

## Alternativa: usar Ollama local
Se não quiser usar a Groq API, instale o Ollama (https://ollama.com) e não defina `GROQ_API_KEY`. O app detecta automaticamente e usa Ollama.

## Verificar sintaxe do código
```bash
python -c "import ast; ast.parse(open('biomedical_data_digger.py', encoding='utf-8').read()); print('OK')"

## Executar testes

Na raiz do projeto:

```bash
python -m unittest discover -s tests -v
```
```

## Deploy para produção (Render)
```bash
git add biomedical-article-summariser/biomedical_data_digger.py
git commit -m "descrição da alteração"
git push
```
O Render detecta o push e faz redeploy automaticamente.

## Configuração do Render (painel web)
| Campo | Valor |
|---|---|
| Root Directory | `biomedical-article-summariser` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python biomedical_data_digger.py` |
| Environment: GROQ_API_KEY | (sua chave) |
| Environment: PYTHON_VERSION | `3.11.9` |
| Environment: DATABASE_URL | URL privada do PostgreSQL |
| Environment: APP_ENV | `production` |

**CRÍTICO:** A variável `PYTHON_VERSION=3.11.9` deve estar definida no painel do Render. Sem ela o Render usa Python 3.14 e o build falha.

### Banco de contas

As contas são armazenadas na tabela `users`. Em produção, crie um PostgreSQL
persistente e configure sua URL privada na variável `DATABASE_URL` do serviço
web. No Render, use a Internal Database URL do banco quando o banco estiver no
mesmo ambiente. O serviço não inicia em produção sem essa variável, evitando
que contas sejam gravadas acidentalmente no disco efêmero do plano Free.

Para desenvolvimento local, a ausência de `DATABASE_URL` usa SQLite em
`biomedical-article-summariser/accounts.sqlite3`. Esse arquivo é apenas um
fallback local e não deve ser usado para persistência no Render.
