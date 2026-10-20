"""
US-30337 — Consultar agenda de aulas.

CA-CAG-01: visualização diária, semanal e mensal.
CA-CAG-02: aluno, horário e status visíveis, com indicação visual por status.
CA-CAG-03: navegação entre períodos mantém o filtro de status.

Datas fixas: 21/09/2026 é uma segunda-feira, então a semana de teste vai de
21/09 a 27/09. As aulas são criadas direto no banco (sem full_clean) porque
estão no passado — aqui só a consulta importa, não o agendamento.
"""
import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from agenda import visoes
from agenda.models import Aula
from alunos.models import Aluno

URL = reverse("agenda:listar")


@pytest.fixture
def professor(db):
    return User.objects.create_user(username="prof1", password="senha123")


@pytest.fixture
def outro_professor(db):
    return User.objects.create_user(username="prof2", password="senha123")


def _aluno(professor, nome="Maria Silva", cpf="12345678901"):
    aluno = Aluno(professor=professor, nome=nome, cpf=cpf, telefone="83999999999")
    aluno.full_clean()
    aluno.save()
    return aluno


@pytest.fixture
def aluno(professor):
    return _aluno(professor)


@pytest.fixture
def logado(client, professor):
    client.force_login(professor)
    return client


def aula(professor, aluno, dia, hora=10, minuto=0, status=Aula.Status.AGENDADA, **kwargs):
    """Cria uma aula no horário LOCAL (America/Sao_Paulo) informado."""
    inicio = timezone.make_aware(datetime(dia.year, dia.month, dia.day, hora, minuto))
    return Aula.objects.create(
        professor=professor, aluno=aluno, data_hora_inicio=inicio, status=status, **kwargs
    )


def ids_do_periodo(contexto):
    """IDs de todas as aulas exibidas, em qualquer visão."""
    celulas = contexto["dias"] if "dias" in contexto else [c for s in contexto["semanas"] for c in s]
    return {a.pk for c in celulas for a in c["aulas"]}


def consulta(url):
    return {chave: valor[0] for chave, valor in parse_qs(urlparse(url).query).items()}


# ---------------------------------------------------------------------------
# CA-CAG-01 — três visões
# ---------------------------------------------------------------------------
class TestVisaoSemanal:
    def test_sanity_21_09_2026_e_segunda_feira(self):
        assert date(2026, 9, 21).weekday() == 0

    def test_visao_padrao_e_a_semanal(self, logado):
        resposta = logado.get(URL)

        assert resposta.status_code == 200
        assert resposta.context["visao"] == "semana"

    def test_cenario_visualizar_agenda_semanal_agrupada_por_dia(self, logado, professor, aluno):
        segunda = aula(professor, aluno, date(2026, 9, 21), 8)
        quarta_a = aula(professor, aluno, date(2026, 9, 23), 9)
        quarta_b = aula(professor, aluno, date(2026, 9, 23), 15)

        contexto = logado.get(URL, {"visao": "semana", "data": "2026-09-23"}).context

        dias = contexto["dias"]
        assert [d["data"] for d in dias] == [date(2026, 9, 21) + timedelta(days=i) for i in range(7)]
        assert [a.pk for a in dias[0]["aulas"]] == [segunda.pk]
        assert [a.pk for a in dias[2]["aulas"]] == [quarta_a.pk, quarta_b.pk]  # em ordem de horário
        assert contexto["total_aulas"] == 3

    def test_semana_vai_de_segunda_a_domingo(self, logado, professor, aluno):
        domingo_anterior = aula(professor, aluno, date(2026, 9, 20), 10)
        segunda = aula(professor, aluno, date(2026, 9, 21), 0, 5)
        domingo = aula(professor, aluno, date(2026, 9, 27), 23, 55)
        segunda_seguinte = aula(professor, aluno, date(2026, 9, 28), 0, 5)

        contexto = logado.get(URL, {"visao": "semana", "data": "2026-09-24"}).context

        assert contexto["inicio"] == date(2026, 9, 21)
        assert contexto["fim"] == date(2026, 9, 27)
        assert ids_do_periodo(contexto) == {segunda.pk, domingo.pk}
        assert domingo_anterior.pk not in ids_do_periodo(contexto)
        assert segunda_seguinte.pk not in ids_do_periodo(contexto)

    def test_aula_noturna_pertence_ao_dia_local_e_nao_ao_dia_utc(self, logado, professor, aluno):
        # 23h30 de domingo em São Paulo já é segunda 02h30 em UTC.
        noturna = aula(professor, aluno, date(2026, 9, 27), 23, 30)
        assert timezone.localtime(noturna.data_hora_inicio).day == 27

        contexto = logado.get(URL, {"visao": "semana", "data": "2026-09-23"}).context

        assert [a.pk for a in contexto["dias"][6]["aulas"]] == [noturna.pk]


