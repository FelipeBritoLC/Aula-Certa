"""
US-30333 — Definir informações da aula agendada.

CA-DEF-01: modalidade, duração, horário e local editáveis enquanto AGENDADA.
CA-DEF-02: alterar duração/horário reaplica a validação de conflito (CA-AGE-01).
CA-DEF-03: aulas REALIZADA, CANCELADA ou FALTA não são editáveis.
"""
from datetime import timedelta

import pytest  # type: ignore[import-not-found]
from django.contrib.auth import get_user_model  # type: ignore[import-not-found]
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from agenda.forms import EditarAulaForm
from agenda.models import Aula
from alunos.models import Aluno

User = get_user_model()

CONTEUDO_50 = "Revisão de equações do segundo grau com resolução de exercícios."


@pytest.fixture
def professor(db):
    return User.objects.create_user(username="prof1", password="senha123")


@pytest.fixture
def outro_professor(db):
    return User.objects.create_user(username="prof2", password="senha123")


def _aluno(professor, cpf="12345678901", nome="Maria Silva", **kwargs):
    aluno = Aluno(professor=professor, nome=nome, cpf=cpf, telefone="83999999999", **kwargs)
    aluno.full_clean()
    aluno.save()
    return aluno


@pytest.fixture
def aluno(professor):
    return _aluno(professor)


def em_dois_dias(hora, minuto=0):
    """Horário local daqui a dois dias (futuro com folga, em qualquer fuso)."""
    base = timezone.localtime() + timedelta(days=2)
    return base.replace(hour=hora, minute=minuto, second=0, microsecond=0)


def criar_aula(professor, aluno, inicio, **kwargs):
    aula = Aula(professor=professor, aluno=aluno, data_hora_inicio=inicio, **kwargs)
    aula.full_clean()
    aula.save()
    return aula


def dados_do_form(aula, **alteracoes):
    """Dados de POST equivalentes ao que o navegador enviaria para a aula."""
    dados = {
        "data_hora_inicio": timezone.localtime(aula.data_hora_inicio).strftime("%Y-%m-%dT%H:%M"),
        "duracao_minutos": aula.duracao_minutos,
        "modalidade": aula.modalidade,
        "local": aula.local,
    }
    dados.update(alteracoes)
    return dados


def mudar_status(aula, status, **extra):
    """Muda o status direto no banco (simula uma aula que já foi registrada)."""
    Aula.objects.filter(pk=aula.pk).update(status=status, **extra)
    aula.refresh_from_db()
    return aula


