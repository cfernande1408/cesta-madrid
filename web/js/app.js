import {
  codificarLista,
  costeLinea,
  decodificarLista,
  formatoCantidad,
  formatoEuros,
  formatoPrecioUnidad,
  pasoCantidad,
  recomendacion,
} from "./comparador.js";

const CLAVE_LISTA = "cesta-madrid:lista";
const UMBRAL_REPARTIR = 3; // euros mínimos de ahorro para recomendar ir a dos súper

const estado = {
  datos: null,
  lista: {},
  abiertos: new Set(),
  filtro: "",
};

const $ = (id) => document.getElementById(id);

/** Crea un elemento. Los textos van siempre como texto, nunca como HTML. */
function h(tag, attrs = {}, ...hijos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const hijo of hijos.flat()) {
    if (hijo == null || hijo === false) continue;
    el.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return el;
}

// ---------- Persistencia ----------

function cargarLista() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_LISTA)) || {};
  } catch {
    return {};
  }
}

function guardarLista() {
  try {
    localStorage.setItem(CLAVE_LISTA, JSON.stringify(estado.lista));
  } catch {
    /* Sin almacenamiento (modo privado): la lista vive solo en esta pestaña. */
  }
}

// ---------- Datos ----------

function articulos() {
  return estado.datos?.articulos ?? [];
}

function articulo(id) {
  return articulos().find((a) => a.id === id);
}

/** Súper con algún precio: los únicos que entran en la comparación. */
function supersConDatos() {
  return (estado.datos?.supermercados ?? []).filter((s) => s.encontrados > 0);
}

function nombreSuper(id) {
  return estado.datos?.supermercados.find((s) => s.id === id)?.nombre ?? id;
}

function idsEnLista() {
  return articulos()
    .filter((a) => estado.lista[a.id] > 0)
    .map((a) => a.id);
}

function masBarato(a) {
  let mejor = null;
  for (const [superId, oferta] of Object.entries(a.ofertas ?? {})) {
    if (oferta.unit_price == null) continue;
    if (!mejor || oferta.unit_price < mejor.oferta.unit_price) mejor = { superId, oferta };
  }
  return mejor;
}

// ---------- Fechas ----------

const horaFmt = new Intl.DateTimeFormat("es-ES", { hour: "numeric", minute: "2-digit" });
const diaFmt = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" });

function cuando(iso) {
  if (!iso) return "nunca";
  const fecha = new Date(iso);
  const hoy = new Date();
  const ayer = new Date(hoy);
  ayer.setDate(hoy.getDate() - 1);
  const mismoDia = (a, b) => a.toDateString() === b.toDateString();
  if (mismoDia(fecha, hoy)) return `hoy a las ${horaFmt.format(fecha)}`;
  if (mismoDia(fecha, ayer)) return `ayer a las ${horaFmt.format(fecha)}`;
  return `el ${diaFmt.format(fecha)}`;
}

function esViejo(iso) {
  return !iso || Date.now() - new Date(iso).getTime() > 36 * 3600 * 1000;
}

// ---------- Render ----------

function render() {
  const r = recomendacion(articulos(), estado.lista, supersConDatos(), UMBRAL_REPARTIR);
  renderResumen(r);
  renderLista(r);
  renderCatalogo();
  renderBarraMovil(r);
}

