from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

import geopandas as gpd
from playwright.sync_api import sync_playwright
from pyproj import Transformer
from shapely.geometry import GeometryCollection, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union


URL_TEMPLATE = (
    "https://fogocruzado.org.br/mapadosgruposarmados/Mapview_Final/"
    "Mapa_Controle_Influencia_{year}.html"
)

CODIGO_DIR = Path(__file__).resolve().parent
PROJETO_DIR = CODIGO_DIR.parent
DADOS_DIR = PROJETO_DIR / "dados"
FACCOES_DIR = DADOS_DIR / "brutos" / "faccoes"
MALHAS_DIR = DADOS_DIR / "brutos" / "malhas"
RAW_DIR_DEFAULT = FACCOES_DIR / "geojson_bruto_2019_2024"
ENRICHED_DIR_DEFAULT = FACCOES_DIR / "geojson_enriquecido_2019_2024"
SUMMARY_PATH_DEFAULT = PROJETO_DIR / "resultados" / "auditorias" / "extracao_mapas_faccoes.json"
REF_2017_DEFAULT = MALHAS_DIR / "limite_bairros_2017.geojson"
REF_2024_DEFAULT = MALHAS_DIR / "limite_bairros_2024.geojson"

AREA_TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)

FAVELA_ALIASES = {
    "ada": "ADA",
    "amigos dos amigos": "ADA",
    "amigo dos amigos": "ADA",
    "bonde do ecko": "Bonde do Ecko",
    "cevada": "CV",
    "comando vermelho": "CV",
    "cv": "CV",
    "milicia": "Milicia",
    "milicia ": "Milicia",
    "milicia tradicional": "Milicia",
    "milicia nova": "Milicia",
    "tcp": "TCP",
    "terceiro comando": "TCP",
    "terceiro comando puro": "TCP",
}

