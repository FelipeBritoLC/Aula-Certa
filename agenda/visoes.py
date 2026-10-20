"""
US-30337 — Consultar agenda de aulas: visões diária, semanal e mensal.

Critérios de aceitação implementados:
CA-CAG-01: três formatos de visualização (dia, semana, mês).
CA-CAG-02: cada aula exibe aluno, horário e status (a indicação visual por
           cor/ícone fica no template + CSS, a partir de Aula.status).
CA-CAG-03: a navegação entre períodos e a troca de visão preservam o filtro
           de status — por isso todos os links são montados aqui, a partir
           dos mesmos três parâmetros (visao, data, status).

Convenções:
- A semana vai de segunda a domingo.
- Os dias são sempre os do fuso do projeto (America/Sao_Paulo): uma aula às
  23h30 pertence àquele dia, mesmo que em UTC já seja o dia seguinte.
"""
import calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from .models import Aula

VISOES = (("dia", "Dia"), ("semana", "Semana"), ("mes", "Mês"))
VISAO_PADRAO = "semana"
DIAS_DA_SEMANA = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def interpretar_parametros(get):
    """Lê visao/data/status da query string, caindo em valores seguros."""
    visao = get.get("visao")
    if visao not in dict(VISOES):
        visao = VISAO_PADRAO

    try:
        data = date.fromisoformat(get.get("data", ""))
    except ValueError:
        data = timezone.localdate()

    status = get.get("status")
    if status not in Aula.Status.values:
        status = ""

    return visao, data, status


def periodo(visao, data):
    """Primeiro e último dia (inclusive) do período que contém `data`."""
    if visao == "dia":
        return data, data
    if visao == "semana":
        inicio = data - timedelta(days=data.weekday())
        return inicio, inicio + timedelta(days=6)
    ultimo_dia = calendar.monthrange(data.year, data.month)[1]
    return data.replace(day=1), data.replace(day=ultimo_dia)


def deslocar(visao, data, sentido):
    """Data de referência do período anterior (-1) ou seguinte (+1)."""
    if visao == "dia":
        return data + timedelta(days=sentido)
    if visao == "semana":
        return data + timedelta(days=7 * sentido)
    primeiro = data.replace(day=1)
    if sentido > 0:
        return (primeiro + timedelta(days=32)).replace(day=1)
    return (primeiro - timedelta(days=1)).replace(day=1)


def url_agenda(visao, data, status=""):
    params = {"visao": visao, "data": data.isoformat()}
    if status:
        params["status"] = status
    return f"{reverse('agenda:listar')}?{urlencode(params)}"


def aulas_por_dia(professor, inicio, fim, status=""):
    """Aulas do professor entre `inicio` e `fim` (inclusive), agrupadas por dia local."""
    inicio_dt = timezone.make_aware(datetime.combine(inicio, time.min))
    fim_dt = timezone.make_aware(datetime.combine(fim + timedelta(days=1), time.min))

    aulas = (
        Aula.objects.filter(
            professor=professor,
            data_hora_inicio__gte=inicio_dt,
            data_hora_inicio__lt=fim_dt,
        )
        .select_related("aluno")
        .order_by("data_hora_inicio")
    )
    if status:
        aulas = aulas.filter(status=status)

    por_dia = defaultdict(list)
    for aula in aulas:
        por_dia[timezone.localtime(aula.data_hora_inicio).date()].append(aula)
    return por_dia


def _celula(dia, mes_de_referencia, por_dia, hoje, status):
    return {
        "data": dia,
        "aulas": por_dia.get(dia, []),
        "hoje": dia == hoje,
        "no_mes": dia.month == mes_de_referencia,
        "url_dia": url_agenda("dia", dia, status),
    }


def montar_contexto(professor, visao, data, status):
    inicio, fim = periodo(visao, data)
    por_dia = aulas_por_dia(professor, inicio, fim, status)
    hoje = timezone.localdate()

    contexto = {
        "visao": visao,
        "data": data,
        "inicio": inicio,
        "fim": fim,
        "status_selecionado": status,
        "total_aulas": sum(len(aulas) for aulas in por_dia.values()),
        "url_anterior": url_agenda(visao, deslocar(visao, data, -1), status),
        "url_proxima": url_agenda(visao, deslocar(visao, data, +1), status),
        "url_hoje": url_agenda(visao, hoje, status),
        "visoes": [
            {"valor": valor, "rotulo": rotulo,
             "url": url_agenda(valor, data, status), "ativa": valor == visao}
            for valor, rotulo in VISOES
        ],
        "filtros_status": [
            {"valor": valor, "rotulo": rotulo,
             "url": url_agenda(visao, data, valor), "ativo": valor == status}
            for valor, rotulo in [("", "Todas")] + list(Aula.Status.choices)
        ],
        "dias_da_semana": DIAS_DA_SEMANA,
    }

    if visao == "mes":
        calendario = calendar.Calendar(firstweekday=0)
        contexto["semanas"] = [
            [_celula(dia, data.month, por_dia, hoje, status) for dia in semana]
            for semana in calendario.monthdatescalendar(data.year, data.month)
        ]
    else:
        dias, dia = [], inicio
        while dia <= fim:
            dias.append(_celula(dia, dia.month, por_dia, hoje, status))
            dia += timedelta(days=1)
        contexto["dias"] = dias

    return contexto