function renderResumen(r) {
  const etiqueta = $("etiqueta");
  const barras = $("barras");
  etiqueta.replaceChildren();
  barras.replaceChildren();
  const n = idsEnLista().length;

  if (!estado.datos) return;

  if (!supersConDatos().length) {
    etiqueta.append(
      h("div", { class: "etiqueta etiqueta--vacia" },
        h("p", { class: "etiqueta__intro" }, "Todavía no hay precios"),
        h("p", { class: "etiqueta__nota" }, "Se descargan cada mañana. Vuelve en un rato."),
      ),
    );
    return;
  }

  if (n === 0) {
    etiqueta.append(
      h("div", { class: "etiqueta etiqueta--vacia" },
        h("p", { class: "etiqueta__intro" }, "Tu lista está vacía"),
        h("p", { class: "etiqueta__nota" }, "Añade lo que necesitas y aquí verás en qué supermercado te sale más barato todo junto."),
      ),
    );
    return;
  }

  const { uno, par, ahorro, totales } = r;
  if (r.tipo === "dos") {
    const [a, b] = par.ids;
    const enA = Object.values(par.reparto).filter((s) => s === a).length;
    const enB = Object.values(par.reparto).filter((s) => s === b).length;
    etiqueta.append(
      h("div", { class: "etiqueta" },
        h("p", { class: "etiqueta__intro" }, "Lo más barato es repartir la compra"),
        h("p", { class: "etiqueta__super" }, `${nombreSuper(a)} + ${nombreSuper(b)}`),
        h("p", { class: "etiqueta__total" }, formatoEuros(par.total)),
        h("ul", { class: "reparto" },
          h("li", {}, `${nombreSuper(a)}: ${enA} ${enA === 1 ? "artículo" : "artículos"}`),
          h("li", {}, `${nombreSuper(b)}: ${enB} ${enB === 1 ? "artículo" : "artículos"}`),
        ),
        h("p", { class: "etiqueta__nota" },
          "Ahorras ", h("strong", {}, formatoEuros(ahorro)),
          ` frente a comprarlo todo en ${uno.nombre} (${formatoEuros(uno.total)}).`,
        ),
        notaFaltan(par.faltan),
      ),
    );
  } else {
    const repartir =
      par && par.usados === 2 && ahorro > 0.5 && par.faltan.length <= uno.faltan.length
        ? h("p", { class: "etiqueta__nota" },
            `Repartiendo entre ${nombreSuper(par.ids[0])} y ${nombreSuper(par.ids[1])} ahorrarías solo ${formatoEuros(ahorro)}.`)
        : null;
    etiqueta.append(
      h("div", { class: "etiqueta" },
        h("p", { class: "etiqueta__intro" }, n === 1 ? "Tu artículo sale más barato en" : `Tus ${n} artículos salen más baratos en`),
        h("p", { class: "etiqueta__super" }, uno.nombre),
        h("p", { class: "etiqueta__total" }, formatoEuros(uno.total)),
        repartir,
        notaFaltan(uno.faltan),
      ),
    );
  }

  const max = Math.max(...totales.map((t) => t.total), 0.01);
  const ganador = r.tipo === "uno" ? uno.id : null;
  barras.append(
    h("ol", { class: "barras", "aria-label": "Total de tu lista en cada supermercado" },
      totales.map((t) =>
        h("li", { class: `barra${t.id === ganador ? " barra--ganadora" : ""}` },
          h("span", { class: "barra__nombre" }, t.nombre),
          h("span", { class: "barra__pista", "aria-hidden": "true" },
            h("span", { class: "barra__relleno", style: `width:${Math.max(2, (t.total / max) * 100)}%` }),
          ),
          h("span", { class: "barra__total" }, formatoEuros(t.total)),
          t.faltan.length
            ? h("span", { class: "barra__falta" },
                `Sin precio: ${t.faltan.map((id) => articulo(id)?.nombre ?? id).join(", ")}`)
            : null,
        ),
      ),
    ),
  );
}

function notaFaltan(faltan) {
  if (!faltan.length) return null;
  const nombres = faltan.map((id) => articulo(id)?.nombre ?? id).join(", ");
  return h("p", { class: "etiqueta__nota" }, `No incluye ${nombres}: no hay precio comparable.`);
}

