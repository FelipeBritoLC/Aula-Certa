"""
US-30358 / Task 32587 — testes funcionais das telas de cadastro e consulta
de alunos (US-30321 e US-30323), que só tinham testes de regra no model.
"""
import pytest
from django.urls import reverse

from alunos.models import Aluno


def criar_aluno(professor, nome="Maria Silva", cpf="12345678901", **kwargs):
    aluno = Aluno(professor=professor, nome=nome, cpf=cpf, telefone="83999999999", **kwargs)
    aluno.full_clean()
    aluno.save()
    return aluno


def dados(**extra):
    base = {"nome": "Maria Silva", "cpf": "123.456.789-01", "telefone": "83999999999", "situacao": "ATIVO"}
    base.update(extra)
    return base


class TestCadastroPelaTela:
    def test_get_exibe_formulario(self, logado):
        resposta = logado.get(reverse("alunos:cadastrar"))
        assert resposta.status_code == 200
        assert resposta.context["titulo"] == "Cadastrar aluno"

    def test_cadastrar_com_sucesso(self, logado, professor):
        resposta = logado.post(reverse("alunos:cadastrar"), dados())
        aluno = Aluno.objects.get()
        assert resposta.status_code == 302
        assert resposta.url == reverse("alunos:detalhe", args=[aluno.pk])
        assert aluno.professor == professor
        assert aluno.cpf == "12345678901"

    def test_cpf_duplicado_exibe_erro(self, logado, professor):
        criar_aluno(professor)
        resposta = logado.post(reverse("alunos:cadastrar"), dados(nome="Outra Pessoa"))
        assert resposta.status_code == 200
        assert "Já existe um aluno cadastrado com este CPF." in resposta.content.decode()
        assert Aluno.objects.count() == 1

    def test_campos_obrigatorios_vazios(self, logado):
        resposta = logado.post(reverse("alunos:cadastrar"), dados(nome="", telefone=""))
        assert resposta.status_code == 200
        assert not Aluno.objects.exists()


class TestConsultaPelaTela:
    def test_filtro_por_situacao(self, logado, professor):
        criar_aluno(professor, nome="Ativa")
        criar_aluno(professor, nome="Inativa", cpf="11122233344", situacao=Aluno.Situacao.INATIVO)
        resposta = logado.get(reverse("alunos:listar"), {"situacao": "INATIVO"})
        assert [a.nome for a in resposta.context["page_obj"]] == ["Inativa"]

    def test_paginacao_de_10_em_10(self, logado, professor):
        for i in range(12):
            criar_aluno(professor, nome=f"Aluno {i:02d}", cpf=f"{i:011d}")
        primeira = logado.get(reverse("alunos:listar"))
        segunda = logado.get(reverse("alunos:listar"), {"page": 2})
        assert len(primeira.context["page_obj"]) == 10
        assert len(segunda.context["page_obj"]) == 2

    def test_ficha_de_aluno_de_outro_professor_retorna_404(self, logado, outro_professor):
        alheio = criar_aluno(outro_professor)
        assert logado.get(reverse("alunos:detalhe", args=[alheio.pk])).status_code == 404

    @pytest.mark.parametrize("rota", ["alunos:listar", "alunos:cadastrar"])
    def test_exige_login(self, client, db, rota):
        resposta = client.get(reverse(rota))
        assert resposta.status_code == 302
        assert "/login/" in resposta.url
