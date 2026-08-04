"""Gera o relatório final do pipeline automatizado."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _cabecalho(traces, inicio, modelo, uso) -> list[str]:
    fim = datetime.now(timezone.utc)
    origens = Counter(t.get("origem", "?") for t in traces)
    sinteticos = origens.get("sintetico", 0)

    linhas = [
        "# Relatório de evals — Papinha Fácil",
        "",
        f"Gerado em {fim:%Y-%m-%d %H:%M} UTC · "
        f"{(fim - inicio).total_seconds():.0f}s de execução",
        "",
        f"- **Traces:** {len(traces)} "
        f"({', '.join(f'{k}={v}' for k, v in sorted(origens.items()))})",
    ]
    if uso:
        linhas += [
            f"- **Modelo:** `{modelo}`",
            f"- **Custo:** {uso.chamadas} chamadas, {uso.entrada:,} tokens de entrada, "
            f"{uso.saida:,} de saída · ~US$ {uso.custo_estimado(modelo):.2f}",
        ]
    if uso and uso.erros:
        linhas.append(f"- ⚠️ **{uso.erros} chamada(s) falharam** — os itens "
                      f"correspondentes ficaram de fora")
    if sinteticos:
        linhas += ["", f"> [!WARNING]",
                   f"> {sinteticos} trace(s) desta amostra são **sintéticos**. "
                   f"Taxa de falha só descreve o bot quando calculada sobre traces reais."]
    return linhas


def _secao_auditoria(auditados) -> list[str]:
    if not auditados:
        return []
    procede = [a for a in auditados if a["auditoria"]["veredito"] == "procede"]
    fp = [a for a in auditados if a["auditoria"]["veredito"] == "falso_positivo"]
    incerto = [a for a in auditados if a["auditoria"]["veredito"] == "incerto"]
    precisao = len(procede) / len(auditados)

    linhas = [
        "", "---", "", "## 🔍 Auditoria dos achados",
        "",
        "Cada achado dos avaliadores foi reexaminado ao lado do trace que o "
        "originou, com uma única pergunta: **o bot recomendou a prática, ou "
        "apenas a mencionou para desaconselhá-la?**",
        "",
        f"| Veredito | Achados |", "|:---|---:|",
        f"| ✅ Procede | {len(procede)} |",
        f"| ❌ Falso positivo | {len(fp)} |",
        f"| ⚠️ Incerto (revisão humana) | {len(incerto)} |",
        f"| **Precisão dos avaliadores** | **{precisao:.0%}** |",
        "",
    ]

    if precisao < 0.8:
        linhas += [
            "> [!CAUTION]",
            f"> Precisão de {precisao:.0%} significa que a taxa de falha bruta "
            "**descreve os detectores, não o bot**. Corrija os falsos positivos "
            "abaixo antes de reportar qualquer número.", "",
        ]

    if procede:
        linhas += ["### Falhas confirmadas", ""]
        for a in sorted(procede, key=lambda x: x["trace_id"]):
            linhas.append(f"**{a['trace_id']} · {a['avaliador']}** — "
                          f"{a['auditoria']['explicacao']}")
            linhas.append("")

    if fp:
        linhas += ["<details>", "<summary><b>Falsos positivos "
                   f"({len(fp)}) — por que cada um não procede</b></summary>", ""]
        for a in sorted(fp, key=lambda x: x["trace_id"]):
            linhas.append(f"- **{a['trace_id']} · {a['avaliador']}** — "
                          f"{a['auditoria']['o_que_a_resposta_faz']}")
        linhas += ["", "</details>", ""]

    if incerto:
        linhas += ["### ⚠️ Fila de revisão humana", ""]
        for a in sorted(incerto, key=lambda x: x["trace_id"]):
            linhas.append(f"- **{a['trace_id']} · {a['avaliador']}** — "
                          f"{a['auditoria']['explicacao']}")
        linhas.append("")

    return linhas


def _secao_taxonomia(taxonomia, anotacoes) -> list[str]:
    if not taxonomia:
        return []
    linhas = [
        "", "---", "", "## 🗂️ Taxonomia observada",
        "",
        "Derivada dos dados por codificação aberta e axial — não da hipótese "
        "inicial.", "", taxonomia.resumo, "",
        "| Modo de falha | Gravidade | Traces | Avaliador |",
        "|:---|:---:|:---:|:---:|",
    ]
    icone = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "⚪"}
    tipo = {"codigo": "⚙️ código", "juiz": "⚖️ juiz", "humano": "👤 humano"}
    for c in sorted(taxonomia.categorias,
                    key=lambda x: (["critica", "alta", "media", "baixa"].index(x.gravidade),
                                   -len(x.traces))):
        linhas.append(f"| **{c.rotulo}** | {icone.get(c.gravidade, '')} "
                      f"{c.gravidade} | {len(c.traces)} | {tipo.get(c.avaliador_sugerido, '')} |")

    linhas += ["", "### Definições operacionais", ""]
    for c in taxonomia.categorias:
        linhas += [f"**{c.rotulo}** ({c.gravidade})", "",
                   f"{c.definicao}", "",
                   f"*Traces:* {', '.join(c.traces) or '—'}  ",
                   f"*Avaliador sugerido:* {tipo.get(c.avaliador_sugerido, '')} — {c.por_que}",
                   ""]

    if taxonomia.modos_nao_observados:
        linhas += [
            "### Modos da hipótese sem ocorrência", "",
            "Ausência é informação: estes avaliadores **não têm dados para ser "
            "validados** ainda — não que o bot esteja imune a eles.", "",
        ]
        for m in taxonomia.modos_nao_observados:
            linhas.append(f"- {m}")
        linhas.append("")
    return linhas


def _secao_codificacao(anotacoes) -> list[str]:
    if not anotacoes:
        return []
    falhas = [a for a in anotacoes if a["resultado"] == "falha"]
    linhas = [
        "", "---", "", "## ✍️ Codificação aberta", "",
        f"{len(falhas)} de {len(anotacoes)} traces com falha "
        f"({len(falhas)/len(anotacoes):.0%}).", "",
        "<details>", "<summary><b>Anotação trace a trace</b></summary>", "",
        "| Trace | Consulta | Resultado | Primeira falha |",
        "|:---|:---|:---:|:---|",
    ]
    for a in sorted(anotacoes, key=lambda x: x["trace_id"]):
        marca = "❌" if a["resultado"] == "falha" else "✅"
        linhas.append(f"| {a['trace_id']} | {a.get('query_id') or '—'} | {marca} | "
                      f"{a['primeira_falha'] or a['observacao']} |")
    linhas += ["", "</details>", ""]
    return linhas


def _secao_codigo(brutos, revisar) -> list[str]:
    if not brutos and not revisar:
        return []
    por_avaliador = Counter(a["avaliador"] for a in brutos)
    linhas = ["", "---", "", "## ⚙️ Avaliadores determinísticos", "",
              "Contagem **bruta**, antes da auditoria — ver a seção de auditoria "
              "para quais destes procedem.", "",
              "| Avaliador | Modo | Achados |", "|:---|:---:|---:|"]
    for nome, qtd in por_avaliador.most_common():
        from avaliadores.codigo import MODO_DE_FALHA
        linhas.append(f"| `{nome}` | {MODO_DE_FALHA.get(nome, '—')} | {qtd} |")
    if revisar:
        linhas += ["", f"Além disso, **{len(revisar)}** achado(s) em fila de "
                   "revisão (heurística disparou, exige olho humano).", ""]
    return linhas


def _rodape() -> list[str]:
    return [
        "", "---", "",
        "## Como ler este relatório", "",
        "A **precisão dos avaliadores** é o número a olhar primeiro. Se ela for "
        "baixa, a taxa de falha bruta não descreve o bot — descreve os bugs dos "
        "detectores. Neste projeto, quatro rodadas manuais reportaram 100%, 64%, "
        "48% e 18% de falha; as três primeiras estavam erradas, e toda correção "
        "foi no eval, nenhuma no bot.", "",
        "A auditoria automatizada é ela própria um juiz — e **um juiz não "
        "validado não é avaliador, é um segundo LLM opinando**. Rotule uma "
        "amostra dos achados à mão e rode `validar_juiz.py` para medir o TPR/TNR "
        "da auditoria antes de confiar nela.", "",
        "<sub>Gerado por `auto.py` · Papinha Fácil Evals</sub>", "",
    ]


def gerar(caminho: Path, traces, brutos, revisar, auditados, anotacoes,
          taxonomia, uso, inicio, modelo) -> None:
    linhas = _cabecalho(traces, inicio, modelo, uso)
    linhas += _secao_auditoria(auditados)
    linhas += _secao_taxonomia(taxonomia, anotacoes)
    linhas += _secao_codificacao(anotacoes)
    linhas += _secao_codigo(brutos, revisar)
    linhas += _rodape()
    caminho.write_text("\n".join(linhas), encoding="utf-8")
