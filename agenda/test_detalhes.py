"""
US-30339 — Informar detalhes da aula realizada (Tasks 32581–32584).

CA-DET-01: material, avaliação e recomendações são opcionais e podem ser
           informados no registro da aula ou depois, pela tela de detalhes.
CA-DET-02: os detalhes só podem ser informados em aulas REALIZADA.
CA-DET-03: os detalhes aparecem na página da aula e na ficha do aluno.
"""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from agenda.forms import DetalhesAulaForm
from agenda.models import Aula
from alunos.models import Aluno

CONTEUDO = "Revisão de equações do segundo grau com resolução de exercícios do livro."


@pytest.fixture
def professor(db):
    return User.objects.create_user(username="prof1", password="senha123")


@pytest.fixture
def outro_professor(db):
    return User.objects.create_user(username="prof2", password="senha123")


@pytest.fixture
def logado(client, professor):
    client.force_login(professor)
    return client


def criar_aluno(professor, cpf="12345678901"):
    aluno = Aluno(professor=professor, nome="Maria Silva", cpf=cpf, telefone="83999999999")
    aluno.full_clean()
    aluno.save()
    return aluno


def criar_aula(professor, aluno=None, dias=2, hora=14):
    aluno = aluno or criar_aluno(professor)
    inicio = (timezone.localtime() + timedelta(days=dias)).replace(
        hour=hora, minute=0, second=0, microsecond=0
    )
    aula = Aula(professor=professor, aluno=aluno, data_hora_inicio=inicio)
    aula.full_clean()
    aula.save()
    return aula


@pytest.fixture
def aula_realizada(professor):
    aula = criar_aula(professor)
    aula.registrar_como_realizada(CONTEUDO)
    return aula


class TestModelagem:
    """Task 32581."""

    def test_registrar_com_detalhes(self, professor):
        aula = criar_aula(professor)
        aula.registrar_como_realizada(
            CONTEUDO,
            material_utilizado="  Lista 3 de exercícios ",
            avaliacao_desempenho=Aula.Avaliacao.BOM,
            recomendacoes="Refazer questões 4 a 7.",
        )
        aula.refresh_from_db()
        assert aula.status == Aula.Status.REALIZADA
        assert aula.material_utilizado == "Lista 3 de exercícios"
        assert aula.avaliacao_desempenho == "BOM"
        assert aula.get_avaliacao_desempenho_display() == "Bom"
        assert aula.recomendacoes == "Refazer questões 4 a 7."
        assert aula.tem_detalhes

    def test_detalhes_sao_opcionais(self, aula_realizada):
        aula_realizada.refresh_from_db()
        assert aula_realizada.status == Aula.Status.REALIZADA
        assert not aula_realizada.tem_detalhes

    def test_avaliacao_invalida_e_rejeitada(self, aula_realizada):
        aula_realizada.avaliacao_desempenho = "EXCELENTE"
        with pytest.raises(ValidationError) as exc:
            aula_realizada.full_clean()
        assert "avaliacao_desempenho" in exc.value.message_dict

    @pytest.mark.parametrize("status", ["AGENDADA", "CANCELADA", "FALTA"])
    def test_detalhes_em_aula_nao_realizada_sao_rejeitados(self, professor, status):
        """CA-DET-02."""
        aula = criar_aula(professor)
        Aula.objects.filter(pk=aula.pk).update(status=status)
        aula.refresh_from_db()
        aula.recomendacoes = "Estudar capítulo 2"
        with pytest.raises(ValidationError) as exc:
            aula.full_clean()
        assert "só podem ser informados em aulas realizadas" in str(exc.value)

    def test_conteudo_curto_continua_bloqueando_mesmo_com_detalhes(self, professor):
        aula = criar_aula(professor)
        with pytest.raises(ValidationError):
            aula.registrar_como_realizada("curto", recomendacoes="Revisar")
        aula.refresh_from_db()
        assert aula.status == Aula.Status.AGENDADA
        assert aula.recomendacoes == ""


