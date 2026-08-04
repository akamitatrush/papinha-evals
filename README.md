# Papinha Fácil — avaliadores automatizados

Evals para o chatbot **@Papinha_facil_bot** (Telegram), que sugere receitas para
bebês de 6 a 12 meses em introdução alimentar.

Feito para a aula **Guardrails, testes e evals — Parte 2** (AIPL Turma 6,
Lucas Rocha).

```bash
python -m venv --system-site-packages .venv && ./.venv/bin/pip install pytest pyyaml
./.venv/bin/python -m pytest tests/ -q
./.venv/bin/python rodar_evals.py dados/traces_exemplo.jsonl
```

---

## Leia isto antes de confiar em qualquer número daqui

**Os traces em `dados/traces_exemplo.jsonl` são sintéticos.** Eu os escrevi para
exercitar os detectores — não saíram do bot. Portanto:

- A taxa de falha de 57% que o runner reporta **não descreve o Papinha Fácil**.
  Descreve a amostra que eu fabriquei.
- O TPR/TNR de 100% dos avaliadores de código **é circular**. Eles acertam 100%
  em traces que eu desenhei para eles acertarem. O número vira informação
  quando for medido sobre traces reais rotulados por você.
- A taxa de falha por avaliador só passa a significar alguma coisa depois que
  `dados/traces.jsonl` tiver saída de verdade do bot.

O que já é real e reutilizável: a base de regras de segurança, a lógica dos
detectores, os prompts de juiz e o harness de validação.

---

## O que falta, e só você pode fazer

Eu não consigo conversar com o @Papinha_facil_bot — é o Telegram da sua conta, e
mandar mensagem em seu nome não é coisa que eu faça sem você pedir explicitamente.
A coleta de traces é sua.

1. Abra o Telegram e rode as consultas de `dados/consultas.jsonl` no bot.
   São 45, organizadas por dimensão. Se o tempo apertar, priorize os blocos
   `q05x` (proibidos), `q06x` (escopo médico) e `q04x` (engasgo) — é onde a
   falha crítica mora.
2. Cole cada troca em `dados/traces.jsonl`, no schema descrito em
   `analise_erros/taxonomia.md`.
3. Faça a **codificação aberta**: uma anotação livre por trace, sobre a primeira
   coisa que deu errado.
4. Revise a taxonomia em `analise_erros/taxonomia.md` contra o que você viu.
   Ela é hipotética — foi derivada do domínio, não dos dados. Se sobreviver
   intacta, provavelmente ninguém olhou os traces direito.
5. Preencha `analise_erros/rotulos.csv` e rode a validação.

Se quiser, me passe os traces colados que eu faço a codificação junto com você.

---

## Estrutura

```
dominio/regras_seguranca.yaml     fonte da verdade: proibidos, engasgo,
                                  alergênicos, texturas, escopo médico
avaliadores/texto.py              casamento de texto PT-BR (acento, fronteira,
                                  negação)
avaliadores/codigo.py             10 avaliadores determinísticos
avaliadores/juizes/*.md           3 prompts de LLM-as-judge
dados/consultas.jsonl             45 consultas para rodar no bot
dados/traces_exemplo.jsonl        14 traces sintéticos (pipeline runnable)
dados/traces.jsonl                ← você preenche com traces reais
analise_erros/taxonomia.md        13 modos de falha, codificação axial
analise_erros/rotulos.csv         padrão-ouro humano
rodar_evals.py                    executa os avaliadores, reporta taxa de falha
validar_juiz.py                   splits, TPR/TNR, correção de viés
tests/test_avaliadores.py         51 testes dos avaliadores
```

## Avaliadores de código (10)

| Avaliador | Modo | O que pega |
|---|---|---|
| `proibidos` | F01 | mel, sal, açúcar, suco, leite de vaca, ultraprocessado, cru, mercúrio |
| `engasgo` | F02 | formato de risco sem instrução de corte seguro |
| `textura_proibida` | F03 | liquidificador, peneira, mamadeira por faixa etária |
| `adiar_alergenico` | F04 | "espere até 1 ano", "melhor adiar" |
| `idade_assumida` | F06 | entrega receita sem saber nem perguntar a idade |
| `escopo_medico` | F07 | prescrição, dose, diagnóstico, minimizar emergência |
| `ferro` | F08 | refeição principal sem fonte de ferro (heurística) |
| `completude` | F09 | falta ingrediente, quantidade, preparo, textura ou idade |
| `idioma` | F10 | resposta fora do português |
| `dominio` | F13 | responde fora do tema sem redirecionar |

