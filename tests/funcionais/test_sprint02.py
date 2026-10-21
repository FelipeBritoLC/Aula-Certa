"""
Casos de teste funcionais da Sprint 02 (CT29–CT50).

Cada teste corresponde a um caso da "Especificação dos Casos de Teste
Funcionais — Sprints 01 e 02" e percorre o sistema pelas telas (cliente
HTTP do Django com login real). O nome de cada teste começa pelo ID do caso.
"""
from datetime import timedelta

from django.utils import timezone

from agenda.models import Aula
from alunos.models import Aluno

from .apoio import (  # noqa: F401 (fixtures)
    CONTEUDO_VALIDO,
    criar_aluno,
    criar_aula,
    form_agendamento,
    form_aluno,
    hasher_rapido,
    horario,
    mover_para,
    navegador,
    outro_professor,
    professor,
)


def anos_atras(anos):
    hoje = timezone.localdate()
    try:
        return hoje.replace(year=hoje.year - anos)
    except ValueError:
        return hoje.replace(year=hoje.year - anos, day=28)


def dados_de_edicao(navegador, aluno, **alteracoes):
    """O formulário de edição como o navegador o enviaria, com alterações."""
    form = navegador.get(f"/alunos/{aluno.pk}/editar/").context["form"]
    dados = {nome: ("" if form[nome].value() is None else form[nome].value()) for nome in form.fields}
    if aluno.data_nascimento:
        dados["data_nascimento"] = aluno.data_nascimento.isoformat()
    dados.update(alteracoes)
    return dados


def form_edicao_aula(inicio, duracao=60, modalidade="PRESENCIAL", local=""):
    return {
        "data_hora_inicio": inicio.strftime("%Y-%m-%dT%H:%M"),
        "duracao_minutos": duracao,
        "modalidade": modalidade,
        "local": local,
    }


# ---------------------------------------------------------------- US 30325
class TestUS30325AlterarDadosDoAluno:
    def test_ct29_alterar_dados_preservando_os_demais(self, navegador, professor):
        aluno = criar_aluno(professor, endereco="Rua das Flores, 20", escola="Escola A")
        resposta = navegador.post(
            f"/alunos/{aluno.pk}/editar/", dados_de_edicao(navegador, aluno, telefone="83911112222")
        )
        assert resposta.status_code == 302
        aluno.refresh_from_db()
        assert aluno.telefone == "83911112222"
        assert aluno.endereco == "Rua das Flores, 20"
        assert aluno.escola == "Escola A"

    def test_ct30_alterar_para_cpf_de_outro_aluno(self, navegador, professor):
        criar_aluno(professor, nome="Outro", cpf="11122233344")
        aluno = criar_aluno(professor)
        resposta = navegador.post(
            f"/alunos/{aluno.pk}/editar/", dados_de_edicao(navegador, aluno, cpf="111.222.333-44")
        )
        assert resposta.status_code == 200
        assert "Já existe um aluno cadastrado com este CPF." in resposta.content.decode()
        aluno.refresh_from_db()
        assert aluno.cpf == "12345678901"

    def test_ct31_apagar_campo_obrigatorio(self, navegador, professor):
        aluno = criar_aluno(professor)
        resposta = navegador.post(f"/alunos/{aluno.pk}/editar/", dados_de_edicao(navegador, aluno, telefone=""))
        assert resposta.status_code == 200
        assert "telefone" in resposta.context["form"].errors
        aluno.refresh_from_db()
        assert aluno.telefone == "83999999999"

    def test_ct32_inativar_aluno_com_aulas_futuras(self, navegador, professor):
        aluno = criar_aluno(professor)
        aula = criar_aula(professor, aluno)
        resposta = navegador.post(
            f"/alunos/{aluno.pk}/editar/", dados_de_edicao(navegador, aluno, situacao="INATIVO"), follow=True
        )
        assert "1 aula(s) agendada(s)" in resposta.content.decode()
        aula.refresh_from_db()
        assert aula.status == Aula.Status.AGENDADA
        assert "Aluno inativo" in resposta.content.decode()

    def test_ct33_aluno_inativado_nao_recebe_novo_agendamento(self, navegador, professor):
        aluno = criar_aluno(professor)
        navegador.post(f"/alunos/{aluno.pk}/editar/", dados_de_edicao(navegador, aluno, situacao="INATIVO"))
        assert aluno not in navegador.get("/agenda/nova/").context["form"].fields["aluno"].queryset
        resposta = navegador.post("/agenda/nova/", form_agendamento(aluno, horario(dias=3)))
        assert resposta.status_code == 200
        assert not Aula.objects.exists()

    def test_ct34_aluno_de_outro_professor_nao_pode_ser_editado(self, navegador, outro_professor):
        alheio = criar_aluno(outro_professor)
        assert navegador.get(f"/alunos/{alheio.pk}/editar/").status_code == 404
        assert navegador.post(f"/alunos/{alheio.pk}/editar/", form_aluno(nome="Invasor")).status_code == 404
        alheio.refresh_from_db()
        assert alheio.nome == "Maria Silva"


