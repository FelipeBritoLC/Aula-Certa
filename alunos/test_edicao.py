"""
US-30325 — Alterar dados do aluno (Tasks 32576, 32577, 32578, 32579).

CA-ALT-01: CPF único por professor e campos obrigatórios também na alteração.
CA-ALT-02: inativar mantém as aulas existentes e bloqueia novos agendamentos;
           o professor é avisado das aulas futuras que continuam agendadas.
"""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from agenda.forms import AgendamentoForm
from agenda.models import Aula
from alunos.models import Aluno


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


def criar_aluno(professor, **kwargs):
    dados = dict(professor=professor, nome="Maria Silva", cpf="12345678901", telefone="83999999999")
    dados.update(kwargs)
    aluno = Aluno(**dados)
    aluno.full_clean()
    aluno.save()
    return aluno


def dados_do_aluno(aluno, **alteracoes):
    """POST completo do formulário, como o navegador enviaria."""
    dados = {
        "nome": aluno.nome,
        "cpf": aluno.cpf,
        "telefone": aluno.telefone,
        "email": aluno.email,
        "data_nascimento": aluno.data_nascimento.isoformat() if aluno.data_nascimento else "",
        "endereco": aluno.endereco,
        "disciplina": aluno.disciplina,
        "serie_nivel": aluno.serie_nivel,
        "escola": aluno.escola,
        "observacoes": aluno.observacoes,
        "responsavel_nome": aluno.responsavel_nome,
        "responsavel_telefone": aluno.responsavel_telefone,
        "responsavel_email": aluno.responsavel_email,
        "responsavel_parentesco": aluno.responsavel_parentesco,
        "valor_hora": aluno.valor_hora or "",
        "situacao": aluno.situacao,
    }
    dados.update(alteracoes)
    return dados


def agendar(professor, aluno, dias=2):
    inicio = (timezone.localtime() + timedelta(days=dias)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    aula = Aula(professor=professor, aluno=aluno, data_hora_inicio=inicio)
    aula.full_clean()
    aula.save()
    return aula


def textos(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class TestAlteracaoComSucesso:
    def test_tela_de_edicao_vem_preenchida(self, logado, professor):
        aluno = criar_aluno(professor, endereco="Rua A, 10")
        resposta = logado.get(reverse("alunos:editar", args=[aluno.pk]))
        assert resposta.status_code == 200
        assert "Editar aluno — Maria Silva" in resposta.content.decode()
        assert resposta.context["form"].initial["endereco"] == "Rua A, 10"

    def test_altera_dados_e_redireciona_para_a_ficha(self, logado, professor):
        aluno = criar_aluno(professor)
        resposta = logado.post(
            reverse("alunos:editar", args=[aluno.pk]),
            dados_do_aluno(aluno, telefone="83911112222", escola="Escola Nova"),
        )
        assert resposta.status_code == 302
        assert resposta.url == reverse("alunos:detalhe", args=[aluno.pk])
        aluno.refresh_from_db()
        assert aluno.telefone == "83911112222"
        assert aluno.escola == "Escola Nova"

    def test_editar_nao_apaga_o_endereco(self, logado, professor):
        """Regressão: o campo endereço não era exibido e era apagado ao salvar."""
        aluno = criar_aluno(professor, endereco="Rua A, 10")
        resposta = logado.get(reverse("alunos:editar", args=[aluno.pk]))
        assert 'name="endereco"' in resposta.content.decode()
        logado.post(reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, telefone="83900000000"))
        aluno.refresh_from_db()
        assert aluno.endereco == "Rua A, 10"

    def test_cancelar_volta_para_a_ficha_do_aluno(self, logado, professor):
        aluno = criar_aluno(professor)
        resposta = logado.get(reverse("alunos:editar", args=[aluno.pk]))
        assert reverse("alunos:detalhe", args=[aluno.pk]) in resposta.content.decode()

    def test_nome_continua_sanitizado_na_alteracao(self, logado, professor):
        aluno = criar_aluno(professor)
        logado.post(reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, nome="  Maria   Souza "))
        aluno.refresh_from_db()
        assert aluno.nome == "Maria Souza"