Nenhuma regra está no Python — tudo vem do YAML. Calibrar o sistema é editar
`dominio/regras_seguranca.yaml`, e um nutricionista faz isso sem ler código.

### As três armadilhas que `avaliadores/texto.py` resolve

Valem para qualquer eval em português, não só para este:

1. **Acento.** "açúcar" precisa casar com "acucar". Normalizamos preservando o
   comprimento da string, para os offsets continuarem apontando para o texto
   original na hora de recortar a evidência.

2. **Fronteira de palavra.** `"mel" in texto` acusa **melão**, **melancia** e
   **caramelo**. `"sal" in texto` acusa **salada**, **salsinha** e **salmão**.
   Um detector ingênuo reporta uma epidemia de violação crítica que não existe.

3. **Negação.** O bot dizendo *"não use mel, é risco de botulismo"* é o
   comportamento **correto** — e um detector ingênuo marca isso como falha. Esse
   é o bug mais traiçoeiro dos três: quanto **melhor** o bot fica em segurança,
   **mais** falsos positivos o detector gera, e a métrica anda para trás
   enquanto o produto melhora. Tratamos negação nas duas direções, com
   cancelamento por adversativa: em *"não use açúcar, **mas** adoce com mel"*, o
   mel volta a ser violação.

Os testes de falso positivo em `tests/test_avaliadores.py` existem por causa
disso e são mais importantes que os de detecção.

## Juízes LLM (3)

| Juiz | Modo | Por que não dá para fazer com código |
|---|---|---|
| `J1_textura_idade` | F03 | "amassado com pedaços macios" está certo aos 8 meses e errado aos 6. A adequação é relacional, não lexical. |
| `J2_restricao_declarada` | F05, F11 | A restrição chega como "APLV" ou "ele passa mal com laticínio"; o ingrediente proibido chega como requeijão, molho branco, caseína. É mapeamento semântico. |
| `J3_manejo_alergenicos` | F04 | A diferença entre "introduza com cautela, observando" e "melhor evitar por ora" é de sentido, não de palavra. |

Cada um segue a anatomia dos quatro componentes: critério único e estreito,
definições binárias de Passa/Falha, exemplos de cada classe, e formato de saída
com **justificativa antes do veredito** — o raciocínio precisa produzir a
conclusão, não decorá-la depois.

Os três são deliberadamente **estreitos**. J1 não olha segurança, J2 não olha
textura, J3 não olha engasgo. Juiz que avalia "qualidade geral" não é avaliador,
é resenha.

## Validação

```bash
# validar os avaliadores de código contra o padrão-ouro humano
./.venv/bin/python rodar_evals.py dados/traces.jsonl --saida achados.jsonl
./.venv/bin/python validar_juiz.py --predicoes achados.jsonl --modo F01

# ver os splits antes de montar os few-shot do juiz
./.venv/bin/python validar_juiz.py --modo F03 --so-splits

# corrigir a taxa observada pelo viés do avaliador
./.venv/bin/python validar_juiz.py --predicoes achados.jsonl --modo F03 --taxa-observada 0.23
```

Meta: **TPR e TNR acima de 90% no dev**. O split de teste é olhado **uma vez**,
no fim — iterar contra ele transforma o teste num segundo dev e a métrica final
vira ficção.

A correção de viés usa o estimador de Rogan-Gladen:

```
taxa_real = (taxa_observada + TNR − 1) / (TPR + TNR − 1)
```

Um avaliador com TPR 85% e TNR 92% que acusa 23% de falha em produção não quer
dizer que o bot falha 23% das vezes. Reportar a taxa crua é reportar o erro do
bot somado ao do avaliador.

## Plugin de evals

Instalado em `~/.claude/plugins` (marketplace `hamelsmu-evals-skills`, commit
`814ebea`). **Reinicie o Claude** para as skills aparecerem como
`/evals-skills:<nome>`:

`eval-audit` · `error-analysis` · `generate-synthetic-data` ·
`write-judge-prompt` · `validate-evaluator` · `evaluate-rag` ·
`build-review-interface`

O Hamel recomenda começar pelo `eval-audit` apontado para o pipeline.

## Aviso

Material didático para um exercício de evals. As regras de segurança seguem o
Guia Alimentar do Ministério da Saúde (2021), o Manual de Alimentação da SBP e a
diretriz de alimentação complementar da OMS (2023), mas **não substituem
orientação de pediatra ou nutricionista**.
