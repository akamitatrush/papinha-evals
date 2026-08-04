#!/usr/bin/env python3
"""
Converte um export do Telegram Desktop em traces.jsonl.

Fluxo:
  1. Converse com o @Papinha_facil_bot no Telegram (as 45 consultas de
     dados/consultas.jsonl, ou as que der tempo).
  2. No Telegram Desktop: abra o chat do bot → ⋮ → "Exportar histórico da
     conversa" → formato "JSON legível por máquina" → sem mídia.
     Sai um result.json.
  3. Rode:

       python coleta/importar_telegram.py result.json --saida dados/traces.jsonl

O script pareia cada mensagem SUA com a(s) resposta(s) do bot que vêm em
seguida, e tenta casar o texto enviado com dados/consultas.jsonl para herdar
query_id, idade_meses e restrições. O que não casar vira trace com
query_id=null e idade extraída por regex do próprio texto ("bebê de 8 meses").

Não requer chave, API nem login: é só um conversor de arquivo local.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONSULTAS_PADRAO = RAIZ / "dados" / "consultas.jsonl"

LIMIAR_FUZZY = 0.87  # similaridade mínima para casar consulta editada de leve


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def texto_da_mensagem(msg: dict) -> str:
    """O campo text do export pode ser string ou lista de trechos/entidades."""
    t = msg.get("text", "")
    if isinstance(t, str):
        return t
    partes = []
    for trecho in t:
        partes.append(trecho if isinstance(trecho, str) else trecho.get("text", ""))
    return "".join(partes)


def carregar_consultas(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    consultas = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                consultas.append(json.loads(linha))
    return consultas


def casar_consulta(texto: str, consultas: list[dict]) -> dict | None:
    """Casa o texto enviado com uma consulta do kit, exato ou aproximado."""
    alvo = normalizar(texto)
    for c in consultas:
        if normalizar(c["texto"]) == alvo:
            return c
    melhor, melhor_ratio = None, 0.0
    for c in consultas:
        r = difflib.SequenceMatcher(None, alvo, normalizar(c["texto"])).ratio()
        if r > melhor_ratio:
            melhor, melhor_ratio = c, r
    return melhor if melhor_ratio >= LIMIAR_FUZZY else None


_IDADE = re.compile(r"(\d{1,2})\s*(?:meses|mes\b|mesinhos)")


def idade_do_texto(texto: str) -> int | None:
    m = _IDADE.search(normalizar(texto))
    if m:
        idade = int(m.group(1))
        if 0 < idade <= 36:
            return idade
    if re.search(r"\b1 ano e meio\b", normalizar(texto)):
        return 18
    return None


def identificar_bot(export: dict, nome_bot: str | None) -> str:
    """Em export de chat pessoal, `name` é o interlocutor — o bot."""
    if nome_bot:
        return nome_bot
    nome = export.get("name")
    if nome:
        return nome
    raise SystemExit("não consegui identificar o bot; passe --bot \"Nome do bot\"")


def parear(mensagens: list[dict], nome_bot: str) -> list[dict]:
    """Agrupa: mensagem do usuário -> respostas do bot até a próxima do usuário."""
    pares = []
    atual = None
    for msg in mensagens:
        if msg.get("type") != "message":
            continue
        texto = texto_da_mensagem(msg).strip()
        if not texto:
            continue
        de_bot = msg.get("from") == nome_bot
        if de_bot:
            if atual is not None:
                atual["respostas"].append(texto)
        else:
            if atual is not None and atual["respostas"]:
                pares.append(atual)
            elif atual is not None:
                # duas mensagens do usuário seguidas: turno multiturno
                atual["turnos_extras"].append(texto)
                continue
            atual = {"pergunta": texto, "respostas": [], "turnos_extras": [],
                     "data": msg.get("date", "")}
    if atual is not None and atual["respostas"]:
        pares.append(atual)
    return pares


def main() -> int:
    p = argparse.ArgumentParser(description="Export do Telegram Desktop -> traces.jsonl")
    p.add_argument("export", type=Path, help="result.json exportado do Telegram Desktop")
    p.add_argument("--saida", type=Path, default=RAIZ / "dados" / "traces.jsonl")
    p.add_argument("--consultas", type=Path, default=CONSULTAS_PADRAO)
    p.add_argument("--bot", help="nome exibido do bot (autodetectado pelo campo 'name')")
    p.add_argument("--anexar", action="store_true",
                   help="acrescenta ao arquivo de saída em vez de recusar sobrescrever")
    args = p.parse_args()

    export = json.loads(args.export.read_text(encoding="utf-8"))
    nome_bot = identificar_bot(export, args.bot)
    consultas = carregar_consultas(args.consultas)

    pares = parear(export.get("messages", []), nome_bot)
    if not pares:
        print("nenhum par pergunta->resposta encontrado. O nome do bot está certo? "
              f"(usei: {nome_bot!r})", file=sys.stderr)
        return 2

    if args.saida.exists() and args.saida.stat().st_size > 0 and not args.anexar:
        print(f"{args.saida} já tem conteúdo. Use --anexar para acrescentar, ou "
              f"aponte --saida para outro arquivo.", file=sys.stderr)
        return 2

    # ids sequenciais continuando o que já existe no arquivo
    proximo = 1
    if args.anexar and args.saida.exists():
        with open(args.saida, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    m = re.match(r"t(\d+)", json.loads(linha).get("id", ""))
                    if m:
                        proximo = max(proximo, int(m.group(1)) + 1)

    casados = 0
    with open(args.saida, "a" if args.anexar else "w", encoding="utf-8") as f:
        for par in pares:
            consulta = casar_consulta(par["pergunta"], consultas)
            if consulta:
                casados += 1
            trace = {
                "id": f"t{proximo:03d}",
                "query_id": consulta["id"] if consulta else None,
                "origem": "real",
                "idade_meses": (consulta.get("idade_meses") if consulta
                                else idade_do_texto(par["pergunta"])),
                "restricoes": [],
                "input": par["pergunta"],
                "output": "\n\n".join(par["respostas"]),
                "data": par["data"],
                "nota": "",
            }
            if par["turnos_extras"]:
                trace["historico"] = " | ".join([par["pergunta"], *par["turnos_extras"]])
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
            proximo += 1

    print(f"{len(pares)} traces gravados em {args.saida} "
          f"({casados} casados com consultas do kit, {len(pares) - casados} avulsos)")
    print("\npróximos passos:")
    print(f"  ./.venv/bin/python rodar_evals.py {args.saida}")
    print(f"  # e abra anotar.html arrastando {args.saida} para rotular")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