class TestRegrasDeNegocioNaAlteracao:
    """CA-ALT-01 / Task 32576."""

    def test_cpf_de_outro_aluno_do_mesmo_professor_e_rejeitado(self, logado, professor):
        criar_aluno(professor, nome="Outro", cpf="11122233344")
        aluno = criar_aluno(professor)
        resposta = logado.post(
            reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, cpf="111.222.333-44")
        )
        assert resposta.status_code == 200
        assert "Já existe um aluno cadastrado com este CPF." in resposta.content.decode()
        aluno.refresh_from_db()
        assert aluno.cpf == "12345678901"

    def test_manter_o_proprio_cpf_e_permitido(self, logado, professor):
        aluno = criar_aluno(professor)
        resposta = logado.post(
            reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, cpf="123.456.789-01")
        )
        assert resposta.status_code == 302

    def test_cpf_ja_usado_por_aluno_de_outro_professor_e_permitido(self, logado, professor, outro_professor):
        criar_aluno(outro_professor, cpf="11122233344")
        aluno = criar_aluno(professor)
        resposta = logado.post(
            reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, cpf="11122233344")
        )
        assert resposta.status_code == 302

    @pytest.mark.parametrize("campo", ["nome", "cpf", "telefone"])
    def test_campo_obrigatorio_vazio_e_rejeitado(self, logado, professor, campo):
        aluno = criar_aluno(professor)
        resposta = logado.post(reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, **{campo: ""}))
        assert resposta.status_code == 200
        assert resposta.context["form"].errors.get(campo)
        aluno.refresh_from_db()
        assert getattr(aluno, campo)

    def test_cpf_com_quantidade_errada_de_digitos_e_rejeitado(self, logado, professor):
        aluno = criar_aluno(professor)
        resposta = logado.post(reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, cpf="123"))
        assert resposta.status_code == 200
        assert "CPF deve conter 11 dígitos." in resposta.content.decode()

    def test_professor_nao_edita_aluno_de_outro_professor(self, logado, outro_professor):
        alheio = criar_aluno(outro_professor)
        assert logado.get(reverse("alunos:editar", args=[alheio.pk])).status_code == 404
        resposta = logado.post(reverse("alunos:editar", args=[alheio.pk]), dados_do_aluno(alheio, nome="Invasor"))
        assert resposta.status_code == 404
        alheio.refresh_from_db()
        assert alheio.nome == "Maria Silva"

    def test_edicao_exige_login(self, client, professor):
        aluno = criar_aluno(professor)
        resposta = client.get(reverse("alunos:editar", args=[aluno.pk]))
        assert resposta.status_code == 302
        assert "/login/" in resposta.url


class TestInativacao:
    """CA-ALT-02 / Task 32577."""

    def test_inativar_com_aulas_futuras_avisa_e_mantem_as_aulas(self, logado, professor):
        aluno = criar_aluno(professor)
        aula = agendar(professor, aluno)
        resposta = logado.post(
            reverse("alunos:editar", args=[aluno.pk]),
            dados_do_aluno(aluno, situacao=Aluno.Situacao.INATIVO),
        )
        assert resposta.status_code == 302
        mensagens = " ".join(textos(resposta))
        assert "1 aula(s) agendada(s)" in mensagens
        aula.refresh_from_db()
        assert aula.status == Aula.Status.AGENDADA

    def test_inativar_sem_aulas_futuras_informa_o_bloqueio(self, logado, professor):
        aluno = criar_aluno(professor)
        resposta = logado.post(
            reverse("alunos:editar", args=[aluno.pk]),
            dados_do_aluno(aluno, situacao=Aluno.Situacao.INATIVO),
        )
        assert "Novos agendamentos para este aluno estão bloqueados." in " ".join(textos(resposta))

    def test_editar_aluno_ja_inativo_nao_repete_o_aviso(self, logado, professor):
        aluno = criar_aluno(professor, situacao=Aluno.Situacao.INATIVO)
        resposta = logado.post(reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, escola="X"))
        assert textos(resposta) == ["Dados do aluno atualizados."]

    def test_tela_mostra_ajuda_quando_aluno_ativo_tem_aulas_futuras(self, logado, professor):
        aluno = criar_aluno(professor)
        agendar(professor, aluno)
        resposta = logado.get(reverse("alunos:editar", args=[aluno.pk]))
        assert "novos agendamentos ficam bloqueados" in resposta.content.decode()

    def test_aluno_inativado_some_do_formulario_de_agendamento(self, logado, professor):
        aluno = criar_aluno(professor)
        logado.post(reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, situacao=Aluno.Situacao.INATIVO))
        form = AgendamentoForm(professor=professor)
        assert aluno not in form.fields["aluno"].queryset

    def test_post_forjado_de_agendamento_para_aluno_inativado_e_recusado(self, logado, professor):
        aluno = criar_aluno(professor)
        logado.post(reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, situacao=Aluno.Situacao.INATIVO))
        inicio = (timezone.localtime() + timedelta(days=3)).replace(hour=10, minute=0)
        resposta = logado.post(
            reverse("agenda:criar"),
            {
                "aluno": aluno.pk,
                "data_hora_inicio": inicio.strftime("%Y-%m-%dT%H:%M"),
                "duracao_minutos": 60,
                "modalidade": "PRESENCIAL",
                "local": "",
            },
        )
        assert resposta.status_code == 200
        assert not Aula.objects.filter(aluno=aluno).exists()

    def test_reativar_libera_novos_agendamentos(self, logado, professor):
        aluno = criar_aluno(professor, situacao=Aluno.Situacao.INATIVO)
        logado.post(reverse("alunos:editar", args=[aluno.pk]), dados_do_aluno(aluno, situacao=Aluno.Situacao.ATIVO))
        assert aluno in AgendamentoForm(professor=professor).fields["aluno"].queryset

    def test_aulas_futuras_agendadas_ignora_passadas_e_nao_agendadas(self, professor):
        aluno = criar_aluno(professor)
        futura = agendar(professor, aluno, dias=2)
        realizada = agendar(professor, aluno, dias=4)
        Aula.objects.filter(pk=realizada.pk).update(status=Aula.Status.CANCELADA)
        passada = agendar(professor, aluno, dias=6)
        Aula.objects.filter(pk=passada.pk).update(data_hora_inicio=timezone.now() - timedelta(days=1))
        assert list(aluno.aulas_futuras_agendadas()) == [futura]
