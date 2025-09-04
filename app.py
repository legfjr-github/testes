import streamlit as st
import requests
from bs4 import BeautifulSoup
import yt_dlp
import os
import re
from urllib.parse import urljoin # Importar para lidar com URLs relativas
import concurrent.futures # Para execução paralela

# --- Configurações Iniciais ---
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

st.set_page_config(layout="wide", page_title="Downloader de Vídeos Inteligente")

st.title("🔗 Downloader de Vídeos Inteligente")
st.write("Este aplicativo busca links de vídeo em um site, permite que você selecione quais baixar e os salva nas resoluções 720p ou 1080p com um nome personalizado.")

# --- Inicialização do st.session_state ---
# Inicializar todas as variáveis que precisam persistir entre as re-execuções
if 'main_url' not in st.session_state:
    st.session_state.main_url = "https://example.com" # Valor padrão
if 'base_name' not in st.session_state:
    st.session_state.base_name = "VideoBase"
if 'base_number' not in st.session_state:
    st.session_state.base_number = 50
if 'available_video_options' not in st.session_state:
    st.session_state.available_video_options = [] # Armazena (display_string, url, page_title_raw)
if 'selected_video_display_names' not in st.session_state:
    st.session_state.selected_video_display_names = [] # Armazena os nomes de exibição selecionados
if 'processed_videos_data' not in st.session_state:
    st.session_state.processed_videos_data = {} # Armazena dados completos dos vídeos selecionados após "Processar"
if 'download_statuses' not in st.session_state:
    st.session_state.download_statuses = {} # Armazena o status do download para cada URL (pending, downloading, completed, error)
if 'downloaded_files' not in st.session_state:
    st.session_state.downloaded_files = {} # Armazena os caminhos dos arquivos baixados

# --- Funções Auxiliares ---