EXTRACTION_SCRIPT = r"""
() => {
  function isPrimitive(value) {
    return value === null || ["string", "number", "boolean"].includes(typeof value);
  }

  function safeSerialize(value, depth = 0, seen = new WeakSet()) {
    if (depth > 4) {
      return null;
    }
    if (isPrimitive(value)) {
      return value;
    }
    if (typeof value === "function" || typeof value === "undefined") {
      return null;
    }
    if (typeof Element !== "undefined" && value instanceof Element) {
      return value.outerHTML;
    }
    if (typeof value === "object") {
      if (seen.has(value)) {
        return null;
      }
      seen.add(value);
      if (Array.isArray(value)) {
        return value.slice(0, 50).map((item) => safeSerialize(item, depth + 1, seen));
      }
      const out = {};
      for (const [key, nested] of Object.entries(value)) {
        if (key.startsWith("_")) {
          continue;
        }
        const serialized = safeSerialize(nested, depth + 1, seen);
        if (serialized !== null) {
          out[key] = serialized;
        }
      }
      return out;
    }
    return String(value);
  }

  function htmlToText(value) {
    if (!value) {
      return null;
    }
    if (typeof value !== "string") {
      if (typeof Element !== "undefined" && value instanceof Element) {
        value = value.outerHTML;
      } else {
        value = String(value);
      }
    }
    const wrapper = document.createElement("div");
    wrapper.innerHTML = value;
    const text = wrapper.textContent ? wrapper.textContent.replace(/\s+/g, " ").trim() : "";
    return text || null;
  }

  function closeRing(ring) {
    if (!Array.isArray(ring) || ring.length === 0) {
      return ring;
    }
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (Array.isArray(first) && Array.isArray(last) && (first[0] !== last[0] || first[1] !== last[1])) {
      return [...ring, first];
    }
    return ring;
  }

  function convertLatLngs(value) {
    if (!Array.isArray(value)) {
      return null;
    }
    if (value.length === 0) {
      return [];
    }
    if (value[0] && typeof value[0].lat === "number" && typeof value[0].lng === "number") {
      return value.map((point) => [point.lng, point.lat]);
    }
    return value.map(convertLatLngs);
  }

  function nestedDepth(value) {
    let depth = 0;
    let cursor = value;
    while (Array.isArray(cursor) && cursor.length) {
      depth += 1;
      cursor = cursor[0];
    }
    return depth;
  }

  function geometryFromLatLngs(latlngs) {
    const coordinates = convertLatLngs(latlngs);
    if (!coordinates) {
      return null;
    }
    const depth = nestedDepth(coordinates);
    if (depth === 2) {
      return { type: "Polygon", coordinates: [closeRing(coordinates)] };
    }
    if (depth === 3) {
      return { type: "Polygon", coordinates: coordinates.map(closeRing) };
    }
    if (depth === 4) {
      return {
        type: "MultiPolygon",
        coordinates: coordinates.map((polygon) => polygon.map(closeRing)),
      };
    }
    return null;
  }

  function getPopupHtml(layer) {
    if (!layer || !layer._popup) {
      return null;
    }
    const content = layer._popup._content ?? layer._popup.getContent?.();
    if (!content) {
      return null;
    }
    if (typeof Element !== "undefined" && content instanceof Element) {
      return content.outerHTML;
    }
    return typeof content === "string" ? content : String(content);
  }

  function getTooltipHtml(layer) {
    if (!layer || !layer._tooltip) {
      return null;
    }
    const content = layer._tooltip._content ?? layer._tooltip.getContent?.();
    if (!content) {
      return null;
    }
    if (typeof Element !== "undefined" && content instanceof Element) {
      return content.outerHTML;
    }
    return typeof content === "string" ? content : String(content);
  }

  function getGeometry(layer) {
    try {
      if (typeof layer.toGeoJSON === "function") {
        const payload = layer.toGeoJSON();
        if (payload?.type === "Feature" && payload.geometry) {
          if (payload.geometry.type === "Polygon" || payload.geometry.type === "MultiPolygon") {
            return payload.geometry;
          }
        }
        if (payload?.type === "Polygon" || payload?.type === "MultiPolygon") {
          return payload;
        }
      }
    } catch (error) {}
    try {
      if (typeof layer.getLatLngs === "function") {
        return geometryFromLatLngs(layer.getLatLngs());
      }
    } catch (error) {}
    return null;
  }

  function collectMaps() {
    const maps = [];
    const seen = new Set();

    function addMap(candidate) {
      if (!candidate || typeof candidate.eachLayer !== "function") {
        return;
      }
      const mapId = candidate._leaflet_id ?? candidate._container?.id ?? candidate._container;
      if (seen.has(mapId)) {
        return;
      }
      seen.add(mapId);
      maps.push(candidate);
    }

    if (window.L?.Map) {
      for (const value of Object.values(window)) {
        if (value instanceof window.L.Map) {
          addMap(value);
        }
      }
    }

    for (const element of document.querySelectorAll(".leaflet-container, .html-widget")) {
      addMap(element._leaflet_map);
      if (window.HTMLWidgets?.find && element.id) {
        try {
          const instance = window.HTMLWidgets.find("#" + element.id);
          addMap(instance?.getMap?.() ?? instance?.map ?? instance);
        } catch (error) {}
      }
    }

    return maps;
  }

  function layerType(layer) {
    if (layer?.feature?.geometry?.type) {
      return layer.feature.geometry.type;
    }
    if (layer?.constructor?.name) {
      return layer.constructor.name;
    }
    return typeof layer;
  }

  function flattenLayer(layer, mapIndex, out, seen) {
    if (!layer) {
      return;
    }
    const layerId = layer._leaflet_id ?? layer._leaflet_stamp ?? null;
    if (layerId !== null && seen.has(layerId)) {
      return;
    }
    if (layerId !== null) {
      seen.add(layerId);
    }

    const geometry = getGeometry(layer);
    if (geometry && (geometry.type === "Polygon" || geometry.type === "MultiPolygon")) {
      const popupHtml = getPopupHtml(layer);
      const tooltipHtml = getTooltipHtml(layer);
      const featureProperties = safeSerialize(layer.feature?.properties ?? {});
      const layerOptions = safeSerialize(layer.options ?? {});

      out.push({
        type: "Feature",
        geometry,
        properties: {
          map_index: mapIndex,
          layer_id: layerId,
          layer_type: layerType(layer),
          popup_html: popupHtml,
          popup_text: htmlToText(popupHtml),
          tooltip_html: tooltipHtml,
          tooltip_text: htmlToText(tooltipHtml),
          feature_properties: featureProperties,
          raw_options: JSON.stringify(layerOptions ?? {}),
        },
      });
    }

    if (typeof layer.eachLayer === "function") {
      layer.eachLayer((child) => flattenLayer(child, mapIndex, out, seen));
    }
  }

  const maps = collectMaps();
  const features = [];
  const seenLayers = new Set();
  maps.forEach((map, index) => {
    map.eachLayer((layer) => flattenLayer(layer, index, features, seenLayers));
  });

  const cloudflareText =
    document.body?.innerText?.includes("Enable JavaScript and cookies to continue") ||
    document.title === "Just a moment...";

  return {
    title: document.title,
    url: location.href,
    map_count: maps.length,
    feature_count: features.length,
    cloudflare_detected: Boolean(cloudflareText),
    features,
  };
}
"""


