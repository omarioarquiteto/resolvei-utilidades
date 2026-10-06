from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/financiamento", tags=["financiamento"])

BCB_BASE = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata"
BCB_DAILY = BCB_BASE + "/TaxasJurosDiariaPorInicioPeriodo"
BCB_MONTHLY = BCB_BASE + "/TaxasJurosMensalPorMes"

BANKS = [
    {
        "id": "caixa",
        "name": "CAIXA",
        "aliases": ["CAIXA ECONOMICA FEDERAL"],
        "real_estate": "Imóveis: SAC e PRICE. Linhas públicas com TR, IPCA, Poupança CAIXA e taxa fixa. O contrato real também pode incluir MIP/DFI e demais encargos.",
        "vehicle": "Veículos: Crédito Auto CAIXA para carros e motos, novos e usados; a página pública informa financiamento de até 90%, com taxa prefixada, sujeito à análise.",
        "source_real_estate": "https://www.caixa.gov.br/voce/habitacao/financiamento-habitacao/Paginas/default.aspx",
        "source_vehicle": "https://www.caixa.gov.br/agenciadigital/credito/Paginas/default.aspx",
    },
    {
        "id": "bb",
        "name": "Banco do Brasil",
        "aliases": ["BCO DO BRASIL S.A.", "BANCO DO BRASIL S.A."],
        "real_estate": "Imóveis: linhas MCMV, Classe Média, Pró-Cotista, SFH e SBPE. A página pública informa até 80% de financiamento para imóveis urbanos e prazo de até 420 meses em determinadas linhas.",
        "vehicle": "Veículos: o BB informa que as condições dependem do perfil, veículo, entrada e prazo; a página pública consultada informa até 70% de financiamento para veículos.",
        "source_real_estate": "https://www.bb.com.br/site/pra-voce/financiamentos/financiamento-imobiliario/",
        "source_vehicle": "https://www.bb.com.br/site/pra-voce/financiamentos/financiamento-de-veiculos/",
    },
    {
        "id": "santander",
        "name": "Santander",
        "aliases": ["BCO SANTANDER (BRASIL) S.A.", "SANTANDER SCFI S.A."],
        "real_estate": "Imóveis: até 90% para residencial, prazo de até 35 anos e opções PRICE fixa ou SAC atualizável; FGTS pode ser utilizado conforme as regras vigentes.",
        "vehicle": "Veículos: até 100%, novos ou usados, com prazo de até 60 meses, sujeito à análise.",
        "source_real_estate": "https://www.santander.com.br/financiamentos/credito-imobiliario",
        "source_vehicle": "https://www.santander.com.br/financiamentos/financiamento-de-veiculos",
    },
    {
        "id": "bradesco",
        "name": "Bradesco",
        "aliases": ["BCO BRADESCO S.A.", "BCO BRADESCO FINANC. S.A."],
        "real_estate": "Imóveis: SAC e Tabela Price. A página de simulador apresenta comparação direta entre os dois sistemas; há linhas vinculadas ao rendimento da poupança.",
        "vehicle": "Veículos: financiamento de até 100% e prazo de até 60 meses, incluindo veículos novos e usados, sujeito às condições da proposta.",
        "source_real_estate": "https://banco.bradesco/html/classic/produtos-servicos/emprestimo-e-financiamento/encontre-seu-credito/simuladores-imoveis.shtm",
        "source_vehicle": "https://www.bdn.bradesco.com.br/html/prime/produtos-servicos/emprestimo-e-financiamento/financiamento-veiculos.shtm",
    },
    {
        "id": "itau",
        "name": "Itaú",
        "aliases": ["ITAÚ UNIBANCO HOLDING S.A.", "ITAU UNIBANCO HOLDING S.A.", "ITAÚ UNIBANCO S.A.", "ITAU UNIBANCO S.A."],
        "real_estate": "Imóveis: linhas de taxa prefixada e juros da poupança; a simulação pública oferece SAC e MIX. A taxa individual depende da proposta e do perfil.",
        "vehicle": "Veículos: as condições variam conforme perfil do cliente e proposta; não há uma taxa única válida para todos.",
        "source_real_estate": "https://www.itau.com.br/emprestimos-financiamentos/credito-imobiliario",
        "source_vehicle": "https://feito.itau.com.br/financiamento-carro-verdades-mitos",
    },
]

CACHE_TTL = 12 * 60 * 60
_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cached(key: str) -> Any | None:
    with _lock:
        item = _cache.get(key)
        if item and time.time() - item[0] < CACHE_TTL:
            return item[1]
    return None


def _set_cache(key: str, value: Any) -> None:
    with _lock:
        _cache[key] = (time.time(), value)