class TestRegistroPelaTela:
    """Tasks 32582 — detalhes no formulário de registro."""

    def test_formulario_de_registro_exibe_os_campos(self, logado, professor):
        aula = criar_aula(professor)
        html = logado.get(reverse("agenda:registrar", args=[aula.pk])).content.decode()
        for campo in ["material_utilizado", "avaliacao_desempenho", "recomendacoes"]:
            assert f'name="{campo}"' in html

    def test_registrar_aula_com_detalhes_pela_tela(self, logado, professor):
        aula = criar_aula(professor)
        resposta = logado.post(
            reverse("agenda:registrar", args=[aula.pk]),
            {
                "conteudo_trabalhado": CONTEUDO,
                "observacoes": "",
                "material_utilizado": "Livro Dante, cap. 4",
                "avaliacao_desempenho": "OTIMO",
                "recomendacoes": "Avançar para inequações.",
            },
        )
        assert resposta.status_code == 302
        aula.refresh_from_db()
        assert aula.status == Aula.Status.REALIZADA
        assert aula.material_utilizado == "Livro Dante, cap. 4"
        assert aula.avaliacao_desempenho == "OTIMO"

    def test_registrar_sem_detalhes_continua_funcionando(self, logado, professor):
        aula = criar_aula(professor)
        resposta = logado.post(
            reverse("agenda:registrar", args=[aula.pk]),
            {"conteudo_trabalhado": CONTEUDO},
        )
        assert resposta.status_code == 302
        aula.refresh_from_db()
        assert aula.status == Aula.Status.REALIZADA


class TestTelaDeDetalhes:
    """Task 32582 — tela própria para informar/corrigir os detalhes depois."""

    def test_get_exibe_formulario(self, logado, aula_realizada):
        resposta = logado.get(reverse("agenda:detalhes", args=[aula_realizada.pk]))
        assert resposta.status_code == 200
        assert isinstance(resposta.context["form"], DetalhesAulaForm)

    def test_salvar_detalhes(self, logado, aula_realizada):
        resposta = logado.post(
            reverse("agenda:detalhes", args=[aula_realizada.pk]),
            {
                "material_utilizado": "Apostila de frações",
                "avaliacao_desempenho": "REGULAR",
                "recomendacoes": "  Praticar 10 exercícios por dia  ",
            },
        )
        assert resposta.status_code == 302
        assert resposta.url == reverse("agenda:detalhe", args=[aula_realizada.pk])
        aula_realizada.refresh_from_db()
        assert aula_realizada.avaliacao_desempenho == "REGULAR"
        assert aula_realizada.recomendacoes == "Praticar 10 exercícios por dia"

    def test_salvar_nao_altera_conteudo_nem_status(self, logado, aula_realizada):
        logado.post(
            reverse("agenda:detalhes", args=[aula_realizada.pk]),
            {"material_utilizado": "Quadro", "avaliacao_desempenho": "", "recomendacoes": ""},
        )
        aula_realizada.refresh_from_db()
        assert aula_realizada.conteudo_trabalhado == CONTEUDO
        assert aula_realizada.status == Aula.Status.REALIZADA

    def test_limpar_os_detalhes_e_permitido(self, logado, professor):
        aula = criar_aula(professor)
        aula.registrar_como_realizada(CONTEUDO, avaliacao_desempenho="BOM")
        logado.post(
            reverse("agenda:detalhes", args=[aula.pk]),
            {"material_utilizado": "", "avaliacao_desempenho": "", "recomendacoes": ""},
        )
        aula.refresh_from_db()
        assert not aula.tem_detalhes

    def test_avaliacao_invalida_na_tela_e_rejeitada(self, logado, aula_realizada):
        resposta = logado.post(
            reverse("agenda:detalhes", args=[aula_realizada.pk]),
            {"material_utilizado": "", "avaliacao_desempenho": "EXCELENTE", "recomendacoes": ""},
        )
        assert resposta.status_code == 200
        assert resposta.context["form"].errors.get("avaliacao_desempenho")

    @pytest.mark.parametrize("metodo", ["get", "post"])
    def test_aula_agendada_e_redirecionada_sem_alterar(self, logado, professor, metodo):
        """CA-DET-02 na interface."""
        aula = criar_aula(professor)
        resposta = getattr(logado, metodo)(
            reverse("agenda:detalhes", args=[aula.pk]),
            {"material_utilizado": "X", "avaliacao_desempenho": "BOM", "recomendacoes": "Y"},
        )
        assert resposta.status_code == 302
        assert resposta.url == reverse("agenda:detalhe", args=[aula.pk])
        aula.refresh_from_db()
        assert not aula.tem_detalhes

    def test_aula_de_outro_professor_retorna_404(self, logado, outro_professor):
        aula = criar_aula(outro_professor)
        aula.registrar_como_realizada(CONTEUDO)
        assert logado.get(reverse("agenda:detalhes", args=[aula.pk])).status_code == 404

    def test_exige_login(self, client, aula_realizada):
        resposta = client.get(reverse("agenda:detalhes", args=[aula_realizada.pk]))
        assert resposta.status_code == 302
        assert "/login/" in resposta.url


