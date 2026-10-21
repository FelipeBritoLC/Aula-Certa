from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import PagamentoForm
from .models import Mensalidade, Pagamento

DIAS_TOLERANCIA_INADIMPLENCIA = 5


@login_required
def listar_mensalidades(request):
    """US-30345 — Consultar pagamentos/mensalidades registradas (visão simples)."""
    mensalidades = Mensalidade.objects.filter(aluno__professor=request.user).select_related("aluno")
    return render(request, "financeiro/lista_mensalidades.html", {"mensalidades": mensalidades})


@login_required
def registrar_pagamento(request, mensalidade_id):
    """
    US-30344 / Task 31622 — Registrar pagamento do aluno.

    Cenário: Erro em valor inválido — tratado pela validação do form
    (min_value) e pelo ValidationError do model (defesa em profundidade).
    """
    mensalidade = get_object_or_404(
        Mensalidade, pk=mensalidade_id, aluno__professor=request.user
    )

    if request.method == "POST":
        form = PagamentoForm(request.POST)
        if form.is_valid():
            try:
                Pagamento.registrar(
                    mensalidade=mensalidade,
                    valor_pago=form.cleaned_data["valor_pago"],
                    forma_pagamento=form.cleaned_data["forma_pagamento"],
                    data_pagamento=form.cleaned_data.get("data_pagamento"),
                    observacoes=form.cleaned_data.get("observacoes", ""),
                )
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(None, err)
            else:
                messages.success(request, "Pagamento registrado com sucesso.")
                return redirect("financeiro:mensalidades")
    else:
        form = PagamentoForm(initial={"valor_pago": mensalidade.saldo})

    return render(
        request,
        "financeiro/registrar_pagamento.html",
        {"form": form, "mensalidade": mensalidade},
    )


@login_required
def identificar_inadimplentes(request):
    """
    US-30350 / Task 31623 — Identificar alunos inadimplentes.

    CA-INA-01: registros onde data_vencimento < hoje - 5 dias e
               status_pagamento != 'PAGO'.
    CA-INA-02: agregação de débitos pendentes por aluno.
    """
    limite = timezone.localdate() - timedelta(days=DIAS_TOLERANCIA_INADIMPLENCIA)

    # Valor não numérico ou negativo é ignorado (antes gerava erro 500).
    filtro_dias = request.GET.get("min_dias", "").strip()
    if not filtro_dias.isdigit():
        filtro_dias = ""

    mensalidades_vencidas = (
        Mensalidade.objects.filter(
            aluno__professor=request.user,
            data_vencimento__lt=limite,
        )
        .exclude(status=Mensalidade.Status.PAGO)
        .select_related("aluno")
    )

    agregados = {}
    for mensalidade in mensalidades_vencidas:
        dias = mensalidade.dias_em_atraso()
        if filtro_dias and dias < int(filtro_dias):
            continue
        registro = agregados.setdefault(
            mensalidade.aluno_id,
            {"aluno": mensalidade.aluno, "total_em_atraso": 0, "max_dias_atraso": 0},
        )
        registro["total_em_atraso"] += mensalidade.saldo
        registro["max_dias_atraso"] = max(registro["max_dias_atraso"], dias)

    inadimplentes = sorted(
        agregados.values(), key=lambda item: item["max_dias_atraso"], reverse=True
    )

    return render(
        request,
        "financeiro/inadimplentes.html",
        {"inadimplentes": inadimplentes, "filtro_dias": filtro_dias},
    )
