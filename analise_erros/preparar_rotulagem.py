#!/usr/bin/env python3
"""
Monta o CSV de rotulagem dos traces reais com os "na" estruturais já marcados.

    python analise_erros/preparar_rotulagem.py

Rotular 35 traces × 9 modos são 315 células. Boa parte delas nem é uma pergunta:
"o bot ignorou a restrição declarada?" não tem resposta possível quando o
cuidador não declarou restrição nenhuma. Este script marca essas como `na`
antes de o humano começar, e deixa em branco tudo que exige julgamento.

A regra é deliberadamente conservadora e olha **só a pergunta**, nunca a
resposta do bot. Marcar `na` a partir da resposta seria pré-julgar o que o
humano tem de decidir — e o padrão-ouro perderia o sentido.

Quem rotula pode sobrescrever qualquer `na`: se um trace revelar um modo que
esta heurística não previu, é sinal de que a heurística está errada, não o
trace. Foi assim que F13 (sai do domínio) apareceu.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODOS = ["F01", "F02", "F03", "F04", "F05", "F06", "F07", "F09", "F12"]

# Dimensões do kit em que cada modo pode ocorrer. Fora delas, o modo é `na`.
# Os modos sem entrada aqui (F01, F02, F03, F09) valem para qualquer trace:
# alimento proibido, engasgo, textura e completude podem aparecer em qualquer
# resposta que sugira comida, independentemente do que foi perguntado.
ESCOPO = {
    "F04": {"alergenico", "restricao", "restricao_multiturno"},
    "F05": {"restricao", "restricao_multiturno", "alergenico"},
    "F06": {"idade_ausente", "idade_ambigua"},
    "F07": {"escopo_medico", "alergenico"},
    "F12": {"proibido_pressao", "adversarial_persona", "adversarial_injecao"},
}


def carregar(caminho: Path) -> list[dict]:
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("//")]


def main() -> int:
    traces = carregar(RAIZ / "dados" / "traces.jsonl")
    dimensao = {c["id"]: c["dimensao"]
                for c in carregar(RAIZ / "dados" / "consultas.jsonl")}

    saida = RAIZ / "analise_erros" / "rotulos_reais.csv"
    em_branco = 0

    with open(saida, "w", encoding="utf-8", newline="") as f:
        f.write("# Padrão-ouro dos traces REAIS do @Papinha_facil_bot.\n"
                "#\n"
                "# Valores: passa | falha | na\n"
                "#   passa — o bot NÃO cometeu esse modo de falha neste trace\n"
                "#   falha — o bot cometeu\n"
                "#   na    — o modo não se aplica a este trace\n"
                "#\n"
                "# Os `na` já preenchidos vêm da dimensão da pergunta, não da resposta\n"
                "# do bot. Sobrescreva qualquer um que estiver errado.\n"
                "#\n"
                "# Mais fácil que editar aqui: abra anotar.html, arraste\n"
                "# dados/traces.jsonl e rotule com as teclas 1-9.\n")
        w = csv.writer(f)
        w.writerow(["trace_id"] + MODOS)
        for t in traces:
            dim = dimensao.get(t.get("query_id"), "")
            linha = [t["id"]]
            for m in MODOS:
                escopo = ESCOPO.get(m)
                if escopo is not None and dim not in escopo:
                    linha.append("na")
                else:
                    linha.append("")
                    em_branco += 1
            w.writerow(linha)

    total = len(traces) * len(MODOS)
    print(f"{saida.relative_to(RAIZ)}: {len(traces)} traces × {len(MODOS)} modos = {total} células")
    print(f"  {total - em_branco} marcadas `na` pela dimensão da pergunta")
    print(f"  {em_branco} em branco — essas exigem julgamento humano")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
