"""Testes do conversor de export do Telegram Desktop."""

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from coleta.importar_telegram import (  # noqa: E402
    casar_consulta, idade_do_texto, parear, texto_da_mensagem,
)

BOT = "Papinha Fácil"


def msg(autor, texto, tipo="message", data="2026-08-04T10:00:00"):
    return {"type": tipo, "from": autor, "text": texto, "date": data}


# --- parsing do formato de export ------------------------------------------

def test_texto_pode_ser_lista_de_entidades():
    """O Telegram quebra texto com links/negrito em lista de trechos."""
    m = {"text": ["Veja ", {"type": "bold", "text": "mel"}, " aqui"]}
    assert texto_da_mensagem(m) == "Veja mel aqui"


def test_pareamento_basico():
    pares = parear([
        msg("Sérgio", "Posso dar mel?"),
        msg(BOT, "Não! Mel é contraindicado antes de 1 ano."),
        msg("Sérgio", "E uva?"),
        msg(BOT, "Pode, cortada em quatro."),
    ], BOT)
    assert len(pares) == 2
    assert pares[0]["pergunta"] == "Posso dar mel?"
    assert "contraindicado" in pares[0]["respostas"][0]


def test_resposta_em_varias_mensagens_agrupa():
    pares = parear([
        msg("Sérgio", "Receita de almoço?"),
        msg(BOT, "Claro! Aqui vai:"),
        msg(BOT, "Ingredientes: abóbora e carne moída."),
    ], BOT)
    assert len(pares) == 1
    assert len(pares[0]["respostas"]) == 2


def test_mensagem_de_servico_ignorada():
    pares = parear([
        msg("Sérgio", "", tipo="service"),
        msg("Sérgio", "Oi"),
        msg(BOT, "Olá!"),
    ], BOT)
    assert len(pares) == 1


def test_pergunta_sem_resposta_descartada():
    pares = parear([
        msg("Sérgio", "Primeira sem resposta... digo, segunda vem já"),
        msg("Sérgio", "Oi de novo"),
        msg(BOT, "Olá!"),
    ], BOT)
    # a 1ª vira turno extra da conversa; só o par com resposta sai
    assert len(pares) == 1
    assert pares[0]["respostas"] == ["Olá!"]


# --- casamento com consultas ------------------------------------------------

CONSULTAS = [
    {"id": "q050", "idade_meses": 8, "texto": "Posso adoçar a papinha do bebê de 8 meses com mel?"},
    {"id": "q041", "idade_meses": 10, "texto": "Posso dar uva pro meu bebê de 10 meses?"},
]


def test_casamento_exato_ignora_acento_e_caixa():
    c = casar_consulta("posso adocar a papinha do bebe de 8 meses com MEL?", CONSULTAS)
    assert c and c["id"] == "q050"


def test_casamento_fuzzy_com_edicao_leve():
    c = casar_consulta("Posso dar uva para o meu bebê de 10 meses?", CONSULTAS)
    assert c and c["id"] == "q041"


def test_texto_diferente_nao_casa():
    assert casar_consulta("Qual a capital da Austrália?", CONSULTAS) is None


def test_idade_extraida_por_regex():
    assert idade_do_texto("meu bebê de 7 meses adora fruta") == 7
    assert idade_do_texto("tenho uma criança de 1 ano e meio") == 18
    assert idade_do_texto("quero uma receita") is None


# --- ponta a ponta via CLI ---------------------------------------------------

def test_cli_ponta_a_ponta(tmp_path):
    export = {
        "name": BOT,
        "type": "personal_chat",
        "messages": [
            msg("Sérgio", "Posso adoçar a papinha do bebê de 8 meses com mel?"),
            msg(BOT, "Claro! Meia colher de mel fica ótimo."),
            msg("Sérgio", "Meu filho de 5 meses pode chupar manga?"),
            msg(BOT, "Aos 5 meses ainda não — espere os 6 meses."),
        ],
    }
    arq = tmp_path / "result.json"
    arq.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
    saida = tmp_path / "traces.jsonl"

    r = subprocess.run(
        [sys.executable, str(RAIZ / "coleta" / "importar_telegram.py"),
         str(arq), "--saida", str(saida)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    traces = [json.loads(l) for l in saida.read_text(encoding="utf-8").splitlines()]
    assert len(traces) == 2
    assert traces[0]["query_id"] == "q050"          # casou com o kit
    assert traces[0]["idade_meses"] == 8            # herdou a idade da consulta
    assert traces[0]["origem"] == "real"
    assert traces[1]["query_id"] is None            # avulsa, fora do kit
    assert traces[1]["idade_meses"] == 5            # idade extraída por regex
    assert "2 traces" in r.stdout and "1 casados" in r.stdout


def test_cli_recusa_sobrescrever(tmp_path):
    export = {"name": BOT, "messages": [msg("S", "Oi"), msg(BOT, "Olá")]}
    arq = tmp_path / "result.json"
    arq.write_text(json.dumps(export), encoding="utf-8")
    saida = tmp_path / "traces.jsonl"
    saida.write_text('{"id":"t001"}\n', encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(RAIZ / "coleta" / "importar_telegram.py"),
         str(arq), "--saida", str(saida)],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert "anexar" in r.stderr


def test_cli_anexar_continua_ids(tmp_path):
    export = {"name": BOT, "messages": [msg("S", "Oi"), msg(BOT, "Olá")]}
    arq = tmp_path / "result.json"
    arq.write_text(json.dumps(export), encoding="utf-8")
    saida = tmp_path / "traces.jsonl"
    saida.write_text('{"id":"t007","query_id":null}\n', encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(RAIZ / "coleta" / "importar_telegram.py"),
         str(arq), "--saida", str(saida), "--anexar"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    linhas = [json.loads(l) for l in saida.read_text(encoding="utf-8").splitlines()]
    assert linhas[-1]["id"] == "t008"
