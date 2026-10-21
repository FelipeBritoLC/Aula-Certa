"""
Casos de teste funcionais da Sprint 01 (CT01–CT28).

Cada teste corresponde a um caso da "Especificação dos Casos de Teste
Funcionais — Sprints 01 e 02" e percorre o sistema pelas telas (cliente
HTTP do Django com login real). O nome de cada teste começa pelo ID do caso.
"""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from agenda.models import Aula
from alunos.models import Aluno
from financeiro.models import Mensalidade, Pagamento

from .apoio import (  # noqa: F401 (fixtures)
    CONTEUDO_VALIDO,
    SENHA,
    criar_aluno,
    criar_aula,
    criar_mensalidade,
    form_agendamento,
    form_aluno,
    hasher_rapido,
    horario,
    mover_para,
    navegador,
    outro_professor,
    professor,
)


# ---------------------------------------------------------------- US 30356
class TestUS30356AcessoAoSistema:
    def test_ct01_login_com_credenciais_validas(self, client, professor):
        resposta = client.post("/login/", {"username": "professor", "password": SENHA})
        assert resposta.status_code == 302
        assert client.get("/").status_code == 200

    def test_ct02_login_com_senha_invalida(self, client, professor):
        resposta = client.post("/login/", {"username": "professor", "password": "errada"})
        assert resposta.status_code == 200
        assert resposta.context["form"].errors
        assert client.get("/").status_code == 302

    def test_ct03_paginas_internas_exigem_login(self, client, db):
        for url in ["/", "/alunos/", "/alunos/novo/", "/agenda/", "/agenda/nova/",
                    "/financeiro/mensalidades/", "/financeiro/inadimplentes/"]:
            resposta = client.get(url)
            assert resposta.status_code == 302, url
            assert "/login/" in resposta.url, url
        assert client.get("/api/dashboard/estatisticas/").status_code == 401


# ---------------------------------------------------------------- US 30321
class TestUS30321CadastrarAluno:
    def test_ct04_cadastrar_aluno_com_dados_validos(self, navegador):
        resposta = navegador.post("/alunos/novo/", form_aluno(email="maria@example.com"))
        aluno = Aluno.objects.get()
        assert resposta.status_code == 302
        assert resposta.url == f"/alunos/{aluno.pk}/"
        ficha = navegador.get(resposta.url).content.decode()
        assert "Maria Silva" in ficha and "12345678901" in ficha

    def test_ct05_cpf_ja_cadastrado_para_o_professor(self, navegador, professor):
        criar_aluno(professor)
        resposta = navegador.post("/alunos/novo/", form_aluno(nome="Outra Pessoa"))
        assert resposta.status_code == 200
        assert "Já existe um aluno cadastrado com este CPF." in resposta.content.decode()
        assert Aluno.objects.count() == 1

    def test_ct06_campos_obrigatorios_nao_preenchidos(self, navegador):
        resposta = navegador.post("/alunos/novo/", form_aluno(nome="", cpf="", telefone=""))
        assert resposta.status_code == 200
        erros = resposta.context["form"].errors
        assert {"nome", "cpf", "telefone"} <= set(erros)
        assert not Aluno.objects.exists()

    def test_ct07_nome_e_cpf_sao_padronizados(self, navegador):
        navegador.post("/alunos/novo/", form_aluno(nome="  Maria    Silva  ", cpf="123.456.789-01"))
        aluno = Aluno.objects.get()
        assert aluno.nome == "Maria Silva"
        assert aluno.cpf == "12345678901"

    def test_ct08_cpf_com_quantidade_invalida_de_digitos(self, navegador):
        resposta = navegador.post("/alunos/novo/", form_aluno(cpf="1234567890"))
        assert resposta.status_code == 200
        assert "CPF deve conter 11 dígitos." in resposta.content.decode()
        assert not Aluno.objects.exists()


