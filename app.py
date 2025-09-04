import streamlit as st
import requests
from bs4 import BeautifulSoup
import yt_dlp
import os
import re

# --- Configurações Iniciais ---
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

st.set_page_config(layout="wide", page_title="Downloader de Vídeos Inteligente")

st.title("🔗 Downloader de Vídeos Inteligente")
st.write("Este aplicativo busca links de vídeo em um site, permite que você selecione quais baixar e os salva nas resoluções 720p ou 1080p com um nome personalizado.")

# --- Funções Auxiliares ---

def get_page_title(url):
    """Busca o título de uma página web."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('title')
        if title:
            return title.get_text(strip=True)
        return "Título Desconhecido"
    except requests.exceptions.RequestException as e:
        st.warning(f"Não foi possível obter o título da página {url}: {e}")
        return "Título Desconhecido"

def clean_filename(title):
    """Limpa o título para ser usado como nome de arquivo."""
    title = re.sub(r'[\\/*?:"<>|]', "", title)  # Remove caracteres inválidos para nome de arquivo
    title = title.replace(" ", "_") # Opcional: substitui espaços por underscores
    return title.strip()

def get_video_info(url):
    """Obtém informações sobre o vídeo (tamanhos, formatos) sem baixar."""
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'force_generic_extractor': True, # Tenta extrair info mesmo que não seja um site 'reconhecido'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except yt_dlp.utils.DownloadError as e:
        st.error(f"Não foi possível extrair informações do vídeo em {url}: {e}")
        return None

def find_best_format(info_dict, height):
    """Encontra o melhor formato de vídeo para uma dada altura."""
    best_format = None
    for f in info_dict.get('formats', []):
        if f.get('height') == height and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
            if not best_format or f.get('tbr', 0) > best_format.get('tbr', 0): # tbr = total bitrate
                best_format = f
    return best_format

def get_format_size(format_dict):
    """Calcula o tamanho aproximado do arquivo em MB."""
    if format_dict:
        # filesiz_approx é geralmente mais confiável que filesize
        size_bytes = format_dict.get('filesize') or format_dict.get('filesize_approx')
        if size_bytes:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
    return "N/D"

# --- Interface do Streamlit ---

st.header("1. Insira o Link Base e Detalhes de Nomeação")
main_url = st.text_input("Link do Site (URL principal):", "https://example.com") # Adicione um valor padrão para teste
base_name = st.text_input("Nome Base para o Vídeo:", "VideoBase")
base_number = st.number_input("Número Base para o Vídeo (será incrementado):", min_value=1, value=50)

# Inicializar session_state para armazenar os links encontrados
if 'found_links' not in st.session_state:
    st.session_state.found_links = []
if 'selected_links' not in st.session_state:
    st.session_state.selected_links = []

# Botão para buscar links
if st.button("Buscar Links de Vídeo"):
    st.session_state.found_links = []
    st.session_state.selected_links = []
    if main_url:
        st.info(f"Buscando links em: {main_url}...")
        try:
            response = requests.get(main_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Encontrar todos os links que contêm 'view_video'
            links = []
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                # Construir URL absoluta se for relativa
                if href.startswith('/'):
                    full_href = requests.compat.urljoin(main_url, href)
                else:
                    full_href = href
                
                if 'view_video' in full_href and full_href not in links:
                    links.append(full_href)
            
            if links:
                st.session_state.found_links = links
                st.success(f"Encontrados {len(links)} links com 'view_video'.")
            else:
                st.warning("Nenhum link com 'view_video' encontrado nesta página.")
        except requests.exceptions.RequestException as e:
            st.error(f"Erro ao acessar a URL principal: {e}")
    else:
        st.warning("Por favor, insira uma URL válida para buscar os links.")

st.header("2. Selecione os Vídeos para Baixar")
if st.session_state.found_links:
    selected_links_display = st.multiselect(
        "Selecione os links de vídeo que você deseja baixar:",
        options=st.session_state.found_links,
        default=st.session_state.selected_links # Mantém a seleção entre as execuções
    )
    st.session_state.selected_links = selected_links_display

    if st.button("Processar Vídeos Selecionados"):
        if not st.session_state.selected_links:
            st.warning("Por favor, selecione pelo menos um link para processar.")
        else:
            current_video_number = base_number
            st.header("3. Detalhes e Download dos Vídeos")
            
            for i, video_url in enumerate(st.session_state.selected_links):
                st.subheader(f"Processando Vídeo {i+1}: {video_url}")
                
                with st.spinner(f"Obtendo informações para {video_url}..."):
                    page_title_raw = get_page_title(video_url)
                    clean_page_title = clean_filename(page_title_raw)
                    
                    video_info = get_video_info(video_url)

                if video_info:
                    st.write(f"Título da Página: **{page_title_raw}**")
                    
                    format_720p = find_best_format(video_info, 720)
                    format_1080p = find_best_format(video_info, 1080)
                    
                    st.write(f"Tamanho aproximado (720p): {get_format_size(format_720p)}")
                    st.write(f"Tamanho aproximado (1080p): {get_format_size(format_1080p)}")
                    
                    resolution_options = {}
                    if format_720p:
                        resolution_options["720p"] = "720p"
                    if format_1080p:
                        resolution_options["1080p"] = "1080p"
                    
                    if not resolution_options:
                        st.warning("Nenhuma resolução 720p ou 1080p encontrada para este vídeo. Tente outra URL ou verifique a disponibilidade.")
                        continue

                    chosen_resolution_str = st.radio(
                        f"Selecione a resolução para este vídeo ({video_url}):",
                        options=list(resolution_options.keys()),
                        key=f"res_choice_{i}"
                    )
                    
                    chosen_resolution_int = int(chosen_resolution_str.replace('p', ''))
                    
                    final_filename_base = f"{base_name}{current_video_number} {clean_page_title}"
                    output_filename = f"{final_filename_base}_{chosen_resolution_str}.mp4"
                    output_filepath = os.path.join(DOWNLOAD_DIR, output_filename)
                    
                    st.info(f"O vídeo será salvo como: `{output_filename}`")

                    if st.button(f"Baixar {chosen_resolution_str} de '{clean_page_title}'", key=f"download_btn_{i}"):
                        try:
                            ydl_opts = {
                                'format': f'bestvideo[height<={chosen_resolution_int}]+bestaudio/best[height<={chosen_resolution_int}]',
                                'outtmpl': output_filepath,
                                'noplaylist': True,
                                'progress_hooks': [lambda d: st.info(d['status']) if d['status'] == 'downloading' else None],
                            }
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                with st.spinner(f"Baixando {output_filename}..."):
                                    ydl.download([video_url])
                            
                            st.success(f"Vídeo '{output_filename}' baixado com sucesso!")
                            
                            # Oferecer link para download do arquivo salvo
                            with open(output_filepath, "rb") as fp:
                                st.download_button(
                                    label=f"Clique para Salvar '{output_filename}'",
                                    data=fp.read(),
                                    file_name=output_filename,
                                    mime="video/mp4",
                                    key=f"serve_download_{i}"
                                )
                            
                        except yt_dlp.utils.DownloadError as e:
                            st.error(f"Erro ao baixar o vídeo {output_filename}: {e}")
                        except Exception as e:
                            st.error(f"Ocorreu um erro inesperado ao baixar: {e}")
                    
                    current_video_number += 1
                    st.markdown("---")
                else:
                    st.warning(f"Não foi possível obter informações de vídeo para: {video_url}. Pulando.")
                    st.markdown("---")

else:
    st.info("Insira uma URL principal e clique em 'Buscar Links de Vídeo' para começar.")
