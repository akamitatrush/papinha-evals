#!/usr/bin/env python3
"""
Executa um juiz LLM sobre um arquivo de traces.

    # ver o prompt montado do primeiro trace, sem gastar token
    python julgar.py avaliadores/juizes/J1_textura_idade.md dados/traces.jsonl --dry-run

    # rodar de verdade (usa o `claude` CLI — consome tokens do seu plano)
    python julgar.py avaliadores/juizes/J1_textura_idade.md dados/traces.jsonl \
        --saida dados/juiz_J1.jsonl

    # validar contra os rótulos humanos
    python validar_juiz.py --predicoes dados/juiz_J1.jsonl --modo F03

Por que o `claude` CLI e não a API: a turma tem plano Pro, não chave de API.
O modo -p (print) roda uma consulta única e devolve o texto — os tokens saem
da assinatura, sem configurar nada.

O executor é retomável: se um lote falhar no meio, rode de novo com a mesma
--saida. Traces já julgados são pulados.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

VERMELHO, AMARELO, VERDE, CINZA, NEGRITO, FIM = (
    "\033[31m", "\033[33m", "\033[32m", "\033[90m", "\033[1m", "\033[0m"
)

# Mapeia cada juiz ao modo de falha que ele cobre (para o veredito jsonl
# encaixar direto no validar_juiz.py)
MODO_DO_JUIZ = {
    "J1_textura_idade": "F03",
    "J2_restricao_declarada": "F05",
    "J3_manejo_alergenicos": "F04",
    "J4_bajulacao_pressao": "F12",
}


def extrair_prompt(caminho_juiz: Path) -> str:
    """Monta o prompt do juiz a partir do markdown.

    Os arquivos de juiz documentam os 4 componentes dentro de cercas de código.
    O prompt executável é a concatenação dos blocos ``` do arquivo, na ordem,
    até a seção "Montagem do prompt" (exclusive) — o que vem depois é
    instrução para humanos, não para o modelo.
    """
    texto = caminho_juiz.read_text(encoding="utf-8")
    corte = texto.find("## Montagem do prompt")
    if corte != -1:
        texto = texto[:corte]
    blocos = re.findall(r"```\n(.*?)```", texto, re.S)
    if not blocos:
        raise SystemExit(f"nenhum bloco de prompt encontrado em {caminho_juiz}")
    return "\n\n".join(b.strip() for b in blocos)


def montar_conversa(trace: dict) -> str:
    idade = trace.get("idade_meses")
    partes = [
        "## Conversa a avaliar",
        "",
        f"Idade informada: {f'{idade} meses' if idade is not None else 'não informada'}",
    ]
    if trace.get("restricoes"):
        partes.append(f"Restrições declaradas pelo usuário: {', '.join(trace['restricoes'])}")
    if trace.get("historico"):
        partes.append(f"Histórico da conversa: {trace['historico']}")
    partes += [
        f"Mensagem do usuário: {trace.get('input', '')}",
        f"Resposta do Papinha Fácil: {trace.get('output', '')}",
    ]
    return "\n".join(partes)


def extrair_json(texto: str) -> dict | None:
    """Extrai o primeiro objeto JSON da resposta, tolerando cercas de código."""
    texto = re.sub(r"```(?:json)?", "", texto)
    ini = texto.find("{")
    if ini == -1:
        return None
    profundidade = 0
    for i, ch in enumerate(texto[ini:], start=ini):
        if ch == "{":
            profundidade += 1
        elif ch == "}":
            profundidade -= 1
            if profundidade == 0:
                try:
                    return json.loads(texto[ini:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def chamar_claude(prompt: str, modelo: str, timeout_s: int) -> str:
    r = subprocess.run(
        ["claude", "-p", "--model", modelo, "--"],
        input=prompt, capture_output=True, text=True, timeout=timeout_s,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"claude saiu com código {r.returncode}")
    return r.stdout


def main() -> int:
    p = argparse.ArgumentParser(description="Executa um juiz LLM sobre traces")
    p.add_argument("juiz", type=Path, help="arquivo do juiz, ex.: avaliadores/juizes/J1_textura_idade.md")
    p.add_argument("traces", type=Path, help="arquivo .jsonl de traces")
    p.add_argument("--saida", type=Path, help="jsonl de vereditos (padrão: dados/juiz_<nome>.jsonl)")
    p.add_argument("--modelo", default="claude-sonnet-5",
                   help="modelo do juiz (padrão: claude-sonnet-5 — juiz não precisa do modelo mais caro)")
    p.add_argument("--limite", type=int, help="julga só os N primeiros traces pendentes")
    p.add_argument("--timeout", type=int, default=120, help="segundos por chamada")
    p.add_argument("--dry-run", action="store_true",
                   help="mostra o prompt do primeiro trace pendente e sai, sem gastar token")
    args = p.parse_args()

    nome_juiz = args.juiz.stem
    modo = MODO_DO_JUIZ.get(nome_juiz, "?")
    prompt_base = extrair_prompt(args.juiz)

    traces = []
    with open(args.traces, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha and not linha.startswith("//"):
                traces.append(json.loads(linha))
    if not traces:
        print("nenhum trace lido.", file=sys.stderr)
        return 2

    saida = args.saida or RAIZ / "dados" / f"juiz_{nome_juiz}.jsonl"

    # retomada: pula o que já foi julgado
    ja_julgados: set[str] = set()
    if saida.exists():
        with open(saida, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    ja_julgados.add(json.loads(linha)["trace_id"])

    pendentes = [t for t in traces if t["id"] not in ja_julgados]
    if args.limite:
        pendentes = pendentes[:args.limite]

    print(f"\n{NEGRITO}Juiz {nome_juiz}{FIM} {CINZA}(modo {modo}, modelo {args.modelo}){FIM}")
    print(f"{CINZA}{len(traces)} traces · {len(ja_julgados)} já julgados · "
          f"{len(pendentes)} a julgar{FIM}\n")

    if not pendentes:
        print("nada a fazer.")
        return 0

    if args.dry_run:
        prompt = f"{prompt_base}\n\n{montar_conversa(pendentes[0])}"
        print(f"{CINZA}--- prompt completo do trace {pendentes[0]['id']} "
              f"({len(prompt)} chars) ---{FIM}\n")
        print(prompt)
        return 0

    ok = erros = 0
    with open(saida, "a", encoding="utf-8") as f:
        for n, trace in enumerate(pendentes, 1):
            prompt = f"{prompt_base}\n\n{montar_conversa(trace)}"
            try:
                resposta = chamar_claude(prompt, args.modelo, args.timeout)
                veredito_json = extrair_json(resposta)
                if veredito_json is None or "veredito" not in veredito_json:
                    raise ValueError(f"resposta sem JSON de veredito: {resposta[:200]!r}")
                veredito = str(veredito_json["veredito"]).strip().upper()
                if veredito not in {"PASSA", "FALHA"}:
                    raise ValueError(f"veredito inesperado: {veredito!r}")
                registro = {
                    "trace_id": trace["id"],
                    "juiz": nome_juiz,
                    "modo": modo,
                    "veredito": "falha" if veredito == "FALHA" else "passa",
                    "detalhe": veredito_json,
                }
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
                f.flush()
                ok += 1
                cor = VERMELHO if veredito == "FALHA" else VERDE
                just = str(veredito_json.get("justificativa", ""))[:90]
                print(f"  [{n}/{len(pendentes)}] {trace['id']} {cor}{veredito}{FIM} "
                      f"{CINZA}{just}{FIM}")
            except subprocess.TimeoutExpired:
                erros += 1
                print(f"  [{n}/{len(pendentes)}] {trace['id']} {AMARELO}timeout — pulei; "
                      f"rode de novo para retomar{FIM}")
            except Exception as e:
                erros += 1
                print(f"  [{n}/{len(pendentes)}] {trace['id']} {VERMELHO}erro:{FIM} "
                      f"{str(e)[:160]}")
            time.sleep(0.5)  # gentileza com o rate limit

    print(f"\n{VERDE}{ok} julgados{FIM}"
          + (f" · {VERMELHO}{erros} com erro{FIM} (rode de novo para retomar)" if erros else ""))
    print(f"{CINZA}vereditos em {saida}{FIM}")
    print(f"\npróximo passo:\n  ./.venv/bin/python validar_juiz.py "
          f"--predicoes {saida} --modo {modo}")
    return 0 if erros == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
