#!/usr/bin/env python3
"""
Envia as consultas do kit ao @Papinha_facil_bot pela SUA conta do Telegram e
captura as respostas direto em traces.jsonl.

⚠️  Este script age como VOCÊ no Telegram. Ele só envia as consultas do kit ao
bot indicado — nada além disso — mas leia antes de rodar, como qualquer script
que usa sua conta.

Preparação (uma vez):
  1. ./.venv/bin/pip install telethon
  2. Crie credenciais de aplicativo em https://my.telegram.org/apps
     (App api_id e api_hash — são suas, não as compartilhe nem as commite).
  3. Exporte no shell:
       export TELEGRAM_API_ID=1234567
       export TELEGRAM_API_HASH=abcdef...

Uso:
    ./.venv/bin/python coleta/enviar_consultas.py                # todas as 45
    ./.venv/bin/python coleta/enviar_consultas.py --dimensao proibido_direto
    ./.venv/bin/python coleta/enviar_consultas.py --limite 5     # só as 5 primeiras

No primeiro uso o Telethon pede seu telefone e o código de login que chega no
seu próprio Telegram — é você autenticando você. Fica salvo um arquivo
papinha_coleta.session (já no .gitignore) para as próximas execuções.

O script é retomável: consultas cujo query_id já está no arquivo de saída são
puladas. Intervalo entre envios de 8s por padrão — o bot é do professor e a
turma inteira vai testá-lo; não vale derrubar o rate limit dos colegas.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

try:
    from telethon import TelegramClient
    from telethon.errors import FloodWaitError
except ImportError:
    print("Telethon não instalado. Rode:\n  ./.venv/bin/pip install telethon",
          file=sys.stderr)
    sys.exit(2)

BOT_PADRAO = "@Papinha_facil_bot"
SESSAO = str(RAIZ / "coleta" / "papinha_coleta")
TIMEOUT_RESPOSTA = 90       # o bot pode demorar; LLM atrás dele
JANELA_RESPOSTA_EXTRA = 6   # segundos aguardando mensagens adicionais da mesma resposta


def carregar_consultas(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def ja_coletados(saida: Path) -> set[str]:
    if not saida.exists():
        return set()
    ids = set()
    with open(saida, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                qid = json.loads(linha).get("query_id")
                if qid:
                    ids.add(qid)
    return ids


def turnos_da_consulta(texto: str) -> list[str]:
    """q034 codifica multiturno como 'TURNO 1: ... | TURNO 2: ...'."""
    if "TURNO" not in texto:
        return [texto]
    partes = re.split(r"\s*\|\s*", texto)
    turnos = []
    for p in partes:
        m = re.match(r"TURNO \d+:\s*'?(.*?)'?\s*$", p.strip())
        turnos.append(m.group(1) if m else p.strip())
    return turnos


def proximo_id(saida: Path) -> int:
    n = 1
    if saida.exists():
        with open(saida, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    m = re.match(r"t(\d+)", json.loads(linha).get("id", ""))
                    if m:
                        n = max(n, int(m.group(1)) + 1)
    return n


async def coletar_resposta(conv) -> str:
    """Primeira resposta + eventuais mensagens extras logo em seguida."""
    resposta = await conv.get_response()
    partes = [resposta.raw_text or ""]
    while True:
        try:
            extra = await asyncio.wait_for(conv.get_response(),
                                           timeout=JANELA_RESPOSTA_EXTRA)
            partes.append(extra.raw_text or "")
        except asyncio.TimeoutError:
            break
    return "\n\n".join(p for p in partes if p)


async def main() -> int:
    p = argparse.ArgumentParser(description="Envia consultas ao bot e captura traces")
    p.add_argument("--bot", default=BOT_PADRAO)
    p.add_argument("--consultas", type=Path, default=RAIZ / "dados" / "consultas.jsonl")
    p.add_argument("--saida", type=Path, default=RAIZ / "dados" / "traces.jsonl")
    p.add_argument("--dimensao", help="filtra por dimensão (ex.: proibido_direto)")
    p.add_argument("--limite", type=int)
    p.add_argument("--intervalo", type=float, default=8.0,
                   help="segundos entre consultas (padrão 8; seja gentil com o bot)")
    args = p.parse_args()

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        print("Defina TELEGRAM_API_ID e TELEGRAM_API_HASH no ambiente.\n"
              "Crie as credenciais em https://my.telegram.org/apps", file=sys.stderr)
        return 2

    consultas = carregar_consultas(args.consultas)
    if args.dimensao:
        consultas = [c for c in consultas if c.get("dimensao") == args.dimensao]
    feitos = ja_coletados(args.saida)
    pendentes = [c for c in consultas if c["id"] not in feitos]
    if args.limite:
        pendentes = pendentes[:args.limite]

    print(f"{len(consultas)} consultas · {len(feitos)} já coletadas · "
          f"{len(pendentes)} a enviar para {args.bot}")
    if not pendentes:
        print("nada a fazer.")
        return 0

    n_trace = proximo_id(args.saida)
    async with TelegramClient(SESSAO, int(api_id), api_hash) as cliente:
        with open(args.saida, "a", encoding="utf-8") as f:
            for i, consulta in enumerate(pendentes, 1):
                turnos = turnos_da_consulta(consulta["texto"])
                try:
                    async with cliente.conversation(
                            args.bot, timeout=TIMEOUT_RESPOSTA) as conv:
                        respostas = []
                        for turno in turnos:
                            await conv.send_message(turno)
                            respostas.append(await coletar_resposta(conv))
                    trace = {
                        "id": f"t{n_trace:03d}",
                        "query_id": consulta["id"],
                        "origem": "real",
                        "idade_meses": consulta.get("idade_meses"),
                        "restricoes": [],
                        "input": turnos[-1],
                        "output": respostas[-1],
                        "nota": "",
                    }
                    if len(turnos) > 1:
                        trace["historico"] = " | ".join(
                            t + " -> " + r[:80] for t, r in zip(turnos, respostas))
                    f.write(json.dumps(trace, ensure_ascii=False) + "\n")
                    f.flush()
                    n_trace += 1
                    print(f"  [{i}/{len(pendentes)}] {consulta['id']} ok "
                          f"({len(respostas[-1])} chars)")
                except asyncio.TimeoutError:
                    print(f"  [{i}/{len(pendentes)}] {consulta['id']} sem resposta "
                          f"em {TIMEOUT_RESPOSTA}s — pulei; rode de novo para retomar")
                except FloodWaitError as e:
                    print(f"  rate limit do Telegram: aguardando {e.seconds}s...")
                    await asyncio.sleep(e.seconds + 1)
                await asyncio.sleep(args.intervalo)

    print(f"\ntraces em {args.saida}")
    print("próximos passos:")
    print(f"  ./.venv/bin/python rodar_evals.py {args.saida}")
    print(f"  # e abra anotar.html arrastando {args.saida} para rotular")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
