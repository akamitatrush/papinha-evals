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
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Paleta de marcas do modo escuro (padrão), validada contra a superfície #0C0E12:
#   node scripts/validate_palette.js "#A83F2E,#C38618,#1F9480" --mode dark \
#        --surface "#0C0E12"                                    → ALL CHECKS PASS
# Vermelho e âmbar se confundem sob deuteranopia quando têm a mesma luminosidade;
# a separação aqui é por L (0.51 / 0.665 / 0.60), não por matiz.
# O modo claro mantém a paleta anterior, validada em `--mode light`.
#
# As fontes vêm da rede quando há rede, mas o arquivo tem de abrir offline —
# por isso toda família tem pilha de fallback do sistema.
CSS = """
@import url("https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap");
:root{
  --papel:#07080A; --superficie:#0C0E12; --superficie-alta:#11141A;
  --tinta:#EDF1F6; --tinta-meia:#9AA5B4; --tinta-fina:#5D6675;
  --regua:#1B1F27; --regua-forte:#2B323E; --acento:#2FE3C4;
  --real:#A83F2E; --ruido:#4A525F; --pendente:#C38618; --ok:#1F9480;
  /* tintas vivas: só para texto pequeno, onde a cor de marca não teria contraste */
  --real-viva:#FF7A63; --pendente-viva:#FFC24D; --ok-viva:#4EE0C0;
  --mono:"JetBrains Mono","SF Mono","IBM Plex Mono",ui-monospace,Menlo,monospace;
  --sans:"Sora","Segoe UI",system-ui,Helvetica,sans-serif;
  --serifada:var(--sans);
  color-scheme:dark;
}
@media (prefers-color-scheme:light){:root:where(:not([data-tema="escuro"])){
  --papel:#F7F4EE; --superficie:#FFFDF9; --superficie-alta:#FFFFFF;
  --tinta:#1F1B16; --tinta-meia:#6B6259; --tinta-fina:#9C9287;
  --regua:#E4DDD2; --regua-forte:#D2C8B8; --acento:#1F4E5F;
  --real:#d03b3b; --ruido:#B8AFA2; --pendente:#fab219; --ok:#0ca30c;
  --real-viva:#b32626; --pendente-viva:#8a5c00; --ok-viva:#0a7d0a; color-scheme:light;}}
:root[data-tema="claro"]{
  --papel:#F7F4EE; --superficie:#FFFDF9; --superficie-alta:#FFFFFF;
  --tinta:#1F1B16; --tinta-meia:#6B6259; --tinta-fina:#9C9287;
  --regua:#E4DDD2; --regua-forte:#D2C8B8; --acento:#1F4E5F;
  --real:#d03b3b; --ruido:#B8AFA2; --pendente:#fab219; --ok:#0ca30c;
  --real-viva:#b32626; --pendente-viva:#8a5c00; --ok-viva:#0a7d0a; color-scheme:light;}
*{box-sizing:border-box;margin:0}
body{font-family:var(--sans);font-weight:300;background:var(--papel);color:var(--tinta);
  line-height:1.55;-webkit-font-smoothing:antialiased;position:relative}
/* malha de blueprint, a mesma do site — some no modo claro e na impressão */
body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:linear-gradient(var(--regua) 1px,transparent 1px),
                   linear-gradient(90deg,var(--regua) 1px,transparent 1px);
  background-size:72px 72px;opacity:.45;
  -webkit-mask-image:radial-gradient(ellipse 85% 45% at 50% 0%,#000,transparent 75%);
  mask-image:radial-gradient(ellipse 85% 45% at 50% 0%,#000,transparent 75%)}
@media (prefers-color-scheme:light){
  :root:where(:not([data-tema="escuro"])) body::before{display:none}}
:root[data-tema="claro"] body::before{display:none}
@media print{body::before{display:none}}
.folha{max-width:62rem;margin:0 auto;padding:3.5rem 1.5rem 5rem;position:relative;z-index:1}
h1{font-family:var(--sans);font-weight:600;font-size:clamp(2rem,5vw,3rem);
  line-height:1.02;letter-spacing:-.04em;margin-bottom:.5rem}
h1 em{font-style:normal;color:var(--acento);text-shadow:0 0 38px rgba(47,227,196,.4)}
h2{font-family:var(--sans);font-weight:500;font-size:1.45rem;letter-spacing:-.03em;
  margin:3.25rem 0 .25rem;padding-top:1.6rem;border-top:1px solid var(--regua)}
.dica{color:var(--tinta-meia);font-size:.9375rem;margin-bottom:1.5rem;max-width:44rem}
.etiqueta{font-family:var(--mono);font-size:.625rem;font-weight:500;letter-spacing:.18em;
  text-transform:uppercase;color:var(--tinta-fina)}
.cabecalho-meta{font-family:var(--mono);font-size:.72rem;letter-spacing:.06em;
  color:var(--tinta-meia);display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:2.5rem}
.cabecalho-meta .divisor{color:var(--regua-forte)}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(8rem,1fr));
  gap:1px;background:var(--regua);border:1px solid var(--regua);border-radius:4px;
  overflow:hidden;margin-bottom:2rem}
.tile{background:var(--superficie);padding:1.05rem 1.15rem 1.15rem;position:relative}
.tile::after{content:"";position:absolute;top:0;left:0;width:100%;height:1px;opacity:.32;
  background:linear-gradient(90deg,transparent,var(--acento),transparent)}
.tile .valor{font-family:var(--mono);font-size:1.75rem;font-weight:700;
  letter-spacing:-.04em;font-variant-numeric:tabular-nums;line-height:1.1}
.tile .rotulo{font-size:.75rem;color:var(--tinta-meia);margin-top:.35rem}

.heroi{display:flex;align-items:baseline;gap:1.15rem;flex-wrap:wrap;margin-bottom:1rem}
.heroi .n{font-family:var(--mono);font-size:clamp(3rem,10vw,5rem);font-weight:700;
  letter-spacing:-.06em;line-height:1;font-variant-numeric:tabular-nums}
.heroi .n.baixa{color:var(--real-viva);text-shadow:0 0 44px rgba(255,122,99,.3)}
.heroi .n.media{color:var(--pendente-viva);text-shadow:0 0 44px rgba(255,194,77,.28)}
.heroi .n.alta{color:var(--ok-viva);text-shadow:0 0 44px rgba(78,224,192,.3)}
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
  border:1px solid var(--regua-forte);background:var(--superficie);cursor:default;
  transition:transform .15s}
.cel:hover{transform:translateY(-2px)}
.cel.falha{background:var(--real);border-color:var(--real-viva);color:#fff;font-weight:700}
.cel.passa{background:transparent;border-color:var(--ok);color:var(--ok-viva)}

.rolo{overflow-x:auto}
.correcoes{display:grid;grid-template-columns:repeat(auto-fit,minmax(17rem,1fr));
  gap:1rem;margin-top:1rem}
.correcao{border:1px solid var(--regua);border-radius:4px;background:var(--superficie);
  padding:1rem 1.1rem}
.correcao.incorrigivel{border-color:var(--real);box-shadow:inset 0 0 0 1px rgba(168,63,46,.3)}
.correcao.incorrigivel p b{color:var(--real-viva)}
.correcao>b{display:block;font-family:var(--mono);font-size:.72rem;
  color:var(--acento);margin-bottom:.7rem}
.correcao .par{display:flex;align-items:baseline;gap:.6rem;padding:.35rem 0;
  border-bottom:1px solid var(--regua)}
.correcao .par:last-of-type{border-bottom:none}
.correcao .par span{font-size:.8125rem;color:var(--tinta-meia)}
.correcao .par i{margin-left:auto;font-style:normal;font-family:var(--mono);
  font-size:1.15rem;font-weight:700;font-variant-numeric:tabular-nums}
.correcao .par i.ruim{color:var(--real-viva)}
.correcao .par i.bom{color:var(--ok-viva)}
.correcao p{font-size:.8125rem;line-height:1.55;color:var(--tinta-fina);
  margin:.7rem 0 0}
.matrizes{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));
  gap:1rem;margin-top:1rem}
.matriz{margin:0;border:1px solid var(--regua);border-radius:4px;
  background:var(--superficie);padding:.9rem 1rem 1rem}
.matriz figcaption{display:flex;align-items:baseline;gap:.5rem;margin-bottom:.6rem}
.matriz figcaption b{font-family:var(--mono);font-size:.8rem;color:var(--acento)}
.matriz figcaption span{font-size:.75rem;color:var(--tinta-fina)}
.matriz table{width:100%;margin:0;border-collapse:separate;border-spacing:2px}
.matriz th{font-family:var(--mono);font-size:.55rem;letter-spacing:.06em;
  text-transform:uppercase;color:var(--tinta-fina);border:none;padding:.2rem;
  text-align:center;font-weight:500;line-height:1.4}
.matriz tbody th{text-align:right;padding-right:.5rem}
.matriz th i{font-style:normal;color:var(--tinta-meia)}
.matriz td{text-align:center;padding:.6rem .3rem;border:none;border-radius:3px;
  font-family:var(--mono);font-size:1.25rem;font-weight:700;line-height:1.1;
  background:var(--papel);vertical-align:middle}
.matriz td span{display:block;font-size:.5rem;font-weight:500;letter-spacing:.1em;
  color:var(--tinta-fina);margin-top:.15rem}
.matriz td.ok{color:var(--tinta-meia)}
.matriz td.fp{color:var(--pendente-viva);background:rgba(195,134,24,.1)}
.matriz td.fn{color:var(--real-viva);background:rgba(168,63,46,.16);
  box-shadow:inset 0 0 0 1px var(--real)}
table{width:100%;border-collapse:collapse;margin-top:1rem;font-size:.875rem}
th{text-align:left;font-family:var(--mono);font-size:.625rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--tinta-fina);font-weight:500;
  padding:.45rem .5rem;border-bottom:1px solid var(--regua-forte)}
td{padding:.55rem .5rem;border-bottom:1px solid var(--regua);vertical-align:top}
td.mono{font-family:var(--mono);font-size:.75rem;font-variant-numeric:tabular-nums;
  color:var(--tinta-meia);white-space:nowrap}
.grav{display:inline-flex;align-items:center;gap:.4rem;white-space:nowrap}

details{margin-top:1rem;border:1px solid var(--regua);border-radius:4px;
  background:var(--superficie)}
summary{padding:.65rem .95rem;cursor:pointer;font-size:.875rem;color:var(--tinta-meia)}
summary:hover{color:var(--acento)}
details > div{padding:0 .95rem .95rem}
.achado{padding:.85rem 0;border-top:1px solid var(--regua);font-size:.9375rem}
.achado:first-child{border-top:none}
.achado .quem{font-family:var(--mono);font-size:.72rem;letter-spacing:.05em;
  color:var(--acento);display:block;margin-bottom:.25rem}

.alerta{border-left:2px solid var(--real-viva);background:var(--superficie);
  border-radius:0 4px 4px 0;padding:.95rem 1.15rem;margin:1.25rem 0;font-size:.9375rem}
.alerta.aviso{border-left-color:var(--pendente-viva)}
.alerta b{display:block;margin-bottom:.3rem;font-weight:500}
.rodape{margin-top:4rem;padding-top:1.5rem;border-top:1px solid var(--regua);
  font-size:.8125rem;color:var(--tinta-fina);line-height:1.7}
.tema{position:fixed;top:.9rem;right:1.1rem;width:2.1rem;height:2.1rem;display:grid;
  place-items:center;z-index:5;border:1px solid var(--regua-forte);border-radius:4px;
  background:var(--superficie);color:var(--tinta-meia);cursor:pointer;
  transition:transform .3s,border-color .3s,color .3s}
.tema:hover{transform:rotate(-25deg);border-color:var(--acento);color:var(--acento)}
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


def _secao_validacao(raiz: Path) -> str:
    """Bloco de TPR/TNR medidos contra rótulo humano.

    Só aparece quando analise_erros/validacao.json existe. Sem ele o relatório
    abre com a precisão *estimada* pelo auditor — que é ele próprio um juiz não
    medido. Esta seção é a única coisa aqui que não depende de nenhum LLM.
    """
    caminho = raiz / "analise_erros" / "validacao.json"
    if not caminho.exists():
        return (
            '<h2>Validação contra rótulo humano</h2>'
            '<p class="dica">Ainda não feita — nenhum <code>validacao.json</code>.</p>'
            '<div class="alerta aviso"><b>Os avaliadores não estão medidos</b>'
            'Sem TPR/TNR, cada avaliador é uma opinião automatizada. Rotule uma '
            'amostra em <code>anotar.html</code> e rode <code>validar_todos.py</code> '
            'para substituir a precisão estimada por precisão medida.</div>'
        )

    d = json.loads(caminho.read_text(encoding="utf-8"))
    meta = d.get("meta", 0.9)
    linhas = []
    for modo, v in sorted(d.get("modos", {}).items()):
        if not v.get("n"):
            linhas.append(
                f'<tr><td class="mono">{_e(modo)}</td><td>{_e(v["avaliador"])}</td>'
                f'<td class="mono">—</td><td class="mono">—</td>'
                f'<td class="mono">—</td><td class="mono">—</td>'
                f'<td>sem rótulo</td></tr>')
            continue
        tpr, tnr, f1 = v.get("tpr"), v.get("tnr"), v.get("f1")
        def _p(x):
            return "—" if x is None else f"{x:.0%}"
        def _c(x):
            if x is None:
                return "var(--tinta-fina)"
            return "var(--ok-viva)" if x >= meta else "var(--real-viva)"
        veredito = ("confiável" if (tpr or 0) >= meta and (tnr or 0) >= meta
                    else "não confiável ainda")
        linhas.append(
            f'<tr><td class="mono">{_e(modo)}</td><td>{_e(v["avaliador"])}</td>'
            f'<td class="mono">{v["n"]}</td>'
            f'<td class="mono" style="color:{_c(tpr)}">{_p(tpr)}</td>'
            f'<td class="mono" style="color:{_c(tnr)}">{_p(tnr)}</td>'
            f'<td class="mono" style="color:{_c(f1)}">{_p(f1)}</td>'
            f'<td>{veredito}</td></tr>')

    matrizes = "".join(
        _matriz(m, v) for m, v in sorted(d.get("modos", {}).items()) if v.get("n")
    )
    correcoes = "".join(
        _correcao(m, v, []) for m, v in sorted(d.get("modos", {}).items()) if v.get("n")
    )

    # O auditor é a peça que decide o que procede. Se ele estiver medido, o
    # aviso vem antes de tudo: a precisão que este relatório publica é opinião
    # dele, e o leitor precisa saber quanto essa opinião vale.
    aud = d.get("modos", {}).get("AUDITOR")
    alerta_auditor = ""
    if aud and aud.get("tpr") is not None:
        soma = aud["tpr"] + aud["tnr"]
        conc = (aud["vp"] + aud["vn"]) / aud["n"]
        alerta_auditor = (
            f'<div class="alerta"><b>O auditor foi medido — e não é confiável</b>'
            f'Ele concorda com o julgamento humano em <b>{conc:.0%}</b> dos casos '
            f'(n={aud["n"]}), com TPR {aud["tpr"]:.0%} e TNR {aud["tnr"]:.0%}. '
            f'A soma TPR+TNR é <b>{soma:.3f}</b>: um avaliador com essa soma '
            f'encostando em 1 acerta quase tanto quanto erra. '
            f'A correção de viés divide por (TPR+TNR−1) = {soma - 1:.3f} e, '
            f'aplicada à precisão que ele reporta, devolve um número negativo — '
            f'impossível. <b>Não dá para corrigir o que este auditor reporta.</b> '
            f'Toda taxa deste relatório que dependa da auditoria carrega essa '
            f'incerteza.</div>'
        )

    n = d.get("n_rotulos", 0)
    aviso = ""
    if n < 40:
        aviso = ('<div class="alerta aviso"><b>Amostra pequena</b>'
                 f'{n} traces rotulados. A meta é ~100, com 30 a 50 de cada classe. '
                 'Abaixo disso o intervalo de confiança do TPR/TNR é largo demais '
                 'para decidir alguma coisa — o número serve de sinal, não de prova.</div>')

    return (
        '<h2>Validação contra rótulo humano</h2>'
        + alerta_auditor +
        f'<p class="dica">Classe positiva é <b>falha</b>. TPR é quanto o avaliador '
        f'pega do que o humano marcou como falha; TNR é quanto ele deixa passar do '
        f'que o humano marcou como correto. O F1 é a média harmônica de '
        f'precisão e TPR — só sobe quando os dois sobem. Meta: {meta:.0%}.</p>'
        '<div class="rolo"><table><thead><tr><th>modo</th><th>avaliador</th>'
        '<th>n</th><th>TPR</th><th>TNR</th><th>F1</th><th>veredito</th></tr></thead>'
        f'<tbody>{"".join(linhas)}</tbody></table></div>{aviso}'
        + (f'<p class="dica" style="margin-top:2rem">Cada avaliador em quatro '
           f'caixas. A diagonal é acerto; fora dela, discordância. Neste domínio '
           f'os dois erros não custam o mesmo: um <b>falso positivo</b> gasta '
           f'tempo de revisão, um <b>falso negativo</b> deixa passar mel para um '
           f'bebê de 8 meses. Por isso o FN vem destacado.</p>'
           f'<div class="matrizes">{matrizes}</div>'
           + (f'<h2>Correção de viés</h2>'
              f'<p class="dica">Com TPR e TNR medidos, a taxa que o detector '
              f'reporta pode ser corrigida sem rotular a produção inteira — é a '
              f'razão prática de validar o avaliador.</p>'
              f'<div class="correcoes">{correcoes}</div>' if correcoes else "")
           if matrizes else "")
    )


def _correcao(modo: str, v: dict, brutos: list) -> str:
    """Taxa bruta versus taxa corrigida pelo viés do próprio avaliador.

    Rogan-Gladen: real = (observada + TNR - 1) / (TPR + TNR - 1). É a razão
    prática de medir o avaliador — com TPR e TNR na mão dá para corrigir o
    número que ele reporta, sem rotular a produção inteira.
    """
    tpr, tnr = v.get("tpr"), v.get("tnr")
    if tpr is None or tnr is None or (tpr + tnr - 1) <= 0:
        return ""
    n = v["n"]
    bruta = (v["vp"] + v["fp"]) / n if n else 0
    bruto_real = (bruta + tnr - 1) / (tpr + tnr - 1)

    # Correção fora de [0,1] não é erro de conta: é o avaliador dizendo que não
    # carrega informação suficiente. O denominador é (TPR + TNR - 1) — quando a
    # soma encosta em 1, ele acerta quase tanto quanto erra e não há verdade a
    # recuperar. Recortar para 0% aqui esconderia justamente isso.
    if not 0.0 <= bruto_real <= 1.0:
        return (
            f'<div class="correcao incorrigivel">'
            f'<b>{_e(modo)} · {_e(v["avaliador"])}</b>'
            f'<div class="par"><span>taxa bruta</span><i class="ruim">{bruta:.1%}</i></div>'
            f'<div class="par"><span>TPR + TNR</span>'
            f'<i class="ruim">{tpr + tnr:.3f}</i></div>'
            f'<p><b>Não corrigível.</b> A correção de viés divide por '
            f'(TPR + TNR − 1) = {tpr + tnr - 1:.3f} e devolve {bruto_real:+.0%}, '
            f'que é impossível. Um avaliador com a soma encostando em 1 acerta '
            f'quase tanto quanto erra — não há verdade a recuperar do que ele '
            f'reporta.</p></div>'
        )

    real = bruto_real
    erro = (bruta - real) / real if real else 0
    return (
        f'<div class="correcao">'
        f'<b>{_e(modo)} · {_e(v["avaliador"])}</b>'
        f'<div class="par"><span>taxa bruta do detector</span>'
        f'<i class="ruim">{bruta:.1%}</i></div>'
        f'<div class="par"><span>corrigida pelo TPR/TNR</span>'
        f'<i class="bom">{real:.1%}</i></div>'
        f'<p>O número bruto {"superestima" if erro > 0 else "subestima"} em '
        f'<b>{abs(erro):.0%}</b>. Reportar a taxa crua seria reportar os bugs do '
        f'detector junto com o comportamento do bot.</p></div>'
    )


def _matriz(modo: str, v: dict) -> str:
    """Matriz de confusão de um modo. FN destacado: é o erro que dói aqui."""
    return f"""
