#!/usr/bin/env python3
"""
Pipeline de evals do Papinha Fácil, ponta a ponta e sem humano no meio.

    export ANTHROPIC_API_KEY=sk-ant-...
    ./.venv/bin/python auto.py                     # usa dados/traces.jsonl
    ./.venv/bin/python auto.py --coletar           # coleta do bot antes (Telethon)
    ./.venv/bin/python auto.py --so-codigo         # sem chamadas de API

O que ele faz, na ordem:

    1. coleta      traces do @Papinha_facil_bot          (opcional, Telethon)
    2. avalia      10 avaliadores determinísticos        (grátis, milissegundos)
    3. julga       4 juízes LLM sobre os traces          (API)
    4. audita      triagem de falso positivo dos achados (API)  <- o passo caro
    5. codifica    codificação aberta, um rótulo/trace   (API)
    6. agrupa      codificação axial -> taxonomia        (API)
    7. relata      relatório em markdown

O passo 4 é a razão de existir deste programa. Sem ele o pipeline reporta uma
taxa de falha que descreve os bugs dos detectores, não o comportamento do bot —
foi o que aconteceu nas quatro rodadas manuais deste projeto (100% → 64% → 48%
→ 18%, todas corrigindo o eval, nenhuma corrigindo o bot).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from avaliadores import codigo as C  # noqa: E402

NEGRITO, CINZA, VERDE, VERMELHO, AMARELO, FIM = (
    "\033[1m", "\033[90m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"
)


def etapa(n: int, total: int, titulo: str) -> None:
    print(f"\n{NEGRITO}[{n}/{total}] {titulo}{FIM}")


def ler_traces(caminho: Path) -> list[dict]:
    if not caminho.exists():
        raise SystemExit(f"{caminho} não existe. Rode com --coletar ou colete os traces antes.")
    traces = []
    for n, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
        linha = linha.strip()
        if not linha or linha.startswith("//"):
            continue
        try:
            traces.append(json.loads(linha))
        except json.JSONDecodeError as e:
            print(f"{AMARELO}linha {n} inválida, pulada: {e}{FIM}", file=sys.stderr)
    if not traces:
        raise SystemExit(f"{caminho} não tem trace algum.")
    return traces


def coletar(bot: str, limite: int | None) -> None:
    cmd = [sys.executable, str(RAIZ / "coleta" / "enviar_consultas.py"), "--bot", bot]
    if limite:
        cmd += ["--limite", str(limite)]
    print(f"{CINZA}$ {' '.join(cmd)}{FIM}")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("coleta falhou — veja o erro acima")


def main() -> int:
    p = argparse.ArgumentParser(description="Pipeline de evals automatizado")
    p.add_argument("--traces", type=Path, default=RAIZ / "dados" / "traces.jsonl")
    p.add_argument("--saida", type=Path, default=RAIZ / "relatorio.md")
    p.add_argument("--coletar", action="store_true", help="coleta do bot antes de avaliar")
    p.add_argument("--bot", default="@Papinha_facil_bot")
    p.add_argument("--limite-coleta", type=int)
    p.add_argument("--so-codigo", action="store_true",
                   help="só avaliadores determinísticos, sem chamadas de API")
    p.add_argument("--amostra", type=int,
                   help="usa só os N primeiros traces — teste de fumaça barato")
    p.add_argument("--modelo", default="claude-opus-5",
                   help="modelo dos juízes e da auditoria (padrão: claude-opus-5; "
                        "use claude-haiku-4-5 para testar barato)")
    p.add_argument("--esforco", default="medium",
                   choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--concorrencia", type=int, default=4)
    args = p.parse_args()

    total = 3 if args.so_codigo else 7
    n = 0
    inicio = datetime.now(timezone.utc)

    # --- 1. coleta ---
    if args.coletar:
        n += 1
        etapa(n, total, "Coleta de traces no Telegram")
        coletar(args.bot, args.limite_coleta)

    traces = ler_traces(args.traces)
    if args.amostra:
        traces = traces[:args.amostra]
        print(f"{AMARELO}amostra de {len(traces)} traces — resultado NÃO é "
              f"representativo, serve para provar o pipeline{FIM}")
    por_id = {t["id"]: t for t in traces}
    origens = {}
    for t in traces:
        origens[t.get("origem", "?")] = origens.get(t.get("origem", "?"), 0) + 1
    print(f"{CINZA}{len(traces)} traces · "
          f"{', '.join(f'{k}={v}' for k, v in origens.items())}{FIM}")

    # --- 2. avaliadores de código ---
    n += 1
    etapa(n, total, "Avaliadores determinísticos")
    regras = C.carregar_regras()
    achados = []
    for t in traces:
        achados.extend(a.dict() for a in C.avaliar(t, regras))
    brutos = [a for a in achados if a["veredito"] == "falha"]
    revisar = [a for a in achados if a["veredito"] == "revisar"]
    print(f"  {len(brutos)} achados de falha · {len(revisar)} em revisão")

    if args.so_codigo:
        n += 1
        etapa(n, total, "Relatório")
        from relatorio import gerar
        gerar(args.saida, traces, brutos, revisar, [], [], None, None, inicio, args.modelo)
        print(f"{VERDE}relatório em {args.saida}{FIM}")
        return 0

    from llm.cliente import ClienteLLM
    from llm import tarefas

    # Estimativa ANTES de gastar. Uma rodada completa em Opus custa alguns
    # dólares; disparar isso sem avisar é o tipo de surpresa que faz alguém
    # desligar a automação de vez.
    n_juizes = len(list((RAIZ / "avaliadores" / "juizes").glob("J*.md")))
    n_uteis = sum(1 for t in traces if (t.get("output") or "").strip())
    chamadas = n_juizes * n_uteis + len(brutos) + n_uteis + 1
    # ~4k tokens de entrada e ~400 de saída por chamada, medido nos traces reais
    precos = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (3.0, 15.0),
              "claude-haiku-4-5": (1.0, 5.0)}
    p_ent, p_sai = precos.get(args.modelo, (5.0, 25.0))
    est = (chamadas * 4000 / 1e6) * p_ent + (chamadas * 400 / 1e6) * p_sai
    print(f"{AMARELO}~{chamadas} chamadas de API · estimativa ~US$ {est:.2f} "
          f"({args.modelo}){FIM}")
    if est > 1.0 and sys.stdin.isatty():
        if input(f"  continuar? [s/N] ").strip().lower() not in ("s", "sim", "y"):
            print("cancelado — nada foi gasto.")
            return 0

    llm = ClienteLLM(modelo=args.modelo, esforco=args.esforco,
                     concorrencia=args.concorrencia)
    print(f"{CINZA}modelo {args.modelo} · esforço {args.esforco} · "
          f"{args.concorrencia} chamadas concorrentes{FIM}")

    # --- 3. juízes ---
    n += 1
    etapa(n, total, "Juízes LLM")
    avaliaveis = [t for t in traces if (t.get("output") or "").strip()]
    if len(avaliaveis) < len(traces):
        print(f"{CINZA}  {len(traces) - len(avaliaveis)} trace(s) sem resposta, "
              f"fora da avaliação{FIM}")
    vereditos = []
    for juiz in sorted((RAIZ / "avaliadores" / "juizes").glob("J*.md")):
        vereditos.extend(tarefas.julgar(llm, juiz, avaliaveis))
    falhas_juiz = [v for v in vereditos if v["veredito"] == "falha"]
    print(f"  {len(falhas_juiz)} falhas apontadas pelos juízes")

    # --- 4. auditoria de falsos positivos ---
    n += 1
    etapa(n, total, "Auditoria de falsos positivos")
    a_auditar = brutos + [{**v, "avaliador": v["juiz"], "regras": [],
                           "gravidade": "n/a"} for v in falhas_juiz]
    auditados = tarefas.auditar(llm, a_auditar, por_id)
    procede = [a for a in auditados if a["auditoria"]["veredito"] == "procede"]
    fp = [a for a in auditados if a["auditoria"]["veredito"] == "falso_positivo"]
    incerto = [a for a in auditados if a["auditoria"]["veredito"] == "incerto"]
    precisao = len(procede) / len(auditados) if auditados else 0
    cor = VERDE if precisao >= 0.8 else (AMARELO if precisao >= 0.5 else VERMELHO)
    print(f"  {VERDE}{len(procede)} procedem{FIM} · {VERMELHO}{len(fp)} falsos "
          f"positivos{FIM} · {AMARELO}{len(incerto)} incertos{FIM}")
    print(f"  precisão dos avaliadores: {cor}{precisao:.0%}{FIM}")

    # --- 5. codificação aberta ---
    n += 1
    etapa(n, total, "Codificação aberta")
    anotacoes = tarefas.codificar(llm, avaliaveis)
    n_falha = sum(1 for a in anotacoes if a["resultado"] == "falha")
    print(f"  {n_falha}/{len(anotacoes)} traces com falha ({n_falha/max(1,len(anotacoes)):.0%})")

    # --- 6. codificação axial ---
    n += 1
    etapa(n, total, "Codificação axial")
    taxonomia = tarefas.agrupar(llm, anotacoes)
    if taxonomia:
        print(f"  {len(taxonomia.categorias)} modos de falha observados · "
              f"{len(taxonomia.modos_nao_observados)} da hipótese sem ocorrência")

    # --- 7. relatório ---
    n += 1
    etapa(n, total, "Relatório")
    from relatorio import gerar
    gerar(args.saida, traces, brutos, revisar, auditados, anotacoes, taxonomia,
          llm.uso, inicio, args.modelo)

    u = llm.uso
    print(f"\n{CINZA}{u.chamadas} chamadas · {u.entrada:,} tokens de entrada · "
          f"{u.saida:,} de saída · ~US$ {u.custo_estimado(args.modelo):.2f}"
          + (f" · {u.erros} erro(s)" if u.erros else "") + f"{FIM}")
    print(f"{VERDE}relatório em {args.saida}{FIM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
