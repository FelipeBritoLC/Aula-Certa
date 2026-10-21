"""
US-30322 — Informar dados complementares do aluno.

CA-COMP-01: data de nascimento não pode estar no futuro.
CA-COMP-02: aluno menor de 18 anos exige nome e telefone do responsável.
CA-COMP-03: dados acadêmicos e do responsável aparecem na ficha do aluno.
"""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno


@pytest.fixture
def professor(db):
    return User.objects.create_user(username="prof1", password="senha123")


@pytest.fixture
def logado(client, professor):
    client.force_login(professor)
    return client


def anos_atras(anos, dias=0):
    hoje = timezone.localdate()
    try:
        data = hoje.replace(year=hoje.year - anos)
    except ValueError:  # 29/02 em ano não bissexto
        data = hoje.replace(year=hoje.year - anos, day=28)
    return data + timedelta(days=dias)


def novo_aluno(professor, **kwargs):
    dados = dict(professor=professor, nome="Ana Lima", cpf="12345678901", telefone="83999999999")
    dados.update(kwargs)
    return Aluno(**dados)


def salvar(aluno):
    aluno.full_clean()
    aluno.save()
    return aluno


class TestIdade:
    def test_idade_em_anos_completos(self, professor):
        assert novo_aluno(professor, data_nascimento=anos_atras(15)).idade == 15

    def test_aniversario_amanha_ainda_nao_conta(self, professor):
        assert novo_aluno(professor, data_nascimento=anos_atras(18, dias=1)).idade == 17

    def test_sem_data_de_nascimento_nao_ha_idade(self, professor):
        aluno = novo_aluno(professor)
        assert aluno.idade is None
        assert not aluno.is_menor_de_idade()


class TestResponsavelObrigatorioParaMenor:
    """CA-COMP-02."""

    def test_menor_sem_responsavel_e_rejeitado(self, professor):
        with pytest.raises(ValidationError) as exc:
            salvar(novo_aluno(professor, data_nascimento=anos_atras(12)))
        assert set(exc.value.message_dict) == {"responsavel_nome", "responsavel_telefone"}

    def test_menor_sem_telefone_do_responsavel_e_rejeitado(self, professor):
        with pytest.raises(ValidationError) as exc:
            salvar(novo_aluno(professor, data_nascimento=anos_atras(12), responsavel_nome="Carla Lima"))
        assert set(exc.value.message_dict) == {"responsavel_telefone"}

    def test_menor_com_responsavel_e_aceito(self, professor):
        aluno = salvar(
            novo_aluno(
                professor,
                data_nascimento=anos_atras(12),
                responsavel_nome="  Carla   Lima ",
                responsavel_telefone="83977776666",
            )
        )
        assert aluno.responsavel_nome == "Carla Lima"

    def test_quem_faz_18_hoje_nao_precisa_de_responsavel(self, professor):
        assert salvar(novo_aluno(professor, data_nascimento=anos_atras(18))).pk

    def test_quem_faz_18_amanha_ainda_precisa_de_responsavel(self, professor):
        with pytest.raises(ValidationError):
            salvar(novo_aluno(professor, data_nascimento=anos_atras(18, dias=1)))

    def test_adulto_ou_sem_nascimento_nao_precisa_de_responsavel(self, professor):
        assert salvar(novo_aluno(professor, data_nascimento=anos_atras(30))).pk
        assert salvar(novo_aluno(professor, cpf="11122233344")).pk


class TestDataDeNascimento:
    """CA-COMP-01."""

    def test_data_no_futuro_e_rejeitada(self, professor):
        amanha = timezone.localdate() + timedelta(days=1)
        with pytest.raises(ValidationError) as exc:
            salvar(novo_aluno(professor, data_nascimento=amanha))
        assert "data_nascimento" in exc.value.message_dict


class TestFormularioEFicha:
    """CA-COMP-02 pela interface e CA-COMP-03."""

    def dados(self, **extra):
        dados = {"nome": "Ana Lima", "cpf": "12345678901", "telefone": "83999999999", "situacao": "ATIVO"}
        dados.update(extra)
        return dados

    def test_cadastro_de_menor_sem_responsavel_mostra_erro_no_campo(self, logado):
        resposta = logado.post(
            reverse("alunos:cadastrar"),
            self.dados(data_nascimento=anos_atras(10).isoformat()),
        )
        assert resposta.status_code == 200
        assert "Informe o responsável: o aluno é menor de idade." in resposta.content.decode()
        assert not Aluno.objects.exists()

    def test_cadastro_de_menor_com_responsavel(self, logado):
        resposta = logado.post(
            reverse("alunos:cadastrar"),
            self.dados(
                data_nascimento=anos_atras(10).isoformat(),
                responsavel_nome="Carla Lima",
                responsavel_telefone="83977776666",
                responsavel_parentesco="Mãe",
            ),
        )
        assert resposta.status_code == 302
        assert Aluno.objects.get().responsavel_parentesco == "Mãe"

    def test_ficha_exibe_dados_academicos_e_responsavel(self, logado, professor):
        aluno = salvar(
            novo_aluno(
                professor,
                data_nascimento=anos_atras(14),
                serie_nivel="9º ano",
                escola="Escola Estadual Lyceu",
                disciplina="Matemática",
                observacoes="Dificuldade em frações",
                endereco="Rua das Flores, 20",
                responsavel_nome="Carla Lima",
                responsavel_telefone="83977776666",
                responsavel_email="carla@example.com",
                responsavel_parentesco="Mãe",
            )
        )
        html = logado.get(reverse("alunos:detalhe", args=[aluno.pk])).content.decode()
        for texto in [
            "9º ano", "Escola Estadual Lyceu", "Dificuldade em frações", "Rua das Flores, 20",
            "Carla Lima", "83977776666", "carla@example.com", "Mãe", "(14 anos)",
        ]:
            assert texto in html

    def test_ficha_sem_responsavel_mostra_aviso_neutro(self, logado, professor):
        aluno = salvar(novo_aluno(professor))
        html = logado.get(reverse("alunos:detalhe", args=[aluno.pk])).content.decode()
        assert "Nenhum responsável cadastrado." in html
        assert "menor de idade sem responsável" not in html

    def test_ficha_alerta_menor_legado_sem_responsavel(self, logado, professor):
        """Alunos cadastrados antes da regra continuam acessíveis, com alerta."""
        aluno = salvar(novo_aluno(professor))
        Aluno.objects.filter(pk=aluno.pk).update(data_nascimento=anos_atras(10))
        html = logado.get(reverse("alunos:detalhe", args=[aluno.pk])).content.decode()
        assert "Aluno menor de idade sem responsável cadastrado." in html
