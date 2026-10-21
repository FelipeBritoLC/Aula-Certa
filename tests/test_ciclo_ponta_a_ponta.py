"""
US-30358 / Task 32589 — ciclo de teste funcional ponta a ponta (versão
automatizada do roteiro em docs/testes/ciclo-funcional-sprint02.md).

Percorre o sistema como o professor faria, só pelas telas (cliente HTTP do
Django, com login real), encadeando as user stories entregues nas Sprints
01 e 02. Cada passo corresponde a um passo numerado do roteiro manual.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from agenda.models import Aula
from alunos.models import Aluno
from financeiro.models import Mensalidade

CONTEUDO = "Frações: soma e subtração com denominadores diferentes, exercícios 1 a 12."


def anos_atras(anos):
    hoje = timezone.localdate()
    try:
        return hoje.replace(year=hoje.year - anos)
    except ValueError:
        return hoje.replace(year=hoje.year - anos, day=28)


@pytest.mark.django_db
def test_ciclo_completo_do_professor(client):
    hoje = timezone.localdate()
    User.objects.create_superuser(username="professor", password="senha-forte-123", email="")

    # Passo 1 — login
    resposta = client.post(reverse("login"), {"username": "professor", "password": "senha-forte-123"})
    assert resposta.status_code == 302
    assert client.get(reverse("dashboard:index")).status_code == 200

    # Passo 2 — cadastrar aluno menor de idade (US 30321 + 30322):
    # sem responsável é recusado; com responsável é aceito.
    aluno_post = {
        "nome": "Pedro Henrique Lima",
        "cpf": "529.982.247-25",
        "telefone": "83991112222",
        "data_nascimento": anos_atras(13).isoformat(),
        "disciplina": "Matemática",
        "serie_nivel": "8º ano",
        "escola": "Escola Municipal Centro",
        "situacao": "ATIVO",
    }
    resposta = client.post(reverse("alunos:cadastrar"), aluno_post)
    assert resposta.status_code == 200
    assert "o aluno é menor de idade" in resposta.content.decode()

    aluno_post.update(responsavel_nome="Ana Lima", responsavel_telefone="83993334444", responsavel_parentesco="Mãe")
    resposta = client.post(reverse("alunos:cadastrar"), aluno_post)
    assert resposta.status_code == 302
    aluno = Aluno.objects.get()

    # Passo 3 — consultar alunos (US 30323) e abrir a ficha (US 30322)
    lista = client.get(reverse("alunos:listar"), {"nome": "pedro"})
    assert [a.pk for a in lista.context["page_obj"]] == [aluno.pk]
    ficha = client.get(reverse("alunos:detalhe", args=[aluno.pk])).content.decode()
    assert "Escola Municipal Centro" in ficha and "Ana Lima" in ficha

    # Passo 4 — agendar aula (US 30332) e ver o conflito de horário barrado
    inicio = (timezone.localtime() + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
    agendamento = {
        "aluno": aluno.pk,
        "data_hora_inicio": inicio.strftime("%Y-%m-%dT%H:%M"),
        "duracao_minutos": 60,
        "modalidade": "PRESENCIAL",
        "local": "Casa do aluno",
    }
    assert client.post(reverse("agenda:criar"), agendamento).status_code == 302
    aula = Aula.objects.get()
    conflito = client.post(reverse("agenda:criar"), agendamento)
    assert "Conflito de horário" in conflito.content.decode()

    # Passo 5 — editar a aula agendada (US 30333)
    novo_inicio = inicio.replace(hour=16)
    resposta = client.post(
        reverse("agenda:editar", args=[aula.pk]),
        {
            "data_hora_inicio": novo_inicio.strftime("%Y-%m-%dT%H:%M"),
            "duracao_minutos": 90,
            "modalidade": "ONLINE",
            "local": "Google Meet",
        },
    )
    assert resposta.status_code == 302
    aula.refresh_from_db()
    assert (aula.modalidade, aula.duracao_minutos) == ("ONLINE", 90)

    # Passo 6 — consultar a agenda na visão semanal (US 30337)
    agenda = client.get(reverse("agenda:listar"), {"visao": "semana", "data": novo_inicio.date().isoformat()})
    assert agenda.status_code == 200
    assert "Pedro Henrique Lima" in agenda.content.decode()

    # Passo 7 — registrar a aula como realizada, com detalhes (US 30338 + 30339)
    resposta = client.post(
        reverse("agenda:registrar", args=[aula.pk]),
        {
            "conteudo_trabalhado": CONTEUDO,
            "observacoes": "Aluno participativo.",
            "material_utilizado": "Lista de exercícios 2",
            "avaliacao_desempenho": "BOM",
            "recomendacoes": "Revisar MMC antes da próxima aula.",
        },
    )
    assert resposta.status_code == 302
    aula.refresh_from_db()
    assert aula.status == Aula.Status.REALIZADA

    # Passo 8 — completar os detalhes depois e conferir o histórico na ficha
    client.post(
        reverse("agenda:detalhes", args=[aula.pk]),
        {
            "material_utilizado": "Lista de exercícios 2 e jogo de frações",
            "avaliacao_desempenho": "OTIMO",
            "recomendacoes": "Revisar MMC antes da próxima aula.",
        },
    )
    ficha = client.get(reverse("alunos:detalhe", args=[aluno.pk])).content.decode()
    assert "Desempenho: Ótimo" in ficha
    assert "jogo de frações" in ficha

    # Passo 9 — lançar mensalidades pelo Django Admin (a tela própria é Sprint 03):
    # a do mês corrente e uma antiga, vencida há 20 dias.
    for competencia, valor, vencimento in [
        (hoje.replace(day=1), "400.00", hoje + timedelta(days=10)),
        ((hoje.replace(day=1) - timedelta(days=1)).replace(day=1), "350.00", hoje - timedelta(days=20)),
    ]:
        resposta = client.post(
            "/admin/financeiro/mensalidade/add/",
            {
                "aluno": aluno.pk,
                "competencia": competencia.isoformat(),
                "valor_total": valor,
                "data_vencimento": vencimento.isoformat(),
                "status": "PENDENTE",
                "observacoes": "",
                "_save": "Salvar",
            },
        )
        assert resposta.status_code == 302, resposta.content.decode()[:500]
    atual = Mensalidade.objects.get(competencia=hoje.replace(day=1))
    antiga = Mensalidade.objects.exclude(pk=atual.pk).get()

    # Passo 10 — inadimplência (US 30350): a mensalidade vencida aparece
    inadimplentes = client.get(reverse("financeiro:inadimplentes"))
    assert [i["aluno"].pk for i in inadimplentes.context["inadimplentes"]] == [aluno.pk]

    # Passo 11 — registrar pagamentos (US 30344): parcial e depois o restante
    client.post(reverse("financeiro:pagar", args=[atual.pk]), {"valor_pago": "150.00", "forma_pagamento": "PIX"})
    atual.refresh_from_db()
    assert atual.status == Mensalidade.Status.PENDENTE and atual.saldo == Decimal("250.00")
    client.post(reverse("financeiro:pagar", args=[atual.pk]), {"valor_pago": "250.00", "forma_pagamento": "PIX"})
    client.post(reverse("financeiro:pagar", args=[antiga.pk]), {"valor_pago": "350.00", "forma_pagamento": "DINHEIRO"})
    atual.refresh_from_db()
    antiga.refresh_from_db()
    assert atual.status == antiga.status == Mensalidade.Status.PAGO
    assert client.get(reverse("financeiro:inadimplentes")).context["inadimplentes"] == []

    # Passo 12 — painel de indicadores (US 30355) reflete o mês quitado
    painel = client.get(reverse("dashboard:index")).context
    assert painel["total_alunos_ativos"] == 1
    assert painel["faturamento_gerado"] == Decimal("400.00")
    assert painel["valor_pendente"] == 0
    assert painel["total_inadimplentes"] == 0

    # Passo 13 — inativar o aluno (US 30325): aviso e bloqueio de novos agendamentos
    edicao = client.get(reverse("alunos:editar", args=[aluno.pk])).context["form"]
    dados_edicao = {
        campo: ("" if valor is None else valor) for campo, valor in edicao.initial.items()
        if campo in edicao.fields
    }
    dados_edicao["data_nascimento"] = aluno.data_nascimento.isoformat()
    dados_edicao["situacao"] = "INATIVO"
    resposta = client.post(reverse("alunos:editar", args=[aluno.pk]), dados_edicao, follow=True)
    assert "Novos agendamentos para este aluno estão bloqueados." in resposta.content.decode()
    form_agendamento = client.get(reverse("agenda:criar")).context["form"]
    assert aluno not in form_agendamento.fields["aluno"].queryset

    # Passo 14 — logout
    client.post(reverse("logout"))
    assert client.get(reverse("dashboard:index")).status_code == 302
