"""
Painel visual do relatório de evals.

Formas escolhidas pelo trabalho que cada dado faz:

  precisão dos avaliadores   → número-herói (uma manchete, não um gráfico)
  procede / FP / incerto     → barra de composição única, rótulos diretos
  achados por avaliador      → barras horizontais empilhadas (magnitude + parte)
  resultado por trace        → grade de células (identidade, escaneável)
  taxonomia                  → tabela com gravidade por ícone + rótulo

Sem biblioteca: SVG e CSS inline. O arquivo abre offline como qualquer outro
artefato do projeto.

Cor: vermelho = falha real do bot, cinza = ruído do detector, âmbar = pendente
de humano. Status nunca carrega significado sozinho — sempre acompanha rótulo.
"""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Paleta de status (fixa, validada) + superfície de papel do projeto.
# `node scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a" --mode light` → PASS
CSS = """
:root{
  --papel:#F7F4EE; --superficie:#FFFDF9; --tinta:#1F1B16; --tinta-meia:#6B6259;
  --tinta-fina:#9C9287; --regua:#E4DDD2; --regua-forte:#D2C8B8; --acento:#1F4E5F;
  --real:#d03b3b; --ruido:#B8AFA2; --pendente:#fab219; --ok:#0ca30c;
  --serifada:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  --mono:"SF Mono","JetBrains Mono","IBM Plex Mono",ui-monospace,Menlo,monospace;
  --sans:Optima,"Avenir Next","Segoe UI",Helvetica,sans-serif;
}
@media (prefers-color-scheme:dark){:root:where(:not([data-tema="claro"])){
  --papel:#14120E; --superficie:#1B1915; --tinta:#EDE7DC; --tinta-meia:#A79E90;
  --tinta-fina:#736B60; --regua:#2E2A23; --regua-forte:#413B31; --acento:#7FBECE;
  --real:#e66767; --ruido:#5C554B; --pendente:#D99A3C; --ok:#63C48C; color-scheme:dark;}}
:root[data-tema="escuro"]{
  --papel:#14120E; --superficie:#1B1915; --tinta:#EDE7DC; --tinta-meia:#A79E90;
  --tinta-fina:#736B60; --regua:#2E2A23; --regua-forte:#413B31; --acento:#7FBECE;
  --real:#e66767; --ruido:#5C554B; --pendente:#D99A3C; --ok:#63C48C; color-scheme:dark;}
*{box-sizing:border-box;margin:0}
body{font-family:var(--sans);background:var(--papel);color:var(--tinta);
  line-height:1.5;-webkit-font-smoothing:antialiased}
.folha{max-width:56rem;margin:0 auto;padding:3.5rem 1.5rem 5rem}
h1{font-family:var(--serifada);font-weight:400;font-size:clamp(1.9rem,4.5vw,2.6rem);
  line-height:1.12;letter-spacing:-.015em;margin-bottom:.4rem}
h1 em{font-style:italic;color:var(--acento)}
h2{font-family:var(--serifada);font-weight:400;font-size:1.5rem;letter-spacing:-.01em;
  margin:3rem 0 .25rem;padding-top:1.5rem;border-top:1px solid var(--regua)}
.dica{color:var(--tinta-meia);font-size:.9375rem;margin-bottom:1.5rem;max-width:44rem}
.etiqueta{font-family:var(--mono);font-size:.625rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--tinta-fina)}
.cabecalho-meta{font-family:var(--mono);font-size:.75rem;color:var(--tinta-meia);
  display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:2.5rem}
.cabecalho-meta .divisor{color:var(--regua-forte)}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(8rem,1fr));
  gap:1px;background:var(--regua);border:1px solid var(--regua);margin-bottom:2rem}
.tile{background:var(--superficie);padding:1rem 1.1rem}
.tile .valor{font-family:var(--mono);font-size:1.75rem;font-weight:600;
  letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1.1}
.tile .rotulo{font-size:.75rem;color:var(--tinta-meia);margin-top:.2rem}

.heroi{display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap;margin-bottom:1rem}
.heroi .n{font-family:var(--mono);font-size:clamp(3rem,10vw,4.5rem);font-weight:600;
  letter-spacing:-.05em;line-height:1;font-variant-numeric:tabular-nums}
.heroi .n.baixa{color:var(--real)} .heroi .n.media{color:var(--pendente)}
.heroi .n.alta{color:var(--ok)}
.heroi .glosa{font-size:.9375rem;color:var(--tinta-meia);max-width:26rem}

.composicao{display:flex;height:14px;border-radius:2px;overflow:hidden;gap:2px;margin:.75rem 0 .6rem}
.composicao > i{display:block}
.legenda{display:flex;gap:1.25rem;flex-wrap:wrap;font-size:.8125rem;color:var(--tinta-meia)}
.legenda span{display:inline-flex;align-items:center;gap:.4rem}
.chip{width:10px;height:10px;border-radius:2px;flex:0 0 auto}
.legenda b{font-family:var(--mono);color:var(--tinta);font-variant-numeric:tabular-nums}

.barras{display:grid;grid-template-columns:auto 1fr auto;gap:.4rem .75rem;
  align-items:center;margin-top:1rem}
.barras .nome{font-family:var(--mono);font-size:.75rem;color:var(--tinta-meia);
  text-align:right;white-space:nowrap}
.trilho{display:flex;gap:2px;height:16px;align-items:center}
.trilho i{display:block;height:100%;border-radius:2px;min-width:2px}
.barras .num{font-family:var(--mono);font-size:.75rem;font-variant-numeric:tabular-nums;
  color:var(--tinta-meia);white-space:nowrap}

.grade{display:flex;flex-wrap:wrap;gap:4px;margin-top:1rem}
.cel{width:26px;height:26px;border-radius:2px;display:grid;place-items:center;
  font-family:var(--mono);font-size:.5rem;color:var(--tinta-fina);
  border:1px solid var(--regua-forte);background:var(--superficie);cursor:default}
.cel.falha{background:var(--real);border-color:var(--real);color:#fff;font-weight:700}
.cel.passa{background:transparent;border-color:var(--ok);color:var(--ok)}

table{width:100%;border-collapse:collapse;margin-top:1rem;font-size:.875rem}
th{text-align:left;font-family:var(--mono);font-size:.625rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--tinta-fina);font-weight:500;
  padding:.4rem .5rem;border-bottom:1px solid var(--regua-forte)}
td{padding:.55rem .5rem;border-bottom:1px solid var(--regua);vertical-align:top}
td.mono{font-family:var(--mono);font-size:.75rem;font-variant-numeric:tabular-nums;
  color:var(--tinta-meia);white-space:nowrap}
.grav{display:inline-flex;align-items:center;gap:.4rem;white-space:nowrap}

details{margin-top:1rem;border:1px solid var(--regua);background:var(--superficie)}
summary{padding:.6rem .9rem;cursor:pointer;font-size:.875rem;color:var(--tinta-meia)}
summary:hover{color:var(--tinta)}
details > div{padding:0 .9rem .9rem}
.achado{padding:.8rem 0;border-top:1px solid var(--regua);font-size:.9375rem}
.achado:first-child{border-top:none}
.achado .quem{font-family:var(--mono);font-size:.75rem;color:var(--acento);
  display:block;margin-bottom:.2rem}

.alerta{border-left:3px solid var(--real);background:var(--superficie);
  padding:.9rem 1.1rem;margin:1.25rem 0;font-size:.9375rem}
.alerta.aviso{border-left-color:var(--pendente)}
.alerta b{display:block;margin-bottom:.25rem}
.rodape{margin-top:4rem;padding-top:1.5rem;border-top:1px solid var(--regua);
  font-size:.8125rem;color:var(--tinta-meia);line-height:1.65}
.tema{position:fixed;top:.75rem;right:1rem;width:2rem;height:2rem;display:grid;
  place-items:center;border:1px solid var(--regua-forte);border-radius:50%;
  background:var(--superficie);color:var(--tinta-meia);cursor:pointer;
  transition:transform .3s}
.tema:hover{transform:rotate(-25deg)}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""


def _e(s) -> str:
    return html.escape(str(s or ""))


def _tile(valor, rotulo) -> str:
    return f'<div class="tile"><div class="valor">{_e(valor)}</div>' \
           f'<div class="rotulo">{_e(rotulo)}</div></div>'


def _barras_empilhadas(linhas, maximo) -> str:
    """linhas: [(nome, [(quantidade, cor, titulo), ...], total_rotulo)]"""
    out = ['<div class="barras">']
    for nome, partes, rotulo in linhas:
        total = sum(q for q, _, _ in partes) or 1
        segs = "".join(
            f'<i style="background:{cor};flex:{q}" title="{_e(t)}: {q}"></i>'
            for q, cor, t in partes if q
        )
        largura = (total / maximo * 100) if maximo else 0
        out.append(
            f'<span class="nome">{_e(nome)}</span>'
            f'<span class="trilho" style="width:{largura:.1f}%">{segs}</span>'
            f'<span class="num">{_e(rotulo)}</span>'
        )
    out.append("</div>")
    return "".join(out)


def gerar_html(caminho: Path, traces, brutos, revisar, auditados, anotacoes,
               taxonomia, uso, inicio, modelo) -> None:
    fim = datetime.now(timezone.utc)
    origens = Counter(t.get("origem", "?") for t in traces)

    procede = [a for a in auditados if a["auditoria"]["veredito"] == "procede"]
    fp = [a for a in auditados if a["auditoria"]["veredito"] == "falso_positivo"]
    incerto = [a for a in auditados if a["auditoria"]["veredito"] == "incerto"]
    precisao = len(procede) / len(auditados) if auditados else None

    p = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>Relatório de evals — Papinha Fácil</title>',
         f'<style>{CSS}</style></head><body>',
         '<button class="tema" id="tema" aria-label="Alternar tema">◐</button>',
         '<div class="folha">']

    # ── cabeçalho ──
    p.append('<span class="etiqueta">Relatório de avaliação</span>')
    p.append('<h1>Papinha Fácil — <em>evals</em></h1>')
    meta = [f"{fim:%Y-%m-%d %H:%M} UTC", f"{(fim - inicio).total_seconds():.0f}s"]
    meta.append(", ".join(f"{k}={v}" for k, v in sorted(origens.items())))
    if uso and uso.chamadas:
        meta += [f"modelo {modelo}",
                 f"{uso.chamadas} chamadas",
                 f"~US$ {uso.custo_estimado(modelo):.2f}"]
    p.append('<div class="cabecalho-meta">'
             + '<span class="divisor">·</span>'.join(f"<span>{_e(m)}</span>" for m in meta)
             + '</div>')

    # ── tiles ──
    n_falha_cod = sum(1 for a in anotacoes if a["resultado"] == "falha")
    p.append('<div class="tiles">')
    p.append(_tile(len(traces), "traces avaliados"))
    p.append(_tile(len(brutos), "achados brutos"))
    p.append(_tile(len(procede) if auditados else "—", "falhas confirmadas"))
    p.append(_tile(f"{precisao:.0%}" if precisao is not None else "—",
                   "precisão dos avaliadores"))
    if anotacoes:
        p.append(_tile(f"{n_falha_cod}/{len(anotacoes)}", "traces com falha"))
    p.append('</div>')

    if origens.get("sintetico"):
        p.append(f'<div class="alerta aviso"><b>{origens["sintetico"]} trace(s) '
                 f'sintéticos nesta amostra</b>Taxa de falha só descreve o bot '
                 f'quando calculada sobre traces reais.</div>')

    # ── auditoria: herói + composição ──
    if auditados:
        classe = "alta" if precisao >= .8 else ("media" if precisao >= .5 else "baixa")
        p.append('<h2>Auditoria dos achados</h2>')
        p.append('<p class="dica">Cada achado foi reexaminado ao lado do trace que o '
                 'originou, com uma pergunta só: <b>o bot recomendou a prática, ou '
                 'apenas a mencionou para desaconselhá-la?</b></p>')
        p.append(f'<div class="heroi"><span class="n {classe}">{precisao:.0%}</span>'
                 f'<span class="glosa">dos achados procedem. O resto é ruído dos '
                 f'detectores — e entraria no relatório como se fosse falha do bot.'
                 f'</span></div>')

        total = len(auditados)
        p.append('<div class="composicao">')
        for q, cor in ((len(procede), "var(--real)"), (len(fp), "var(--ruido)"),
                       (len(incerto), "var(--pendente)")):
            if q:
                p.append(f'<i style="flex:{q};background:{cor}"></i>')
        p.append('</div>')
        p.append('<div class="legenda">'
                 f'<span><i class="chip" style="background:var(--real)"></i>'
                 f'falha real do bot <b>{len(procede)}</b></span>'
                 f'<span><i class="chip" style="background:var(--ruido)"></i>'
                 f'falso positivo <b>{len(fp)}</b></span>'
                 f'<span><i class="chip" style="background:var(--pendente)"></i>'
                 f'revisão humana <b>{len(incerto)}</b></span></div>')

        if precisao < .8:
            p.append('<div class="alerta"><b>A taxa bruta não descreve o bot</b>'
                     f'Com {precisao:.0%} de precisão, a contagem de achados mede '
                     'sobretudo os bugs dos detectores. Corrija os falsos positivos '
                     'antes de reportar qualquer número.</div>')

        # barras por avaliador: quanto de cada detector sobrevive à auditoria
        por = {}
        for a in auditados:
            d = por.setdefault(a["avaliador"], {"procede": 0, "falso_positivo": 0, "incerto": 0})
            d[a["auditoria"]["veredito"]] += 1
        maximo = max(sum(v.values()) for v in por.values()) if por else 1
        linhas = []
        for nome, v in sorted(por.items(), key=lambda kv: -sum(kv[1].values())):
            linhas.append((nome, [
                (v["procede"], "var(--real)", "procede"),
                (v["incerto"], "var(--pendente)", "incerto"),
                (v["falso_positivo"], "var(--ruido)", "falso positivo"),
            ], f'{v["procede"]}/{sum(v.values())}'))
        p.append('<h2>Quanto sobrevive de cada avaliador</h2>')
        p.append('<p class="dica">Barra cheia é o que o detector apontou; a parte '
                 'vermelha é o que resistiu à auditoria.</p>')
        p.append(_barras_empilhadas(linhas, maximo))

        if procede:
            p.append('<h2>Falhas confirmadas</h2>')
            p.append('<div>')
            for a in sorted(procede, key=lambda x: x["trace_id"]):
                p.append(f'<div class="achado"><span class="quem">'
                         f'{_e(a["trace_id"])} · {_e(a["avaliador"])}</span>'
                         f'{_e(a["auditoria"]["explicacao"])}</div>')
            p.append('</div>')

        if fp:
            p.append(f'<details><summary>Falsos positivos ({len(fp)}) — '
                     f'por que cada um não procede</summary><div>')
            for a in sorted(fp, key=lambda x: x["trace_id"]):
                p.append(f'<div class="achado"><span class="quem">'
                         f'{_e(a["trace_id"])} · {_e(a["avaliador"])}</span>'
                         f'{_e(a["auditoria"]["o_que_a_resposta_faz"])}</div>')
            p.append('</div></details>')

        if incerto:
            p.append('<h2>Fila de revisão humana</h2><div>')
            for a in sorted(incerto, key=lambda x: x["trace_id"]):
                p.append(f'<div class="achado"><span class="quem">'
                         f'{_e(a["trace_id"])} · {_e(a["avaliador"])}</span>'
                         f'{_e(a["auditoria"]["explicacao"])}</div>')
            p.append('</div>')

    # ── grade de traces ──
    if anotacoes:
        p.append('<h2>Resultado por trace</h2>')
        p.append('<p class="dica">Codificação aberta: uma pergunta por trace — '
                 'o sistema produziu um bom resultado?</p>')
        p.append('<div class="grade">')
        for a in sorted(anotacoes, key=lambda x: x["trace_id"]):
            falhou = a["resultado"] == "falha"
            titulo = f'{a["trace_id"]}: {a["primeira_falha"] or a["observacao"]}'
            p.append(f'<div class="cel {"falha" if falhou else "passa"}" '
                     f'title="{_e(titulo)}">{_e(a["trace_id"].replace("t", ""))}</div>')
        p.append('</div>')
        p.append(f'<div class="legenda" style="margin-top:.75rem">'
                 f'<span><i class="chip" style="background:var(--real)"></i>'
                 f'falha <b>{n_falha_cod}</b></span>'
                 f'<span><i class="chip" style="border:1px solid var(--ok);'
                 f'background:transparent"></i>passa '
                 f'<b>{len(anotacoes) - n_falha_cod}</b></span></div>')

    # ── taxonomia ──
    if taxonomia:
        icone = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "⚪"}
        tipo = {"codigo": "⚙️ código", "juiz": "⚖️ juiz", "humano": "👤 humano"}
        p.append('<h2>Taxonomia observada</h2>')
        p.append(f'<p class="dica">{_e(taxonomia.resumo)}</p>')
        p.append('<table><thead><tr><th>Modo de falha</th><th>Gravidade</th>'
                 '<th>Traces</th><th>Avaliador</th></tr></thead><tbody>')
        ordem = ["critica", "alta", "media", "baixa"]
        for c in sorted(taxonomia.categorias,
                        key=lambda x: (ordem.index(x.gravidade), -len(x.traces))):
            p.append(f'<tr><td><b>{_e(c.rotulo)}</b><br>'
                     f'<span style="color:var(--tinta-meia);font-size:.8125rem">'
                     f'{_e(c.definicao)}</span></td>'
                     f'<td class="mono"><span class="grav">'
                     f'{icone.get(c.gravidade, "")} {_e(c.gravidade)}</span></td>'
                     f'<td class="mono">{len(c.traces)}</td>'
                     f'<td class="mono">{tipo.get(c.avaliador_sugerido, "")}</td></tr>')
        p.append('</tbody></table>')

        if taxonomia.modos_nao_observados:
            p.append('<details><summary>Modos da hipótese sem ocorrência '
                     f'({len(taxonomia.modos_nao_observados)})</summary><div>'
                     '<p class="dica" style="margin-top:.75rem">Ausência é '
                     'informação: estes avaliadores <b>não têm dados para ser '
                     'validados</b> ainda — não que o bot esteja imune a eles.</p>')
            for m in taxonomia.modos_nao_observados:
                p.append(f'<div class="achado">{_e(m)}</div>')
            p.append('</div></details>')

    # ── rodapé ──
    p.append('<div class="rodape"><p><b>Como ler.</b> A precisão dos avaliadores é o '
             'número a olhar primeiro. Se ela for baixa, a taxa de falha bruta '
             'descreve os bugs dos detectores, não o bot. Neste projeto, quatro '
             'rodadas manuais reportaram 100%, 64%, 48% e 18% de falha — as três '
             'primeiras estavam erradas, e toda correção foi no eval, nenhuma no '
             'bot.</p><p style="margin-top:.75rem"><b>O auditor é ele próprio um '
             'juiz não validado.</b> Automatizar o julgamento não elimina a '
             'validação humana — move ela de <i>toda rodada</i> para <i>uma vez</i>. '
             'Rotule uma amostra à mão em <code>anotar.html</code> e meça o TPR/TNR '
             'do auditor com <code>validar_juiz.py</code> antes de confiar neste '
             'número.</p></div>')

    p.append('</div><script>'
             'document.getElementById("tema").onclick=()=>{'
             'const a=document.documentElement.getAttribute("data-tema");'
             'const esc=a==="escuro"||(!a&&matchMedia("(prefers-color-scheme:dark)").matches);'
             'document.documentElement.setAttribute("data-tema",esc?"claro":"escuro")};'
             '</script></body></html>')

    caminho.write_text("".join(p), encoding="utf-8")