<figure class="matriz">
  <figcaption><b>{_e(modo)}</b> <span>{_e(v["avaliador"])}</span></figcaption>
  <table>
    <thead><tr><th></th>
      <th>humano<br><i>falha</i></th><th>humano<br><i>passa</i></th></tr></thead>
    <tbody>
      <tr><th>avaliador <i>falha</i></th>
        <td class="ok">{v["vp"]}<span>VP</span></td>
        <td class="fp">{v["fp"]}<span>FP</span></td></tr>
      <tr><th>avaliador <i>passa</i></th>
        <td class="fn">{v["fn"]}<span>FN</span></td>
        <td class="ok">{v["vn"]}<span>VN</span></td></tr>
    </tbody>
  </table>
</figure>"""


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
        p.append(_secao_validacao(Path(__file__).resolve().parent))
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

    # Rodada sem LLM: as seções acima dependem da auditoria, mas achado por
    # avaliador e resultado por trace saem direto dos avaliadores de código.
    # Sem isto o painel da rodada grátis fica só com o cabeçalho.
    if not auditados and brutos:
        por_av = Counter(a["avaliador"] for a in brutos)
        criticas = Counter(a["avaliador"] for a in brutos if a.get("gravidade") == "critica")
        maximo = max(por_av.values())
        linhas = [
            (nome, [(criticas.get(nome, 0), "var(--real)", "crítica"),
                    (n - criticas.get(nome, 0), "var(--pendente)", "não crítica")],
             f'{criticas.get(nome, 0)}/{n}')
            for nome, n in por_av.most_common()
        ]
        p.append('<h2>Achados por avaliador</h2>')
        p.append('<p class="dica">Contagem <b>bruta</b>, sem auditoria. Vermelho é '
                 'gravidade crítica. Estes números descrevem o que os detectores '
                 'apontaram — não necessariamente o que o bot fez.</p>')
        p.append(_barras_empilhadas(linhas, maximo))

        com_falha = {a["trace_id"] for a in brutos}
        p.append('<h2>Resultado por trace</h2>')
        p.append('<p class="dica">Uma célula por trace. Vermelha, ao menos um '
                 'detector apontou falha.</p><div class="grade">')
        for t in traces:
            marca = "falha" if t["id"] in com_falha else "passa"
            p.append(f'<div class="cel {marca}" title="{_e(t["id"])}">'
                     f'{_e(str(t["id"])[-3:])}</div>')
        p.append('</div>')
        p.append(f'<p class="dica" style="margin-top:.8rem">'
                 f'<b>{len(com_falha)}</b> de <b>{len(traces)}</b> traces com ao '
                 f'menos um achado — <b>{len(com_falha)/max(1,len(traces)):.0%}</b> '
                 f'bruto.</p>')

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
