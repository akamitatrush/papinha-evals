#!/usr/bin/env python3
"""
Valida um avaliador (de código ou juiz LLM) contra rótulos humanos.

    # valida os avaliadores de código contra o padrão-ouro
    python rodar_evals.py dados/traces_exemplo.jsonl --saida /tmp/achados.jsonl
    python validar_juiz.py --predicoes /tmp/achados.jsonl --modo F01

    # valida um juiz LLM
    python validar_juiz.py --predicoes dados/juiz_J1.jsonl --modo F03

    # mostra os splits antes de rodar o juiz
    python validar_juiz.py --modo F03 --so-splits

    # corrige a taxa de falha observada em produção pelo viés do avaliador
    python validar_juiz.py --predicoes dados/juiz_J1.jsonl --modo F03 --taxa-observada 0.23

Convenção: a classe POSITIVA é FALHA — é ela que estamos tentando detectar.

    TPR (sensibilidade) = P(avaliador diz FALHA | humano disse FALHA)
    TNR (especificidade) = P(avaliador diz PASSA | humano disse PASSA)

Meta: TPR e TNR acima de 90% no split de dev. O split de teste é olhado UMA vez,
no fim. Iterar contra o teste transforma ele num segundo dev e a métrica final
vira ficção.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SEMENTE = 20260804  # split determinístico: mesma entrada, mesma partição, sempre

VERMELHO, AMARELO, VERDE, CINZA, NEGRITO, FIM = (
    "\033[31m", "\033[33m", "\033[32m", "\033[90m", "\033[1m", "\033[0m"
)

# Mapeia o avaliador de código que cobre cada modo de falha
AVALIADOR_DO_MODO = {
    "F01": "proibidos", "F02": "engasgo", "F03": "textura_proibida",
    "F04": "adiar_alergenico", "F06": "idade_assumida", "F07": "escopo_medico",
    "F09": "completude", "F10": "idioma", "F13": "dominio",
}


def ler_rotulos(caminho: Path, modo: str) -> dict[str, str]:
    """trace_id -> 'falha' | 'passa', pulando comentários e 'na'."""
    linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines()
              if l.strip() and not l.lstrip().startswith("#")]
    leitor = csv.DictReader(linhas)
    if modo not in (leitor.fieldnames or []):
        raise SystemExit(f"modo '{modo}' não existe em {caminho}. "
                         f"Colunas: {', '.join(leitor.fieldnames or [])}")
    rotulos = {}
    for linha in leitor:
        valor = (linha.get(modo) or "").strip().lower()
        if valor in {"falha", "passa"}:
            rotulos[linha["trace_id"].strip()] = valor
    return rotulos


def ler_predicoes(caminho: Path, modo: str) -> dict[str, str]:
    """trace_id -> 'falha' | 'passa'.

    Aceita a saída de rodar_evals.py (vários avaliadores por trace, filtrada
    pelo avaliador que cobre o modo) ou um jsonl de juiz LLM.
    """
    alvo = AVALIADOR_DO_MODO.get(modo)
    predicoes = {}
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            reg = json.loads(linha)
            if "avaliador" in reg and alvo and reg["avaliador"] != alvo:
                continue
            tid = reg.get("trace_id") or reg.get("id")
            veredito = str(reg.get("veredito", "")).strip().lower()
            if veredito == "revisar":       # fila de revisão não é predição
                continue
            if veredito in {"falha", "fail"}:
                predicoes[tid] = "falha"
            elif veredito in {"passa", "pass"}:
                predicoes[tid] = "passa"
    return predicoes


def dividir(ids_rotulados: dict[str, str]) -> dict[str, list[str]]:
    """Split estratificado 15/42/43 (treino/dev/teste), determinístico."""
    rng = random.Random(SEMENTE)
    splits = {"treino": [], "dev": [], "teste": []}
    for classe in ("falha", "passa"):
        ids = sorted(t for t, r in ids_rotulados.items() if r == classe)
        rng.shuffle(ids)
        n = len(ids)
        n_treino = max(1, round(n * 0.15)) if n >= 3 else 0
        n_dev = round((n - n_treino) * 0.49)
        splits["treino"] += ids[:n_treino]
        splits["dev"] += ids[n_treino:n_treino + n_dev]
        splits["teste"] += ids[n_treino + n_dev:]
    return splits


def metricas(rotulos: dict[str, str], predicoes: dict[str, str], ids: list[str]) -> dict:
    vp = fp = vn = fn = 0
    erros = {"fp": [], "fn": []}
    ausentes = []
    for tid in ids:
        if tid not in predicoes:
            ausentes.append(tid)
            continue
        humano, maquina = rotulos[tid], predicoes[tid]
        if humano == "falha" and maquina == "falha":
            vp += 1
        elif humano == "passa" and maquina == "falha":
            fp += 1
            erros["fp"].append(tid)
        elif humano == "passa" and maquina == "passa":
            vn += 1
        else:
            fn += 1
            erros["fn"].append(tid)
    return {
        "vp": vp, "fp": fp, "vn": vn, "fn": fn,
        "tpr": vp / (vp + fn) if (vp + fn) else None,
        "tnr": vn / (vn + fp) if (vn + fp) else None,
        "n": vp + fp + vn + fn,
        "erros": erros,
        "ausentes": ausentes,
    }


def corrigir_vies(taxa_obs: float, tpr: float, tnr: float) -> float | None:
    """Estimador de Rogan-Gladen: taxa verdadeira a partir da observada.

        real = (observada + TNR - 1) / (TPR + TNR - 1)

    Um avaliador com TPR 0,85 e TNR 0,92 que acusa 23% de falha em produção não
    significa que o bot falha 23% das vezes. Reportar a taxa crua é reportar o
    erro do avaliador somado ao erro do bot.
    """
    denom = tpr + tnr - 1
    if abs(denom) < 1e-9:
        return None  # avaliador não informativo: não dá para inverter
    return min(1.0, max(0.0, (taxa_obs + tnr - 1) / denom))


def barra(v: float | None) -> str:
    if v is None:
        return f"{CINZA}—{FIM}"
    cor = VERDE if v >= 0.9 else (AMARELO if v >= 0.75 else VERMELHO)
    return f"{cor}{v:>6.1%}{FIM}"


def main() -> int:
    p = argparse.ArgumentParser(description="Validação de avaliador contra rótulos humanos")
    p.add_argument("--rotulos", type=Path, default=RAIZ / "analise_erros" / "rotulos.csv")
    p.add_argument("--predicoes", type=Path, help="jsonl de achados ou de saída do juiz")
    p.add_argument("--modo", required=True, help="modo de falha, ex.: F01")
    p.add_argument("--so-splits", action="store_true")
    p.add_argument("--taxa-observada", type=float,
                   help="taxa de falha bruta em produção, para corrigir pelo viés")
    args = p.parse_args()

    rotulos = ler_rotulos(args.rotulos, args.modo)
    if not rotulos:
        print(f"nenhum rótulo válido para {args.modo}.", file=sys.stderr)
        return 2

    splits = dividir(rotulos)
    n_falha = sum(1 for r in rotulos.values() if r == "falha")

    print(f"\n{NEGRITO}Validação — modo {args.modo}{FIM}")
    print(f"{CINZA}{len(rotulos)} traces rotulados · {n_falha} falha · "
          f"{len(rotulos) - n_falha} passa{FIM}")
    print(f"{CINZA}splits: treino={len(splits['treino'])} dev={len(splits['dev'])} "
          f"teste={len(splits['teste'])} (semente {SEMENTE}){FIM}\n")

    if len(rotulos) < 40:
        print(f"{AMARELO}Amostra pequena.{FIM} {CINZA}A meta é ~100 traces rotulados, "
              f"com 30 a 50 de cada classe. Abaixo disso, TPR e TNR têm intervalo de "
              f"confiança largo demais para decidir alguma coisa.{FIM}\n")

    if args.so_splits:
        for nome in ("treino", "dev", "teste"):
            print(f"{NEGRITO}{nome}{FIM}: {', '.join(sorted(splits[nome])) or '—'}")
        print(f"\n{CINZA}Use o split de TREINO como fonte dos exemplos few-shot do juiz. "
              f"Nunca coloque dev ou teste dentro do prompt.{FIM}")
        return 0

    if not args.predicoes:
        print("faltou --predicoes (ou use --so-splits).", file=sys.stderr)
        return 2

    predicoes = ler_predicoes(args.predicoes, args.modo)
    if not predicoes:
        print(f"nenhuma predição encontrada em {args.predicoes} para {args.modo}.",
              file=sys.stderr)
        return 2

    print(f"{CINZA}{'split':<10} {'n':>4} {'VP':>4} {'FP':>4} {'VN':>4} {'FN':>4} "
          f"{'TPR':>8} {'TNR':>8}{FIM}")
    resultados = {}
    for nome in ("dev", "teste"):
        m = metricas(rotulos, predicoes, splits[nome])
        resultados[nome] = m
        print(f"{nome:<10} {m['n']:>4} {m['vp']:>4} {m['fp']:>4} {m['vn']:>4} "
              f"{m['fn']:>4} {barra(m['tpr'])} {barra(m['tnr'])}")

    todos = metricas(rotulos, predicoes, sorted(rotulos))
    print(f"{NEGRITO}{'total':<10}{FIM} {todos['n']:>4} {todos['vp']:>4} {todos['fp']:>4} "
          f"{todos['vn']:>4} {todos['fn']:>4} {barra(todos['tpr'])} {barra(todos['tnr'])}")

    if todos["ausentes"]:
        print(f"\n{AMARELO}sem predição para{FIM} {CINZA}"
              f"{', '.join(todos['ausentes'][:12])}{FIM}")

    if todos["erros"]["fn"]:
        print(f"\n{VERMELHO}Falsos negativos{FIM} {CINZA}(humano viu falha, avaliador "
              f"não viu — os que doem){FIM}")
        print(f"  {', '.join(todos['erros']['fn'])}")
    if todos["erros"]["fp"]:
        print(f"\n{AMARELO}Falsos positivos{FIM} {CINZA}(avaliador alarmou sem "
              f"motivo){FIM}")
        print(f"  {', '.join(todos['erros']['fp'])}")

    dev = resultados["dev"]
    if dev["tpr"] is not None and dev["tnr"] is not None:
        if dev["tpr"] >= 0.9 and dev["tnr"] >= 0.9:
            print(f"\n{VERDE}Dev acima de 90% nas duas métricas.{FIM} "
                  f"{CINZA}Pode medir no teste — uma vez só.{FIM}")
        else:
            print(f"\n{AMARELO}Dev abaixo de 90%.{FIM} {CINZA}Itere no avaliador olhando "
                  f"os erros acima. Cada falso negativo é um caso que o prompt ou a "
                  f"regra ainda não cobre.{FIM}")

    if args.taxa_observada is not None:
        tpr, tnr = todos["tpr"], todos["tnr"]
        if tpr is None or tnr is None:
            print(f"\n{AMARELO}Sem TPR/TNR completos: correção de viés indisponível.{FIM}")
        else:
            real = corrigir_vies(args.taxa_observada, tpr, tnr)
            print(f"\n{NEGRITO}Correção de viés{FIM}")
            print(f"  taxa observada em produção : {args.taxa_observada:.1%}")
            print(f"  TPR={tpr:.1%}  TNR={tnr:.1%}")
            if real is None:
                print(f"  {VERMELHO}avaliador não informativo (TPR+TNR≈1){FIM}")
            else:
                print(f"  {NEGRITO}taxa real estimada         : {real:.1%}{FIM}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
