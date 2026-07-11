from pathlib import Path
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv


projeto = Path(__file__).resolve().parents[1]
load_dotenv(projeto / ".env")

email = os.getenv("FOGOCRUZADO_EMAIL")
senha = os.getenv("FOGOCRUZADO_PASSWORD")

if not email or not senha:
    raise RuntimeError(
        "Defina FOGOCRUZADO_EMAIL e FOGOCRUZADO_PASSWORD no ambiente ou no arquivo .env."
    )

arquivo_saida = (
    projeto
    / "dados"
    / "brutos"
    / "fogo_cruzado"
    / "ocorrencias_fogo_cruzado_2019_2024_atualizado.csv"
)
arquivo_saida.parent.mkdir(parents=True, exist_ok=True)

url_login = "https://api-service.fogocruzado.org.br/api/v2/auth/login"
url_estados = "https://api-service.fogocruzado.org.br/api/v2/states"
url_ocorrencias = "https://api-service.fogocruzado.org.br/api/v2/occurrences"

sessao = requests.Session()

resposta_login = sessao.post(
    url_login,
    json={"email": email, "password": senha},
    timeout=60,
)
resposta_login.raise_for_status()

token = resposta_login.json()["data"]["accessToken"]
sessao.headers.update({"Authorization": f"Bearer {token}"})

resposta_estados = sessao.get(url_estados, timeout=60)
resposta_estados.raise_for_status()
estados = pd.DataFrame(resposta_estados.json()["data"])

id_rio = estados.loc[estados["name"].eq("Rio de Janeiro"), "id"].iloc[0]


def extrair_nome(valor):
    if isinstance(valor, dict):
        return valor.get("name")
    return valor


registros = []
pagina = 1
take = 100

while True:
    resposta = sessao.get(
        url_ocorrencias,
        params={"idState": id_rio, "page": pagina, "take": take},
        timeout=120,
    )
    resposta.raise_for_status()
    carga = resposta.json()
    dados_pagina = carga.get("data", [])

    if not dados_pagina:
        break

    for item in dados_pagina:
        police_action = item.get("policeAction")
        registros.append(
            {
                "id": item.get("id"),
                "city_name": extrair_nome(item.get("city")),
                "date": item.get("date"),
                "neighborhood_name": extrair_nome(item.get("neighborhood")),
                "policeAction": police_action,
                "fc_acao_policial": int(bool(police_action)),
            }
        )

    print(f"Pagina {pagina}: {len(dados_pagina)} registros")

    if not carga.get("pageMeta", {}).get("hasNextPage", False):
        break

    pagina += 1
    time.sleep(0.2)

ocorrencias = pd.DataFrame(registros)
ocorrencias["date"] = pd.to_datetime(ocorrencias["date"], errors="coerce", utc=True)

recorte = ocorrencias.loc[
    ocorrencias["city_name"].eq("Rio de Janeiro")
    & ocorrencias["date"].dt.year.between(2019, 2024),
    ["id", "city_name", "date", "neighborhood_name", "policeAction", "fc_acao_policial"],
].copy()

recorte["date"] = recorte["date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
recorte.to_csv(arquivo_saida, index=False, encoding="utf-8-sig")

print("Registros salvos:", len(recorte))
print("Primeira data:", recorte["date"].min())
print("Ultima data:", recorte["date"].max())
print("Arquivo:", arquivo_saida)
