"""
US-30358 / Task 32587 — testes funcionais das telas do módulo Financeiro.

Cobre os caminhos das views que os testes de regra (financeiro/tests.py)
não exercitavam: listagem, registro de pagamento pela tela, isolamento
entre professores e o filtro de dias da inadimplência.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from financeiro.models import Mensalidade, Pagamento


def criar_aluno(professor, nome="Maria Silva", cpf="12345678901"):
    aluno = Aluno(professor=professor, nome=nome, cpf=cpf, telefone="83999999999")
    aluno.full_clean()
    aluno.save()
    return aluno


def criar_mensalidade(aluno, valor="300.00", vencimento_dias=10):
    hoje = timezone.localdate()
    return Mensalidade.objects.create(
        aluno=aluno,
        competencia=hoje.replace(day=1),
        valor_total=Decimal(valor),
        data_vencimento=hoje + timedelta(days=vencimento_dias),
    )


class TestListarMensalidades:
    def test_lista_apenas_mensalidades_do_professor(self, logado, professor, outro_professor):
        criar_mensalidade(criar_aluno(professor, nome="Aluno Meu"))
        criar_mensalidade(criar_aluno(outro_professor, nome="Aluno Alheio"))
        resposta = logado.get(reverse("financeiro:mensalidades"))
        assert resposta.status_code == 200
        nomes = [m.aluno.nome for m in resposta.context["mensalidades"]]
        assert nomes == ["Aluno Meu"]

    def test_exige_login(self, client, db):
        resposta = client.get(reverse("financeiro:mensalidades"))
        assert resposta.status_code == 302
        assert "/login/" in resposta.url


class TestRegistrarPagamentoPelaTela:
    def test_get_sugere_o_saldo_da_mensalidade(self, logado, professor):
        mensalidade = criar_mensalidade(criar_aluno(professor))
        Pagamento.registrar(mensalidade, Decimal("100.00"), "PIX")
        resposta = logado.get(reverse("financeiro:pagar", args=[mensalidade.pk]))
        assert resposta.status_code == 200
        assert resposta.context["form"].initial["valor_pago"] == Decimal("200.00")

    def test_pagamento_total_quita_a_mensalidade(self, logado, professor):
        mensalidade = criar_mensalidade(criar_aluno(professor))
        resposta = logado.post(
            reverse("financeiro:pagar", args=[mensalidade.pk]),
            {"valor_pago": "300.00", "forma_pagamento": "PIX", "data_pagamento": "", "observacoes": ""},
        )
        assert resposta.status_code == 302
        assert resposta.url == reverse("financeiro:mensalidades")
        mensalidade.refresh_from_db()
        assert mensalidade.status == Mensalidade.Status.PAGO

    def test_pagamento_parcial_mantem_pendente(self, logado, professor):
        mensalidade = criar_mensalidade(criar_aluno(professor))
        logado.post(
            reverse("financeiro:pagar", args=[mensalidade.pk]),
            {"valor_pago": "120.50", "forma_pagamento": "DINHEIRO"},
        )
        mensalidade.refresh_from_db()
        assert mensalidade.status == Mensalidade.Status.PENDENTE
        assert mensalidade.saldo == Decimal("179.50")

    @pytest.mark.parametrize("valor", ["0", "-10", "abc"])
    def test_valor_invalido_nao_registra(self, logado, professor, valor):
        mensalidade = criar_mensalidade(criar_aluno(professor))
        resposta = logado.post(
            reverse("financeiro:pagar", args=[mensalidade.pk]),
            {"valor_pago": valor, "forma_pagamento": "PIX"},
        )
        assert resposta.status_code == 200
        assert resposta.context["form"].errors
        assert not Pagamento.objects.exists()

    def test_erro_de_regra_do_model_aparece_no_formulario(self, logado, professor, monkeypatch):
        """Defesa em profundidade: um ValidationError do model vira erro do form."""
        mensalidade = criar_mensalidade(criar_aluno(professor))

        def recusar(*args, **kwargs):
            raise ValidationError({"valor_pago": "Valor recusado pela regra de negócio."})

        monkeypatch.setattr(Pagamento, "registrar", classmethod(lambda cls, *a, **k: recusar()))
        resposta = logado.post(
            reverse("financeiro:pagar", args=[mensalidade.pk]),
            {"valor_pago": "50.00", "forma_pagamento": "PIX"},
        )
        assert resposta.status_code == 200
        assert "Valor recusado pela regra de negócio." in resposta.content.decode()

    def test_mensalidade_de_outro_professor_retorna_404(self, logado, outro_professor):
        mensalidade = criar_mensalidade(criar_aluno(outro_professor))
        assert logado.get(reverse("financeiro:pagar", args=[mensalidade.pk])).status_code == 404
        resposta = logado.post(
            reverse("financeiro:pagar", args=[mensalidade.pk]),
            {"valor_pago": "300.00", "forma_pagamento": "PIX"},
        )
        assert resposta.status_code == 404
        assert not Pagamento.objects.exists()


class TestFiltroDeInadimplencia:
    def test_filtro_min_dias_mantem_apenas_atrasos_maiores(self, logado, professor):
        criar_mensalidade(criar_aluno(professor, nome="Atraso 10"), vencimento_dias=-10)
        criar_mensalidade(criar_aluno(professor, nome="Atraso 40", cpf="11122233344"), vencimento_dias=-40)
        resposta = logado.get(reverse("financeiro:inadimplentes"), {"min_dias": "30"})
        nomes = [item["aluno"].nome for item in resposta.context["inadimplentes"]]
        assert nomes == ["Atraso 40"]

    @pytest.mark.parametrize("valor", ["abc", "-5", "3.5", ""])
    def test_filtro_invalido_e_ignorado_sem_erro(self, logado, professor, valor):
        """Regressão: valor não numérico em min_dias gerava erro 500."""
        criar_mensalidade(criar_aluno(professor), vencimento_dias=-10)
        resposta = logado.get(reverse("financeiro:inadimplentes"), {"min_dias": valor})
        assert resposta.status_code == 200
        assert len(resposta.context["inadimplentes"]) == 1
