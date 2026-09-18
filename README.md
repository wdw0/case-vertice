# Vértice Intelligence

Protótipo de um **Decision Copilot com IA** desenvolvido para o Case Vértice.

O sistema utiliza uma camada analítica determinística para identificar oportunidades em **margem, marketing, estoque e atendimento**. A IA utiliza **Tool Calling** para consultar essas informações e gerar respostas executivas rastreáveis.

## Arquitetura

```text
Usuário
   ↓
LLM
   ↓
Tool Calling
   ↓
Tools determinísticas
   ↓
Contexto analítico
   ↓
Resposta executiva
```

## Requisitos

- Python 3.10+
- Chave de API do EloAgents

## Como executar

Clone o repositório e entre na pasta:

```bash
git clone <URL_DO_REPOSITORIO>
cd case-vertice
```

Crie o ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

Configure as variáveis de ambiente:

```bash
cp .env.example .env
```

Edite o `.env`:

```env
ELOAGENTS_API_KEY=sua_chave
ELOAGENTS_API_BASE=https://chat.eloagents.click/api
VERTICE_MODEL=openai/gemini-3-flash-preview
```

### Executar demonstração sem LLM

```bash
python app.py --demo "Onde estamos perdendo margem?"
```

Outros exemplos:

```bash
python app.py --demo "Quais canais têm maior eficiência de aquisição?"
python app.py --demo "Quais problemas de estoque deveriam ser analisados?"
```

### Executar com LLM

```bash
python app.py "Onde estamos perdendo margem?"
```

Exemplo:

```bash
python app.py "Quais oportunidades deveriam ser priorizadas nos próximos 30 dias?"
```

## Estrutura

```text
ai/          # Agente, Tools e integração com o LLM
data/        # Contexto analítico estruturado
notebooks/   # Camada analítica da Etapa 1
tests/       # Testes automatizados
app.py       # Interface de execução
```

## Segurança

O arquivo `.env` contém credenciais e não deve ser versionado.

O arquivo `.env.example` serve apenas como modelo de configuração.