# ---------------------------------------------------------------- US 30323
class TestUS30323ConsultarAlunos:
    def test_ct09_listagem_exibe_apenas_alunos_do_professor(self, navegador, professor, outro_professor):
        criar_aluno(professor, nome="Aluno Meu")
        criar_aluno(outro_professor, nome="Aluno Alheio")
        html = navegador.get("/alunos/").content.decode()
        assert "Aluno Meu" in html
        assert "Aluno Alheio" not in html

    def test_ct10_filtro_por_nome(self, navegador, professor):
        criar_aluno(professor, nome="Ana Beatriz")
        criar_aluno(professor, nome="Bruno César", cpf="11122233344")
        resposta = navegador.get("/alunos/", {"nome": "bea"})
        assert [a.nome for a in resposta.context["page_obj"]] == ["Ana Beatriz"]

    def test_ct11_filtro_por_situacao(self, navegador, professor):
        criar_aluno(professor, nome="Ativa")
        criar_aluno(professor, nome="Inativa", cpf="11122233344", situacao=Aluno.Situacao.INATIVO)
        resposta = navegador.get("/alunos/", {"situacao": "INATIVO"})
        assert [a.nome for a in resposta.context["page_obj"]] == ["Inativa"]

    def test_ct12_paginacao_de_dez_alunos(self, navegador, professor):
        for i in range(12):
            criar_aluno(professor, nome=f"Aluno {i:02d}", cpf=f"{i:011d}")
        assert len(navegador.get("/alunos/").context["page_obj"]) == 10
        assert len(navegador.get("/alunos/", {"page": 2}).context["page_obj"]) == 2


# ---------------------------------------------------------------- US 30332
class TestUS30332CriarAgendamento:
    def test_ct13_agendar_aula_com_dados_validos(self, navegador, professor):
        aluno = criar_aluno(professor)
        inicio = horario(dias=2, hora=14)
        resposta = navegador.post("/agenda/nova/", form_agendamento(aluno, inicio))
        aula = Aula.objects.get()
        assert resposta.status_code == 302
        assert resposta.url == f"/agenda/{aula.pk}/"
        assert aula.status == Aula.Status.AGENDADA
        detalhe = navegador.get(resposta.url).content.decode()
        assert "Maria Silva" in detalhe
        assert inicio.strftime("%d/%m/%Y %H:%M") in detalhe

    def test_ct14_conflito_de_horario(self, navegador, professor):
        aluno = criar_aluno(professor)
        criar_aula(professor, aluno, horario(hora=14))
        resposta = navegador.post("/agenda/nova/", form_agendamento(aluno, horario(hora=14, minuto=30)))
        assert resposta.status_code == 200
        assert "Conflito de horário" in resposta.content.decode()
        assert Aula.objects.count() == 1

    def test_ct15_aluno_inativo_nao_pode_ser_agendado(self, navegador, professor):
        inativo = criar_aluno(professor, situacao=Aluno.Situacao.INATIVO)
        formulario = navegador.get("/agenda/nova/").context["form"]
        assert inativo not in formulario.fields["aluno"].queryset
        resposta = navegador.post("/agenda/nova/", form_agendamento(inativo, horario()))
        assert resposta.status_code == 200
        assert not Aula.objects.exists()

    def test_ct16_agendamento_retroativo(self, navegador, professor):
        aluno = criar_aluno(professor)
        ontem = timezone.localtime() - timedelta(days=1)
        resposta = navegador.post("/agenda/nova/", form_agendamento(aluno, ontem))
        assert resposta.status_code == 200
        assert "retroativa" in resposta.content.decode()
        assert not Aula.objects.exists()


