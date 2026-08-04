"""
Utilitários de casamento de texto em português.

Três armadilhas que este módulo existe para resolver, e que derrubam a maioria
das primeiras versões de um avaliador de código em português:

1. ACENTO. "açúcar" e "acucar" precisam casar. Normalizamos preservando o
   comprimento da string, para que os offsets continuem apontando para o texto
   original na hora de extrair a evidência.

2. FRONTEIRA DE PALAVRA. `"mel" in texto` acusa violação em "melão",
   "melancia" e "caramelo". `"sal" in texto` acusa em "salada", "salsinha" e
   "salmão". Casamos sempre com \\b.

3. NEGAÇÃO. O bot dizendo "não use mel, é risco de botulismo" é o
   comportamento CORRETO, e um detector ingênuo marca isso como falha. Pior:
   quanto melhor o bot fica, mais falsos positivos o detector gera. Aqui a
   negação é detectada em ambas as direções, com cancelamento por adversativa.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

# --- Normalização -----------------------------------------------------------

def normalizar(texto: str) -> str:
    """Minúsculas e sem acento, preservando o comprimento caractere a caractere.

    Preservar o comprimento é o que permite usar os offsets do texto
    normalizado para recortar evidência do texto original.
    """
    saida = []
    for ch in texto:
        decomposto = unicodedata.normalize("NFD", ch)
        base = "".join(c for c in decomposto if not unicodedata.combining(c))
        saida.append(base.lower() if len(base) == 1 else ch.lower())
    return "".join(saida)


def _regex_termo(termo: str) -> re.Pattern:
    """Compila um termo (possivelmente multipalavra) com fronteira e plural."""
    palavras = [re.escape(p) for p in normalizar(termo).split()]
    corpo = r"\s+".join(palavras)
    return re.compile(rf"\b{corpo}(?:e?s)?\b")


_CACHE: dict[str, re.Pattern] = {}


def compilar(termo: str) -> re.Pattern:
    if termo not in _CACHE:
        _CACHE[termo] = _regex_termo(termo)
    return _CACHE[termo]


# --- Sentenças --------------------------------------------------------------

_FIM_SENTENCA = re.compile(r"[.!?\n;]+")


def limites_sentenca(texto_norm: str, pos: int) -> tuple[int, int]:
    """Início e fim da sentença que contém `pos`."""
    inicio = 0
    fim = len(texto_norm)
    for m in _FIM_SENTENCA.finditer(texto_norm):
        if m.end() <= pos:
            inicio = m.end()
        elif m.start() >= pos:
            fim = m.start()
            break
    return inicio, fim


# --- Negação ----------------------------------------------------------------

NEGACOES_ANTES = [
    "nao", "nunca", "jamais", "evite", "evitar", "sem", "nada de", "nem",
    "proibido", "proibida", "contraindicado", "contraindicada", "livre de",
    "zero", "dispense", "exceto", "fuja de", "longe de", "abolir", "elimine",
    "nao adicione", "nao use", "nao ofereca", "nao de", "deixe de fora",
    "substitua o", "substitua a", "no lugar do", "no lugar da", "em vez de",
    "ao inves de",
]

PROIBICOES_DEPOIS = [
    "contraindicad", "proibid", "nao pode", "nao deve", "faz mal", "e perigos",
    "deve ser evitad", "nao e recomendad", "nao e indicad", "so apos", "so depois",
    "apenas apos", "risco de", "nao antes", "somente apos", "e vetad", "e proibid",
    "nunca", "jamais", "evite", "nao ofereca",
]

ADVERSATIVAS = ["mas", "porem", "contudo", "entretanto", "no entanto", "todavia", "ja o", "ja a"]

JANELA_ANTES = 55
JANELA_DEPOIS = 70


def mencao_segura(texto_norm: str, ini: int, fim: int) -> bool:
    """True quando o termo aparece dentro de uma advertência, não de uma sugestão.

    Regra: procura pista de negação ANTES (na mesma sentença, dentro da janela)
    ou pista de proibição DEPOIS. Uma adversativa entre a negação e o termo
    cancela a negação — em "não use açúcar, mas pode adoçar com mel", o "mel"
    continua sendo uma sugestão.
    """
    s_ini, s_fim = limites_sentenca(texto_norm, ini)
    antes = texto_norm[max(s_ini, ini - JANELA_ANTES):ini]
    depois = texto_norm[fim:min(s_fim, fim + JANELA_DEPOIS)]

    for pista in NEGACOES_ANTES:
        m = None
        for m in compilar(pista).finditer(antes):
            pass
        if m is None:
            continue
        # a negação vale, a menos que uma adversativa apareça entre ela e o termo
        entre = antes[m.end():]
        if any(compilar(adv).search(entre) for adv in ADVERSATIVAS):
            continue
        return True

    for pista in PROIBICOES_DEPOIS:
        if re.search(rf"\b{re.escape(pista)}", depois):
            return True

    return False


# --- Busca ------------------------------------------------------------------

@dataclass
class Ocorrencia:
    termo: str
    inicio: int
    fim: int
    trecho: str
    segura: bool = False


def buscar(texto: str, termos: Iterable[str], checar_negacao: bool = True) -> list[Ocorrencia]:
    """Todas as ocorrências dos termos, com o recorte de evidência do original."""
    norm = normalizar(texto)
    achados: list[Ocorrencia] = []
    vistos: set[tuple[int, int]] = set()

    for termo in termos:
        for m in compilar(termo).finditer(norm):
            chave = (m.start(), m.end())
            if chave in vistos:
                continue
            vistos.add(chave)
            trecho = texto[max(0, m.start() - 45):min(len(texto), m.end() + 45)].strip()
            achados.append(Ocorrencia(
                termo=termo,
                inicio=m.start(),
                fim=m.end(),
                trecho=f"…{trecho}…",
                segura=mencao_segura(norm, m.start(), m.end()) if checar_negacao else False,
            ))

    return sorted(achados, key=lambda o: o.inicio)


def violacoes(texto: str, termos: Iterable[str]) -> list[Ocorrencia]:
    """Só as ocorrências que NÃO estão sob negação — as que de fato acusam."""
    return [o for o in buscar(texto, termos) if not o.segura]


def contem(texto: str, termos: Iterable[str]) -> bool:
    norm = normalizar(texto)
    return any(compilar(t).search(norm) for t in termos)


def proximo(texto: str, ocorrencia: Ocorrencia, termos: Iterable[str], janela: int = 260) -> bool:
    """True se algum dos termos aparece perto da ocorrência.

    Usado para a lógica de engasgo: a instrução de corte seguro pode estar na
    linha seguinte, não necessariamente na mesma frase.
    """
    norm = normalizar(texto)
    ini = max(0, ocorrencia.inicio - janela)
    fim = min(len(norm), ocorrencia.fim + janela)
    janela_txt = norm[ini:fim]
    return any(compilar(t).search(janela_txt) for t in termos)