@st.cache_data(ttl=3600) # Cachear títulos por 1 hora
def get_page_title(url):
    """Busca o título de uma página web."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
        h1_tag = soup.find('h1') # Fallback para <h1>
        if h1_tag:
            return h1_tag.get_text(strip=True)
        return "Título Desconhecido"
    except requests.exceptions.RequestException as e:
        return f"Erro ao obter título ({e})"

def clean_filename(title):
    """Limpa o título para ser usado como nome de arquivo."""
    title = re.sub(r'[\\/*?:"<>|]', "", title)
    title = title.replace(" ", "_")
    return title.strip()

@st.cache_data(ttl=3600) # Cachear informações de vídeo por 1 hora
def get_video_info(url):
    """Obtém informações sobre o vídeo (tamanhos, formatos) sem baixar."""
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'force_generic_extractor': True,
            'noplaylist': True,
            'default_search': 'ytsearch', # Ajuda a yt-dlp a inferir o tipo de link
            'retries': 3,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except yt_dlp.utils.DownloadError as e:
        st.error(f"Não foi possível extrair informações do vídeo em {url}: {e}")
        return None
    except Exception as e:
        st.error(f"Erro inesperado ao obter informações do vídeo em {url}: {e}")
        return None

def find_best_format(info_dict, height):
    """
    Encontra o melhor formato de vídeo para uma dada altura.
    Prioriza formatos que já contêm áudio, e depois os que são apenas vídeo (DASH).
    """
    best_format = None
    best_tbr = -1.0 # Usar -1.0 para garantir que qualquer bitrate válido seja maior

    for f in info_dict.get('formats', []):
        if f.get('height') == height and f.get('vcodec') != 'none':
            current_tbr = f.get('tbr')
            current_tbr_float = float(current_tbr) if current_tbr is not None else 0.0

            # Prioriza formatos com áudio e vídeo combinados
            if f.get('acodec') != 'none':
                if current_tbr_float > best_tbr:
                    best_format = f
                    best_tbr = current_tbr_float
            # Em seguida, considere formatos apenas de vídeo (DASH) se não tivermos um formato combinado melhor
            elif (best_format is None or best_format.get('acodec') == 'none') and 'format_id' in f and 'dash' in f['format_id']:
                 if current_tbr_float > best_tbr:
                    best_format = f
                    best_tbr = current_tbr_float
    return best_format

def get_format_size(format_dict):
    """Calcula o tamanho aproximado do arquivo em MB."""
    if format_dict:
        size_bytes = format_dict.get('filesize') or format_dict.get('filesize_approx')
        if size_bytes:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
    return "N/D"

# --- Interface do Streamlit ---

st.header("1. Insira o Link Base e Detalhes de Nomeação")
st.session_state.main_url = st.text_input("Link do Site (URL principal):", st.session_state.main_url, key="main_url_input")
st.session_state.base_name = st.text_input("Nome Base para o Vídeo:", st.session_state.base_name, key="base_name_input")
st.session_state.base_number = st.number_input("Número Base para o Vídeo (será incrementado):", min_value=1, value=st.session_state.base_number, key="base_number_input")

if st.button("Buscar Links de Vídeo"):
    # Limpa estados anteriores ao buscar novos links
    st.session_state.available_video_options = []
    st.session_state.selected_video_display_names = []
    st.session_state.processed_videos_data = {}
    st.session_state.download_statuses = {}
    st.session_state.downloaded_files = {}
    
    main_url_to_fetch = st.session_state.main_url

    if main_url_to_fetch:
        st.info(f"Buscando links em: {main_url_to_fetch}...")
        try:
            response = requests.get(main_url_to_fetch, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            unique_video_urls = set()
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                full_href = urljoin(main_url_to_fetch, href)
                
                if 'view_video' in full_href:
                    unique_video_urls.add(full_href)
            
            if unique_video_urls:
                st.write("Obtendo títulos das páginas (isso pode levar um tempo para muitos links)...")
                progress_bar = st.progress(0)
                progress_text = st.empty()
                total_links = len(unique_video_urls)
                
                links_with_titles = []
                # Usar ThreadPoolExecutor para buscar títulos em paralelo
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor: # Limita workers para não sobrecarregar
                    future_to_url = {executor.submit(get_page_title, url): url for url in sorted(list(unique_video_urls))}
                    
                    for idx, future in enumerate(concurrent.futures.as_completed(future_to_url)):
                        url = future_to_url[future]
                        try:
                            title = future.result()
                            display_name = f"{title} - {url}"
                            links_with_titles.append((display_name, url, title))
                        except Exception as exc:
                            st.warning(f"Erro ao obter título de {url}: {exc}")
                            display_name = f"Erro ao obter título - {url}"
                            links_with_titles.append((display_name, url, "Erro ao obter título"))
                        
                        progress_bar.progress((idx + 1) / total_links)
                        progress_text.text(f"Obtendo títulos: {idx + 1}/{total_links} links processados.")

                st.session_state.available_video_options = links_with_titles
                progress_bar.empty()
                progress_text.empty()
                st.success(f"Encontrados e processados {len(st.session_state.available_video_options)} links únicos com 'view_video'.")
            else:
                st.warning("Nenhum link com 'view_video' encontrado nesta página.")
        except requests.exceptions.RequestException as e:
            st.error(f"Erro ao acessar a URL principal: {e}")
    else:
        st.warning("Por favor, insira uma URL válida para buscar os links.")

st.header("2. Selecione os Vídeos para Baixar")
if st.session_state.available_video_options:
    display_options = [item[0] for item in st.session_state.available_video_options]
    
    # O default do multiselect deve vir diretamente do session_state para consistência
    st.session_state.selected_video_display_names = st.multiselect(
        "Selecione os vídeos que você deseja baixar:",
        options=display_options,
        default=st.session_state.selected_video_display_names,
        key="video_multiselect" # Chave única para o widget
    )
    
    # Mapear os nomes de exibição selecionados de volta para seus dados completos (display_name, url, page_title_raw)
    selected_video_data = [
        item for item in st.session_state.available_video_options
        if item[0] in st.session_state.selected_video_display_names
    ]

    # Botão para processar os vídeos selecionados (obter informações de tamanho/resolução)
    if st.button("Processar Vídeos Selecionados", key="process_selected_videos"):
        if not selected_video_data:
            st.warning("Por favor, selecione pelo menos um vídeo para processar.")
        else:
            # Prepara os dados para processamento na seção 3
            st.session_state.processed_videos_data = {}
            st.session_state.download_statuses = {}
            st.session_state.downloaded_files = {}

            # Use ThreadPoolExecutor para obter informações de vídeo em paralelo
            st.info("Obtendo informações de vídeo (formatos e tamanhos aproximados) em paralelo...")
            info_progress_bar = st.progress(0)
            info_progress_text = st.empty()
            total_selected = len(selected_video_data)
            
            futures_video_info = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_video_item = {executor.submit(get_video_info, item[1]): item for item in selected_video_data}
                
                for idx, future in enumerate(concurrent.futures.as_completed(future_to_video_item)):
                    video_item = future_to_video_item[future] # (display_string, url, page_title_raw)
                    url = video_item[1]
                    title_raw = video_item[2]
                    
                    try:
                        video_info = future.result()
                        current_video_number = st.session_state.base_number + idx # Atribui número sequencial
                        
                        st.session_state.processed_videos_data[url] = {
                            "display_name": video_item[0],
                            "url": url,
                            "page_title_raw": title_raw,
                            "current_video_number": current_video_number,
                            "video_info": video_info # Armazena as informações do yt-dlp
                        }
                        st.session_state.download_statuses[url] = 'pending' # Inicializa status
                    except Exception as e:
                        st.error(f"Erro ao obter informações para {url}: {e}")
                        # Ainda adiciona para exibição com erro
                        st.session_state.processed_videos_data[url] = {
                            "display_name": video_item[0],
                            "url": url,
                            "page_title_raw": title_raw,
                            "current_video_number": st.session_state.base_number + idx,
                            "video_info": None # Marca como sem info
                        }
                        st.session_state.download_statuses[url] = 'error_info_fetch'

                    info_progress_bar.progress((idx + 1) / total_selected)
                    info_progress_text.text(f"Processando informações de vídeo: {idx + 1}/{total_selected} vídeos.")

            info_progress_bar.empty()
            info_progress_text.empty()
            st.success("Informações de vídeo processadas!")
            # Isso irá re-executar o script para exibir a seção 3
            st.rerun()

# --- Seção 3: Detalhes e Download dos Vídeos ---
if st.session_state.processed_videos_data:
    st.header("3. Detalhes e Download dos Vídeos")
    
    # Ordena os vídeos para manter uma ordem consistente na exibição
    sorted_processed_urls = sorted(st.session_state.processed_videos_data.keys(), 
                                   key=lambda u: st.session_state.processed_videos_data[u]['current_video_number'])
    
    for i, video_url in enumerate(sorted_processed_urls):
        video_data = st.session_state.processed_videos_data[video_url]
        page_title_raw = video_data['page_title_raw']
        clean_page_title = clean_filename(page_title_raw)
        video_info = video_data['video_info']
        current_video_number = video_data['current_video_number']

        st.subheader(f"Vídeo {current_video_number}: {page_title_raw}")
        st.markdown(f"URL: `{video_url}`")
        
        download_status = st.session_state.download_statuses.get(video_url, 'pending')

        if video_info:
            
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
                st.warning("Nenhuma resolução 720p ou 1080p encontrada para este vídeo. Verifique a disponibilidade.")
                st.markdown("---")
                continue

            # Garante que a escolha de resolução persista
            default_res_idx = 0
            if f"res_choice_{video_url}" in st.session_state:
                try:
                    default_res_idx = list(resolution_options.keys()).index(st.session_state[f"res_choice_{video_url}"])
                except ValueError:
                    pass # Se a resolução salva não estiver mais disponível, usa o primeiro
            
            chosen_resolution_str = st.radio(
                f"Selecione a resolução para o vídeo {current_video_number}:",
                options=list(resolution_options.keys()),
                index=default_res_idx,
                key=f"res_choice_{video_url}" # Chave única para cada rádio
            )
            chosen_resolution_int = int(chosen_resolution_str.replace('p', ''))
            
            final_filename_base = f"{st.session_state.base_name}{current_video_number} {clean_page_title}"
            output_filename = f"{final_filename_base}_{chosen_resolution_str}.mp4"
            output_filepath = os.path.join(DOWNLOAD_DIR, output_filename)
            
            st.info(f"O vídeo será salvo como: `{output_filename}`")

            # --- Lógica do Botão de Download ---
            if download_status == 'pending':
                if st.button(f"Baixar {chosen_resolution_str} de '{clean_page_title}'", key=f"download_btn_{video_url}"):
                    st.session_state.download_statuses[video_url] = 'downloading'
                    st.session_state.processed_videos_data[video_url]['output_filepath'] = output_filepath # Armazena o caminho
                    st.session_state.processed_videos_data[video_url]['chosen_resolution_int'] = chosen_resolution_int
                    st.session_state.processed_videos_data[video_url]['output_filename'] = output_filename
                    st.rerun() # Re-executa para mostrar o status 'downloading'
            elif download_status == 'downloading':
                st.info(f"Download de '{output_filename}' em progresso...")
                # Tenta baixar o vídeo
                try:
                    ydl_opts = {
                        'format': f'bestvideo[height<={chosen_resolution_int}]+bestaudio/best[height<={chosen_resolution_int}]',
                        'outtmpl': output_filepath,
                        'noplaylist': True,
                        'quiet': True,
                        'retries': 5,
                        # 'progress_hooks': [lambda d: st.info(f"Progresso: {d['status']}. {d.get('_percent_str', '')}")] # Descomente para debug
                    }
                    with st.spinner(f"Baixando {output_filename}... Por favor, aguarde. Isso pode levar alguns minutos."):
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([video_url])
                    
                    st.success(f"Vídeo '{output_filename}' baixado com sucesso!")
                    st.session_state.download_statuses[video_url] = 'completed'
                    st.session_state.downloaded_files[video_url] = output_filepath
                    st.rerun() # Re-executa para mostrar o link de download
                except yt_dlp.utils.DownloadError as e:
                    st.error(f"Erro ao baixar o vídeo {output_filename}: {e}")
                    st.session_state.download_statuses[video_url] = 'error'
                    st.rerun()
                except Exception as e:
                    st.error(f"Ocorreu um erro inesperado ao baixar '{output_filename}': {e}")
                    st.session_state.download_statuses[video_url] = 'error'
                    st.rerun()
            elif download_status == 'completed':
                st.success(f"Download de '{output_filename}' concluído!")
                downloaded_file_path = st.session_state.downloaded_files.get(video_url)
                if downloaded_file_path and os.path.exists(downloaded_file_path):
                    with open(downloaded_file_path, "rb") as fp:
                        st.download_button(
                            label=f"Clique para Salvar '{output_filename}'",
                            data=fp.read(),
                            file_name=output_filename,
                            mime="video/mp4",
                            key=f"serve_download_{video_url}"
                        )
                else:
                    st.error(f"Erro: O arquivo baixado não foi encontrado em {downloaded_file_path}. Por favor, verifique o diretório 'downloads'.")
            elif download_status == 'error' or download_status == 'error_info_fetch':
                st.error(f"Ocorreu um erro no download ou na obtenção de informações para este vídeo. Por favor, tente novamente ou verifique a URL.")
                if st.button(f"Tentar Novamente Baixar '{clean_page_title}'", key=f"retry_download_btn_{video_url}"):
                    st.session_state.download_statuses[video_url] = 'pending'
                    st.rerun() # Re-executa para tentar novamente
            
            st.markdown("---")
        else: # Se video_info for None (erro ao buscar informações)
            st.warning(f"Não foi possível obter informações de vídeo para: {video_url}. Ignorando este vídeo.")
            if download_status == 'error_info_fetch':
                 if st.button(f"Tentar Novamente Obter Info '{clean_page_title}'", key=f"retry_info_btn_{video_url}"):
                    st.session_state.download_statuses[video_url] = 'pending' # Reseta para tentar buscar info novamente
                    st.session_state.processed_videos_data[video_url]['video_info'] = get_video_info(video_url) # Re-tenta buscar info
                    st.rerun()
            st.markdown("---")

else:
    if not st.session_state.available_video_options and not st.session_state.processed_videos_data:
        st.info("Insira uma URL principal e clique em 'Buscar Links de Vídeo' para começar.")
    elif st.session_state.available_video_options and not st.session_state.processed_videos_data:
        st.info("Selecione os vídeos e clique em 'Processar Vídeos Selecionados' para ver os detalhes e opções de download.")
