from django import forms
from django.core.exceptions import ValidationError

from alunos.models import Aluno

from .models import Aula


class AgendamentoForm(forms.ModelForm):
    """US-30332 / Task 31620 — Criar agendamento de aula."""

    duracao_minutos = forms.IntegerField(
        label="Duração (min)",
        min_value=1,
        initial=60,
        widget=forms.NumberInput(attrs={"min": 1, "step": 5}),
    )

    class Meta:
        model = Aula
        fields = ["aluno", "data_hora_inicio", "duracao_minutos", "modalidade", "local"]
        widgets = {
            "data_hora_inicio": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, professor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._professor = professor
        self.fields["aluno"].queryset = Aluno.objects.filter(
            professor=professor, situacao=Aluno.Situacao.ATIVO
        )
        self.fields["data_hora_inicio"].input_formats = ["%Y-%m-%dT%H:%M"]
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        aula = super().save(commit=False)
        aula.professor = self._professor
        try:
            aula.full_clean()
        except ValidationError as exc:
            for field, errs in exc.message_dict.items():
                for err in errs:
                    self.add_error(field if field in self.fields else None, err)
            raise
        if commit:
            aula.save()
        return aula


class EditarAulaForm(forms.ModelForm):
    """
    US-30333 — Definir informações da aula agendada.

    Edita horário, duração, modalidade e local de uma aula ainda AGENDADA
    (CA-DEF-01). As regras de conflito de horário (CA-DEF-02) e de
    bloqueio para aulas já realizadas/canceladas/com falta (CA-DEF-03)
    vivem em Aula.clean(), que o ModelForm executa na validação — assim
    a mesma regra vale para o formulário, o admin e qualquer outro caminho.
    O aluno não é editável aqui (trocar o aluno seria outra aula).
    """

    duracao_minutos = forms.IntegerField(
        label="Duração (min)",
        min_value=1,
        initial=60,
        widget=forms.NumberInput(attrs={"min": 1, "step": 5}),
    )

    class Meta:
        model = Aula
        fields = ["data_hora_inicio", "duracao_minutos", "modalidade", "local"]
        widgets = {
            "data_hora_inicio": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_hora_inicio"].input_formats = ["%Y-%m-%dT%H:%M"]
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["modalidade"].widget.attrs["class"] = "form-select"


class RegistrarAulaForm(forms.Form):
    """Task 31621 — Registrar aula realizada (CA-REG-01)."""

    conteudo_trabalhado = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "form-control",
                "minlength": 50,
                "aria-describedby": "conteudo-contador",
            }
        ),
        label="Conteúdo ministrado (mínimo 50 caracteres)",
    )
    observacoes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
    )

    def clean_conteudo_trabalhado(self):
        conteudo = self.cleaned_data["conteudo_trabalhado"].strip()
        if len(conteudo) < 50:
            raise ValidationError("O conteúdo ministrado deve ter pelo menos 50 caracteres.")
        return conteudo


class RegistrarFaltaForm(forms.Form):
    justificada = forms.BooleanField(required=False, label="Falta justificada")
    observacoes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
    )