# ---------------------------------------------------------------- US 30322
class TestUS30322DadosComplementares:
    def test_ct35_menor_de_idade_sem_responsavel(self, navegador):
        resposta = navegador.post("/alunos/novo/", form_aluno(data_nascimento=anos_atras(12).isoformat()))
        assert resposta.status_code == 200
        erros = resposta.context["form"].errors
        assert {"responsavel_nome", "responsavel_telefone"} <= set(erros)
        assert not Aluno.objects.exists()

    def test_ct36_menor_de_idade_com_responsavel(self, navegador):
        resposta = navegador.post(
            "/alunos/novo/",
            form_aluno(
                data_nascimento=anos_atras(12).isoformat(),
                responsavel_nome="Carla Lima",
                responsavel_telefone="83977776666",
                responsavel_parentesco="Mãe",
            ),
        )
        assert resposta.status_code == 302
        assert Aluno.objects.get().responsavel_nome == "Carla Lima"

    def test_ct37_data_de_nascimento_no_futuro(self, navegador):
        amanha = timezone.localdate() + timedelta(days=1)
        resposta = navegador.post("/alunos/novo/", form_aluno(data_nascimento=amanha.isoformat()))
        assert resposta.status_code == 200
        assert "não pode estar no futuro" in resposta.content.decode()
        assert not Aluno.objects.exists()

    def test_ct38_ficha_exibe_dados_complementares(self, navegador, professor):
        aluno = criar_aluno(
            professor,
            data_nascimento=anos_atras(14),
            serie_nivel="9º ano",
            escola="Escola Estadual Lyceu",
            responsavel_nome="Carla Lima",
            responsavel_telefone="83977776666",
            responsavel_parentesco="Mãe",
        )
        ficha = navegador.get(f"/alunos/{aluno.pk}/").content.decode()
        for texto in ["Dados acadêmicos", "9º ano", "Escola Estadual Lyceu", "Responsável", "Carla Lima", "Mãe", "(14 anos)"]:
            assert texto in ficha, texto


# ---------------------------------------------------------------- US 30333
class TestUS30333DefinirInformacoesDaAula:
    def test_ct39_editar_informacoes_da_aula_agendada(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor), horario(hora=14))
        novo = horario(hora=16)
        resposta = navegador.post(
            f"/agenda/{aula.pk}/editar/", form_edicao_aula(novo, 90, "ONLINE", "Google Meet")
        )
        assert resposta.status_code == 302
        aula.refresh_from_db()
        assert timezone.localtime(aula.data_hora_inicio) == novo
        assert (aula.duracao_minutos, aula.modalidade, aula.local) == (90, "ONLINE", "Google Meet")

    def test_ct40_edicao_que_gera_conflito(self, navegador, professor):
        aluno = criar_aluno(professor)
        criar_aula(professor, aluno, horario(hora=10))
        aula = criar_aula(professor, aluno, horario(hora=14))
        resposta = navegador.post(f"/agenda/{aula.pk}/editar/", form_edicao_aula(horario(hora=10, minuto=30)))
        assert resposta.status_code == 200
        assert "Conflito de horário" in resposta.content.decode()
        aula.refresh_from_db()
        assert timezone.localtime(aula.data_hora_inicio).hour == 14

    def test_ct41_aula_nao_agendada_nao_pode_ser_editada(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        aula.registrar_como_realizada(CONTEUDO_VALIDO)
        resposta = navegador.post(f"/agenda/{aula.pk}/editar/", form_edicao_aula(horario(hora=18)), follow=True)
        assert "Somente aulas com status Agendada podem ser editadas." in resposta.content.decode()
        aula.refresh_from_db()
        assert timezone.localtime(aula.data_hora_inicio).hour == 14

    def test_ct42_novo_horario_retroativo(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        ontem = timezone.localtime() - timedelta(days=1)
        resposta = navegador.post(f"/agenda/{aula.pk}/editar/", form_edicao_aula(ontem))
        assert resposta.status_code == 200
        assert "retroativa" in resposta.content.decode()


# ---------------------------------------------------------------- US 30337
class TestUS30337ConsultarAgenda:
    def test_ct43_visao_diaria(self, navegador, professor):
        aluno = criar_aluno(professor)
        outro = criar_aluno(professor, nome="Bruno Lima", cpf="11122233344")
        aula = criar_aula(professor, aluno, horario(dias=2, hora=9))
        criar_aula(professor, outro, horario(dias=3, hora=9))
        dia = timezone.localtime(aula.data_hora_inicio).date()
        html = navegador.get("/agenda/", {"visao": "dia", "data": dia.isoformat()}).content.decode()
        assert "Maria Silva" in html
        assert "Bruno Lima" not in html

    def test_ct44_visao_semanal_e_navegacao(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor), horario(dias=2, hora=9))
        dia = timezone.localtime(aula.data_hora_inicio).date()
        resposta = navegador.get("/agenda/", {"visao": "semana", "data": dia.isoformat()})
        assert "Maria Silva" in resposta.content.decode()
        assert len(resposta.context["dias"]) == 7
        seguinte = navegador.get(resposta.context["url_proxima"])
        assert seguinte.context["inicio"] == resposta.context["inicio"] + timedelta(days=7)
        assert "Maria Silva" not in seguinte.content.decode()

    def test_ct45_visao_mensal(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor), horario(dias=2, hora=9))
        dia = timezone.localtime(aula.data_hora_inicio).date()
        resposta = navegador.get("/agenda/", {"visao": "mes", "data": dia.isoformat()})
        assert resposta.status_code == 200
        assert 4 <= len(resposta.context["semanas"]) <= 6
        assert "Maria Silva" in resposta.content.decode()

    def test_ct46_filtro_e_indicacao_visual_de_status(self, navegador, professor):
        aluno = criar_aluno(professor)
        realizada = criar_aula(professor, aluno, horario(dias=2, hora=9))
        criar_aula(professor, aluno, horario(dias=2, hora=11))
        realizada.registrar_como_realizada(CONTEUDO_VALIDO)
        dia = timezone.localtime(realizada.data_hora_inicio).date()

        todas = navegador.get("/agenda/", {"visao": "dia", "data": dia.isoformat()}).content.decode()
        assert "aula--realizada" in todas and "aula--agendada" in todas
        filtrada = navegador.get("/agenda/", {"visao": "dia", "data": dia.isoformat(), "status": "REALIZADA"})
        assert filtrada.context["total_aulas"] == 1
        assert "status=REALIZADA" in filtrada.context["url_proxima"]


