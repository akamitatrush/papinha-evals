"""Avaliadores do Papinha Fácil: determinísticos (codigo.py) e juízes LLM (juizes/)."""

from .codigo import AVALIADORES, Achado, avaliar, carregar_regras

__all__ = ["AVALIADORES", "Achado", "avaliar", "carregar_regras"]
