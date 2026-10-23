# Total Loss Investigator — LangGraph workshop sandbox

Sandbox de **seguradora fictícia** para Google Colab: OCR com Tesseract, confiança e bounding boxes por palavra, extração estruturada, Confidence Gate determinístico, revisão humana com `interrupt()` e `Command(resume=...)`, Supervisor cíclico, especialistas com mock APIs e relatório Pydantic.

## Como executar localmente

Na raiz do projeto (a pasta que contém `.env` e `total-loss-investigator/`):

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r total-loss-investigator/requirements.txt
```

O Tesseract precisa estar no PATH. No macOS: `brew install tesseract`. A chave fica no `.env` da raiz, na forma `OPENROUTER_API_KEY=...`. Abra o notebook com o kernel desse `.venv` e execute as células de cima para baixo.

`RUN_LIVE_LLM = True` chama o modelo `qwen/qwen3.5-flash-02-23` via OpenRouter e gera cobrança. `False` usa o supervisor simulado, sem API.

Com o Opik local em `http://localhost:5173`, cada execução aparece no projeto `total-loss-investigator`: o grafo, os nós e as chamadas ao modelo.

## Interface passo a passo

O notebook continua autocontido. A interface em React Flow avança um nó por vez:

```bash
source .venv/bin/activate
cd total-loss-investigator/backend && uvicorn app:app --host 127.0.0.1 --port 8000
```

Em outro terminal, na pasta `total-loss-investigator/frontend`: `npm install && npm run dev`. Abra `http://127.0.0.1:5174`. `RUN_LIVE_LLM=false` diante do uvicorn usa o supervisor simulado.

## Como executar no Colab

1. Abra `Total_Loss_Investigator.ipynb` com o Google Colab.
2. Use **Ambiente de execução → Executar tudo**. O notebook gera seus próprios PDFs sintéticos no runtime, instala Tesseract, uma fonte DejaVu e as dependências Python.
3. Com `RUN_LIVE_LLM = False` **não há cobrança por API**. Os especialistas usam dados mockados; o Supervisor usa uma política simulada para permitir reproduzir os traces.
4. Para usar um LLM via OpenRouter, coloque uma chave no **Colab → Secrets → OPENROUTER_API_KEY**, habilite o acesso do notebook à chave e, na célula de extração, altere `RUN_LIVE_LLM = True`. O OpenRouter cobra por uso; verifique os preços vigentes.
5. Rode a célula de testes: `AUTO-101` percorre Damage → Coverage → Valuation → Damage no modo MOCK; `AUTO-202` termina com menos consultas; `AUTO-303` deve pausar para revisão da placa e orçamento.
6. Para a interface, execute a célula Gradio e use **Run investigation**, corrija o JSON com base no documento de suporte e clique em **Resume from interrupt**.

## Arquivos

- `Total_Loss_Investigator.ipynb`: **notebook autocontido**. Dispensa os outros arquivos para rodar.
- `sample_claims/AUTO-101.pdf`: acidente grave; vistoria complementar.
- `sample_claims/AUTO-202.pdf`: dano leve.
- `sample_claims/AUTO-303.pdf`: dois campos do OCR borrados.
- `sample_claims/AUTO-303_supporting_docs.pdf`: documento legível de apoio para revisão humana de AUTO-303.
- `mock_data/insurance_fixtures.json`: dados sintéticos de apólices, danos e avaliações.

## O que é real vs. simulado

**Real no runtime:** geração de PDFs, OCR Tesseract (texto/confiança/bounding boxes), mapeamento de tokens, validações Pydantic, gate determinístico e (após instalar LangGraph no Colab) pausa/retomada do grafo.

**Simulado:** dados dos sinistros, critérios contratuais, APIs da seguradora e o Supervisor em modo MOCK. **LIVE:** o OpenRouter toma as decisões do Supervisor, produz structured outputs e elabora a justificativa do relatório.

As regras fictícias de perda total usadas nestes três documentos **não são referência jurídica**. A avaliação de sinistros reais exige apólices, regulação aplicável, auditoria, privacidade e revisão por profissional responsável. Nenhum pagamento, recusa final nem acusação de fraude é automatizado.

## Limitações técnicas

- Confidence Tesseract é **por palavra**, não medida calibrada da qualidade de extração de um campo inteiro. Threshold de 86% serve apenas à demo.
- Os nós especialistas utilizam ferramentas determinísticas e evidências simuladas, não múltiplos agentes LLM independentes.
- `InMemorySaver` perde checkpoints se o runtime reiniciar.
- Não exponha documentos reais em interfaces Gradio publicadas, nem inclua tokens em arquivos.
- O sandbox roda localmente com `.venv` (uv), Tesseract e a chave do OpenRouter no `.env`. No Colab, a primeira célula instala Tesseract, a fonte e as bibliotecas.

## Fontes técnicas

- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://openrouter.ai/qwen/qwen3.5-flash-02-23
- https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html
