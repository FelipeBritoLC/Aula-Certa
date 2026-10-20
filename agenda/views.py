from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from . import visoes
from .forms import AgendamentoForm, EditarAulaForm, RegistrarAulaForm, RegistrarFaltaForm
from .models import Aula


@login_required
def criar_agendamento(request):
    """US-30332 — Criar agendamento de aula."""
    if request.method == "POST":
        form = AgendamentoForm(request.POST, professor=request.user)
        if form.is_valid():
            try:
                aula = form.save()
            except ValidationError:
                pass
            else:
                messages.success(request, "Aula agendada com sucesso.")
                return redirect("agenda:detalhe", pk=aula.pk)
    else:
        form = AgendamentoForm(professor=request.user)

    return render(
        request,
        "agenda/form.html",
        {"form": form, "titulo": "Agendar aula", "botao": "Agendar"},
    )


@login_required
def listar_agenda(request):
    """
    US-30337 — Consultar agenda de aulas (visões diária, semanal e mensal).

    Parâmetros (todos opcionais): visao=dia|semana|mes, data=AAAA-MM-DD,
    status=AGENDADA|REALIZADA|CANCELADA|FALTA. A lógica fica em agenda/visoes.py.
    """
    visao, data, status = visoes.interpretar_parametros(request.GET)
    contexto = visoes.montar_contexto(request.user, visao, data, status)
    return render(request, "agenda/lista.html", contexto)


@login_required
def detalhe_aula(request, pk):
    aula = get_object_or_404(Aula, pk=pk, professor=request.user)
    return render(request, "agenda/detalhe.html", {"aula": aula})


@login_required
def editar_aula(request, pk):
    """
    US-30333 — Definir informações da aula agendada.

    CA-DEF-03: só aulas AGENDADAS são editáveis; para as demais, o professor
    é avisado e devolvido à ficha da aula, sem nenhuma alteração.
    """
    aula = get_object_or_404(Aula, pk=pk, professor=request.user)

    if not aula.pode_editar:
        messages.warning(
            request,
            "Somente aulas com status Agendada podem ser editadas.",
        )
        return redirect("agenda:detalhe", pk=aula.pk)

    if request.method == "POST":
        form = EditarAulaForm(request.POST, instance=aula)
        if form.is_valid():
            form.save()
            messages.success(request, "Informações da aula atualizadas.")
            return redirect("agenda:detalhe", pk=aula.pk)
    else:
        form = EditarAulaForm(instance=aula)

    return render(
        request,
        "agenda/form.html",
        {"form": form, "aula": aula, "titulo": "Editar aula", "botao": "Salvar alterações"},
    )


@login_required
def registrar_aula_realizada(request, pk):
    """US-30338 / Task 31621 — Registrar aula realizada."""
    aula = get_object_or_404(Aula, pk=pk, professor=request.user)

    if aula.status != Aula.Status.AGENDADA:
        messages.warning(request, "Somente aulas agendadas podem ser registradas como realizadas.")
        return redirect("agenda:detalhe", pk=aula.pk)

    if request.method == "POST":
        form = RegistrarAulaForm(request.POST)
        if form.is_valid():
            try:
                aula.registrar_como_realizada(
                    conteudo_trabalhado=form.cleaned_data["conteudo_trabalhado"],
                    observacoes=form.cleaned_data["observacoes"],
                )
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
            else:
                messages.success(request, "Aula registrada como realizada.")
                return redirect("agenda:detalhe", pk=aula.pk)
    else:
        form = RegistrarAulaForm()

    return render(request, "agenda/registrar.html", {"form": form, "aula": aula})


@login_required
def registrar_falta(request, pk):
    """US-30340 — Registrar falta do aluno."""
    aula = get_object_or_404(Aula, pk=pk, professor=request.user)
    if request.method == "POST":
        form = RegistrarFaltaForm(request.POST)
        if form.is_valid():
            aula.registrar_falta(
                justificada=form.cleaned_data["justificada"],
                observacoes=form.cleaned_data["observacoes"],
            )
            messages.success(request, "Falta registrada.")
            return redirect("agenda:detalhe", pk=aula.pk)
    else:
        form = RegistrarFaltaForm()
    return render(request, "agenda/registrar_falta.html", {"form": form, "aula": aula})
