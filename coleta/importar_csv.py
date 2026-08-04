#!/usr/bin/env python3
"""
Converte um CSV de conversas em traces.jsonl no formato do projeto.

    # ver o que tem no arquivo antes de converter
    python coleta/importar_csv.py conversas.csv --inspecionar

    # converter, deixando o script adivinhar as colunas
    python coleta/importar_csv.py conversas.csv --saida dados/traces_turma.jsonl

    # dizer as colunas na mão, quando o palpite errar
    python coleta/importar_csv.py conversas.csv \
        --col-pergunta "mensagem_usuario" --col-resposta "resposta_bot"

Para que serve: o kit deste repositório coleta traces direto do Telegram, mas
uma turma inteira avaliando o mesmo bot recebe os traces prontos, num CSV. Este
script traduz aquele formato para o daqui, sem exigir que ninguém edite código.

O que ele NÃO faz: inventar dado. Se a coluna de idade não existir, o trace sai
com `idade_meses: null` — e o avaliador de idade trata isso como "não
informada", que é o comportamento certo. Preencher com um chute contaminaria a
avaliação inteira.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Nomes prováveis por campo, em ordem de preferência. Comparação sem acento,
# sem caixa e sem separador — "Mensagem do Usuário" casa com "mensagem_usuario".
PALPITES = {
    "input":    ["pergunta", "input", "mensagem", "usuario", "user", "prompt",
                 "consulta", "entrada", "question", "cuidador"],
    "output":   ["resposta", "output", "bot", "assistant", "saida", "answer",
                 "completion", "resposta_bot"],
    "id":       ["id", "trace_id", "traceid", "identificador", "n", "numero"],
    "idade":    ["idade", "idade_meses", "meses", "age", "idademeses"],
    "restricoes": ["restricao", "restricoes", "alergia", "alergias", "restriction"],
    # Datasets de turma costumam trazer a análise humana junto — uma coluna com
    # "ERRO: ..." descrevendo o que a resposta tem de errado. Isso é codificação
    # aberta pronta, e vai para o campo `nota` do trace.
    "nota": ["erro", "erros", "observacao", "observacoes", "anotacao", "analise",
             "problema", "avaliacao", "comentario", "diagnostico", "falha"],
}


def chave(s: str) -> str:
    """Normaliza um nome de coluna para comparação frouxa."""
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def achar(colunas: list[str], candidatos: list[str]) -> str | None:
    """Primeiro casamento exato; depois, primeiro que contenha o candidato."""
    mapa = {chave(c): c for c in colunas}
    for cand in candidatos:
        if chave(cand) in mapa:
            return mapa[chave(cand)]
    for cand in candidatos:
        for k, original in mapa.items():
            if chave(cand) in k:
                return original
    return None


def meses(valor: str | None) -> int | None:
    """Extrai um número de meses de textos como '8', '8 meses', '1 ano'."""
    if not valor:
        return None
    txt = valor.strip().lower()
    if re.search(r"\bano", txt):
        n = re.search(r"(\d+)", txt)
        return int(n.group(1)) * 12 if n else None
    n = re.search(r"(\d+)", txt)
    return int(n.group(1)) if n else None


def ler(caminho: Path) -> tuple[list[str], list[dict]]:
    """Lê o CSV tentando os separadores e as codificações mais comuns."""
    for cod in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = caminho.read_text(encoding=cod)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f"não consegui decodificar {caminho}")

    # StringIO, não splitlines(): as respostas do bot têm parágrafos, e
    # splitlines() corta as quebras de linha DENTRO dos campos entre aspas.
    # Um CSV de 195 conversas virava 1284 "linhas".
    def ler_com(dialeto):
        leitor = csv.DictReader(io.StringIO(texto), dialect=dialeto)
        return (leitor.fieldnames or []), list(leitor)

    # O padrão (vírgula, aspas duplas) primeiro. O Sniffer erra em CSV com
    # texto longo entre aspas — nesse mesmo arquivo ele inferiu um dialeto que
    # transformou 195 conversas em 739. Só recorremos a ele se o padrão
    # claramente não serviu.
    colunas, linhas = ler_com(csv.excel)
    if len(colunas) > 1:
        return colunas, linhas

    try:
        return ler_com(csv.Sniffer().sniff(texto[:8192], delimiters=";\t|,"))
    except csv.Error:
        return colunas, linhas


def main() -> int:
    p = argparse.ArgumentParser(description="CSV de conversas -> traces.jsonl")
    p.add_argument("csv", type=Path)
    p.add_argument("--saida", type=Path, default=RAIZ / "dados" / "traces_importados.jsonl")
    p.add_argument("--inspecionar", action="store_true",
                   help="mostra colunas e uma linha de exemplo, sem converter")
    p.add_argument("--col-pergunta"); p.add_argument("--col-resposta")
    p.add_argument("--col-id"); p.add_argument("--col-idade")
    p.add_argument("--col-nota", help="coluna com a análise humana do erro, se houver")
    p.add_argument("--prefixo", default="c", help="prefixo dos ids gerados (padrão: c)")
    p.add_argument("--origem", default="turma", help="rótulo de origem no trace")
    args = p.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"{args.csv} não existe.")

    colunas, linhas = ler(args.csv)
    if not linhas:
        raise SystemExit("o CSV não tem linha de dado alguma.")

    c_in  = args.col_pergunta or achar(colunas, PALPITES["input"])
    c_out = args.col_resposta or achar(colunas, PALPITES["output"])
    c_id  = args.col_id or achar(colunas, PALPITES["id"])
    c_age = args.col_idade or achar(colunas, PALPITES["idade"])
    c_res = achar(colunas, PALPITES["restricoes"])
    c_nota = args.col_nota or achar(colunas, PALPITES["nota"])

    if args.inspecionar:
        print(f"{len(linhas)} linhas · {len(colunas)} colunas\n")
        print("colunas:", ", ".join(colunas), "\n")
        print("palpite do mapeamento:")
        for rotulo, col in (("pergunta", c_in), ("resposta", c_out),
                            ("id", c_id), ("idade", c_age), ("restrições", c_res),
                            ("análise", c_nota)):
            print(f"  {rotulo:<11} -> {col or '(não achei)'}")
        print("\nprimeira linha:")
        for k, v in list(linhas[0].items())[:12]:
            v = (v or "").replace("\n", " ")
            print(f"  {k}: {v[:90]}{'…' if len(v) > 90 else ''}")
        print("\nSe o palpite errou, repita com --col-pergunta / --col-resposta.")
        return 0

    if not c_in or not c_out:
        print("não identifiquei as colunas de pergunta e resposta.", file=sys.stderr)
        print(f"colunas disponíveis: {', '.join(colunas)}", file=sys.stderr)
        print("rode com --inspecionar, ou passe --col-pergunta e --col-resposta.",
              file=sys.stderr)
        return 2

    traces, sem_resposta = [], 0
    for i, linha in enumerate(linhas, 1):
        entrada = (linha.get(c_in) or "").strip()
        saida = (linha.get(c_out) or "").strip()
        if not entrada and not saida:
            continue
        if not saida:
            sem_resposta += 1
        bruto = (linha.get(c_id) or "").strip() if c_id else ""
        traces.append({
            "id": f"{args.prefixo}{bruto}" if bruto else f"{args.prefixo}{i:03d}",
            "query_id": bruto or "",
            "origem": args.origem,
            "idade_meses": meses(linha.get(c_age)) if c_age else None,
            "restricoes": [x.strip() for x in (linha.get(c_res) or "").split(",") if x.strip()]
                          if c_res else [],
            "input": entrada,
            "output": saida,
            "nota": (linha.get(c_nota) or "").strip() if c_nota else "",
        })

    vistos, unicos = set(), []
    for t in traces:                            # ids repetidos quebram a rotulagem
        if t["id"] in vistos:
            t["id"] = f"{t['id']}_{len(unicos)}"
        vistos.add(t["id"])
        unicos.append(t)

    def curto(c: Path) -> str:
        """Caminho relativo ao repo quando dá; absoluto quando a saída é fora."""
        try:
            return str(c.relative_to(RAIZ))
        except ValueError:
            return str(c)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    with open(args.saida, "w", encoding="utf-8") as f:
        for t in unicos:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    com_nota = sum(1 for t in unicos if t["nota"])
    com_idade = sum(1 for t in unicos if t["idade_meses"] is not None)
    print(f"{len(unicos)} traces -> {curto(args.saida)}")
    print(f"  colunas usadas: pergunta={c_in} · resposta={c_out}"
          + (f" · idade={c_age}" if c_age else " · idade=(nenhuma)"))
    print(f"  {com_idade} com idade · {len(unicos) - com_idade} sem")
    if com_nota:
        print(f"  {com_nota} com análise humana já escrita — ela aparece no campo "
              f"de codificação aberta do anotar.html, como ponto de partida")
    if sem_resposta:
        print(f"  {sem_resposta} sem resposta do bot — os avaliadores marcam "
              f"como problema de COLETA, não de comportamento")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
