import os
import re
import sys
import shutil
import subprocess
from datetime import datetime

import pandas as pd

# =====================================================
# CONFIGURAÇÕES
# =====================================================

PASTA_PROJETO = r"G:\Meu Drive\CGE\bi_atualizacao\portal_empregados_terceirizados"
PASTA_UPLOAD = os.path.join(PASTA_PROJETO, "upload")

ARQUIVO_DE_PARA = os.path.join(
    PASTA_PROJETO,
    "de_para_orgao.xlsx"
)

EMPRESA = "Minas Gerais Administração e Serviços S.A"
CNPJ_EMPRESA = "33.224.254/0001-42"

# =====================================================
# LOG
# =====================================================

def log(msg):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{agora}] {msg}")


# =====================================================
# GITHUB
# =====================================================

def atualizar_github():
    log("Atualizando GitHub...")

    comandos = [
        ["git", "add", "."],
        ["git", "commit", "-m", "Atualizacao automatica empregados terceirizados"],
        ["git", "push", "origin", "main"]
    ]

    for cmd in comandos:

        resultado = subprocess.run(
            cmd,
            cwd=PASTA_PROJETO,
            capture_output=True,
            text=True
        )

        if resultado.returncode != 0:

            # commit sem alterações
            if (
                cmd[1] == "commit"
                and (
                    "nothing to commit" in resultado.stdout.lower()
                    or "nothing added to commit" in resultado.stdout.lower()
                )
            ):
                log("Nenhuma alteração para enviar.")
                return

            print(resultado.stdout)
            print(resultado.stderr)

            raise Exception(
                f"Erro ao executar: {' '.join(cmd)}"
            )

    log("GitHub atualizado com sucesso.")


# =====================================================
# MÊS
# =====================================================

def converter_mes_referencia(valor):

    if pd.isna(valor):
        return None

    valor = str(valor).strip().lower()

    meses_num = {
        "01": "jan",
        "02": "fev",
        "03": "mar",
        "04": "abr",
        "05": "mai",
        "06": "jun",
        "07": "jul",
        "08": "ago",
        "09": "set",
        "10": "out",
        "11": "nov",
        "12": "dez"
    }

    # já está correto (mai/26)
    if re.match(
        r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)/\d{2}$",
        valor
    ):
        return valor

    # formato 05/26
    m = re.match(r"^(\d{2})/(\d{2})$", valor)

    if m:
        mes = meses_num[m.group(1)]
        ano = m.group(2)
        return f"{mes}/{ano}"

    # formato 05/2026
    m = re.match(r"^(\d{2})/(\d{4})$", valor)

    if m:
        mes = meses_num[m.group(1)]
        ano = m.group(2)[2:]
        return f"{mes}/{ano}"

    # datas Excel / pandas
    try:
        dt = pd.to_datetime(valor)

        mes = meses_num[dt.strftime("%m")]
        ano = dt.strftime("%y")

        return f"{mes}/{ano}"

    except:
        return None


# =====================================================
# LOCALIZAR ARQUIVO
# =====================================================

def localizar_arquivo_mgs():

    arquivos = [
        arq
        for arq in os.listdir(PASTA_UPLOAD)
        if arq.upper().startswith("RELAÇÃO EMPREGADOS MGS")
        and arq.lower().endswith(".xlsx")
    ]

    if not arquivos:
        raise Exception(
            "Nenhum arquivo RELAÇÃO EMPREGADOS MGS encontrado."
        )

    if len(arquivos) > 1:
        raise Exception(
            f"Mais de um arquivo encontrado: {arquivos}"
        )

    return os.path.join(PASTA_UPLOAD, arquivos[0])


# =====================================================
# ANO DO ARQUIVO
# =====================================================

def obter_ano(nome_arquivo):

    m = re.search(r"(20\d{2})", nome_arquivo)

    if not m:
        raise Exception(
            "Não foi possível identificar o ano do arquivo."
        )

    return m.group(1)


# =====================================================
# PROCESSAMENTO
# =====================================================

