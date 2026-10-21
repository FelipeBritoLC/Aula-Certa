"""
Apoio aos casos de teste funcionais (especificação em docs/testes/).

Este módulo não depende de fixtures globais (conftest.py) de propósito:
os casos da Sprint 01 também são executados contra o código da versão
final daquela sprint, que ainda não tinha essas fixtures.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from agenda.models import Aula
from alunos.models import Aluno
from financeiro.models import Mensalidade

SENHA = "senha-de-teste-123"
CONTEUDO_VALIDO = "Frações: soma e subtração com denominadores diferentes, exercícios 1 a 12."


@pytest.fixture(autouse=True)
def hasher_rapido(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def professor(db):
    return User.objects.create_user(username="professor", password=SENHA)


@pytest.fixture
def outro_professor(db):
    return User.objects.create_user(username="outro", password=SENHA)


@pytest.fixture
def navegador(client, professor):
    """Cliente HTTP autenticado pelo formulário de login, como um usuário real."""
    client.post("/login/", {"username": "professor", "password": SENHA})
    return client


def criar_aluno(professor, nome="Maria Silva", cpf="12345678901", **extra):
    aluno = Aluno(professor=professor, nome=nome, cpf=cpf, telefone="83999999999", **extra)
    aluno.full_clean()
    aluno.save()
    return aluno


def horario(dias=2, hora=14, minuto=0):
    return (timezone.localtime() + timedelta(days=dias)).replace(
        hour=hora, minute=minuto, second=0, microsecond=0
    )


def criar_aula(professor, aluno, inicio=None, **extra):
    aula = Aula(professor=professor, aluno=aluno, data_hora_inicio=inicio or horario(), **extra)
    aula.full_clean()
    aula.save()
    return aula


def mover_para(aula, inicio):
    """Leva a aula para outra data sem passar pela validação (ex.: passado)."""
    Aula.objects.filter(pk=aula.pk).update(data_hora_inicio=inicio)
    aula.refresh_from_db()
    return aula


def criar_mensalidade(aluno, valor="300.00", vencimento_em_dias=10, competencia=None):
    hoje = timezone.localdate()
    return Mensalidade.objects.create(
        aluno=aluno,
        competencia=competencia or hoje.replace(day=1),
        valor_total=Decimal(valor),
        data_vencimento=hoje + timedelta(days=vencimento_em_dias),
    )


def form_agendamento(aluno, inicio, duracao=60):
    return {
        "aluno": aluno.pk,
        "data_hora_inicio": inicio.strftime("%Y-%m-%dT%H:%M"),
        "duracao_minutos": duracao,
        "modalidade": "PRESENCIAL",
        "local": "",
    }


def form_aluno(**extra):
    dados = {"nome": "Maria Silva", "cpf": "123.456.789-01", "telefone": "83999999999", "situacao": "ATIVO"}
    dados.update(extra)
    return dados