class TestVisaoDiaria:
    def test_mostra_somente_as_aulas_do_dia(self, logado, professor, aluno):
        do_dia = aula(professor, aluno, date(2026, 9, 22), 14)
        aula(professor, aluno, date(2026, 9, 21), 14)
        aula(professor, aluno, date(2026, 9, 23), 14)

        contexto = logado.get(URL, {"visao": "dia", "data": "2026-09-22"}).context

        assert len(contexto["dias"]) == 1
        assert ids_do_periodo(contexto) == {do_dia.pk}

    def test_mostra_modalidade_e_local_no_detalhe_do_dia(self, logado, professor, aluno):
        aula(professor, aluno, date(2026, 9, 22), 14, modalidade="ONLINE", local="meet.example.com/x")

        html = logado.get(URL, {"visao": "dia", "data": "2026-09-22"}).content.decode()

        assert "Online" in html
        assert "meet.example.com/x" in html


class TestVisaoMensal:
    def test_mostra_apenas_as_aulas_do_mes(self, logado, professor, aluno):
        aula(professor, aluno, date(2026, 8, 31), 10)  # mês anterior
        no_inicio = aula(professor, aluno, date(2026, 9, 1), 10)
        no_fim = aula(professor, aluno, date(2026, 9, 30), 23, 30)
        aula(professor, aluno, date(2026, 10, 1), 0, 10)  # mês seguinte

        contexto = logado.get(URL, {"visao": "mes", "data": "2026-09-15"}).context

        assert ids_do_periodo(contexto) == {no_inicio.pk, no_fim.pk}
        assert contexto["total_aulas"] == 2

    def test_grade_tem_semanas_completas_de_sete_dias_comecando_na_segunda(self, logado):
        contexto = logado.get(URL, {"visao": "mes", "data": "2026-09-15"}).context

        semanas = contexto["semanas"]
        assert all(len(s) == 7 for s in semanas)
        assert all(s[0]["data"].weekday() == 0 for s in semanas)
        assert semanas[0][1]["data"] == date(2026, 9, 1)  # 01/09/2026 é terça

    def test_dias_de_outro_mes_aparecem_marcados_e_sem_aulas(self, logado, professor, aluno):
        aula(professor, aluno, date(2026, 8, 31), 10)

        contexto = logado.get(URL, {"visao": "mes", "data": "2026-09-15"}).context

        primeira_celula = contexto["semanas"][0][0]
        assert primeira_celula["data"] == date(2026, 8, 31)
        assert primeira_celula["no_mes"] is False
        assert primeira_celula["aulas"] == []

    def test_renderiza_o_nome_do_mes_em_portugues(self, logado):
        html = logado.get(URL, {"visao": "mes", "data": "2026-09-15"}).content.decode()

        assert "Setembro de 2026" in html


class TestRotuloDoPeriodo:
    """Mês em minúsculas no meio da frase, como se escreve em português."""

    def test_rotulo_do_dia(self, logado):
        html = logado.get(URL, {"visao": "dia", "data": "2026-09-22"}).content.decode()
        assert "Terça-feira, 22 de setembro de 2026" in html

    def test_rotulo_da_semana(self, logado):
        html = logado.get(URL, {"visao": "semana", "data": "2026-09-22"}).content.decode()
        assert "21 de setembro a 27 de setembro de 2026" in html


# ---------------------------------------------------------------------------
# CA-CAG-02 — aluno, horário e status visíveis, com indicação visual
# ---------------------------------------------------------------------------
class TestCaCag02ConteudoDaAula:
    @pytest.mark.parametrize("visao", ["dia", "semana", "mes"])
    def test_aluno_horario_e_status_aparecem_em_todas_as_visoes(
        self, logado, professor, aluno, visao
    ):
        aula(professor, aluno, date(2026, 9, 22), 14, 30, status=Aula.Status.REALIZADA)

        html = logado.get(URL, {"visao": visao, "data": "2026-09-22"}).content.decode()

        assert "Maria Silva" in html
        assert "14:30" in html
        assert "Realizada" in html

    @pytest.mark.parametrize(
        "status, classe, rotulo",
        [
            (Aula.Status.AGENDADA, "aula--agendada", "Agendada"),
            (Aula.Status.REALIZADA, "aula--realizada", "Realizada"),
            (Aula.Status.CANCELADA, "aula--cancelada", "Cancelada"),
            (Aula.Status.FALTA, "aula--falta", "Falta"),
        ],
    )
    def test_cada_status_tem_sua_classe_visual_e_seu_texto(
        self, logado, professor, aluno, status, classe, rotulo
    ):
        a = aula(professor, aluno, date(2026, 9, 22), 14, status=status)

        html = logado.get(URL, {"visao": "semana", "data": "2026-09-22"}).content.decode()

        url = re.escape(reverse("agenda:detalhe", args=[a.pk]))
        chip = re.search(
            rf'<a class="aula-chip {classe}"\s+href="{url}".*?</a>', html, flags=re.DOTALL
        )
        assert chip, f"chip com a classe {classe} não encontrado"
        assert rotulo in chip.group(0)

    def test_cada_aula_leva_para_a_ficha(self, logado, professor, aluno):
        a = aula(professor, aluno, date(2026, 9, 22), 14)

        html = logado.get(URL, {"visao": "semana", "data": "2026-09-22"}).content.decode()

        assert reverse("agenda:detalhe", args=[a.pk]) in html

    def test_mensagem_quando_nao_ha_aulas_no_periodo(self, logado):
        html = logado.get(URL, {"visao": "semana", "data": "2026-09-22"}).content.decode()

        assert "Nenhuma aula" in html


