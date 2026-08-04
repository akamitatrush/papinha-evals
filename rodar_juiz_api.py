#!/usr/bin/env python3
"""
Roda um juiz LLM sobre um arquivo de traces, pela API.

    export ANTHROPIC_API_KEY=sk-ant-...
    python rodar_juiz_api.py avaliadores/juizes/J5_verificacao_idade.md \
        dados/traces_turma.jsonl --saida analise_erros/juiz_J5_turma.jsonl

    python validar_juiz.py --modo F06 \
        --rotulos analise_erros/rotulos_turma.csv \
        --predicoes analise_erros/juiz_J5_turma.jsonl

Diferença para `julgar.py`: aquele usa o CLI do Claude e consome a assinatura;
este usa a API e consome a chave. Existe porque o experimento código-versus-juiz
precisa dos dois avaliadores rodando sobre os MESMOS traces, e a rota da API é
a que dá controle de modelo e de custo.

Retomável: traces já julgados na --saida são pulados. Se a execução morrer no
meio, rode de novo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

VERDE, CINZA, AMARELO, NEGRITO, FIM = "\033[32m", "\033[90m", "\033[33m", "\033[1m", "\033[0m"


def main() -> int:
    p = argparse.ArgumentParser(description="Roda um juiz LLM pela API")
    p.add_argument("juiz", type=Path)
    p.add_argument("traces", type=Path)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--modelo", default="claude-haiku-4-5")
    p.add_argument("--esforco", default="medium",
                   choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--concorrencia", type=int, default=6)
    p.add_argument("--amostra", type=int, help="só os N primeiros — teste de fumaça")
    args = p.parse_args()

    for c in (args.juiz, args.traces):
        if not c.exists():
            raise SystemExit(f"{c} não existe.")

    traces = [json.loads(l) for l in args.traces.read_text(encoding="utf-8").splitlines()
              if l.strip()]
    traces = [t for t in traces if (t.get("output") or "").strip()]
    if args.amostra:
        traces = traces[:args.amostra]

    # Retomada: pula o que já foi julgado.
    feitos = set()
    if args.saida.exists():
        for l in args.saida.read_text(encoding="utf-8").splitlines():
            if l.strip():
                feitos.add(json.loads(l)["trace_id"])
    pendentes = [t for t in traces if t["id"] not in feitos]

    if not pendentes:
        print(f"{VERDE}nada a fazer — {len(feitos)} traces já julgados{FIM}")
        return 0

    # Estimativa antes de gastar. O prompt do juiz é longo e o trace também.
    precos = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (3.0, 15.0),
              "claude-haiku-4-5": (1.0, 5.0)}
    p_ent, p_sai = precos.get(args.modelo, (5.0, 25.0))
    est = (len(pendentes) * 5000 / 1e6) * p_ent + (len(pendentes) * 500 / 1e6) * p_sai
    print(f"{AMARELO}{len(pendentes)} traces · ~US$ {est:.2f} ({args.modelo}){FIM}")
    if est > 1.0 and sys.stdin.isatty():
        if input("  continuar? [s/N] ").strip().lower() not in ("s", "sim", "y"):
            print("cancelado — nada foi gasto.")
            return 0

    from llm.cliente import ClienteLLM
    from llm import tarefas

    llm = ClienteLLM(modelo=args.modelo, esforco=args.esforco,
                     concorrencia=args.concorrencia)
    print(f"{CINZA}{args.juiz.stem} · {args.modelo} · {args.concorrencia} concorrentes{FIM}")

    vereditos = tarefas.julgar(llm, args.juiz, pendentes)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    with open(args.saida, "a", encoding="utf-8") as f:
        for v in vereditos:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")

    falhas = sum(1 for v in vereditos if v["veredito"] == "falha")
    u = llm.uso
    print(f"\n{len(vereditos)} julgados · {falhas} falha · {len(vereditos) - falhas} passa")
    print(f"{CINZA}{u.chamadas} chamadas · {u.entrada:,} tokens de entrada · "
          f"{u.saida:,} de saída · ~US$ {u.custo_estimado(args.modelo):.2f}"
          + (f" · {u.erros} erro(s)" if u.erros else "") + f"{FIM}")
    print(f"{VERDE}{args.saida}{FIM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
