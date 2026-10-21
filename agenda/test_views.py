"""
US-30358 / Task 32587 — testes funcionais das telas do módulo Agenda.

Cobre os caminhos das views ainda não exercitados: agendamento pela tela
(sucesso, conflito, data retroativa), erros no registro da aula e o
registro de falta (incluindo o bloqueio para aulas que não estão agendadas).
"""
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from agenda.models import Aula
from alunos.models import Aluno

CONTEUDO = "Revisão de equações do segundo grau com resolução de exercícios do livro."


def criar_aluno(professor, cpf="12345678901"):
    aluno = Aluno(professor=professor, nome="Maria Silva", cpf=cpf, telefone="83999999999")
    aluno.full_clean()
    aluno.save()
    return aluno


def horario(dias=2, hora=14):
    return (timezone.localtime() + timedelta(days=dias)).replace(
        hour=hora, minute=0, second=0, microsecond=0
    )


def criar_aula(professor, aluno, dias=2, hora=14):
    aula = Aula(professor=professor, aluno=aluno, data_hora_inicio=horario(dias, hora))
    aula.full_clean()
    aula.save()
    return aula


def dados_agendamento(aluno, inicio, duracao=60):
    return {
        "aluno": aluno.pk,
        "data_hora_inicio": inicio.strftime("%Y-%m-%dT%H:%M"),
        "duracao_minutos": duracao,
        "modalidade": "ONLINE",
        "local": "Google Meet",
    }


class TestAgendamentoPelaTela:
    def test_get_exibe_formulario(self, logado):
        resposta = logado.get(reverse("agenda:criar"))
        assert resposta.status_code == 200
        assert resposta.context["titulo"] == "Agendar aula"

    def test_agendar_com_sucesso(self, logado, professor):
        aluno = criar_aluno(professor)
        resposta = logado.post(reverse("agenda:criar"), dados_agendamento(aluno, horario()))
        aula = Aula.objects.get()
        assert resposta.status_code == 302
        assert resposta.url == reverse("agenda:detalhe", args=[aula.pk])
        assert aula.professor == professor
        assert aula.local == "Google Meet"

    def test_conflito_de_horario_exibe_erro_e_nao_agenda(self, logado, professor):
        aluno = criar_aluno(professor)
        criar_aula(professor, aluno, hora=14)
        resposta = logado.post(
            reverse("agenda:criar"), dados_agendamento(aluno, horario(hora=14).replace(minute=30))
        )
        assert resposta.status_code == 200
        assert "Conflito de horário" in resposta.content.decode()
        assert Aula.objects.count() == 1

    def test_horario_retroativo_e_rejeitado(self, logado, professor):
        aluno = criar_aluno(professor)
        ontem = timezone.localtime() - timedelta(days=1)
        resposta = logado.post(reverse("agenda:criar"), dados_agendamento(aluno, ontem))
        assert resposta.status_code == 200
        assert "retroativa" in resposta.content.decode()
        assert not Aula.objects.exists()

    def test_aluno_de_outro_professor_nao_pode_ser_escolhido(self, logado, outro_professor):
        alheio = criar_aluno(outro_professor)
        resposta = logado.post(reverse("agenda:criar"), dados_agendamento(alheio, horario()))
        assert resposta.status_code == 200
        assert resposta.context["form"].errors.get("aluno")
        assert not Aula.objects.exists()


class TestDetalheDaAula:
    def test_aula_de_outro_professor_retorna_404(self, logado, outro_professor):
        aula = criar_aula(outro_professor, criar_aluno(outro_professor))
        assert logado.get(reverse("agenda:detalhe", args=[aula.pk])).status_code == 404

    def test_str_da_aula(self, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        assert str(aula).startswith("Maria Silva — ")


class TestRegistroDeAulaPelaTela:
    def test_aula_ja_realizada_redireciona(self, logado, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        aula.registrar_como_realizada(CONTEUDO)
        resposta = logado.get(reverse("agenda:registrar", args=[aula.pk]))
        assert resposta.status_code == 302

    def test_tela_liga_o_contador_de_caracteres(self, logado, professor):
        """O campo traz a marcação lida por static/js/contador-caracteres.js."""
        aula = criar_aula(professor, criar_aluno(professor))
        html = logado.get(reverse("agenda:registrar", args=[aula.pk])).content.decode()
        assert 'data-contador-minimo="50"' in html
        assert 'data-contador-alvo="conteudo-contador"' in html
        assert 'data-contador-botao="btn-concluir"' in html
        assert "js/contador-caracteres.js" in html

    def test_conteudo_curto_mantem_na_tela(self, logado, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        resposta = logado.post(reverse("agenda:registrar", args=[aula.pk]), {"conteudo_trabalhado": "pouco"})
        assert resposta.status_code == 200
        aula.refresh_from_db()
        assert aula.status == Aula.Status.AGENDADA

    def test_erro_do_model_aparece_no_formulario(self, logado, professor, monkeypatch):
        aula = criar_aula(professor, criar_aluno(professor))

        def recusar(self, *args, **kwargs):
            raise ValidationError({"conteudo_trabalhado": "Recusado pela regra de negócio."})

        monkeypatch.setattr(Aula, "registrar_como_realizada", recusar)
        resposta = logado.post(reverse("agenda:registrar", args=[aula.pk]), {"conteudo_trabalhado": CONTEUDO})
        assert resposta.status_code == 200
        assert "Recusado pela regra de negócio." in resposta.content.decode()

    def test_model_recusa_registrar_aula_nao_agendada(self, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        Aula.objects.filter(pk=aula.pk).update(status=Aula.Status.CANCELADA)
        aula.refresh_from_db()
        with pytest.raises(ValidationError):
            aula.registrar_como_realizada(CONTEUDO)


class TestRegistroDeFalta:
    def test_get_exibe_formulario(self, logado, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        assert logado.get(reverse("agenda:registrar_falta", args=[aula.pk])).status_code == 200

    @pytest.mark.parametrize("justificada, esperado", [("on", "JUSTIFICADA"), ("", "NAO_JUSTIFICADA")])
    def test_registrar_falta(self, logado, professor, justificada, esperado):
        aula = criar_aula(professor, criar_aluno(professor))
        dados = {"observacoes": "Avisou pelo WhatsApp"}
        if justificada:
            dados["justificada"] = justificada
        resposta = logado.post(reverse("agenda:registrar_falta", args=[aula.pk]), dados)
        assert resposta.status_code == 302
        aula.refresh_from_db()
        assert aula.status == Aula.Status.FALTA
        assert aula.tipo_falta == esperado
        assert aula.data_registro is not None

    @pytest.mark.parametrize("metodo", ["get", "post"])
    def test_aula_realizada_nao_recebe_falta(self, logado, professor, metodo):
        """Regressão: era possível marcar falta numa aula já realizada."""
        aula = criar_aula(professor, criar_aluno(professor))
        aula.registrar_como_realizada(CONTEUDO)
        resposta = getattr(logado, metodo)(reverse("agenda:registrar_falta", args=[aula.pk]), {})
        assert resposta.status_code == 302
        aula.refresh_from_db()
        assert aula.status == Aula.Status.REALIZADA

    def test_model_recusa_falta_em_aula_nao_agendada(self, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        aula.registrar_falta(justificada=True)
        with pytest.raises(ValidationError):
            aula.registrar_falta(justificada=False)

    def test_aula_de_outro_professor_retorna_404(self, logado, outro_professor):
        aula = criar_aula(outro_professor, criar_aluno(outro_professor))
        assert logado.post(reverse("agenda:registrar_falta", args=[aula.pk]), {}).status_code == 404