# ---------------------------------------------------------------------------
# Filtro por status e isolamento entre professores
# ---------------------------------------------------------------------------
class TestFiltroEIsolamento:
    def test_filtro_por_status(self, logado, professor, aluno):
        agendada = aula(professor, aluno, date(2026, 9, 21), 8, status=Aula.Status.AGENDADA)
        realizada = aula(professor, aluno, date(2026, 9, 22), 8, status=Aula.Status.REALIZADA)

        contexto = logado.get(
            URL, {"visao": "semana", "data": "2026-09-23", "status": "REALIZADA"}
        ).context

        assert ids_do_periodo(contexto) == {realizada.pk}
        assert agendada.pk not in ids_do_periodo(contexto)

    def test_nao_mostra_aulas_de_outro_professor(self, logado, professor, outro_professor, aluno):
        minha = aula(professor, aluno, date(2026, 9, 22), 8)
        aluno_alheio = _aluno(outro_professor, nome="Aluno Alheio", cpf="98765432100")
        aula(outro_professor, aluno_alheio, date(2026, 9, 22), 9)

        resposta = logado.get(URL, {"visao": "semana", "data": "2026-09-23"})

        assert ids_do_periodo(resposta.context) == {minha.pk}
        assert "Aluno Alheio" not in resposta.content.decode()

    def test_acesso_sem_login_redireciona_para_o_login(self, client):
        resposta = client.get(URL)

        assert resposta.status_code == 302
        assert "/login/" in resposta.url


class TestParametrosInvalidos:
    def test_visao_invalida_cai_na_semanal(self, logado):
        assert logado.get(URL, {"visao": "ano"}).context["visao"] == "semana"

    def test_status_invalido_e_ignorado(self, logado, professor, aluno):
        a = aula(professor, aluno, date(2026, 9, 22), 8)

        contexto = logado.get(
            URL, {"visao": "semana", "data": "2026-09-22", "status": "QUALQUER"}
        ).context

        assert contexto["status_selecionado"] == ""
        assert ids_do_periodo(contexto) == {a.pk}

    @pytest.mark.parametrize("data", ["lixo", "2026-13-45", "31/12/2026", ""])
    def test_data_invalida_cai_em_hoje(self, logado, data):
        resposta = logado.get(URL, {"data": data})

        assert resposta.status_code == 200
        assert resposta.context["data"] == timezone.localdate()

    def test_hoje_aparece_destacado_na_semana_corrente(self, logado):
        contexto = logado.get(URL, {"visao": "semana"}).context

        assert sum(1 for d in contexto["dias"] if d["hoje"]) == 1


