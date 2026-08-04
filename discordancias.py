#!/usr/bin/env python3
"""
Onde o avaliador e o humano discordaram — e o que o avaliador argumentou.

    python rodar_evals.py dados/traces.jsonl --saida analise_erros/predicoes_reais.jsonl
    python discordancias.py --modo F06

Escreve discordancias.html e abre lado a lado, para cada caso: o trace, o que
você marcou, o que o avaliador decidiu e a JUSTIFICATIVA dele.

Por que isso existe: `validar_juiz.py` diz *quais* traces discordaram, mas não
*por quê*. E é a justificativa do avaliador que aponta o conserto — critério
estreito demais, exemplo few-shot faltando, exceção não prevista. Sem ela, a
iteração do prompt vira adivinhação.

Os dois erros não custam a mesma coisa neste domínio:

    FALSO NEGATIVO  o avaliador ficou quieto e havia falha
                    -> pode ser mel num bebê de 8 meses
    FALSO POSITIVO  o avaliador gritou e não era nada
                    -> custa tempo de revisão e infla a métrica

Por isso os falsos negativos vêm primeiro e destacados.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from validar_juiz import AVALIADOR_DO_MODO, dividir, ler_predicoes, ler_rotulos  # noqa: E402

VERMELHO, AMARELO, VERDE, CINZA, NEGRITO, FIM = (
    "\033[31m", "\033[33m", "\033[32m", "\033[90m", "\033[1m", "\033[0m"
)


def _e(s) -> str:
    return html.escape(str(s or ""))


CSS = """
:root{--void:#07080A;--painel:#0C0E12;--fio:#1B1F27;--fio-vivo:#2B323E;
 --ink:#EDF1F6;--ink-2:#9AA5B4;--ink-3:#5D6675;--sinal:#2FE3C4;
 --fn:#FF5F45;--fp:#FFB020;
 --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
 --sans:"Sora","Segoe UI",system-ui,sans-serif;color-scheme:dark}
*{box-sizing:border-box;margin:0}
body{background:var(--void);color:var(--ink);font-family:var(--sans);
 font-weight:300;line-height:1.6;padding:2.5rem 1.5rem 5rem}
.folha{max-width:64rem;margin:0 auto}
h1{font-size:clamp(1.7rem,4vw,2.4rem);font-weight:600;letter-spacing:-.035em}
h1 em{font-style:normal;color:var(--sinal)}
.sub{color:var(--ink-2);margin:.6rem 0 2rem;max-width:44rem}
.etiqueta{font-family:var(--mono);font-size:.625rem;letter-spacing:.16em;
 text-transform:uppercase;color:var(--ink-3)}
h2{font-size:1.25rem;font-weight:500;letter-spacing:-.02em;margin:2.5rem 0 .3rem;
 padding-top:1.4rem;border-top:1px solid var(--fio)}
.dica{color:var(--ink-2);font-size:.9375rem;margin-bottom:1.2rem;max-width:46rem}
.caso{border:1px solid var(--fio);border-radius:6px;background:var(--painel);
 padding:1.2rem 1.35rem;margin-bottom:1rem}
.caso.fn{border-left:3px solid var(--fn)}
.caso.fp{border-left:3px solid var(--fp)}
.caso-topo{display:flex;align-items:baseline;gap:.8rem;flex-wrap:wrap;
 margin-bottom:.9rem}
.tid{font-family:var(--mono);font-weight:700;font-size:1.05rem}
.selo{font-family:var(--mono);font-size:.6rem;letter-spacing:.12em;
 text-transform:uppercase;border:1px solid currentColor;border-radius:3px;
 padding:.1rem .4rem}
.selo.fn{color:var(--fn)} .selo.fp{color:var(--fp)}
.veredicto{margin-left:auto;font-family:var(--mono);font-size:.75rem;
 color:var(--ink-3)}
.veredicto b{color:var(--ink)}
.turno{margin-bottom:.7rem}
.turno .etiqueta{display:block;margin-bottom:.2rem}
.bolha{border-left:2px solid var(--fio-vivo);padding:.35rem 0 .35rem .85rem;
 white-space:pre-wrap;font-size:.9rem;color:var(--ink-2);max-height:16rem;
 overflow:auto}
.arg{margin-top:.9rem;padding-top:.9rem;border-top:1px solid var(--fio);
 font-size:.9rem}
.arg b{display:block;font-family:var(--mono);font-size:.6rem;letter-spacing:.14em;
 text-transform:uppercase;color:var(--ink-3);margin-bottom:.3rem;font-weight:500}
.ev{font-family:var(--mono);font-size:.78rem;color:var(--sinal);
 background:rgba(47,227,196,.08);border:1px solid rgba(47,227,196,.2);
 border-radius:3px;padding:.4rem .55rem;margin-top:.45rem;overflow-wrap:anywhere}
.vazio{color:var(--ink-3);font-style:italic}
.aviso{border-left:2px solid var(--fp);background:var(--painel);
 padding:.9rem 1.1rem;border-radius:0 4px 4px 0;margin:1.5rem 0;
 font-size:.9rem;color:var(--ink-2)}
.aviso b{color:var(--fp);display:block;margin-bottom:.25rem}
"""


def bloco(caso: dict) -> str:
    tipo = caso["tipo"]                       # "fn" ou "fp"
    rotulo = "falso negativo" if tipo == "fn" else "falso positivo"
    t = caso["trace"]
    a = caso["achado"]

    ev = ""
    if a and a.get("evidencias"):
        ev = "".join(f'<div class="ev">{_e(x)}</div>' for x in a["evidencias"][:3])

    just = (a or {}).get("justificativa") or ""
    corpo_just = (f'<div>{_e(just)}</div>{ev}' if just
                  else '<div class="vazio">O avaliador não deixou justificativa '
                       'para este caso.</div>')

    return f"""
