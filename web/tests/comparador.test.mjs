import assert from "node:assert/strict";
import { test } from "node:test";

import {
  codificarLista,
  costeLinea,
  decodificarLista,
  formatoCantidad,
  formatoEuros,
  mejorPar,
  ordenarTotales,
  pasoCantidad,
  recomendacion,
  totalesPorSuper,
} from "../js/comparador.js";

const supers = [
  { id: "m", nombre: "Mercadona" },
  { id: "d", nombre: "Dia" },
  { id: "a", nombre: "Alcampo" },
];

const of = (unit_price) => ({ unit_price, price: unit_price });

const articulos = [
  { id: "leche", unidad: "l", ofertas: { m: of(0.94), d: of(0.83), a: of(0.88) } },
  { id: "arroz", unidad: "kg", ofertas: { m: of(1.2), d: of(1.5), a: of(1.0) } },
  { id: "aceite", unidad: "l", ofertas: { m: of(8.0), d: of(9.5) } },
];

test("coste de línea = precio unidad × cantidad", () => {
  assert.equal(costeLinea(of(0.83), 6), 0.83 * 6);
  assert.equal(costeLinea(null, 6), null);
  assert.equal(costeLinea(of(1), 0), null);
});

test("totales por súper y artículos que faltan", () => {
  const lista = { leche: 6, arroz: 2, aceite: 1 };
  const t = Object.fromEntries(totalesPorSuper(articulos, lista, supers).map((x) => [x.id, x]));
  assert.equal(t.m.total, 16.04); // 5.64 + 2.4 + 8
  assert.equal(t.d.total, 17.48); // 4.98 + 3 + 9.5
  assert.deepEqual(t.a.faltan, ["aceite"]);
  assert.equal(t.a.total, 7.28); // 5.28 + 2
});

test("ordenar prioriza tener todo antes que el precio", () => {
  const lista = { leche: 6, arroz: 2, aceite: 1 };
  const orden = ordenarTotales(totalesPorSuper(articulos, lista, supers)).map((x) => x.id);
  assert.deepEqual(orden, ["m", "d", "a"]);
});

test("mejor pareja reparte cada artículo al más barato", () => {
  const lista = { leche: 6, arroz: 2, aceite: 1 };
  const par = mejorPar(articulos, lista, supers);
  assert.deepEqual(par.ids, ["m", "a"]);
  assert.deepEqual(par.reparto, { leche: "a", arroz: "a", aceite: "m" });
  assert.equal(par.total, 15.28); // 5.28 + 2 + 8
  assert.equal(par.faltan.length, 0);
});

test("recomienda un súper si repartir ahorra poco", () => {
  const lista = { leche: 6, arroz: 2, aceite: 1 };
  const r = recomendacion(articulos, lista, supers, 3);
  assert.equal(r.tipo, "uno");
  assert.equal(r.uno.id, "m");
  assert.equal(r.ahorro, 0.76);
});

test("recomienda repartir si el ahorro supera el umbral", () => {
  const lista = { leche: 60, arroz: 20, aceite: 1 };
  const r = recomendacion(articulos, lista, supers, 3);
  assert.equal(r.tipo, "dos");
  assert.equal(r.uno.id, "m");
  assert.deepEqual(r.par.ids, ["d", "a"]);
  assert.equal(r.ahorro, 9.1);
});

test("lista vacía", () => {
  const r = recomendacion(articulos, {}, supers);
  assert.equal(r.uno.total, 0);
});

test("codificar y decodificar la lista", () => {
  const texto = codificarLista({ leche: 6, arroz: 0.5, nada: 0 });
  assert.equal(texto, "leche:6,arroz:0.5");
  assert.deepEqual(decodificarLista(texto + ",falso:3,aceite:x", ["leche", "arroz", "aceite"]), {
    leche: 6,
    arroz: 0.5,
  });
  assert.deepEqual(decodificarLista("", ["leche"]), {});
});

test("formatos en español", () => {
  assert.equal(formatoEuros(48.2).replace(/\s/g, " "), "48,20 €");
  assert.equal(formatoCantidad(6, "l"), "6 L");
  assert.equal(formatoCantidad(0.25, "kg"), "250 g");
  assert.equal(formatoCantidad(1.5, "kg"), "1,5 kg");
  assert.equal(formatoCantidad(12, "ud"), "12 uds.");
});

test("paso del selector de cantidad", () => {
  assert.equal(pasoCantidad("ud", 12), 6);
  assert.equal(pasoCantidad("kg", 0.25), 0.05);
  assert.equal(pasoCantidad("l", 6), 1);
});