# ---------------------------------------------------------------- US 30338
class TestUS30338RegistrarAulaRealizada:
    def test_ct17_registrar_aula_com_conteudo_valido(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        resposta = navegador.post(f"/agenda/{aula.pk}/registrar/", {"conteudo_trabalhado": CONTEUDO_VALIDO})
        assert resposta.status_code == 302
        aula.refresh_from_db()
        assert aula.status == Aula.Status.REALIZADA
        assert aula.data_registro is not None
        assert "Frações" in navegador.get(f"/agenda/{aula.pk}/").content.decode()

    def test_ct18_conteudo_com_menos_de_50_caracteres(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        tela = navegador.get(f"/agenda/{aula.pk}/registrar/").content.decode()
        assert 'minlength="50"' in tela
        assert 'id="btn-concluir" type="submit" class="btn btn-success" disabled' in tela
        resposta = navegador.post(f"/agenda/{aula.pk}/registrar/", {"conteudo_trabalhado": "Revisão rápida."})
        assert resposta.status_code == 200
        assert "pelo menos 50 caracteres" in resposta.content.decode()
        aula.refresh_from_db()
        assert aula.status == Aula.Status.AGENDADA

    def test_ct19_aula_ja_realizada_nao_e_registrada_novamente(self, navegador, professor):
        aula = criar_aula(professor, criar_aluno(professor))
        aula.registrar_como_realizada(CONTEUDO_VALIDO)
        resposta = navegador.get(f"/agenda/{aula.pk}/registrar/", follow=True)
        assert resposta.redirect_chain[-1][0] == f"/agenda/{aula.pk}/"
        assert "Somente aulas agendadas podem ser registradas" in resposta.content.decode()


# ---------------------------------------------------------------- US 30344
class TestUS30344RegistrarPagamento:
    def test_ct20_pagamento_total_quita_a_mensalidade(self, navegador, professor):
        aluno = criar_aluno(professor)
        Aluno.objects.filter(pk=aluno.pk).update(saldo_devedor=Decimal("300.00"))
        mensalidade = criar_mensalidade(aluno, "300.00")
        resposta = navegador.post(
            f"/financeiro/mensalidades/{mensalidade.pk}/pagar/",
            {"valor_pago": "300.00", "forma_pagamento": "PIX"},
        )
        assert resposta.status_code == 302
        mensalidade.refresh_from_db()
        aluno.refresh_from_db()
        assert mensalidade.status == Mensalidade.Status.PAGO
        assert aluno.saldo_devedor == Decimal("0.00")

    def test_ct21_pagamento_parcial(self, navegador, professor):
        mensalidade = criar_mensalidade(criar_aluno(professor), "300.00")
        navegador.post(
            f"/financeiro/mensalidades/{mensalidade.pk}/pagar/",
            {"valor_pago": "100.00", "forma_pagamento": "DINHEIRO"},
        )
        mensalidade.refresh_from_db()
        assert mensalidade.status == Mensalidade.Status.PENDENTE
        assert mensalidade.saldo == Decimal("200.00")

    def test_ct22_valor_zero_ou_negativo(self, navegador, professor):
        mensalidade = criar_mensalidade(criar_aluno(professor))
        for valor in ["0", "-50"]:
            resposta = navegador.post(
                f"/financeiro/mensalidades/{mensalidade.pk}/pagar/",
                {"valor_pago": valor, "forma_pagamento": "PIX"},
            )
            assert resposta.status_code == 200, valor
            assert "maior que zero" in resposta.content.decode(), valor
        assert not Pagamento.objects.exists()


# ---------------------------------------------------------------- US 30350
class TestUS30350IdentificarInadimplentes:
    def test_ct23_mensalidade_vencida_ha_mais_de_5_dias(self, navegador, professor):
        criar_mensalidade(criar_aluno(professor), vencimento_em_dias=-6)
        resposta = navegador.get("/financeiro/inadimplentes/")
        assert [i["aluno"].nome for i in resposta.context["inadimplentes"]] == ["Maria Silva"]

    def test_ct24_tolerancia_de_5_dias_e_mensalidade_paga(self, navegador, professor):
        criar_mensalidade(criar_aluno(professor, nome="Dentro da tolerância"), vencimento_em_dias=-5)
        paga = criar_mensalidade(criar_aluno(professor, nome="Já pagou", cpf="11122233344"), vencimento_em_dias=-30)
        Pagamento.registrar(paga, paga.valor_total, "PIX")
        assert navegador.get("/financeiro/inadimplentes/").context["inadimplentes"] == []

    def test_ct25_debitos_agregados_por_aluno(self, navegador, professor):
        aluno = criar_aluno(professor)
        hoje = timezone.localdate()
        criar_mensalidade(aluno, "300.00", vencimento_em_dias=-40,
                          competencia=(hoje.replace(day=1) - timedelta(days=40)).replace(day=1))
        criar_mensalidade(aluno, "250.00", vencimento_em_dias=-10)
        inadimplentes = navegador.get("/financeiro/inadimplentes/").context["inadimplentes"]
        assert len(inadimplentes) == 1
        assert inadimplentes[0]["total_em_atraso"] == Decimal("550.00")
        assert inadimplentes[0]["max_dias_atraso"] == 40

    def test_ct26_filtro_por_dias_minimos_de_atraso(self, navegador, professor):
        criar_mensalidade(criar_aluno(professor, nome="Atraso 10"), vencimento_em_dias=-10)
        criar_mensalidade(criar_aluno(professor, nome="Atraso 40", cpf="11122233344"), vencimento_em_dias=-40)
        filtrado = navegador.get("/financeiro/inadimplentes/", {"min_dias": "30"})
        assert [i["aluno"].nome for i in filtrado.context["inadimplentes"]] == ["Atraso 40"]
        invalido = navegador.get("/financeiro/inadimplentes/", {"min_dias": "abc"})
        assert invalido.status_code == 200
        assert len(invalido.context["inadimplentes"]) == 2


# ---------------------------------------------------------------- US 30355
class TestUS30355VisualizarIndicadores:
    def test_ct27_painel_exibe_os_indicadores_do_mes(self, navegador, professor):
        aluno = criar_aluno(professor)
        criar_aluno(professor, nome="Outro Ativo", cpf="11122233344")
        criar_aluno(professor, nome="Inativo", cpf="55566677788", situacao=Aluno.Situacao.INATIVO)
        aula = criar_aula(professor, aluno)
        aula.registrar_como_realizada(CONTEUDO_VALIDO)
        mover_para(aula, timezone.now() - timedelta(minutes=5))
        mensalidade = criar_mensalidade(aluno, "400.00")
        Pagamento.registrar(mensalidade, Decimal("100.00"), "PIX")

        contexto = navegador.get("/").context
        assert contexto["total_alunos_ativos"] == 2
        assert contexto["aulas_realizadas_mes"] == 1
        assert contexto["faturamento_gerado"] == Decimal("400.00")
        assert contexto["valor_pendente"] == Decimal("300.00")
        assert contexto["indice_inadimplencia"] == Decimal("75.0")

    def test_ct28_indicadores_por_competencia_para_os_graficos(self, navegador, professor):
        aluno = criar_aluno(professor)
        mensalidade = criar_mensalidade(aluno, "400.00")
        Pagamento.registrar(mensalidade, Decimal("100.00"), "PIX")
        competencia = timezone.localdate().strftime("%Y-%m")

        dados = navegador.get("/api/dashboard/estatisticas/", {"competencia": competencia}).json()
        assert dados["faturamento_gerado"] == "400.00"
        assert dados["valor_total_pago"] == "100.00"
        assert dados["valor_pendente"] == "300.00"

        vazio = navegador.get("/api/dashboard/estatisticas/", {"competencia": "2020-01"}).json()
        assert vazio["total_mensalidades"] == 0
        assert navegador.get("/api/dashboard/estatisticas/", {"competencia": "2026-13"}).status_code == 400