# ---------------------------------------------------------------------------
# CA-CAG-03 — navegação mantém o filtro de status
# ---------------------------------------------------------------------------
class TestCaCag03NavegacaoPreservaFiltro:
    def test_periodo_anterior_e_proximo_mantem_status_e_visao(self, logado):
        contexto = logado.get(
            URL, {"visao": "semana", "data": "2026-09-23", "status": "AGENDADA"}
        ).context

        proxima, anterior = consulta(contexto["url_proxima"]), consulta(contexto["url_anterior"])
        assert proxima == {"visao": "semana", "data": "2026-09-30", "status": "AGENDADA"}
        assert anterior == {"visao": "semana", "data": "2026-09-16", "status": "AGENDADA"}

    def test_botao_hoje_mantem_status(self, logado):
        contexto = logado.get(URL, {"visao": "mes", "status": "FALTA"}).context

        hoje = consulta(contexto["url_hoje"])
        assert hoje["status"] == "FALTA"
        assert hoje["data"] == timezone.localdate().isoformat()

    def test_cenario_alternar_visoes_mantem_o_filtro_aplicado(self, logado):
        """BDD: semanal aberta -> troca para mensal -> mesmo filtro de status."""
        contexto = logado.get(
            URL, {"visao": "semana", "data": "2026-09-23", "status": "AGENDADA"}
        ).context

        links = {v["valor"]: consulta(v["url"]) for v in contexto["visoes"]}
        assert set(links) == {"dia", "semana", "mes"}
        for valor, params in links.items():
            assert params == {"visao": valor, "data": "2026-09-23", "status": "AGENDADA"}

    def test_trocar_o_filtro_mantem_visao_e_data(self, logado):
        contexto = logado.get(URL, {"visao": "mes", "data": "2026-09-23"}).context

        links = {f["valor"]: consulta(f["url"]) for f in contexto["filtros_status"]}
        assert links["REALIZADA"] == {"visao": "mes", "data": "2026-09-23", "status": "REALIZADA"}
        assert links[""] == {"visao": "mes", "data": "2026-09-23"}  # "Todas" tira o filtro

    def test_clicar_num_dia_abre_a_visao_diaria_com_o_mesmo_filtro(self, logado):
        contexto = logado.get(
            URL, {"visao": "semana", "data": "2026-09-23", "status": "FALTA"}
        ).context

        quarta = consulta(contexto["dias"][2]["url_dia"])
        assert quarta == {"visao": "dia", "data": "2026-09-23", "status": "FALTA"}

    def test_o_filtro_ativo_e_marcado_na_tela(self, logado):
        contexto = logado.get(URL, {"status": "FALTA"}).context

        ativos = [f["valor"] for f in contexto["filtros_status"] if f["ativo"]]
        assert ativos == ["FALTA"]


# ---------------------------------------------------------------------------
# Cálculo de períodos (funções puras)
# ---------------------------------------------------------------------------
class TestCalculoDePeriodos:
    @pytest.mark.parametrize(
        "visao, ref, sentido, esperado",
        [
            ("dia", date(2026, 9, 22), +1, date(2026, 9, 23)),
            ("dia", date(2026, 9, 1), -1, date(2026, 8, 31)),
            ("semana", date(2026, 9, 23), +1, date(2026, 9, 30)),
            ("semana", date(2026, 9, 23), -1, date(2026, 9, 16)),
            ("mes", date(2026, 9, 23), +1, date(2026, 10, 1)),
            ("mes", date(2026, 9, 23), -1, date(2026, 8, 1)),
            ("mes", date(2026, 12, 15), +1, date(2027, 1, 1)),   # virada de ano
            ("mes", date(2027, 1, 31), -1, date(2026, 12, 1)),   # virada de ano
            ("mes", date(2026, 1, 31), +1, date(2026, 2, 1)),    # 31 -> mês curto
            ("mes", date(2026, 3, 31), -1, date(2026, 2, 1)),
        ],
    )
    def test_deslocar(self, visao, ref, sentido, esperado):
        assert visoes.deslocar(visao, ref, sentido) == esperado

    @pytest.mark.parametrize(
        "visao, ref, inicio, fim",
        [
            ("dia", date(2026, 9, 22), date(2026, 9, 22), date(2026, 9, 22)),
            ("semana", date(2026, 9, 21), date(2026, 9, 21), date(2026, 9, 27)),  # segunda
            ("semana", date(2026, 9, 27), date(2026, 9, 21), date(2026, 9, 27)),  # domingo
            ("mes", date(2026, 9, 10), date(2026, 9, 1), date(2026, 9, 30)),
            ("mes", date(2028, 2, 10), date(2028, 2, 1), date(2028, 2, 29)),      # bissexto
            ("mes", date(2026, 12, 31), date(2026, 12, 1), date(2026, 12, 31)),
        ],
    )
    def test_periodo(self, visao, ref, inicio, fim):
        assert visoes.periodo(visao, ref) == (inicio, fim)


# ---------------------------------------------------------------------------
# Desempenho: sem consulta extra por aula (N+1)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("visao", ["dia", "semana", "mes"])
def test_numero_de_consultas_nao_cresce_com_a_quantidade_de_aulas(
    logado, professor, django_assert_max_num_queries, visao
):
    for i in range(12):
        aluno_i = _aluno(professor, nome=f"Aluno {i}", cpf=f"100000000{i:02d}")
        aula(professor, aluno_i, date(2026, 9, 22), 6 + i)

    with django_assert_max_num_queries(6):
        resposta = logado.get(URL, {"visao": visao, "data": "2026-09-22"})

    assert resposta.status_code == 200
    assert "Aluno 11" in resposta.content.decode()
