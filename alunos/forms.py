from django import forms

from .models import Aluno


class AlunoForm(forms.ModelForm):
    class Meta:
        model = Aluno
        fields = [
            "nome", "cpf", "telefone", "email",
            "data_nascimento", "endereco",
            "disciplina", "serie_nivel", "escola", "observacoes",
            "responsavel_nome", "responsavel_telefone",
            "responsavel_email", "responsavel_parentesco",
            "valor_hora", "situacao",
        ]
        widgets = {
            "data_nascimento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "cpf": forms.TextInput(attrs={"class": "form-control", "placeholder": "000.000.000-00"}),
            "telefone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, professor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._professor = professor
        for field in self.fields.values():
            classe = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", classe)

    def save(self, commit=True):
        aluno = super().save(commit=False)
        if self._professor is not None:
            aluno.professor = self._professor
        aluno.full_clean()
        if commit:
            aluno.save()
        return aluno


class AlunoFiltroForm(forms.Form):
    """Task 31764 — filtros de busca da listagem de alunos."""
    nome = forms.CharField(required=False, label="Nome")
    situacao = forms.ChoiceField(
        required=False,
        choices=[("", "Todas")] + list(Aluno.Situacao.choices),
        label="Situação",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-select" if isinstance(field, forms.ChoiceField) else "form-control")