def parser():
    arg_parser = argparse.ArgumentParser(description="Extrai HTML do mapa do Fogo Cruzado e salva GeoJSON 2019-2024.")
    arg_parser.add_argument("--start-year", type=int, default=2019)
    arg_parser.add_argument("--end-year", type=int, default=2024)
    arg_parser.add_argument("--raw-dir", default=str(RAW_DIR_DEFAULT))
    arg_parser.add_argument("--enriched-dir", default=str(ENRICHED_DIR_DEFAULT))
    arg_parser.add_argument("--summary-path", default=str(SUMMARY_PATH_DEFAULT))
    arg_parser.add_argument("--bairro-ref-2017", default=str(REF_2017_DEFAULT))
    arg_parser.add_argument("--bairro-ref-2024", default=str(REF_2024_DEFAULT))
    arg_parser.add_argument(
        "--user-data-dir",
        default=str(PROJETO_DIR / ".cache" / "playwright-profile"),
    )
    arg_parser.add_argument("--timeout-ms", type=int, default=45000)
    arg_parser.add_argument("--interactive-wait-seconds", type=int, default=30)
    arg_parser.add_argument("--headless", action="store_true")
    arg_parser.add_argument("--cdp-url", default=None)
    return arg_parser


def escrever_json(caminho: Path, conteudo: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")


def normalizar_texto(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return " ".join(texto.lower().split())


def texto_limpo(valor):
    if valor is None:
        return None
    texto = " ".join(str(valor).split())
    return texto or None


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def carregar_malha(caminho: Path, prioridade: int, ano_ref: int) -> list[dict]:
    gdf = gpd.read_file(caminho)
    nome_colunas = ["nome", "NOME", "bairro", "BAIRRO", "name", "Name", "nm_bairro", "NM_BAIRRO"]
    codigo_colunas = ["codbairro", "CODBAIRRO", "codbairro_long", "CODBAIRRO_LONG", "codbnum", "CODBNUM"]

    coluna_nome = next((col for col in nome_colunas if col in gdf.columns), None)
    coluna_codigo = next((col for col in codigo_colunas if col in gdf.columns), None)
    if coluna_nome is None:
        raise ValueError(f"Nenhuma coluna de bairro encontrada em {caminho}")

    referencias = []
    for _, linha in gdf.iterrows():
        if linha.geometry is None or linha.geometry.is_empty:
            continue
        bairro = texto_limpo(linha[coluna_nome])
        if not bairro:
            continue
        referencias.append(
            {
                "bairro": bairro,
                "bairro_codigo": texto_limpo(linha[coluna_codigo]) if coluna_codigo else None,
                "prioridade": prioridade,
                "bairro_ref_year": ano_ref,
                "geometry": linha.geometry,
            }
        )
    return referencias


def geometry_area_m2(geometry: BaseGeometry) -> float:
    return transform(AREA_TRANSFORMER.transform, geometry).area


def normalizar_geom(geometry: BaseGeometry | None) -> BaseGeometry | None:
    if geometry is None or geometry.is_empty:
        return None
    geometry = geometry.buffer(0)
    if geometry.is_empty or geometry.area <= 0:
        return None
    return geometry


def achatar_dict(payload, max_depth: int = 3) -> list[tuple[str, object]]:
    itens = []

    def visitar(valor, caminho, depth):
        if depth > max_depth:
            return
        if isinstance(valor, dict):
            for chave, nested in valor.items():
                novo_caminho = f"{caminho}.{chave}" if caminho else str(chave)
                visitar(nested, novo_caminho, depth + 1)
            return
        if isinstance(valor, list):
            for indice, nested in enumerate(valor[:10]):
                visitar(nested, f"{caminho}[{indice}]", depth + 1)
            return
        itens.append((caminho, valor))

    visitar(payload, "", 0)
    return itens


def procurar_campo(payload: dict, candidatos: list[str]):
    candidatos_norm = [normalizar_texto(item) for item in candidatos]
    for caminho, valor in achatar_dict(payload):
        if valor is None:
            continue
        caminho_norm = normalizar_texto(caminho.replace(".", " ").replace("[", " ").replace("]", " "))
        if any(chave in caminho_norm for chave in candidatos_norm):
            texto = texto_limpo(valor)
            if texto:
                return texto
    return None


def derivar_faccao(properties: dict) -> tuple[str | None, str | None]:
    bruto = procurar_campo(
        properties,
        ["faccao", "facção", "faccao_raw", "grupo", "organizacao", "organização", "dominacao", "dominio", "controle"],
    )
    if not bruto:
        popup_text = texto_limpo(properties.get("popup_text"))
        if popup_text:
            match = re.search(r"facc?a[oã]\s*[:=-]\s*([^|,\n]+)", popup_text, flags=re.IGNORECASE)
            if match:
                bruto = texto_limpo(match.group(1))
        if popup_text and not bruto:
            texto_popup = normalizar_texto(popup_text)
            for alias, faccao in FAVELA_ALIASES.items():
                if alias in texto_popup:
                    bruto = faccao
                    break

    faccao = FAVELA_ALIASES.get(normalizar_texto(bruto)) if bruto else None
    if bruto and faccao is None:
        faccao = bruto
    return bruto, faccao


def derivar_bairro_raw(properties: dict):
    bruto = procurar_campo(properties, ["bairro", "nome_bairro", "nm_bairro", "nome", "name"])
    if bruto:
        return bruto
    popup_text = texto_limpo(properties.get("popup_text"))
    if not popup_text:
        return None
    match = re.search(r"bairro\s*[:=-]\s*([^|,\n]+)", popup_text, flags=re.IGNORECASE)
    if match:
        return texto_limpo(match.group(1))
    return None


def preparar_feature(feature: dict, year: int, url: str) -> dict:
    feature = json.loads(json.dumps(feature))
    props = feature.setdefault("properties", {})
    props["year"] = year
    props["source_url"] = url
    props["geometry_type"] = feature["geometry"]["type"]
    props["bairro_raw"] = derivar_bairro_raw(props)
    faccao_raw, faccao = derivar_faccao(props)
    props["faccao_raw"] = faccao_raw
    props["faccao"] = faccao
    return feature


def fragmentar_por_bairro(geometry: BaseGeometry, bairro_raw, refs_2024: list[dict], refs_2017: list[dict]) -> list[dict]:
    if geometry.is_empty:
        return []

    fragments = []
    remainder = geometry

    for referencias, bairro_source, ano_ref in [
        (refs_2024, "spatial_fragment_2024", 2024),
        (refs_2017, "spatial_fragment_2017_fallback", 2017),
    ]:
        matches = []
        for ref in referencias:
            if remainder.is_empty or not remainder.intersects(ref["geometry"]):
                continue
            inter = normalizar_geom(remainder.intersection(ref["geometry"]))
            if inter is None:
                continue
            matches.append(
                {
                    "geometry": inter,
                    "bairro": ref["bairro"],
                    "bairro_codigo": ref["bairro_codigo"],
                    "bairro_source": bairro_source,
                    "bairro_ref_year": ano_ref,
                }
            )

        if matches:
            fragments.extend(matches)
            covered = unary_union([item["geometry"] for item in matches])
            remainder = normalizar_geom(remainder.difference(covered)) or GeometryCollection()

    remainder = normalizar_geom(remainder)
    if remainder is not None:
        fragments.append(
            {
                "geometry": remainder,
                "bairro": None,
                "bairro_codigo": None,
                "bairro_source": "outside_reference_area",
                "bairro_ref_year": None,
            }
        )

    if fragments:
        return fragments

    if bairro_raw:
        return [
            {
                "geometry": geometry,
                "bairro": bairro_raw,
                "bairro_codigo": None,
                "bairro_source": "map",
                "bairro_ref_year": None,
            }
        ]

    return [
        {
            "geometry": geometry,
            "bairro": None,
            "bairro_codigo": None,
            "bairro_source": "outside_reference_area",
            "bairro_ref_year": None,
        }
    ]


def enriquecer_feature(feature: dict, refs_2024: list[dict], refs_2017: list[dict]) -> list[dict]:
    geometry = shape(feature["geometry"])
    props = feature.get("properties", {}).copy()
    bairro_raw = texto_limpo(props.get("bairro_raw")) or derivar_bairro_raw(props)
    faccao_raw, faccao = derivar_faccao(props)
    parent_area_m2 = geometry_area_m2(geometry) if not geometry.is_empty else 0.0

    fragments = fragmentar_por_bairro(geometry, bairro_raw, refs_2024, refs_2017)
    out = []
    for indice, fragment in enumerate(fragments, start=1):
        fragment_area_m2 = geometry_area_m2(fragment["geometry"])
        fragment_props = props.copy()
        fragment_props["bairro_raw"] = bairro_raw
        fragment_props["faccao_raw"] = faccao_raw
        fragment_props["faccao"] = faccao
        fragment_props["bairro"] = fragment["bairro"]
        fragment_props["bairro_codigo"] = fragment["bairro_codigo"]
        fragment_props["bairro_source"] = fragment["bairro_source"]
        fragment_props["bairro_ref_year"] = fragment["bairro_ref_year"]
        fragment_props["fragment_area_m2"] = round(fragment_area_m2, 3)
        fragment_props["fragment_index"] = indice
        fragment_props["fragment_count"] = len(fragments)
        fragment_props["parent_geometry_area_share_pct"] = (
            round(fragment_area_m2 / parent_area_m2 * 100.0, 6) if parent_area_m2 else None
        )
        out.append(
            {
                "type": "Feature",
                "geometry": mapping(fragment["geometry"]),
                "properties": fragment_props,
            }
        )
    return out


def poll_page_features(page, page_timeout_seconds: int, interactive_wait_seconds: int, headless: bool, year: int):
    deadline = time.time() + page_timeout_seconds
    manual_deadline = deadline + (0 if headless else interactive_wait_seconds)
    manual_notice_emitted = False
    last_status_log = 0.0
    last_payload = {
        "feature_count": 0,
        "cloudflare_detected": False,
        "features": [],
        "title": None,
        "url": page.url,
    }

    while time.time() < manual_deadline:
        payload = page.evaluate(EXTRACTION_SCRIPT)
        last_payload = payload
        if payload.get("feature_count", 0) > 0:
            return payload

        now = time.time()
        if now - last_status_log >= 5:
            title = payload.get("title") or "<no-title>"
            print(
                f"[year={year}] waiting features={payload.get('feature_count', 0)} "
                f"cloudflare={payload.get('cloudflare_detected', False)} title={title}"
            )
            last_status_log = now

        if (
            not headless
            and payload.get("cloudflare_detected")
            and not manual_notice_emitted
            and now >= deadline
        ):
            print("Cloudflare ainda ativo. Resolva no navegador aberto; o script vai continuar tentando.")
            manual_notice_emitted = True

        if now >= deadline and headless:
            break

        page.wait_for_timeout(1000)

    return last_payload


def abrir_contexto(user_data_dir: Path, headless: bool, cdp_url: str | None):
    playwright = sync_playwright().start()
    browser = None
    context = None

    if cdp_url:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        return playwright, browser, context, False

    try:
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel="chrome",
            headless=headless,
            viewport={"width": 1440, "height": 1000},
        )
    except Exception:
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=headless,
            viewport={"width": 1440, "height": 1000},
        )
    return playwright, browser, context, True


