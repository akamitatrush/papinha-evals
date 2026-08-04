#!/usr/bin/env python3
"""
Roda a validação de todos os modos de falha de uma vez e grava o resultado.

    python rodar_evals.py dados/traces.jsonl --saida analise_erros/predicoes_reais.jsonl
    python validar_todos.py

Escreve analise_erros/validacao.json, que o relatório lê para abrir com o TPR e
o TNR de cada avaliador — a única evidência de que os números que ele reporta
descrevem o bot, e não os bugs do detector.

Sem isso, o relatório mostra a precisão estimada pelo auditor automático, que é
ele próprio um juiz não medido. Este comando substitui essa estimativa por
medida contra rótulo humano.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from validar_juiz import (  # noqa: E402
    AVALIADOR_DO_MODO, dividir, ler_predicoes, ler_rotulos, metricas,
)

VERMELHO, AMARELO, VERDE, CINZA, NEGRITO, FIM = (
    "\033[31m", "\033[33m", "\033[32m", "\033[90m", "\033[1m", "\033[0m"
)
META = 0.90


def cor(v: float | None) -> str:
    if v is None:
        return CINZA
    return VERDE if v >= META else (AMARELO if v >= 0.7 else VERMELHO)


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0%}"


def main() -> int:
    p = argparse.ArgumentParser(description="Valida todos os modos contra o padrão-ouro")
    p.add_argument("--rotulos", type=Path,
                   default=RAIZ / "analise_erros" / "rotulos_reais.csv")
    p.add_argument("--predicoes", type=Path,
                   default=RAIZ / "analise_erros" / "predicoes_reais.jsonl")
    p.add_argument("--saida", type=Path,
                   default=RAIZ / "analise_erros" / "validacao.json")
    args = p.parse_args()

    if not args.rotulos.exists():
        raise SystemExit(f"{args.rotulos} não existe. Rode "
                         f"analise_erros/preparar_rotulagem.py e rotule antes.")
    if not args.predicoes.exists():
        raise SystemExit(f"{args.predicoes} não existe. Rode:\n"
                         f"  python rodar_evals.py dados/traces.jsonl "
                         f"--saida {args.predicoes}")

    resultado = {"meta": META, "modos": {}}
    print(f"\n{NEGRITO}Validação contra rótulo humano{FIM}")
    print(f"{CINZA}{'modo':<6} {'avaliador':<20} {'n':>4} {'VP':>4} {'FP':>4} "
          f"{'VN':>4} {'FN':>4} {'TPR':>7} {'TNR':>7} {'F1':>7}{FIM}")

    for modo, avaliador in sorted(AVALIADOR_DO_MODO.items()):
        try:
            rotulos = ler_rotulos(args.rotulos, modo)
        except SystemExit:
            continue                      # coluna não existe no CSV
        if not rotulos:
            print(f"{CINZA}{modo:<6} {avaliador:<20} sem rótulo — não validado{FIM}")
            resultado["modos"][modo] = {"avaliador": avaliador, "n": 0,
                                        "tpr": None, "tnr": None, "f1": None}
            continue

        predicoes = ler_predicoes(args.predicoes, modo)
        # Dev + teste juntos: com amostra deste tamanho, separar os splits deixa
        # cada um pequeno demais para significar coisa alguma. O split continua
        # existindo em validar_juiz.py, para quando houver ~100 rótulos.
        m = metricas(rotulos, predicoes, sorted(rotulos))
        resultado["modos"][modo] = {
            "avaliador": avaliador, "n": m["n"],
            "vp": m["vp"], "fp": m["fp"], "vn": m["vn"], "fn": m["fn"],
            "tpr": m["tpr"], "tnr": m["tnr"],
            "precisao": m["precisao"], "f1": m["f1"],
            "falsos_negativos": m["erros"]["fn"], "falsos_positivos": m["erros"]["fp"],
        }
        print(f"{modo:<6} {avaliador:<20} {m['n']:>4} {m['vp']:>4} {m['fp']:>4} "
              f"{m['vn']:>4} {m['fn']:>4} "
              f"{cor(m['tpr'])}{pct(m['tpr']):>7}{FIM} "
              f"{cor(m['tnr'])}{pct(m['tnr']):>7}{FIM} "
              f"{cor(m['f1'])}{pct(m['f1']):>7}{FIM}")

    validados = [v for v in resultado["modos"].values() if v.get("n")]
    resultado["n_modos_validados"] = len(validados)
    resultado["n_rotulos"] = max((v["n"] for v in validados), default=0)

    args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    try:                                    # caminho relativo pode ser de fora
        onde = args.saida.relative_to(RAIZ)
    except ValueError:
        onde = args.saida
    print(f"\n{VERDE}gravado em {onde}{FIM}")

    if resultado["n_rotulos"] < 40:
        print(f"{AMARELO}Amostra pequena.{FIM} {CINZA}A meta é ~100 traces rotulados. "
              f"Abaixo disso o intervalo de confiança do TPR/TNR é largo demais "
              f"para decidir alguma coisa — o número serve de sinal, não de prova.{FIM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
