# Cesta Madrid

Compara cuánto cuesta vuestra lista de la compra en **Mercadona, Dia, Aldi, Alcampo y Ahorramás** (Madrid) y dice dónde sale más barata: en un solo súper o repartiendo entre dos.

**Web:** https://cfernande1408.github.io/cesta-madrid/

## Cómo funciona

1. `cesta.json` define los artículos genéricos que compráis ("Leche semidesnatada", "Huevos"…) con palabras que deben aparecer o que los descartan.
2. Cada mañana, GitHub Actions ejecuta `scraper.run`: busca cada artículo en la web de cada súper y se queda con el producto **más barato por kilo, litro o unidad** que cumple los filtros.
3. Los resultados se guardan en `web/data/precios.json` y la web se publica en GitHub Pages.
4. En la web eliges artículos y cantidades; calcula el total en cada súper y la mejor pareja de súper. La lista se guarda en el navegador y se puede compartir con un enlace.

```
cesta.json ──► scraper (Actions, diario) ──► web/data/precios.json ──► web (Pages)
                 ├─ Mercadona: catálogo por categorías (almacén mad1)
                 ├─ Dia: buscador JSON
                 ├─ Aldi: sitemap de productos + fichas candidatas
                 ├─ Alcampo: buscador JSON
                 └─ Ahorramás: resultados de búsqueda en HTML
```

## Añadir o ajustar artículos

Edita `cesta.json` (se puede hacer desde GitHub). Cada artículo:

| Campo | Para qué |
|---|---|
| `id` | Identificador único, sin espacios |
| `nombre` | Lo que se ve en la web |
| `categoria` | Agrupa los artículos en la web |
| `busqueda` | Texto que se busca en cada súper |
| `incluir` | Frases que **deben** aparecer en el nombre del producto. Alternativas con `\|`: `"espagueti\|spaghetti"`. Si no se pone, se exigen todas las palabras de `busqueda` |
| `excluir` | Frases que descartan un producto (`"sin lactosa"`, `"batido"`) |
| `unidad` | `kg`, `l` o `ud`: en qué se compara el precio |
| `cantidad` | Cantidad habitual al añadirlo a la lista |
| `fijar` | Opcional. Producto concreto por súper: `{"mercadona": "10381"}` |

Al guardar, el workflow **Precios** vuelve a descargar los precios. Para afinar filtros, mira `web/data/estado.json`: para cada artículo y súper indica cuántos resultados hubo, cuántos pasaron los filtros y cuál se eligió.

## Desarrollo

```bash
pip install -r requirements.txt
python -m pytest -q          # tests del scraper
npm test                     # tests del comparador de la web
python -m scraper.run --solo dia   # descargar precios de un súper
python -m http.server -d web       # ver la web en http://localhost:8000
```

Un push que toque el scraper o `cesta.json` lanza el workflow **Precios**. Si el mensaje del commit lleva `[solo: aldi dia]`, solo se consultan esos súper (útil para probar uno sin molestar al resto).

## Avisos

- Son los precios que cada cadena publica en su web (Aldi no vende online, pero publica su surtido con precios de península); en tienda pueden variar algo.
- El coste de cada línea es una estimación: precio por kilo/litro/unidad × cantidad.
- Dia se compara con el precio sin tarjeta Club Dia.
- El scraper hace pocas peticiones y espaciadas (una vez al día). El `robots.txt` de Mercadona no permite rastrear su `/api`; si prefieres respetarlo, quita `mercadona` de `ajustes.supermercados` en `cesta.json`.
- Alcampo protege su web con un WAF que, tras unas pocas búsquedas, pide resolver un reto en el navegador. El scraper no lo salta: para en cuanto aparece y al día siguiente empieza por los artículos con el precio más antiguo, así que los precios de Alcampo se renuevan por turnos y pueden tener unos días (se descartan pasados 14).
- Carrefour no está incluido: su web bloquea las peticiones automáticas.
