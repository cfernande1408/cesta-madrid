// Cálculos de la cesta: totales por súper, mejor súper y mejor pareja.
// Funciones puras, sin DOM, para poder probarlas con `node --test`.

/** Coste estimado de una línea: precio por unidad base × cantidad. */
export function costeLinea(oferta, cantidad) {
  if (!oferta || oferta.unit_price == null || !(cantidad > 0)) return null;
  return oferta.unit_price * cantidad;
}

/**
 * Totales de la lista en cada súper.
 * @param articulos  precios.json → articulos
 * @param lista      { idArticulo: cantidad }
 * @param supers     precios.json → supermercados
 */
export function totalesPorSuper(articulos, lista, supers) {
  const elegidos = articulos.filter((a) => lista[a.id] > 0);
  return supers.map((s) => {
    let total = 0;
    const faltan = [];
    const lineas = {};
    for (const a of elegidos) {
      const coste = costeLinea(a.ofertas?.[s.id], lista[a.id]);
      if (coste == null) faltan.push(a.id);
      else {
        lineas[a.id] = coste;
        total += coste;
      }
    }
    return { id: s.id, nombre: s.nombre, total: redondear(total), faltan, lineas };
  });
}

/** Ordena: primero los que tienen menos artículos sin precio, luego el más barato. */
export function ordenarTotales(totales) {
  return [...totales].sort(
    (a, b) => a.faltan.length - b.faltan.length || a.total - b.total || a.nombre.localeCompare(b.nombre),
  );
}

/** Mejor reparto de la lista entre dos súper: cada artículo va al más barato de los dos. */
export function mejorPar(articulos, lista, supers) {
  const elegidos = articulos.filter((a) => lista[a.id] > 0);
  let mejor = null;
  for (let i = 0; i < supers.length; i++) {
    for (let j = i + 1; j < supers.length; j++) {
      const par = [supers[i], supers[j]];
      let total = 0;
      const faltan = [];
      const reparto = {};
      for (const a of elegidos) {
        let elegido = null;
        let coste = null;
        for (const s of par) {
          const c = costeLinea(a.ofertas?.[s.id], lista[a.id]);
          if (c != null && (coste == null || c < coste)) {
            coste = c;
            elegido = s.id;
          }
        }
        if (elegido == null) faltan.push(a.id);
        else {
          reparto[a.id] = elegido;
          total += coste;
        }
      }
      const usados = new Set(Object.values(reparto));
      const candidato = { ids: par.map((s) => s.id), total: redondear(total), faltan, reparto, usados: usados.size };
      if (
        !mejor ||
        candidato.faltan.length < mejor.faltan.length ||
        (candidato.faltan.length === mejor.faltan.length && candidato.total < mejor.total)
      ) {
        mejor = candidato;
      }
    }
  }
  return mejor;
}

/**
 * Qué conviene: un solo súper o repartir entre dos.
 * Solo se recomienda repartir si se ahorra al menos `umbral` euros sin dejar más artículos fuera.
 */
export function recomendacion(articulos, lista, supers, umbral = 3) {
  const totales = ordenarTotales(totalesPorSuper(articulos, lista, supers));
  const uno = totales[0] ?? null;
  const par = supers.length >= 2 ? mejorPar(articulos, lista, supers) : null;
  if (!uno) return { tipo: "vacio", totales };
  const ahorro = par ? redondear(uno.total - par.total) : 0;
  const repartir =
    par && par.usados === 2 && par.faltan.length <= uno.faltan.length && ahorro >= umbral;
  return { tipo: repartir ? "dos" : "uno", uno, par, ahorro, totales };
}

/** Lista ↔ texto para compartirla en un enlace: "leche:6,huevos:12". */
export function codificarLista(lista) {
  return Object.entries(lista)
    .filter(([, c]) => c > 0)
    .map(([id, c]) => `${id}:${+c.toFixed(3)}`)
    .join(",");
}

export function decodificarLista(texto, idsValidos) {
  const validos = new Set(idsValidos);
  const lista = {};
  for (const parte of (texto || "").split(",")) {
    const [id, cant] = parte.split(":");
    const n = Number(cant);
    if (validos.has(id) && Number.isFinite(n) && n > 0) lista[id] = n;
  }
  return lista;
}

/** Paso del selector de cantidad según la unidad y el tamaño habitual. */
export function pasoCantidad(unidad, cantidadHabitual) {
  if (unidad === "ud") return cantidadHabitual >= 12 ? 6 : 1;
  if (cantidadHabitual < 0.5) return 0.05;
  if (cantidadHabitual < 1) return 0.1;
  if (cantidadHabitual < 2) return 0.5;
  return 1;
}

const euros = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });
const numero = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

export function formatoEuros(n) {
  return n == null ? "–" : euros.format(n);
}

export function formatoCantidad(cantidad, unidad) {
  if (unidad === "kg" && cantidad < 1) return `${numero.format(cantidad * 1000)} g`;
  if (unidad === "l" && cantidad < 1) return `${numero.format(cantidad * 1000)} ml`;
  const nombres = { kg: "kg", l: "L", ud: cantidad === 1 ? "ud." : "uds." };
  return `${numero.format(cantidad)} ${nombres[unidad] ?? unidad}`;
}

export function formatoPrecioUnidad(precio, unidad) {
  const nombres = { kg: "kg", l: "L", ud: "ud." };
  return `${formatoEuros(precio)}/${nombres[unidad] ?? unidad}`;
}

function redondear(n) {
  return Math.round(n * 100) / 100;
}
