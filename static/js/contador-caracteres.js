/*
 * Contador de caracteres com mínimo obrigatório (Task 31621, CA-REG-01).
 *
 * Usado no registro de aula realizada: mostra "N/50 caracteres" enquanto o
 * professor digita e só habilita o botão de concluir quando o conteúdo
 * (sem espaços nas pontas) atinge o mínimo. A validação definitiva continua
 * no servidor; isto é apenas a ajuda visual.
 *
 * Marcação esperada no campo:
 *   data-contador-minimo="50"
 *   data-contador-alvo="<id do elemento do contador>"
 *   data-contador-botao="<id do botão que depende do mínimo>"
 */
(function () {
  "use strict";

  function configurarContador(campo, contador, botao, minimo) {
    function atualizar() {
      const quantidade = campo.value.trim().length;
      const atingiu = quantidade >= minimo;
      contador.textContent = `${quantidade}/${minimo} caracteres`;
      contador.classList.toggle("text-success", atingiu);
      contador.classList.toggle("text-danger", !atingiu);
      if (botao) botao.disabled = !atingiu;
      return atingiu;
    }

    campo.addEventListener("input", atualizar);
    atualizar();
    return atualizar;
  }

  function iniciar(raiz) {
    const campos = raiz.querySelectorAll("[data-contador-minimo]");
    campos.forEach(function (campo) {
      const contador = raiz.getElementById(campo.dataset.contadorAlvo);
      const botao = raiz.getElementById(campo.dataset.contadorBotao);
      const minimo = Number(campo.dataset.contadorMinimo);
      if (contador && minimo > 0) {
        configurarContador(campo, contador, botao, minimo);
      }
    });
    return campos.length;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { configurarContador, iniciar };
  } else {
    iniciar(document);
  }
})();