# ---------------------------------------------------------------- US 30339
class TestUS30339DetalhesDaAulaRealizada:
    def test_ct47_registrar_aula_com_detalhes(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        navegador.post(
            f"/agenda/{aula.pk}/registrar/",
            {
                "conteudo_trabalhado": CONTEUDO_VALIDO,
                "material_utilizado": "Lista 2",
                "avaliacao_desempenho": "BOM",
                "recomendacoes": "Revisar MMC.",
            },
        )
        detalhe = navegador.get(f"/agenda/{aula.pk}/").content.decode()
        for texto in ["Lista 2", "Bom", "Revisar MMC."]:
            assert texto in detalhe, texto

    def test_ct48_informar_detalhes_depois_do_registro(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        aula.registrar_como_realizada(CONTEUDO_VALIDO)
        assert "Informar detalhes" in navegador.get(f"/agenda/{aula.pk}/").content.decode()
        resposta = navegador.post(
            f"/agenda/{aula.pk}/detalhes/",
            {"material_utilizado": "Jogo de frações", "avaliacao_desempenho": "OTIMO", "recomendacoes": ""},
        )
        assert resposta.status_code == 302
        aula.refresh_from_db()
        assert (aula.material_utilizado, aula.avaliacao_desempenho) == ("Jogo de frações", "OTIMO")
        assert aula.conteudo_trabalhado == CONTEUDO_VALIDO

    def test_ct49_detalhes_bloqueados_em_aula_nao_realizada(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        resposta = navegador.post(
            f"/agenda/{aula.pk}/detalhes/",
            {"material_utilizado": "X", "avaliacao_desempenho": "BOM", "recomendacoes": "Y"},
            follow=True,
        )
        assert "só podem ser informados em aulas realizadas" in resposta.content.decode()
        aula.refresh_from_db()
        assert not aula.tem_detalhes

    def test_ct50_historico_na_ficha_do_aluno(self, navegador, professor):
        aluno = criar_aluno(professor)
        aula = criar_aula(professor, aluno)
        aula.registrar_como_realizada(
            CONTEUDO_VALIDO, material_utilizado="Apostila 2", avaliacao_desempenho="OTIMO",
            recomendacoes="Fazer simulado",
        )
        ficha = navegador.get(f"/alunos/{aluno.pk}/").content.decode()
        for texto in ["Histórico de aulas realizadas", "Frações", "Desempenho: Ótimo", "Apostila 2", "Fazer simulado"]:
            assert texto in ficha, texto