def _bcb_get(endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
    query = dict(params)
    query["$format"] = "json"
    try:
        response = requests.get(
            endpoint,
            params=query,
            timeout=12,
            headers={"User-Agent": "Resolvei-Financiamento/1.0"},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("value", []) if isinstance(data, dict) else []
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Não foi possível atualizar os dados do Banco Central.") from exc


def _filter_banks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = {
        str(r.get("InstituicaoFinanceira", "")).strip().upper(): r
        for r in rows if r.get("InstituicaoFinanceira")
    }
    chosen: dict[str, dict[str, Any]] = {}

    for bank in BANKS:
        found = None
        for alias in bank["aliases"]:
            alias_u = alias.upper()
            if alias_u in normalized:
                found = normalized[alias_u]
                break
            for name, row in normalized.items():
                if alias_u in name or name in alias_u:
                    found = row
                    break
            if found:
                break
        if found:
            chosen[bank["id"]] = found

    for row in rows:
        name = str(row.get("InstituicaoFinanceira", "")).strip()
        if not name:
            continue
        key = "bcb:" + "".join(ch for ch in name.lower() if ch.isalnum())[:60]
        if key not in chosen:
            chosen[key] = row

    result = []
    for key, row in chosen.items():
        result.append(
            {
                "id": key,
                "name": str(row.get("InstituicaoFinanceira", "")),
                "monthly_rate": float(row.get("TaxaJurosAoMes") or 0),
                "annual_rate": float(row.get("TaxaJurosAoAno") or 0),
                "start_date": row.get("InicioPeriodo"),
                "end_date": row.get("FimPeriodo"),
                "month": row.get("Mes"),
                "cnpj8": row.get("cnpj8"),
            }
        )
    return result


def _daily_vehicle_rates() -> dict[str, Any]:
    key = "vehicle"
    cached = _cached(key)
    if cached:
        return cached

    rows = _bcb_get(
        BCB_DAILY,
        {
            "$top": "3000",
            "$select": "InicioPeriodo,FimPeriodo,Segmento,Modalidade,InstituicaoFinanceira,TaxaJurosAoMes,TaxaJurosAoAno,cnpj8",
            "$filter": "Segmento eq 'PESSOA FÍSICA' and Modalidade eq 'Aquisição de veículos - Prefixado'",
            "$orderby": "InicioPeriodo desc",
        },
    )
    if not rows:
        raise HTTPException(status_code=502, detail="O Banco Central não retornou dados recentes para aquisição de veículos.")

    latest_start = max(str(r.get("InicioPeriodo") or "") for r in rows)
    latest = [r for r in rows if str(r.get("InicioPeriodo") or "") == latest_start]
    result = {
        "source": BCB_DAILY,
        "source_type": "BCB — média das operações dos últimos dias úteis publicados",
        "reference_start": latest_start,
        "reference_end": max(str(r.get("FimPeriodo") or "") for r in latest),
        "rates": _filter_banks(latest),
    }
    _set_cache(key, result)
    return result


def _monthly_property_rates(modality: str) -> dict[str, Any]:
    key = "property:" + modality
    cached = _cached(key)
    if cached:
        return cached

    rows = _bcb_get(
        BCB_MONTHLY,
        {
            "$top": "5000",
            "$select": "Mes,Modalidade,InstituicaoFinanceira,TaxaJurosAoMes,TaxaJurosAoAno,cnpj8,anoMes",
            "$filter": "Modalidade eq '" + modality + "'",
        },
    )
    if not rows:
        raise HTTPException(status_code=502, detail="O Banco Central não retornou dados para esta modalidade imobiliária.")

    periods = [str(r.get("anoMes") or "") for r in rows if r.get("anoMes")]
    latest_period = max(periods) if periods else ""
    latest = [r for r in rows if str(r.get("anoMes") or "") == latest_period]
    result = {
        "source": BCB_MONTHLY,
        "source_type": "BCB — média mensal das operações informadas pelas instituições",
        "reference_period": str(latest[0].get("Mes") or latest_period),
        "rates": _filter_banks(latest),
    }
    _set_cache(key, result)
    return result


@router.get("/dados")
def financiamento_dados(
    tipo: str = Query("imovel", pattern="^(imovel|veiculo)$"),
    linha: str = Query("tr"),
) -> dict[str, Any]:
    if tipo == "veiculo":
        market = _daily_vehicle_rates()
    else:
        modalities = {
            "tr": "Financiamento imobiliário com taxas de mercado - Pós-fixado referenciado em TR",
            "prefixado": "Financiamento imobiliário com taxas de mercado - Prefixado",
            "tr_regulado": "Financiamento imobiliário com taxas reguladas - Pós-fixado referenciado em TR",
            "prefixado_regulado": "Financiamento imobiliário com taxas reguladas - Prefixado",
        }
        if linha == "poupanca":
            market = {
                "source": None,
                "source_type": "Sem benchmark BCB específico para juros da poupança nesta API.",
                "reference_period": None,
                "rates": [],
            }
        elif linha in modalities:
            market = _monthly_property_rates(modalities[linha])
        else:
            raise HTTPException(status_code=400, detail="Linha de financiamento imobiliário inválida.")

    return {
        "ok": True,
        "fetched_at": _now_iso(),
        "cache_ttl_hours": CACHE_TTL / 3600,
        "tipo": tipo,
        "linha": linha,
        "market": market,
        "banks": BANKS,
        "disclaimer": "As taxas do BCB são médias observadas no mercado e não representam uma proposta ou taxa garantida para o usuário. A condição real depende de perfil, entrada, prazo, produto, garantias e análise de crédito.",
    }


@router.post("/atualizar")
def financiamento_atualizar(tipo: str = "imovel", linha: str = "tr") -> dict[str, Any]:
    key = "vehicle" if tipo == "veiculo" else "property:" + linha
    with _lock:
        _cache.pop(key, None)
    return financiamento_dados(tipo=tipo, linha=linha)