function renderLista(r) {
  const ul = $("lineas");
  ul.replaceChildren();
  const ids = idsEnLista();
  $("contador").textContent = ids.length ? `(${ids.length})` : "";
  $("compartir").disabled = !ids.length;
  $("vaciar").disabled = !ids.length;

  const vacia = document.querySelector(".lista__vacia");
  if (!ids.length) {
    if (!vacia) {
      ul.after(h("p", { class: "lista__vacia" }, "Elige artículos de la cesta más abajo."));
    }
    return;
  }
  vacia?.remove();

  const plan = (id) => (r.tipo === "dos" ? r.par?.reparto[id] : r.uno?.id);

  for (const id of ids) {
    const a = articulo(id);
    const cantidad = estado.lista[id];
    const abierto = estado.abiertos.has(id);
    const mejor = masBarato(a);
    const superPlan = plan(id);
    const coste = costeLinea(a.ofertas?.[superPlan], cantidad);
    const paso = pasoCantidad(a.unidad, a.cantidad);
    const detalleId = `detalle-${id}`;

    ul.append(
      h("li", { class: "linea" },
        h("div", { class: "linea__fila" },
          h("button", {
              type: "button",
              class: "linea__nombre",
              "aria-expanded": String(abierto),
              "aria-controls": detalleId,
              onclick: () => {
                abierto ? estado.abiertos.delete(id) : estado.abiertos.add(id);
                render();
              },
            },
            h("span", { class: "linea__titulo" }, a.nombre),
            h("span", { class: "linea__mejor" },
              mejor
                ? `Más barato en ${nombreSuper(mejor.superId)}: ${formatoPrecioUnidad(mejor.oferta.unit_price, a.unidad)}`
                : "Sin precios todavía",
            ),
          ),
          h("div", { class: "paso", role: "group", "aria-label": `Cantidad de ${a.nombre}` },
            h("button", {
              type: "button",
              "aria-label": cantidad - paso <= 0 ? `Quitar ${a.nombre}` : "Menos",
              onclick: () => cambiarCantidad(id, -paso),
            }, "−"),
            h("output", { "aria-live": "polite" }, formatoCantidad(cantidad, a.unidad)),
            h("button", { type: "button", "aria-label": "Más", onclick: () => cambiarCantidad(id, paso) }, "+"),
          ),
          coste != null
            ? h("span", { class: "linea__coste" }, formatoEuros(coste),
                r.tipo === "dos" ? h("span", { class: "linea__donde" }, nombreSuper(superPlan)) : null)
            : h("span", { class: "linea__coste linea__coste--falta" }, `Sin precio en ${nombreSuper(superPlan)}`),
        ),
        abierto ? detalle(a, cantidad, detalleId, mejor) : null,
      ),
    );
  }
}

function detalle(a, cantidad, detalleId, mejor) {
  const supers = [...(estado.datos.supermercados ?? [])].sort(
    (x, y) => (a.ofertas?.[x.id]?.unit_price ?? Infinity) - (a.ofertas?.[y.id]?.unit_price ?? Infinity),
  );
  const filas = supers.map((s) => {
    const o = a.ofertas?.[s.id];
    if (!o) {
      return h("li", { class: "detalle__super detalle__super--sin" },
        h("span", { class: "detalle__nombre" }, s.nombre),
        h("span", { class: "detalle__producto" }, "No lo hemos encontrado"),
      );
    }
    const esMejor = mejor && mejor.superId === s.id;
    return h("li", { class: `detalle__super${esMejor ? " detalle__super--mejor" : ""}` },
      h("span", { class: "detalle__nombre" }, s.nombre),
      h("span", { class: "detalle__medida" }, formatoPrecioUnidad(o.unit_price, a.unidad)),
      h("span", { class: "detalle__coste" }, formatoEuros(costeLinea(o, cantidad))),
      h("span", { class: "detalle__producto" },
        h("a", { href: o.url, target: "_blank", rel: "noopener" }, o.name),
        `${o.format ? ` (${o.format})` : ""}: ${formatoEuros(o.price)}`,
      ),
    );
  });
  return h("div", { class: "detalle", id: detalleId },
    h("ul", { class: "detalle__lista", "aria-label": `Precios de ${a.nombre} en cada supermercado` }, filas),
    h("button", {
      type: "button",
      class: "boton boton--texto detalle__quitar",
      onclick: () => quitar(a.id),
    }, "Quitar de la lista"),
  );
}

function renderCatalogo() {
  const cont = $("categorias");
  cont.replaceChildren();
  const filtro = normalizar(estado.filtro);
  const disponibles = articulos().filter(
    (a) => !(estado.lista[a.id] > 0) && (!filtro || normalizar(a.nombre).includes(filtro)),
  );
  if (!disponibles.length) {
    cont.append(
      h("p", { class: "catalogo__nada" },
        filtro ? `Nada en la cesta coincide con «${estado.filtro}».` : "Ya tienes en la lista todo lo de la cesta."),
    );
    return;
  }
  const grupos = new Map();
  for (const a of disponibles) {
    if (!grupos.has(a.categoria)) grupos.set(a.categoria, []);
    grupos.get(a.categoria).push(a);
  }
  for (const [categoria, items] of grupos) {
    cont.append(
      h("div", { class: "categoria" },
        h("h3", {}, categoria),
        h("ul", { class: "chips" },
          items.map((a) => {
            const mejor = masBarato(a);
            return h("li", {},
              h("button", { type: "button", class: "chip", onclick: () => anadir(a.id) },
                a.nombre,
                mejor ? h("span", { class: "chip__precio" }, `desde ${formatoPrecioUnidad(mejor.oferta.unit_price, a.unidad)}`) : null,
              ),
            );
          }),
        ),
      ),
    );
  }
}

