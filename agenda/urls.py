from django.urls import path

from . import views

app_name = "agenda"

urlpatterns = [
    path("", views.listar_agenda, name="listar"),
    path("nova/", views.criar_agendamento, name="criar"),
    path("<int:pk>/", views.detalhe_aula, name="detalhe"),
    path("<int:pk>/editar/", views.editar_aula, name="editar"),
    path("<int:pk>/registrar/", views.registrar_aula_realizada, name="registrar"),
    path("<int:pk>/detalhes/", views.informar_detalhes, name="detalhes"),
    path("<int:pk>/falta/", views.registrar_falta, name="registrar_falta"),
]