def extrair_ano(page, year: int, timeout_ms: int, interactive_wait_seconds: int, headless: bool, refs_2024, refs_2017):
    url = URL_TEMPLATE.format(year=year)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception:
        page.wait_for_timeout(1500)

    page.wait_for_timeout(2000)

    payload = poll_page_features(
        page=page,
        page_timeout_seconds=max(10, timeout_ms // 1000),
        interactive_wait_seconds=interactive_wait_seconds,
        headless=headless,
        year=year,
    )

    features = [preparar_feature(feature, year=year, url=url) for feature in payload.get("features", [])]
    raw_payload = feature_collection(features)
    enriched_features = []

    if features:
        for feature in features:
            enriched_features.extend(enriquecer_feature(feature, refs_2024, refs_2017))

    enriched_payload = feature_collection(enriched_features)
    bairro_source_counts = Counter(item["properties"].get("bairro_source", "unresolved") for item in enriched_features)

    return {
        "url": url,
        "raw_payload": raw_payload,
        "enriched_payload": enriched_payload,
        "raw_feature_count": len(features),
        "enriched_feature_count": len(enriched_features),
        "bairro_source_counts": dict(sorted(bairro_source_counts.items())),
        "cloudflare_detected": bool(payload.get("cloudflare_detected")),
    }


def main():
    args = parser().parse_args()
    if args.start_year > args.end_year:
        raise ValueError("--start-year precisa ser menor ou igual a --end-year")

    raw_dir = Path(args.raw_dir)
    enriched_dir = Path(args.enriched_dir)
    summary_path = Path(args.summary_path)
    refs_2017 = carregar_malha(Path(args.bairro_ref_2017), prioridade=0, ano_ref=2017)
    refs_2024 = carregar_malha(Path(args.bairro_ref_2024), prioridade=1, ano_ref=2024)

    raw_dir.mkdir(parents=True, exist_ok=True)
    enriched_dir.mkdir(parents=True, exist_ok=True)

    playwright = None
    browser = None
    context = None
    launched_context = False

    results = []
    try:
        playwright, browser, context, launched_context = abrir_contexto(
            user_data_dir=Path(args.user_data_dir),
            headless=args.headless,
            cdp_url=args.cdp_url,
        )
        page = context.pages[0] if context.pages else context.new_page()

        for year in range(args.start_year, args.end_year + 1):
            print(f"Extraindo {year}...")
            result = extrair_ano(
                page=page,
                year=year,
                timeout_ms=args.timeout_ms,
                interactive_wait_seconds=args.interactive_wait_seconds,
                headless=args.headless,
                refs_2024=refs_2024,
                refs_2017=refs_2017,
            )

            escrever_json(raw_dir / f"{year}.geojson", result["raw_payload"])
            escrever_json(enriched_dir / f"{year}.geojson", result["enriched_payload"])

            status = "ok" if result["raw_feature_count"] > 0 else "empty"
            error = None
            if status == "empty":
                error = "Nenhum poligono foi extraido do HTML."
                if result["cloudflare_detected"]:
                    error = "Nenhum poligono foi extraido. O Cloudflare ainda estava ativo."

            results.append(
                {
                    "year": year,
                    "url": result["url"],
                    "status": status,
                    "raw_feature_count": result["raw_feature_count"],
                    "enriched_feature_count": result["enriched_feature_count"],
                    "bairro_source_counts": result["bairro_source_counts"],
                    "error": error,
                }
            )
    finally:
        if context is not None and launched_context:
            context.close()
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()

    summary = {
        "raw_dir": str(raw_dir),
        "enriched_dir": str(enriched_dir),
        "reference_2017": str(Path(args.bairro_ref_2017)),
        "reference_2024": str(Path(args.bairro_ref_2024)),
        "processed_years": [item["year"] for item in results],
        "ok_years": [item["year"] for item in results if item["status"] == "ok"],
        "failed_years": [item["year"] for item in results if item["status"] != "ok"],
        "results": results,
    }
    escrever_json(summary_path, summary)

    print(f"Resumo salvo em: {summary_path}")
    print(f"Anos processados: {summary['processed_years']}")


if __name__ == "__main__":
    main()
