# Vértice Intelligence

> **AI Decision Copilot para o Case Vértice Retail**

O **Vértice Intelligence** é um protótipo de Decision Copilot desenvolvido para transformar perguntas executivas sobre os dados do case em respostas baseadas em evidências estruturadas, cálculos determinísticos e uma camada de síntese por LLM.

A proposta não é criar um chatbot genérico. O sistema foi desenhado para funcionar como uma **camada de decisão sobre analytics**, mantendo separadas a extração/cálculo dos dados e a interpretação em linguagem natural.

---

## Visão geral

O fluxo principal da aplicação é:

```text
                    Usuário
                       │
                       ▼
             Router determinístico
                       │
                       ▼
              Tool analítica
              determinística
                       │
                       ▼
          Evidência estruturada
                       │
                       ▼
              EloAgents / LLM
            camada de síntese
                       │
                       ▼
                 Resposta
```

O ponto central da arquitetura é que o **LLM não decide qual ferramenta executar e não recalcula os KPIs**. A aplicação seleciona deterministicamente o módulo analítico, executa a consulta e só então envia a evidência estruturada para a camada de linguagem.

---

## Objetivo do projeto

O case propõe uma análise integrada da operação da Vértice Retail, envolvendo:

- margem e rentabilidade;
- devoluções;
- marketing e aquisição;
- estoque;
- atendimento;
- clientes;
- priorização de oportunidades;
- impacto financeiro e operacional.

O Copilot transforma essas análises em uma interface conversacional orientada à decisão.

Exemplos de perguntas:

```text
Onde estamos perdendo margem?

Quais canais têm maior eficiência de aquisição?

Quais problemas de estoque deveriam ser analisados?

Quais oportunidades estão priorizadas?

Qual é a OPP-MKT-01?

O que você tem a dizer sobre o produto Calça Jeans Moderno Nude?

Qual é o primeiro produto por rentabilidade?
```

---

# Principais funcionalidades

## Margem e devoluções

O Copilot consulta a camada analítica de margem para responder sobre:

- margem de contribuição;
- efeito econômico das devoluções;
- pedidos com margem negativa;
- impacto de frete e descontos;
- oportunidades relacionadas à erosão de margem.

A análise preserva as premissas e limitações registradas no contexto estruturado.

---

## Marketing e aquisição

O módulo de marketing permite:

- comparar canais;
- ordenar canais por ROAS;
- ordenar canais por CAC;
- consultar investimento;
- consultar receita gerada;
- analisar oportunidades de eficiência.

### Definição utilizada pelo Copilot

Neste projeto:

```text
ROAS = receita_gerada / investimento

CAC = investimento / conversões
```

Essas métricas são calculadas a partir da camada de marketing do case.

Isso é importante porque o Dashboard possui também uma visão integrada de canais que cruza dados transacionais de vendas com marketing. Portanto, um ROAS exibido pelo Dashboard pode não ser numericamente igual ao ROAS do Copilot.

O Copilot trata como fonte de verdade para eficiência de aquisição os dados da camada de marketing, evitando deduzir atribuição 1:1 entre investimento de marketing e pedidos da base transacional.

---

## Estoque

O módulo de estoque analisa:

- SKUs em ruptura;
- rupturas em produtos de alta demanda;
- cobertura teórica;
- lead time de reposição;
- estoque disponível;
- exposição financeira potencial;
- oportunidades relacionadas à reposição e capital de giro.

## Atendimento

O módulo de atendimento contempla:

- volume de tickets;
- WISMO;
- custo operacional;
- concentração de chamados;
- oportunidades de automação;
- indicadores de experiência.

A concentração de tickets é usada como sinal operacional. Ela não é tratada, por si só, como prova de churn individual.

---

# Interface

A interface foi construída com **Streamlit**.

O projeto possui duas áreas principais:

```text
Copilot
Oportunidades
```

### Copilot

Área conversacional para perguntas sobre os dados e oportunidades.

### Oportunidades

Área para visualização das oportunidades estruturadas e priorizadas.

O Dashboard executivo do case é uma aplicação separada e não é modificado pelo Copilot.

---

# Tecnologias

| Tecnologia | Uso |
|---|---|
| Python | Camada principal da aplicação |
| Streamlit | Interface web |
| LangChain Core | Mensagens e integração da camada LLM |
| LangChain LiteLLM | Integração com o provedor do modelo |
| LiteLLM | Gateway de modelo |
| EloAgents | Provedor do LLM utilizado no projeto |
| Pydantic | Validação de estruturas |
| Pandas | Camada analítica utilizada na preparação dos dados |
| pytest | Testes automatizados |
| python-dotenv | Configuração de variáveis de ambiente |

---

# Requisitos



- Python 3.10+
- `pip`
- chave de API do EloAgents disponibilizada pelo bootcamp.


---

# Instalação

Clone o repositório:

```bash
git clone <URL_DO_REPOSITORIO>
cd <PASTA_DO_PROJETO>
```

Crie o ambiente virtual:

```bash
python3 -m venv .venv
```

Ative o ambiente.

### Linux / macOS

```bash
source .venv/bin/activate
```

### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

---

# Configuração

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Configure o `.env`:

```env
ELOAGENTS_API_KEY=sua_chave_aqui
ELOAGENTS_API_BASE=https://chat.eloagents.click/api
VERTICE_MODEL=openai/gemini-3-flash-preview
```

A chave deve permanecer apenas no `.env`.

**Nunca faça commit da chave para o GitHub.**

---

# Executando

Com o ambiente virtual ativado:

```bash
streamlit run streamlit_app.py
```

Depois abra:

```text
http://localhost:8501
```

Caso a porta esteja ocupada:

```bash
streamlit run streamlit_app.py --server.port 8502
```

---

# Testes

O projeto possui uma suíte de **19 testes** distribuídos entre:

- contrato do contexto;
- Router;
- execução das ferramentas;
- comportamento do Agent;
- follow-ups;
- Product Analytics;
- regras semânticas de estoque;
- contrato de marketing.