# ---------------------------------------------------------------------------
# CA-DEF-01 — definir/editar informações de uma aula agendada
# ---------------------------------------------------------------------------
class TestCaDef01Edicao:
    def test_cenario_edicao_de_dados_da_aula_com_sucesso(self, professor, aluno):
        """BDD: altera a modalidade de presencial para online."""
        aula = criar_aula(professor, aluno, em_dois_dias(14), modalidade="PRESENCIAL")

        form = EditarAulaForm(dados_do_form(aula, modalidade="ONLINE"), instance=aula)
        assert form.is_valid(), form.errors
        form.save()

        aula.refresh_from_db()
        assert aula.modalidade == "ONLINE"
        assert aula.status == Aula.Status.AGENDADA

    def test_define_local_da_aula(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))

        form = EditarAulaForm(dados_do_form(aula, local="Rua das Flores, 100"), instance=aula)
        assert form.is_valid(), form.errors
        form.save()

        aula.refresh_from_db()
        assert aula.local == "Rua das Flores, 100"

    def test_altera_duracao_e_horario_sem_conflito(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        novo_inicio = em_dois_dias(16, 30).strftime("%Y-%m-%dT%H:%M")

        form = EditarAulaForm(
            dados_do_form(aula, data_hora_inicio=novo_inicio, duracao_minutos=90), instance=aula
        )
        assert form.is_valid(), form.errors
        form.save()

        aula.refresh_from_db()
        assert aula.duracao_minutos == 90
        assert timezone.localtime(aula.data_hora_inicio).strftime("%H:%M") == "16:30"

    @pytest.mark.parametrize("duracao", [0, -30])
    def test_duracao_deve_ser_positiva(self, professor, aluno, duracao):
        aula = criar_aula(professor, aluno, em_dois_dias(14))

        form = EditarAulaForm(dados_do_form(aula, duracao_minutos=duracao), instance=aula)

        assert not form.is_valid()
        assert "duracao_minutos" in form.errors

    def test_o_aluno_nao_e_editavel_pelo_formulario(self):
        assert "aluno" not in EditarAulaForm().fields


# ---------------------------------------------------------------------------
# CA-DEF-02 — conflito de horário na edição
# ---------------------------------------------------------------------------
class TestCaDef02ConflitoNaEdicao:
    def test_cenario_aumentar_duracao_que_invade_a_proxima_aula_e_rejeitado(self, professor, aluno):
        """BDD: aula às 14h e outra às 15h; duração da primeira vai para 90 min."""
        primeira = criar_aula(professor, aluno, em_dois_dias(14), duracao_minutos=60)
        criar_aula(professor, aluno, em_dois_dias(15), duracao_minutos=60)

        form = EditarAulaForm(dados_do_form(primeira, duracao_minutos=90), instance=primeira)

        assert not form.is_valid()
        assert "Conflito de horário" in " ".join(form.errors["data_hora_inicio"])
        primeira.refresh_from_db()
        assert primeira.duracao_minutos == 60  # nada foi gravado

    def test_aumentar_duracao_ate_encostar_na_proxima_aula_e_permitido(self, professor, aluno):
        primeira = criar_aula(professor, aluno, em_dois_dias(14), duracao_minutos=30)
        criar_aula(professor, aluno, em_dois_dias(15), duracao_minutos=60)

        form = EditarAulaForm(dados_do_form(primeira, duracao_minutos=60), instance=primeira)

        assert form.is_valid(), form.errors  # termina às 15h00, a outra começa às 15h00

    def test_mover_horario_para_cima_de_outra_aula_e_rejeitado(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(10))
        criar_aula(professor, aluno, em_dois_dias(14), duracao_minutos=60)
        destino = em_dois_dias(14, 30).strftime("%Y-%m-%dT%H:%M")

        form = EditarAulaForm(dados_do_form(aula, data_hora_inicio=destino), instance=aula)

        assert not form.is_valid()
        assert "data_hora_inicio" in form.errors

    def test_aula_nao_conflita_consigo_mesma(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))

        form = EditarAulaForm(dados_do_form(aula, local="Sala 3"), instance=aula)

        assert form.is_valid(), form.errors

    def test_aula_de_outro_professor_nao_gera_conflito(self, professor, outro_professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        aluno_do_outro = _aluno(outro_professor, cpf="98765432100", nome="Pedro")
        criar_aula(outro_professor, aluno_do_outro, em_dois_dias(15))

        form = EditarAulaForm(dados_do_form(aula, duracao_minutos=120), instance=aula)

        assert form.is_valid(), form.errors

    def test_aula_cancelada_nao_gera_conflito(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        cancelada = criar_aula(professor, aluno, em_dois_dias(15))
        mudar_status(cancelada, Aula.Status.CANCELADA)

        form = EditarAulaForm(dados_do_form(aula, duracao_minutos=90), instance=aula)

        assert form.is_valid(), form.errors

    def test_nao_permite_mover_a_aula_para_o_passado(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        ontem = (timezone.localtime() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")

        form = EditarAulaForm(dados_do_form(aula, data_hora_inicio=ontem), instance=aula)

        assert not form.is_valid()
        assert "retroativa" in " ".join(form.errors["data_hora_inicio"])

    def test_aula_agendada_que_ja_passou_pode_ter_a_modalidade_editada(self, professor, aluno):
        """Sem mexer no horário, a regra de 'não retroativo' não deve atrapalhar."""
        inicio = (timezone.localtime() - timedelta(days=1)).replace(second=37, microsecond=123)
        aula = Aula.objects.create(
            professor=professor, aluno=aluno, data_hora_inicio=inicio, duracao_minutos=60
        )  # sem full_clean: simula uma aula que ficou sem ser registrada

        form = EditarAulaForm(dados_do_form(aula, modalidade="ONLINE"), instance=aula)

        assert form.is_valid(), form.errors


# ---------------------------------------------------------------------------
# CA-DEF-03 — aulas não agendadas não são editáveis
# ---------------------------------------------------------------------------
STATUS_BLOQUEADOS = [Aula.Status.REALIZADA, Aula.Status.CANCELADA, Aula.Status.FALTA]


class TestCaDef03BloqueioPorStatus:
    @pytest.mark.parametrize("status", STATUS_BLOQUEADOS)
    def test_cenario_editar_aula_ja_realizada_e_bloqueado_no_modelo(self, professor, aluno, status):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        mudar_status(aula, status, conteudo_trabalhado=CONTEUDO_50)

        aula.duracao_minutos = 90
        with pytest.raises(ValidationError) as erro:
            aula.full_clean()

        assert "Somente aulas com status Agendada" in str(erro.value)

    @pytest.mark.parametrize("status", STATUS_BLOQUEADOS)
    @pytest.mark.parametrize(
        "campo, valor",
        [("modalidade", "ONLINE"), ("local", "Outro lugar"), ("duracao_minutos", 45)],
    )
    def test_nenhum_campo_editavel_pode_ser_alterado(self, professor, aluno, status, campo, valor):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        mudar_status(aula, status, conteudo_trabalhado=CONTEUDO_50)

        form = EditarAulaForm(dados_do_form(aula, **{campo: valor}), instance=aula)

        assert not form.is_valid()
        assert "Somente aulas com status Agendada" in " ".join(form.non_field_errors())

    @pytest.mark.parametrize("status", STATUS_BLOQUEADOS)
    def test_nem_o_horario_pode_ser_alterado(self, professor, aluno, status):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        mudar_status(aula, status, conteudo_trabalhado=CONTEUDO_50)
        outro_horario = em_dois_dias(18).strftime("%Y-%m-%dT%H:%M")

        form = EditarAulaForm(dados_do_form(aula, data_hora_inicio=outro_horario), instance=aula)

        assert not form.is_valid()

    def test_aula_realizada_sem_alteracoes_continua_valida(self, professor, aluno):
        """O bloqueio é sobre ALTERAR; revalidar uma aula intacta não pode falhar."""
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        mudar_status(aula, Aula.Status.REALIZADA, conteudo_trabalhado=CONTEUDO_50)

        aula.full_clean()  # não levanta

    def test_registrar_aula_realizada_continua_funcionando(self, professor, aluno):
        """A transição AGENDADA -> REALIZADA não pode ser confundida com 'edição'."""
        aula = criar_aula(professor, aluno, em_dois_dias(14))

        aula.registrar_como_realizada(CONTEUDO_50)

        aula.refresh_from_db()
        assert aula.status == Aula.Status.REALIZADA

    def test_pode_editar_reflete_o_status(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        assert aula.pode_editar is True
        mudar_status(aula, Aula.Status.CANCELADA)
        assert aula.pode_editar is False


class TestAlunoInativadoComAulasFuturas:
    """CA-ALT-02: inativar o aluno não pode travar as aulas que ele já tinha."""

    def test_editar_aula_existente_de_aluno_inativado(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        aluno.situacao = Aluno.Situacao.INATIVO
        aluno.save()

        form = EditarAulaForm(dados_do_form(aula, modalidade="ONLINE"), instance=aula)

        assert form.is_valid(), form.errors

    def test_registrar_aula_existente_de_aluno_inativado(self, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        aluno.situacao = Aluno.Situacao.INATIVO
        aluno.save()

        aula.registrar_como_realizada(CONTEUDO_50)

        aula.refresh_from_db()
        assert aula.status == Aula.Status.REALIZADA

    def test_novo_agendamento_para_aluno_inativo_continua_bloqueado(self, professor):
        inativo = _aluno(professor, cpf="11122233344", nome="Inativo", situacao="INATIVO")

        with pytest.raises(ValidationError):
            criar_aula(professor, inativo, em_dois_dias(14))


# ---------------------------------------------------------------------------
# View de edição
# ---------------------------------------------------------------------------
class TestEditarAulaView:
    def test_get_exibe_o_formulario_preenchido_no_horario_local(self, client, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14, 30), local="Sala 2")
        client.force_login(professor)

        resposta = client.get(reverse("agenda:editar", args=[aula.pk]))

        html = resposta.content.decode()
        assert resposta.status_code == 200
        esperado = timezone.localtime(aula.data_hora_inicio).strftime("%Y-%m-%dT14:30")
        assert f'value="{esperado}"' in html  # 14:30 local, não UTC
        assert "Sala 2" in html
        assert "Maria Silva" in html

    def test_post_valido_salva_e_redireciona_para_a_ficha(self, client, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        client.force_login(professor)

        resposta = client.post(
            reverse("agenda:editar", args=[aula.pk]),
            dados_do_form(aula, modalidade="ONLINE", local="meet.example.com/abc"),
        )

        assert resposta.status_code == 302
        assert resposta.url == reverse("agenda:detalhe", args=[aula.pk])
        aula.refresh_from_db()
        assert (aula.modalidade, aula.local) == ("ONLINE", "meet.example.com/abc")

    def test_post_com_conflito_reexibe_o_formulario_com_erro(self, client, professor, aluno):
        primeira = criar_aula(professor, aluno, em_dois_dias(14), duracao_minutos=60)
        criar_aula(professor, aluno, em_dois_dias(15), duracao_minutos=60)
        client.force_login(professor)

        resposta = client.post(
            reverse("agenda:editar", args=[primeira.pk]),
            dados_do_form(primeira, duracao_minutos=90),
        )

        assert resposta.status_code == 200
        assert "Conflito de horário" in resposta.content.decode()
        primeira.refresh_from_db()
        assert primeira.duracao_minutos == 60

    @pytest.mark.parametrize("status", STATUS_BLOQUEADOS)
    def test_aula_nao_agendada_nao_abre_para_edicao(self, client, professor, aluno, status):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        mudar_status(aula, status, conteudo_trabalhado=CONTEUDO_50)
        client.force_login(professor)
        url = reverse("agenda:editar", args=[aula.pk])

        get = client.get(url)
        post = client.post(url, dados_do_form(aula, modalidade="ONLINE"), follow=True)

        assert get.status_code == 302 and get.url == reverse("agenda:detalhe", args=[aula.pk])
        assert "Somente aulas com status Agendada" in post.content.decode()
        aula.refresh_from_db()
        assert aula.modalidade == "PRESENCIAL"

    def test_professor_nao_edita_aula_de_outro_professor(
        self, client, professor, outro_professor, aluno
    ):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        client.force_login(outro_professor)

        resposta = client.post(
            reverse("agenda:editar", args=[aula.pk]), dados_do_form(aula, modalidade="ONLINE")
        )

        assert resposta.status_code == 404
        aula.refresh_from_db()
        assert aula.modalidade == "PRESENCIAL"

    def test_acesso_sem_login_redireciona_para_o_login(self, client, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14))

        resposta = client.get(reverse("agenda:editar", args=[aula.pk]))

        assert resposta.status_code == 302
        assert "/login/" in resposta.url


class TestFichaDaAula:
    def test_aula_agendada_mostra_botao_editar_e_o_local(self, client, professor, aluno):
        aula = criar_aula(professor, aluno, em_dois_dias(14), local="Sala 2")
        client.force_login(professor)

        html = client.get(reverse("agenda:detalhe", args=[aula.pk])).content.decode()

        assert reverse("agenda:editar", args=[aula.pk]) in html
        assert "Sala 2" in html

    @pytest.mark.parametrize("status", STATUS_BLOQUEADOS)
    def test_aula_nao_agendada_nao_mostra_botao_editar(self, client, professor, aluno, status):
        aula = criar_aula(professor, aluno, em_dois_dias(14))
        mudar_status(aula, status, conteudo_trabalhado=CONTEUDO_50)
        client.force_login(professor)

        html = client.get(reverse("agenda:detalhe", args=[aula.pk])).content.decode()

        assert reverse("agenda:editar", args=[aula.pk]) not in html


class TestCriarAgendamentoComLocal:
    def test_local_informado_no_agendamento_e_gravado(self, client, professor, aluno):
        client.force_login(professor)
        inicio = em_dois_dias(9).strftime("%Y-%m-%dT%H:%M")

        resposta = client.post(
            reverse("agenda:criar"),
            {
                "aluno": aluno.pk, "data_hora_inicio": inicio, "duracao_minutos": 60,
                "modalidade": "ONLINE", "local": "https://meet.example.com/xyz",
            },
        )

        assert resposta.status_code == 302
        assert Aula.objects.get().local == "https://meet.example.com/xyz"