function renderBarraMovil(r) {
  const barra = $("barra-movil");
  if (!idsEnLista().length || r.tipo === "vacio" || !r.uno) {
    barra.hidden = true;
    barra.dataset.activa = "";
    return;
  }
  barra.dataset.activa = "1";
  const texto = r.tipo === "dos"
    ? [`${nombreSuper(r.par.ids[0])} + ${nombreSuper(r.par.ids[1])}`, formatoEuros(r.par.total)]
    : [r.uno.nombre, formatoEuros(r.uno.total)];
  barra.replaceChildren(h("span", {}, texto[0]), h("strong", {}, texto[1]));
  barra.hidden = barra.dataset.resumenVisible === "1";
}

function renderCabeceraYPie() {
  const d = estado.datos;
  $("frescura").textContent = d ? `Precios actualizados ${cuando(d.generado)}` : "Sin datos de precios";
  const ul = $("estado-supers");
  ul.replaceChildren(
    ...(d?.supermercados ?? []).map((s) =>
      h("li", { class: esViejo(s.actualizado) ? "viejo" : null },
        s.encontrados > 0
          ? `${s.nombre}: ${s.encontrados} artículos, ${cuando(s.actualizado)}`
          : `${s.nombre}: sin datos por ahora`,
      ),
    ),
  );
}

// ---------- Acciones ----------

function anadir(id) {
  const a = articulo(id);
  estado.lista[id] = a.cantidad;
  guardarLista();
  render();
  avisar(`Añadido: ${a.nombre}`);
}

function quitar(id) {
  delete estado.lista[id];
  estado.abiertos.delete(id);
  guardarLista();
  render();
  avisar(`Quitado: ${articulo(id)?.nombre ?? id}`);
}

function cambiarCantidad(id, delta) {
  const nueva = Math.round(((estado.lista[id] ?? 0) + delta) * 1000) / 1000;
  if (nueva <= 0) return quitar(id);
  estado.lista[id] = nueva;
  guardarLista();
  render();
}

async function compartir() {
  const url = `${location.origin}${location.pathname}#l=${codificarLista(estado.lista)}`;
  if (navigator.share) {
    try {
      await navigator.share({ title: "Nuestra lista de la compra", url });
      return;
    } catch (e) {
      if (e?.name === "AbortError") return;
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    avisar("Enlace copiado: quien lo abra verá esta misma lista");
  } catch {
    window.prompt("Copia este enlace:", url);
  }
}

function vaciar() {
  if (!window.confirm("¿Vaciar la lista?")) return;
  estado.lista = {};
  estado.abiertos.clear();
  guardarLista();
  render();
}

let temporizadorAviso;
function avisar(texto) {
  const el = $("aviso");
  el.textContent = texto;
  el.hidden = false;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => (el.hidden = true), 2600);
}

function normalizar(texto) {
  return (texto || "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}

// ---------- Arranque ----------

async function iniciar() {
  try {
    const resp = await fetch("data/precios.json", { cache: "no-cache" });
    if (resp.ok) estado.datos = await resp.json();
  } catch {
    estado.datos = null;
  }
  if (!estado.datos) estado.datos = { generado: null, supermercados: [], articulos: [] };

  const ids = articulos().map((a) => a.id);
  estado.lista = decodificarLista(codificarLista(cargarLista()), ids);

  if (location.hash.startsWith("#l=")) {
    const compartida = decodificarLista(decodeURIComponent(location.hash.slice(3)), ids);
    history.replaceState(null, "", location.pathname + location.search);
    if (Object.keys(compartida).length) {
      estado.lista = compartida;
      guardarLista();
      setTimeout(() => avisar("Lista cargada desde el enlace"), 300);
    }
  }

  $("buscar").addEventListener("input", (e) => {
    estado.filtro = e.target.value;
    renderCatalogo();
  });
  $("compartir").addEventListener("click", compartir);
  $("vaciar").addEventListener("click", vaciar);

  const barra = $("barra-movil");
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(([entrada]) => {
      barra.dataset.resumenVisible = entrada.isIntersecting ? "1" : "";
      barra.hidden = !barra.dataset.activa || entrada.isIntersecting;
    }).observe($("resumen"));
  }

  renderCabeceraYPie();
  render();
}

iniciar();
