import streamlit as st
import pandas as pd
import numpy as np
import io
import unicodedata

def normalize_text(text):
    if pd.isna(text):
        return text
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('ascii')
    return text.upper().strip()

def procesar_archivos(empresas_cliente, empresas_activas):
    # Cambiar el nombre de la columna CompanyCode a VATNum en empresas_activas
    empresas_activas = empresas_activas.rename(columns={'CompanyCode': 'VATNum'})
    
    # Eliminar filas donde más de 5 columnas tienen NaN
    empresas_activas = empresas_activas.dropna(thresh=empresas_activas.shape[1] - 5)
    
    # Filtrar filas que contienen palabras específicas en cualquier columna de texto
    palabras_excluir = ['auditorias', 'onhold', 'AQ', 'Gosupply', 'Aquanima']
    empresas_activas = empresas_activas[~empresas_activas.apply(lambda row: row.astype(str).str.contains('|'.join(palabras_excluir), case=False, na=False).any(), axis=1)]
    
    # Filtrar filas donde la columna 'Description' contiene ciertas palabras clave
    palabras_description = ['Protocolo', 'Cualificaciones', 'Homolo', 'SCM']
    empresas_activas = empresas_activas[~empresas_activas['Description'].astype(str).str.contains('|'.join(palabras_description), case=False, na=False)]
    
    # Normalización de nombres en empresas_cliente
    empresas_cliente['Supplier NAME Original'] = empresas_cliente['Name']
    empresas_cliente['Supplier NAME Cleaned'] = empresas_cliente['Name'].astype(str).str.replace('[ ,.]', '', regex=True).apply(normalize_text)
    empresas_cliente = empresas_cliente.dropna(subset=['Supplier NAME Cleaned']).drop_duplicates(subset=['Supplier NAME Cleaned'])
    
    # Normalización de nombres en empresas_activas
    empresas_activas['Name_GOSUPPLY'] = empresas_activas['Name']
    empresas_activas['Supplier NAME Cleaned'] = empresas_activas['Name_GOSUPPLY'].astype(str).str.replace('[ ,.]', '', regex=True).apply(normalize_text)
    empresas_activas = empresas_activas.drop_duplicates(subset=['Supplier NAME Cleaned'])
    
    # Unión por VATNum
    result_df = pd.merge(empresas_cliente, empresas_activas, on='VATNum', how='left')
    
    # Unión por Supplier NAME Cleaned
    merged_name_cleaned = pd.merge(empresas_cliente, empresas_activas, on='Supplier NAME Cleaned', how='left')
    merged_name_cleaned = merged_name_cleaned.dropna(subset=['CompanyCodeId'])
    
    # Combinar ambos dataframes
    df_combined = pd.concat([result_df, merged_name_cleaned], ignore_index=True)
    
    # Asegurar que StatusTypeId es tratado como texto
    df_combined['StatusTypeId'] = df_combined['StatusTypeId'].astype(str)
    
    # Asignar Status
    df_combined['Status'] = np.where(
        df_combined['StatusTypeId'].isin(['8', '87']),
        'Publicado',
        'En proceso de validación'
    )
    
    # Asignar Nivel
    conditions = [
        df_combined['SubscriptionTypeId'] == 1,
        df_combined['SubscriptionTypeId'] == 2,
        df_combined['SubscriptionTypeId'] == 3,
        df_combined['SubscriptionTypeId'] == 4
    ]
    choices = ['180', '360', 'Basic', 'Elementary']
    df_combined['Nivel'] = np.select(conditions, choices, default='Unknown')
    
    # Eliminar filas donde Nivel es 'Unknown'
    df_combined = df_combined[df_combined['Nivel'] != 'Unknown']
    
    # Eliminar duplicados priorizando Status y Nivel
    duplicates = df_combined[df_combined.duplicated('CompanyCodeId', keep=False)]
    duplicates = duplicates[df_combined['CompanyCodeId'].notna()]
    
    status_priority = pd.CategoricalDtype(categories=["Publicado", "En proceso de validación"], ordered=True)
    nivel_priority = pd.CategoricalDtype(categories=["360", "180", "Basic", "Elementary", "Unknown"], ordered=True)
    
    duplicates.loc[:, 'Status'] = duplicates['Status'].astype(status_priority)
    duplicates.loc[:, 'Nivel'] = duplicates['Nivel'].astype(nivel_priority)
    
    duplicates = duplicates.sort_values(by=['CompanyCodeId', 'Status', 'Nivel'], ascending=[True, True, True])
    df_final = duplicates.drop_duplicates(subset='CompanyCodeId', keep='first')
    
    df_combined = pd.concat([df_final, df_combined.drop(duplicates.index)], ignore_index=True)
    
    return df_combined

st.title("Verificador de Proveedores")

uploaded_file1 = st.file_uploader("Sube el archivo de empresas cliente (Debe contener las columnas VATNum y Name)", type=["xlsx"])
uploaded_file2 = st.file_uploader("Sube el archivo de empresas activas", type=["xlsx"])

if uploaded_file1 and uploaded_file2:
    st.write("Procesando los archivos... Esto puede tardar unos momentos.")
    with st.spinner('Procesando...'):
        empresas_cliente = pd.read_excel(uploaded_file1)
        empresas_activas = pd.read_excel(uploaded_file2)
    
        df_resultado = procesar_archivos(empresas_cliente, empresas_activas)
    
    st.success("Procesamiento completado!")
    st.write("### Vista previa del resultado")
    st.dataframe(df_resultado.head())
    
    # Análisis de resultados
    status_counts = df_resultado['Status'].value_counts()
    nivel_counts = df_resultado['Nivel'].value_counts()
    
    st.write("### Resumen del procesamiento")
    st.write(f"**Publicado:** {status_counts.get('Publicado', 0)}")
    st.write(f"**En proceso de validación:** {status_counts.get('En proceso de validación', 0)}")
    st.write(f"**Nivel 360:** {nivel_counts.get('360', 0)}")
    st.write(f"**Nivel 180:** {nivel_counts.get('180', 0)}")
    st.write(f"**Nivel Basic:** {nivel_counts.get('Basic', 0)}")
    st.write(f"**Nivel Elementary:** {nivel_counts.get('Elementary', 0)}")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_resultado.to_excel(writer, index=False)
    
    st.download_button(
        label="Descargar archivo procesado",
        data=output.getvalue(),
        file_name="Proveedores_Procesados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