class TestExibicao:
    """Task 32583 / CA-DET-03."""

    def test_pagina_da_aula_exibe_detalhes_e_botao(self, logado, professor):
        aula = criar_aula(professor)
        aula.registrar_como_realizada(
            CONTEUDO, material_utilizado="Lista 5", avaliacao_desempenho="BOM",
            recomendacoes="Revisar Bhaskara",
        )
        html = logado.get(reverse("agenda:detalhe", args=[aula.pk])).content.decode()
        assert "Lista 5" in html
        assert "Bom" in html
        assert "Revisar Bhaskara" in html
        assert "Editar detalhes" in html

    def test_aula_realizada_sem_detalhes_oferece_informar(self, logado, aula_realizada):
        html = logado.get(reverse("agenda:detalhe", args=[aula_realizada.pk])).content.decode()
        assert "Informar detalhes" in html
        assert "Não avaliado" in html

    def test_aula_agendada_nao_mostra_botao_de_detalhes(self, logado, professor):
        aula = criar_aula(professor)
        html = logado.get(reverse("agenda:detalhe", args=[aula.pk])).content.decode()
        assert reverse("agenda:detalhes", args=[aula.pk]) not in html

    def test_ficha_do_aluno_exibe_historico_com_detalhes(self, logado, professor):
        aluno = criar_aluno(professor)
        aula = criar_aula(professor, aluno)
        aula.registrar_como_realizada(
            CONTEUDO, material_utilizado="Apostila 2", avaliacao_desempenho="OTIMO",
            recomendacoes="Fazer simulado",
        )
        html = logado.get(reverse("alunos:detalhe", args=[aluno.pk])).content.decode()
        assert "Histórico de aulas realizadas" in html
        assert "Revisão de equações" in html
        assert "Desempenho: Ótimo" in html
        assert "Apostila 2" in html
        assert "Fazer simulado" in html

    def test_ficha_lista_apenas_realizadas_mais_recentes_primeiro(self, logado, professor):
        aluno = criar_aluno(professor)
        antiga = criar_aula(professor, aluno, dias=2)
        recente = criar_aula(professor, aluno, dias=3)
        agendada = criar_aula(professor, aluno, dias=4)
        antiga.registrar_como_realizada(CONTEUDO)
        recente.registrar_como_realizada(CONTEUDO)
        resposta = logado.get(reverse("alunos:detalhe", args=[aluno.pk]))
        assert list(resposta.context["historico_aulas"]) == [recente, antiga]
        assert agendada not in resposta.context["historico_aulas"]
        assert resposta.context["total_aulas_realizadas"] == 2

    def test_ficha_limita_o_historico_a_cinco_aulas(self, logado, professor):
        aluno = criar_aluno(professor)
        for dia in range(2, 9):
            criar_aula(professor, aluno, dias=dia).registrar_como_realizada(CONTEUDO)
        resposta = logado.get(reverse("alunos:detalhe", args=[aluno.pk]))
        assert len(resposta.context["historico_aulas"]) == 5
        assert "últimas 5 de 7" in resposta.content.decode()

    def test_ficha_sem_aulas_realizadas(self, logado, professor):
        aluno = criar_aluno(professor)
        html = logado.get(reverse("alunos:detalhe", args=[aluno.pk])).content.decode()
        assert "Nenhuma aula realizada ainda." in html