<div class="caso {tipo}">
  <div class="caso-topo">
    <span class="tid">{_e(t.get("id"))}</span>
    <span class="selo {tipo}">{rotulo}</span>
    <span class="veredicto">humano <b>{_e(caso["humano"])}</b> ·
      avaliador <b>{_e(caso["maquina"])}</b></span>
  </div>
  <div class="turno"><span class="etiqueta">Cuidador</span>
    <div class="bolha">{_e(t.get("input"))}</div></div>
  <div class="turno"><span class="etiqueta">Papinha Fácil</span>
    <div class="bolha">{_e(t.get("output"))}</div></div>
  <div class="arg"><b>O que o avaliador argumentou</b>{corpo_just}</div>
</div>"""


def main() -> int:
    p = argparse.ArgumentParser(description="Discordâncias entre avaliador e humano")
    p.add_argument("--modo", required=True, help="modo de falha, ex.: F06")
    p.add_argument("--rotulos", type=Path,
                   default=RAIZ / "analise_erros" / "rotulos_reais.csv")
    p.add_argument("--predicoes", type=Path,
                   default=RAIZ / "analise_erros" / "predicoes_reais.jsonl")
    p.add_argument("--traces", type=Path, default=RAIZ / "dados" / "traces.jsonl")
    p.add_argument("--saida", type=Path, default=RAIZ / "discordancias.html")
    p.add_argument("--split", choices=["dev", "treino", "teste", "todos"], default="dev",
                   help="itere no dev; o teste é olhado UMA vez, no fim")
    args = p.parse_args()

    for c in (args.rotulos, args.predicoes, args.traces):
        if not c.exists():
            raise SystemExit(f"{c} não existe.")

    rotulos = ler_rotulos(args.rotulos, args.modo)
    if not rotulos:
        raise SystemExit(f"nenhum rótulo para {args.modo} em {args.rotulos.name}.")
    predicoes = ler_predicoes(args.predicoes, args.modo)
    traces = {json.loads(l)["id"]: json.loads(l)
              for l in args.traces.read_text(encoding="utf-8").splitlines() if l.strip()}

    ids = sorted(rotulos) if args.split == "todos" else sorted(dividir(rotulos)[args.split])

    avaliador = AVALIADOR_DO_MODO.get(args.modo)
    achados = {}
    for l in args.predicoes.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        a = json.loads(l)
        if a.get("avaliador") == avaliador:
            achados[a["trace_id"]] = a

    casos = []
    for tid in ids:
        if tid not in predicoes:
            continue
        h, m = rotulos[tid], predicoes[tid]
        if h == m:
            continue
        casos.append({"tipo": "fn" if h == "falha" else "fp", "humano": h, "maquina": m,
                      "trace": traces.get(tid, {"id": tid}), "achado": achados.get(tid)})

    # Falso negativo primeiro: neste domínio é o erro que dói.
    casos.sort(key=lambda c: (c["tipo"] != "fn", c["trace"].get("id", "")))
    fn = sum(1 for c in casos if c["tipo"] == "fn")
    fp = len(casos) - fn

    aviso = ""
    if args.split == "teste":
        aviso = ('<div class="aviso"><b>Você está olhando o split de TESTE</b>'
                 'Ajustar o prompt a partir daqui transforma o teste num segundo dev, '
                 'e o projeto fica sem nenhum conjunto limpo para dizer se o avaliador '
                 'funciona. Itere no dev.</div>')

    corpo = "".join(bloco(c) for c in casos) or (
        '<p class="dica">Nenhuma discordância neste split. '
        'Ou o avaliador está bom, ou o split é pequeno demais para mostrar erro.</p>')

    doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Discordâncias — {_e(args.modo)}</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="folha">
<span class="etiqueta">Calibração · split {_e(args.split)}</span>
<h1>Onde o avaliador e o humano <em>discordaram</em></h1>
<p class="sub">Modo <b>{_e(args.modo)}</b> · avaliador <code>{_e(avaliador)}</code> ·
{len(ids)} traces no split · <b style="color:var(--fn)">{fn} falsos negativos</b> ·
<b style="color:var(--fp)">{fp} falsos positivos</b></p>
{aviso}
<p class="dica">Cada discordância aponta um conserto diferente. <b>Falso
negativo</b> costuma ser critério estreito demais ou exemplo few-shot faltando.
<b>Falso positivo</b> costuma ser critério largo ou exceção não prevista. Leia a
justificativa do avaliador: é ela que diz qual dos dois.</p>
<h2>Casos</h2>{corpo}
</div></body></html>"""

    args.saida.write_text(doc, encoding="utf-8")
    print(f"\n{NEGRITO}Discordâncias — {args.modo} · split {args.split}{FIM}")
    print(f"{CINZA}{len(ids)} traces rotulados neste split{FIM}")
    print(f"  {VERMELHO}{fn} falsos negativos{FIM} (o avaliador ficou quieto e havia falha)")
    print(f"  {AMARELO}{fp} falsos positivos{FIM} (gritou e não era nada)")
    if casos:
        print(f"{CINZA}  {', '.join(c['trace'].get('id','?') for c in casos[:12])}"
              f"{'…' if len(casos) > 12 else ''}{FIM}")
    print(f"\n{VERDE}{args.saida.name}{FIM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
