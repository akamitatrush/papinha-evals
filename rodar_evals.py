#!/usr/bin/env python3
"""
Roda os avaliadores de código sobre um arquivo de traces.

    python rodar_evals.py dados/traces_exemplo.jsonl
    python rodar_evals.py dados/traces.jsonl --saida resultados.jsonl
    python rodar_evals.py dados/traces.jsonl --so-falhas

A taxa de falha por avaliador é o número que orienta a priorização: conserte
primeiro o que é crítico E prevalente. Falha crítica com prevalência de 1%
importa menos que falha crítica com prevalência de 30%.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from avaliadores import codigo as C

VERMELHO, AMARELO, VERDE, CINZA, NEGRITO, FIM = (
    "\033[31m", "\033[33m", "\033[32m", "\033[90m", "\033[1m", "\033[0m"
)

COR = {"falha": VERMELHO, "revisar": AMARELO, "passa": VERDE}
SIMBOLO = {"falha": "✗", "revisar": "?", "passa": "✓"}

ORDEM_GRAVIDADE = {"critica": 0, "alta": 1, "media": 2, "baixa": 3, "n/a": 4}


def carregar_traces(caminho: Path) -> list[dict]:
    traces = []
    with open(caminho, encoding="utf-8") as f:
        for n, linha in enumerate(f, 1):
            linha = linha.strip()
            if not linha or linha.startswith("//"):
                continue
            try:
                traces.append(json.loads(linha))
            except json.JSONDecodeError as e:
                print(f"{VERMELHO}linha {n} inválida: {e}{FIM}", file=sys.stderr)
    return traces


def main() -> int:
    p = argparse.ArgumentParser(description="Avaliadores de código do Papinha Fácil")
    p.add_argument("traces", type=Path, help="arquivo .jsonl de traces")
    p.add_argument("--saida", type=Path, help="grava os achados em .jsonl")
    p.add_argument("--so-falhas", action="store_true", help="omite traces sem achado")
    p.add_argument("--sem-cor", action="store_true")
    args = p.parse_args()

    if args.sem_cor:
        for k in COR:
            COR[k] = ""
        globals().update(VERMELHO="", AMARELO="", VERDE="", CINZA="", NEGRITO="", FIM="")

    if not args.traces.exists():
        print(f"arquivo não encontrado: {args.traces}", file=sys.stderr)
        return 2

    regras = C.carregar_regras()
    traces = carregar_traces(args.traces)
    if not traces:
        print("nenhum trace lido.", file=sys.stderr)
        return 2

    origens = Counter(t.get("origem", "desconhecida") for t in traces)
    todos, por_avaliador = [], {nome: Counter() for nome in C.AVALIADORES}

    print(f"\n{NEGRITO}Avaliadores de código — Papinha Fácil{FIM}")
    print(f"{CINZA}{len(traces)} traces · origem: "
          f"{', '.join(f'{k}={v}' for k, v in origens.items())}{FIM}\n")

    for trace in traces:
        achados = C.avaliar(trace, regras)
        todos.extend(achados)
        for a in achados:
            por_avaliador[a.avaliador][a.veredito] += 1

        interessantes = [a for a in achados if a.veredito != "passa"]
        if args.so_falhas and not interessantes:
            continue

        idade = trace.get("idade_meses")
        rotulo_idade = f"{idade}m" if idade is not None else "idade n/i"
        cabecalho = f"{NEGRITO}{trace['id']}{FIM} {CINZA}({rotulo_idade}){FIM}"
        entrada = (trace.get("input", "") or "").replace("\n", " ")[:78]

        if not interessantes:
            print(f"{VERDE}✓{FIM} {cabecalho}  {CINZA}{entrada}{FIM}")
            continue

        pior = min(interessantes, key=lambda a: ORDEM_GRAVIDADE.get(a.gravidade, 4))
        print(f"{COR[pior.veredito]}{SIMBOLO[pior.veredito]}{FIM} {cabecalho}  "
              f"{CINZA}{entrada}{FIM}")
        for a in sorted(interessantes, key=lambda x: ORDEM_GRAVIDADE.get(x.gravidade, 4)):
            c = COR[a.veredito]
            print(f"    {c}{SIMBOLO[a.veredito]} {a.avaliador}{FIM} "
                  f"{CINZA}[{a.gravidade}]{FIM} {a.justificativa}")
            for ev in a.evidencias[:2]:
                print(f"      {CINZA}{ev[:150]}{FIM}")
        print()

    # --- resumo ---
    print(f"\n{NEGRITO}Taxa de falha por avaliador{FIM}")
    print(f"{CINZA}{'avaliador':<20} {'modo':<5} {'falha':>7} {'revisar':>8} {'taxa':>7}{FIM}")
    linhas = []
    for nome, contagem in por_avaliador.items():
        falhas = contagem["falha"]
        taxa = falhas / len(traces)
        linhas.append((taxa, nome, falhas, contagem["revisar"]))
    for taxa, nome, falhas, revisar in sorted(linhas, reverse=True):
        cor = VERMELHO if taxa >= 0.2 else (AMARELO if taxa > 0 else VERDE)
        modo = C.MODO_DE_FALHA.get(nome, "—")
        print(f"{nome:<20} {CINZA}{modo:<5}{FIM} {cor}{falhas:>7}{FIM} {revisar:>8} "
              f"{cor}{taxa:>6.0%}{FIM}")

    com_falha = len({a.trace_id for a in todos if a.veredito == "falha"})
    criticas = len({a.trace_id for a in todos
                    if a.veredito == "falha" and a.gravidade == "critica"})
    print(f"\n{NEGRITO}{com_falha}/{len(traces)}{FIM} traces com ao menos uma falha "
          f"({com_falha / len(traces):.0%}) · "
          f"{VERMELHO}{criticas}{FIM} com falha crítica de segurança")

    if any(t.get("origem") == "sintetico" for t in traces):
        print(f"\n{AMARELO}Atenção:{FIM} há traces sintéticos nesta amostra. "
              f"{CINZA}Taxa de falha só descreve o bot quando calculada sobre traces reais.{FIM}")

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as f:
            for a in todos:
                f.write(json.dumps(a.dict(), ensure_ascii=False) + "\n")
        print(f"{CINZA}achados gravados em {args.saida}{FIM}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
