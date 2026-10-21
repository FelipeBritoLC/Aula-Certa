from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import AlunoFiltroForm, AlunoForm
from .models import Aluno

# A consulta completa do histórico, com filtros, é a US-30342 (Sprint 03).
LIMITE_HISTORICO_FICHA = 5


@login_required
def cadastrar_aluno(request):
    """US-30321 / Task 31619 — Cadastrar aluno."""
    if request.method == "POST":
        form = AlunoForm(request.POST, professor=request.user)
        if form.is_valid():
            try:
                aluno = form.save()
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
            else:
                messages.success(request, f"Aluno '{aluno.nome}' cadastrado com sucesso.")
                return redirect("alunos:detalhe", pk=aluno.pk)
    else:
        form = AlunoForm(professor=request.user)

    return render(request, "alunos/form.html", {"form": form, "titulo": "Cadastrar aluno"})


@login_required
def editar_aluno(request, pk):
    """
    US-30325 — Alterar dados do aluno.

    CA-ALT-01 (Task 32576): as mesmas regras do cadastro valem na alteração —
              CPF único por professor e nome, CPF e telefone obrigatórios
              (Aluno.clean()).
    CA-ALT-02 (Task 32577): inativar o aluno mantém as aulas que ele já tinha,
              mas bloqueia novos agendamentos (CA-AGE-02 em Aula.clean() e
              o filtro de alunos ativos no formulário de agendamento). O
              professor é avisado de quantas aulas futuras continuam agendadas.
    """
    aluno = get_object_or_404(Aluno, pk=pk, professor=request.user)
    estava_ativo = aluno.is_ativo()

    if request.method == "POST":
        form = AlunoForm(request.POST, instance=aluno, professor=request.user)
        if form.is_valid():
            try:
                aluno = form.save()
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
            else:
                messages.success(request, "Dados do aluno atualizados.")
                if estava_ativo and not aluno.is_ativo():
                    _avisar_inativacao(request, aluno)
                return redirect("alunos:detalhe", pk=aluno.pk)
    else:
        form = AlunoForm(instance=aluno, professor=request.user)

    return render(
        request,
        "alunos/form.html",
        {
            "form": form,
            "aluno": aluno,
            "titulo": f"Editar aluno — {aluno.nome}",
            "aulas_futuras": aluno.aulas_futuras_agendadas().count(),
        },
    )


def _avisar_inativacao(request, aluno):
    """Task 32577 — informa as consequências da inativação."""
    futuras = aluno.aulas_futuras_agendadas().count()
    if futuras:
        messages.warning(
            request,
            f"Aluno inativado. Ele ainda tem {futuras} aula(s) agendada(s), que foram "
            "mantidas — cancele-as na agenda, se for o caso. Novos agendamentos "
            "para este aluno estão bloqueados.",
        )
    else:
        messages.info(
            request,
            "Aluno inativado. Novos agendamentos para este aluno estão bloqueados.",
        )


@login_required
def listar_alunos(request):
    """
    US-30323 / Task 31763 e 31764 — Consultar alunos cadastrados.

    Cenário BDD (Task 31619): retorna lista paginada e permite filtragem
    por nome, validando a integridade da tabela Alunos.
    """
    filtro_form = AlunoFiltroForm(request.GET or None)
    alunos = Aluno.objects.filter(professor=request.user)

    if filtro_form.is_valid():
        nome = filtro_form.cleaned_data.get("nome")
        situacao = filtro_form.cleaned_data.get("situacao")
        if nome:
            alunos = alunos.filter(nome__icontains=nome)
        if situacao:
            alunos = alunos.filter(situacao=situacao)

    paginator = Paginator(alunos, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "alunos/lista.html",
        {"page_obj": page_obj, "filtro_form": filtro_form},
    )


@login_required
def detalhe_aluno(request, pk):
    """
    Ficha consolidada do aluno.

    US-30322 (CA-COMP-03): dados acadêmicos e do responsável.
    US-30339 / Task 32583 (CA-DET-03): histórico das últimas aulas
    realizadas, com conteúdo, avaliação, material e recomendações.
    """
    aluno = get_object_or_404(Aluno, pk=pk, professor=request.user)
    proximas_aulas = aluno.aulas.filter(status="AGENDADA").order_by("data_hora_inicio")[:5]
    aulas_realizadas = aluno.aulas.filter(status="REALIZADA").order_by("-data_hora_inicio")
    return render(
        request,
        "alunos/detalhe.html",
        {
            "aluno": aluno,
            "proximas_aulas": proximas_aulas,
            "historico_aulas": aulas_realizadas[:LIMITE_HISTORICO_FICHA],
            "total_aulas_realizadas": aulas_realizadas.count(),
        },
    )
