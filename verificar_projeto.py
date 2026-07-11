from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJETO = Path(__file__).resolve().parent
BASE = PROJETO / "dados" / "finais" / "base_longitudinal_2019_2024.csv"
COEFICIENTES = PROJETO / "resultados" / "tabelas" / "modelo_final_coeficientes.csv"
COOK = PROJETO / "resultados" / "tabelas" / "distancia_cook_tabela_diagnostico.csv"
AUDITORIA = PROJETO / "resultados" / "auditorias" / "auditoria_reproducao_tcc.json"


def ler_csv_decimal(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=";", decimal=",")


def conferir_proximo(valor: float, esperado: float, tolerancia: float, nome: str) -> None:
    if abs(float(valor) - esperado) > tolerancia:
        raise AssertionError(f"{nome}: esperado {esperado}, obtido {valor}")


base = ler_csv_decimal(BASE)

assert base.shape == (954, 15)
assert base["bairro"].nunique() == 159
assert sorted(base["ano"].unique().tolist()) == list(range(2019, 2025))
assert not base.duplicated(["bairro", "ano"]).any()
assert not base.isna().any().any()
assert int(base["n_mvi"].sum()) == 7419
assert int(base["fc_total_tiroteios"].sum()) == 15380
assert int(base["fc_acao_policial"].sum()) == 4337

coeficientes = pd.read_csv(COEFICIENTES)
esperados = {
    "(Intercept)": 1.6494,
    "tempo": -0.5241,
    "I(tempo^2)": 0.2149,
    "I(tempo^3)": -0.0242,
    "acao_policial": 0.0351,
    "pop_total": 0.1127,
    "milicia": 0.0062,
    "renda": -0.0675,
    "tempo:acao_policial": 0.0299,
    "I(tempo^2):acao_policial": -0.0136,
    "I(tempo^3):acao_policial": 0.0017,
}

coef_mapa = coeficientes.set_index("termo")["estimativa"].to_dict()
for termo, esperado in esperados.items():
    assert termo in coef_mapa, f"Termo ausente no modelo final: {termo}"
    conferir_proximo(coef_mapa[termo], esperado, 0.0015, termo)

cook = pd.read_csv(COOK)
assert "Barra da Tijuca" in set(cook["bairro"])
barra = cook.loc[cook["bairro"].eq("Barra da Tijuca")].iloc[0]
assert barra["max_abs_dbetacs"] >= 1

artefatos_esperados = [
    "resultados/figuras/cap5_fig01_trajetorias_mvi_bairros.png",
    "resultados/figuras/cap5_fig02_trajetorias_mvi_sem_bangu.png",
    "resultados/figuras/cap5_fig03_trajetorias_amostra_bairros.png",
    "resultados/figuras/cap5_fig04_trajetorias_top10_mvi.png",
    "resultados/figuras/cap5_fig05_renda_mvi_medio.png",
    "resultados/figuras/cap5_fig06_populacao_mvi_medio.png",
    "resultados/figuras/cap5_fig07_favelas_mvi_medio.png",
    "resultados/figuras/cap5_fig08_agua_saneamento_mvi_medio.png",
    "resultados/figuras/cap5_fig09_acao_policial_mvi_anual.png",
    "resultados/figuras/cap5_fig10_tiroteios_mvi_anual.png",
    "resultados/figuras/cap5_fig11_dominio_ada_mvi_anual.png",
    "resultados/figuras/cap5_fig12_dominio_cv_mvi_anual.png",
    "resultados/figuras/cap5_fig13_dominio_milicia_mvi_anual.png",
    "resultados/figuras/cap5_fig14_dominio_tcp_mvi_anual.png",
    "resultados/figuras/cap6_fig21_trajetoria_media_estimada_mvi.jpeg",
    "resultados/figuras/cap6_fig22_observado_ajustado_mvi.jpeg",
    "resultados/figuras/analise_trajetorias_mvi_bairros.png",
    "resultados/figuras/analise_trajetorias_top10_mvi.png",
    "resultados/figuras/analise_mvi_acao_policial_por_ano.png",
    "resultados/figuras/analise_mvi_tiroteios_por_ano.png",
    "resultados/figuras/analise_mvi_dominio_territorial.png",
    "resultados/figuras/distancia_cook_dcls_bairro.png",
    "resultados/figuras/distancia_cook_dbetacs_acao_policial.png",
    "resultados/figuras/distancia_cook_dbetacs_pop_total.png",
    "resultados/figuras/distancia_cook_dbetacs_milicia.png",
    "resultados/figuras/distancia_cook_dbetacs_renda.png",
    "resultados/tabelas/analise_estatisticas_mvi_anuais.csv",
    "resultados/tabelas/analise_correlacao_mvi_entre_anos.csv",
    "resultados/tabelas/modelo_final_coeficientes.csv",
    "resultados/tabelas/distancia_cook_tabela_diagnostico.csv",
]

faltantes = [rel for rel in artefatos_esperados if not (PROJETO / rel).exists()]
assert not faltantes, f"Artefatos ausentes: {faltantes}"

AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
for json_antigo in AUDITORIA.parent.glob("*.json"):
    if json_antigo.name != AUDITORIA.name:
        json_antigo.unlink()

auditoria = {
    "base": {
        "linhas": int(base.shape[0]),
        "colunas": int(base.shape[1]),
        "bairros": int(base["bairro"].nunique()),
        "anos": sorted(int(x) for x in base["ano"].unique()),
        "total_mvi": int(base["n_mvi"].sum()),
        "total_tiroteios": int(base["fc_total_tiroteios"].sum()),
        "total_acoes_policiais": int(base["fc_acao_policial"].sum()),
        "duplicatas_bairro_ano": int(base.duplicated(["bairro", "ano"]).sum()),
        "valores_ausentes": int(base.isna().sum().sum()),
    },
    "modelo_final": {
        "estrutura_correlacao": "Exchangeable",
        "coeficientes_conferidos": esperados,
        "tolerancia_coeficientes": 0.0015,
    },
    "cook": {
        "bairro_maior_dbetacs": "Barra da Tijuca",
        "max_abs_dbetacs_barra": float(barra["max_abs_dbetacs"]),
    },
    "artefatos_conferidos": artefatos_esperados,
}

AUDITORIA.write_text(
    json.dumps(auditoria, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print("Validação concluída.")
print("159 bairros, 954 linhas, 15 variáveis, 7.419 MVI, 15.380 tiroteios e 4.337 ações policiais.")
print(f"Auditoria consolidada: {AUDITORIA}")