def processar():

    arquivo_mgs = localizar_arquivo_mgs()

    log(f"Lendo arquivo: {arquivo_mgs}")

    ano = obter_ano(
        os.path.basename(arquivo_mgs)
    )

    arquivo_destino = os.path.join(
        PASTA_UPLOAD,
        f"terceirizados_{ano}.xlsx"
    )

    if not os.path.exists(arquivo_destino):
        raise Exception(
            f"Arquivo não encontrado: {arquivo_destino}"
        )

    # -------------------------------------------------
    # LEITURA
    # -------------------------------------------------

    df = pd.read_excel(
        arquivo_mgs,
        dtype=str
    )

    df.columns = [str(c).strip() for c in df.columns]

    obrigatorias = [
        "MAT.",
        "NOME",
        "CLIENTES",
        "CARGO ATUAL",
        "REF."
    ]

    faltantes = [
        c
        for c in obrigatorias
        if c not in df.columns
    ]

    if faltantes:
        raise Exception(
            f"Colunas ausentes: {faltantes}"
        )

    # -------------------------------------------------
    # RENOMEAR
    # -------------------------------------------------

    df = df.rename(columns={
        "MAT.": "matricula",
        "NOME": "nome",
        "CLIENTES": "orgao_original",
        "CARGO ATUAL": "cargo",
        "REF.": "ref"
    })

    # -------------------------------------------------
    # DE PARA
    # -------------------------------------------------

    log("Lendo de_para_orgao.xlsx")

    de_para = pd.read_excel(
        ARQUIVO_DE_PARA,
        sheet_name="de_para_orgao",
        dtype=str
    )

    de_para.columns = [
        str(c).strip()
        for c in de_para.columns
    ]

    mapa_orgao = dict(
        zip(
            de_para["de_orgao"],
            de_para["para_orgao"]
        )
    )

    mapa_sigla = dict(
        zip(
            de_para["de_orgao"],
            de_para["para_sigla"]
        )
    )

    mapa_codigo = dict(
        zip(
            de_para["de_orgao"],
            de_para["para_codigo"]
        )
    )

    # -------------------------------------------------
    # ÓRGÃOS NÃO MAPEADOS
    # -------------------------------------------------

    orgaos_encontrados = (
        df["orgao_original"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    nao_mapeados = sorted(
        set(orgaos_encontrados)
        - set(mapa_orgao.keys())
    )

    if nao_mapeados:

        arquivo_alerta = os.path.join(
            PASTA_PROJETO,
            "orgaos_nao_mapeados.xlsx"
        )

        pd.DataFrame({
            "orgao_original": nao_mapeados
        }).to_excel(
            arquivo_alerta,
            index=False
        )

        print("\n")
        print("=" * 60)
        print("ATENÇÃO")
        print("=" * 60)

        for orgao in nao_mapeados:
            print(orgao)

        print("\nArquivo gerado:")
        print(arquivo_alerta)

        print("\nProcessamento interrompido.")
        print("=" * 60)

        return

    # -------------------------------------------------
    # DE/PARA
    # -------------------------------------------------

    df["orgao"] = (
        df["orgao_original"]
        .map(mapa_orgao)
    )

    df["codigo"] = (
        df["orgao_original"]
        .map(mapa_codigo)
    )

    df["sigla"] = (
        df["orgao_original"]
        .map(mapa_sigla)
    )

    # -------------------------------------------------
    # EXCLUIR
    # -------------------------------------------------

    qtd_antes = len(df)

    df = df[
        ~df["orgao"]
        .fillna("")
        .str.upper()
        .eq("EXCLUIR")
    ]

    qtd_excluidos = qtd_antes - len(df)

    log(
        f"Registros excluídos por regra de negócio: {qtd_excluidos}"
    )

    # -------------------------------------------------
    # CAMPOS FIXOS
    # -------------------------------------------------

    df["empresa"] = EMPRESA
    df["cnpj_empresa"] = CNPJ_EMPRESA

    df["mes_referencia"] = (
        df["ref"]
        .apply(converter_mes_referencia)
    )

    mes_ref = (
        df["mes_referencia"]
        .dropna()
        .iloc[0]
    )

    # -------------------------------------------------
    # COLUNAS FINAIS
    # -------------------------------------------------

    df_final = df[[
        "matricula",
        "nome",
        "orgao",
        "codigo",
        "sigla",
        "cargo",
        "empresa",
        "cnpj_empresa",
        "mes_referencia"
    ]].copy()

    df_final = df_final.fillna("")

    log(
        f"Registros válidos: {len(df_final)}"
    )

    # -------------------------------------------------
    # HISTÓRICO
    # -------------------------------------------------

    log(
        f"Atualizando {os.path.basename(arquivo_destino)}"
    )

    historico = pd.read_excel(
        arquivo_destino,
        dtype=str
    )

    if "codigo" not in historico.columns:
        log(
            "AVISO: arquivo histórico sem coluna 'codigo'. "
            "Execute o script de preenchimento do passivo antes de continuar."
        )
        historico.insert(
            historico.columns.get_loc("sigla"),
            "codigo",
            ""
        )

    historico = historico.fillna("")

    historico["mes_referencia"] = (
    historico["mes_referencia"]
    .apply(converter_mes_referencia)
    )

    if "mes_referencia" in historico.columns:

        qtd_mes = len(
            historico[
                historico["mes_referencia"]
                == mes_ref
            ]
        )

        if qtd_mes:
            log(
                f"Removendo {qtd_mes} registros de {mes_ref}"
            )

            historico = historico[
                historico["mes_referencia"]
                != mes_ref
            ]

    historico = pd.concat(
        [historico, df_final],
        ignore_index=True
    )

    historico.to_excel(
        arquivo_destino,
        index=False
    )

    log(
        f"Arquivo atualizado: {arquivo_destino}"
    )

    # -------------------------------------------------
    # REMOVER ARQUIVO PROCESSADO
    # -------------------------------------------------

    os.remove(arquivo_mgs)

    log(
        f"Arquivo removido: {arquivo_mgs}"
    )

    # -------------------------------------------------
    # GITHUB
    # -------------------------------------------------

    atualizar_github()

    log("Processamento concluído.")


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    try:
        processar()

    except Exception as e:

        print("\nERRO:")
        print(str(e))

        sys.exit(1)