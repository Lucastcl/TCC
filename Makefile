PYTHON ?= $(shell if command -v python3.12 >/dev/null 2>&1; then echo python3.12; elif command -v python3.11 >/dev/null 2>&1; then echo python3.11; else echo python3; fi)
VENV := .venv
JUPYTER := $(VENV)/bin/jupyter
RSCRIPT ?= Rscript
HTML := $(abspath resultados/relatorios)
export RENV_CONFIG_SANDBOX_ENABLED := FALSE

.PHONY: setup setup-python setup-r dados atualizar-fontes analise modelagem verificar all

setup: setup-python setup-r

setup-python:
	$(PYTHON) -m venv --clear $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requisitos_python.txt
	$(VENV)/bin/playwright install chromium

setup-r:
	$(RSCRIPT) -e "if (!requireNamespace('renv', quietly = TRUE)) install.packages('renv'); renv::restore(prompt = FALSE)"

dados:
	$(JUPYTER) nbconvert --to notebook --execute 01_preparacao_dados/01_tratamento_isp.ipynb --output-dir resultados/relatorios --output 01_tratamento_isp_executado.ipynb --ExecutePreprocessor.timeout=600
	$(RSCRIPT) -e "rmarkdown::render('01_preparacao_dados/03_tratamento_fogo_cruzado.Rmd', output_dir='$(HTML)', quiet=TRUE)"
	$(RSCRIPT) -e "rmarkdown::render('01_preparacao_dados/04_tratamento_ips.Rmd', output_dir='$(HTML)', quiet=TRUE)"
	$(RSCRIPT) -e "rmarkdown::render('01_preparacao_dados/06_calcular_areas_faccoes.Rmd', output_dir='$(HTML)', quiet=TRUE)"
	$(RSCRIPT) -e "rmarkdown::render('01_preparacao_dados/07_tratamento_ibge.Rmd', output_dir='$(HTML)', quiet=TRUE)"
	$(RSCRIPT) -e "rmarkdown::render('01_preparacao_dados/08_construir_base_longitudinal.Rmd', output_dir='$(HTML)', quiet=TRUE)"

atualizar-fontes:
	$(VENV)/bin/python 01_preparacao_dados/02_baixar_fogo_cruzado.py
	$(VENV)/bin/python 01_preparacao_dados/05_extrair_mapas_faccoes.py
	$(RSCRIPT) -e "rmarkdown::render('01_preparacao_dados/03_tratamento_fogo_cruzado.Rmd', output_dir='$(HTML)', quiet=TRUE)"
	$(RSCRIPT) -e "rmarkdown::render('01_preparacao_dados/06_calcular_areas_faccoes.Rmd', output_dir='$(HTML)', params=list(recalcular_geometrias=TRUE), quiet=TRUE)"

analise:
	$(RSCRIPT) -e "rmarkdown::render('02_analise_exploratoria/01_analise_exploratoria_centralizada.Rmd', output_dir='$(HTML)', quiet=TRUE)"

modelagem:
	$(RSCRIPT) -e "rmarkdown::render('03_modelagem/01_modelagem_gee_final_distancia_de_cook.Rmd', output_dir='$(HTML)', quiet=TRUE)"

verificar:
	$(VENV)/bin/python verificar_projeto.py

all: dados analise modelagem verificar
