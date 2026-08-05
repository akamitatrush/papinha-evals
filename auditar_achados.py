#!/usr/bin/env python3
"""
Roda só a auditoria de falsos positivos sobre um conjunto de traces.

    export ANTHROPIC_API_KEY=sk-ant-...
    python auditar_achados.py --traces dados/traces_turma.jsonl \
        --saida analise_erros/auditoria_turma.jsonl

Existe porque `auto.py` só audita dentro do pipeline completo, que roda os
juízes antes e custa muito mais. A auditoria sozinha é o passo que transforma
contagem bruta em taxa de falha — foi ele que fez 100% virar 18% neste projeto.

E há um motivo melhor: quando existe rótulo humano para algum dos modos, dá
para medir o AUDITOR contra ele. O auditor é um juiz não medido decidindo o que
procede; enquanto ninguém o mede, a precisão que o relatório publica é opinião
de LLM sobre trabalho de LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from avaliadores import codigo as C  # noqa: E402

VERDE, CINZA, AMARELO, VERMELHO, NEGRITO, FIM = (
    "\033[32m", "\033[90m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"
)


def main() -> int:
    p = argparse.ArgumentParser(description="Audita achados de código")
    p.add_argument("--traces", type=Path, default=RAIZ / "dados" / "traces.jsonl")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--modelo", default="claude-haiku-4-5")
    p.add_argument("--avaliador", help="audita só os achados deste avaliador")
    p.add_argument("--concorrencia", type=int, default=8)
    args = p.parse_args()

    traces = [json.loads(l) for l in args.traces.read_text(encoding="utf-8").splitlines()
              if l.strip()]
    por_id = {t["id"]: t for t in traces}
    regras = C.carregar_regras()

    brutos = [a.dict() for t in traces for a in C.avaliar(t, regras)
              if a.veredito == "falha"]
    if args.avaliador:
        brutos = [a for a in brutos if a["avaliador"] == args.avaliador]
    if not brutos:
        raise SystemExit("nenhum achado para auditar.")

    est = (len(brutos) * 5000 / 1e6) * 1.0 + (len(brutos) * 500 / 1e6) * 5.0
    print(f"{AMARELO}{len(brutos)} achados · ~US$ {est:.2f} ({args.modelo}){FIM}")

    from llm.cliente import ClienteLLM
    from llm import tarefas

    llm = ClienteLLM(modelo=args.modelo, concorrencia=args.concorrencia)
    auditados = tarefas.auditar(llm, brutos, por_id)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    with open(args.saida, "w", encoding="utf-8") as f:
        for a in auditados:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")

    procede = [a for a in auditados if a["auditoria"]["veredito"] == "procede"]
    fp = [a for a in auditados if a["auditoria"]["veredito"] == "falso_positivo"]
    incerto = [a for a in auditados if a["auditoria"]["veredito"] == "incerto"]
    precisao = len(procede) / len(auditados) if auditados else 0

    print(f"\n{VERDE}{len(procede)} procedem{FIM} · {VERMELHO}{len(fp)} falsos "
          f"positivos{FIM} · {AMARELO}{len(incerto)} incertos{FIM}")
    print(f"precisão dos avaliadores: {NEGRITO}{precisao:.0%}{FIM}")

    u = llm.uso
    print(f"{CINZA}{u.chamadas} chamadas · ~US$ {u.custo_estimado(args.modelo):.2f}"
          + (f" · {u.erros} erro(s)" if u.erros else "") + f"{FIM}")
    print(f"{VERDE}{args.saida}{FIM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
