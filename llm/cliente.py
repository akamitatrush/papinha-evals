"""
Cliente da API da Anthropic para o pipeline automatizado.

Centraliza o que se repete em toda chamada: retry, concorrência controlada,
saída estruturada validada e contabilidade de tokens. Nenhum outro módulo
fala com a API diretamente.
"""

from __future__ import annotations

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Iterable, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

MODELO_PADRAO = "claude-opus-5"

# Requisições concorrentes. Baixo de propósito: um lote de 33 traces × 4 juízes
# é curto, e estourar o rate limit para economizar 40 segundos não compensa.
CONCORRENCIA_PADRAO = 4

# `max_tokens` limita PENSAMENTO + resposta juntos no Opus 5, onde o pensamento
# é ligado por padrão. Um teto apertado dimensionado só para o JSON de saída
# trunca a resposta no meio. Daí a folga.
MAX_TOKENS = 16000

# `output_config.effort` não existe em todos os modelos: Haiku 4.5 e Sonnet 4.5
# rejeitam o parâmetro com 400. Enviar mesmo assim derruba o lote inteiro —
# foi o que aconteceu no primeiro teste de fumaça (15 erros, zero chamadas úteis).
SEM_ESFORCO = ("claude-haiku", "claude-sonnet-4-5", "claude-3")


def suporta_esforco(modelo: str) -> bool:
    return not modelo.startswith(SEM_ESFORCO)


@dataclass
class Uso:
    """Contabilidade acumulada, para o relatório informar o custo real."""
    entrada: int = 0
    saida: int = 0
    cache_leitura: int = 0
    chamadas: int = 0
    erros: int = 0
    _trava: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def somar(self, usage) -> None:
        with self._trava:
            self.entrada += getattr(usage, "input_tokens", 0) or 0
            self.saida += getattr(usage, "output_tokens", 0) or 0
            self.cache_leitura += getattr(usage, "cache_read_input_tokens", 0) or 0
            self.chamadas += 1

    def registrar_erro(self) -> None:
        with self._trava:
            self.erros += 1

    def custo_estimado(self, modelo: str) -> float:
        """USD aproximado. Preços de tabela do Opus 5; outros modelos são estimativa."""
        precos = {
            "claude-opus-5": (5.0, 25.0),
            "claude-sonnet-5": (3.0, 15.0),
            "claude-haiku-4-5": (1.0, 5.0),
        }
        p_ent, p_sai = precos.get(modelo, (5.0, 25.0))
        return (self.entrada / 1e6) * p_ent + (self.saida / 1e6) * p_sai


class ClienteLLM:
    def __init__(self, modelo: str = MODELO_PADRAO, esforco: str = "medium",
                 concorrencia: int = CONCORRENCIA_PADRAO):
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise SystemExit(
                "ANTHROPIC_API_KEY não definida.\n"
                "  export ANTHROPIC_API_KEY=sk-ant-...\n"
                "Crie a chave em https://platform.claude.com/settings/keys"
            )
        # max_retries do SDK já cobre 429 e 5xx com backoff exponencial.
        self.cliente = anthropic.Anthropic(max_retries=4)
        self.modelo = modelo
        self.esforco = esforco
        self.concorrencia = concorrencia
        self.uso = Uso()

    def estruturado(self, sistema: str, usuario: str, formato: type[T]) -> T | None:
        """Uma chamada com saída validada contra o schema. None em caso de erro.

        Usa saída estruturada em vez de pedir JSON no prompt e torcer: o schema
        é imposto na geração, então não há parsing defensivo nem retry por
        "o modelo respondeu com cerca de código".
        """
        extras = {}
        if suporta_esforco(self.modelo):
            extras["output_config"] = {"effort": self.esforco}
        try:
            resposta = self.cliente.messages.parse(
                model=self.modelo,
                max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": sistema,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": usuario}],
                output_format=formato,
                **extras,
            )
            self.uso.somar(resposta.usage)
            if resposta.stop_reason == "refusal":
                return None
            return resposta.parsed_output
        except anthropic.RateLimitError:
            self.uso.registrar_erro()
            print("  rate limit persistente após retries", file=sys.stderr)
        except anthropic.APIStatusError as e:
            self.uso.registrar_erro()
            print(f"  erro da API ({e.status_code}): {e.message}", file=sys.stderr)
        except anthropic.APIConnectionError:
            self.uso.registrar_erro()
            print("  falha de conexão", file=sys.stderr)
        except Exception as e:  # validação do schema, etc.
            self.uso.registrar_erro()
            print(f"  {type(e).__name__}: {str(e)[:140]}", file=sys.stderr)
        return None

    def mapear(self, itens: Iterable, fn: Callable, rotulo: str = "") -> list:
        """Aplica fn sobre os itens em paralelo, preservando a ordem."""
        itens = list(itens)
        if not itens:
            return []
        feitos = [0]
        trava = threading.Lock()

        def envolver(item):
            r = fn(item)
            with trava:
                feitos[0] += 1
                if rotulo:
                    print(f"\r  {rotulo}: {feitos[0]}/{len(itens)}", end="", flush=True)
            return r

        with ThreadPoolExecutor(max_workers=self.concorrencia) as pool:
            resultados = list(pool.map(envolver, itens))
        if rotulo:
            print()
        return resultados
