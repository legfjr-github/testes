import streamlit as st
import requests
from bs4 import BeautifulSoup
import yt_dlp
import os
import re
from urllib.parse import urljoin
import concurrent.futures # Para execução paralela de busca de títulos e infos

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
    st.session_state.main_url = "https://example.com"
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
if 'start_batch_download' not in st.session_state:
    st.session_state.start_batch_download = False
if 'batch_download_in_progress' not in st.session_state:
    st.session_state.batch_download_in_progress = False

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
        # st.error(f"Não foi possível extrair informações do vídeo em {url}: {e}") # Evitar poluir logs
        return None
    except Exception as e:
        # st.error(f"Erro inesperado ao obter informações do vídeo em {url}: {e}") # Evitar poluir logs
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
            current_tbr_val = f.get('tbr')
            current_tbr = float(current_tbr_val) if current_tbr_val is not None else 0.0

            # Prioriza formatos com áudio e vídeo combinados
            if f.get('acodec') != 'none':
                if current_tbr > best_tbr:
                    best_format = f
                    best_tbr = current_tbr
            # Em seguida, considere formatos apenas de vídeo (DASH) se não tivermos um formato combinado melhor
            # ou se o formato atual for também apenas vídeo e tiver bitrate melhor
            elif (best_format is None or best_format.get('acodec') == 'none') and 'format_id' in f:
                if current_tbr > best_tbr:
                    best_format = f
                    best_tbr = current_tbr
    return best_format

def get_format_size(format_dict):
    """Calcula o tamanho aproximado do arquivo em MB."""
    if format_dict:
        size_bytes = format_dict.get('filesize') or format_dict.get('filesize_approx')
        if size_bytes:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
    return "N/D"

# --- Callbacks para atualização de estado ---
def update_selected_videos_multiselect():
    st.session_state.selected_video_display_names = st.session_state.video_multiselect_value

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
    st.session_state.start_batch_download = False
    st.session_state.batch_download_in_progress = False
    
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
                st.write("Obtendo títulos das páginas (isso pode levar um tempo para muitos links, executando em paralelo)...")
                progress_bar = st.progress(0)
                progress_text = st.empty()
                total_links = len(unique_video_urls)
                
                links_with_titles = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_url = {executor.submit(get_page_title, url): url for url in sorted(list(unique_video_urls))}
                    
                    for idx, future in enumerate(concurrent.futures.as_completed(future_to_url)):
                        url = future_to_url[future]
                        try:
                            title = future.result()
                            display_name = f"{title} - {url}"
                            links_with_titles.append((display_name, url, title))
                        except Exception as exc:
                            # st.warning(f"Erro ao obter título de {url}: {exc}") # Descomentar para debug
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
    
    # Multiselect corrigido com on_change
    st.multiselect(
        "Selecione os vídeos que você deseja baixar:",
        options=display_options,
        default=st.session_state.selected_video_display_names,
        key="video_multiselect_value", # A chave do widget armazena o valor
        on_change=update_selected_videos_multiselect # Callback para atualizar st.session_state.selected_video_display_names
    )
    
    # Mapear os nomes de exibição selecionados de volta para seus dados completos (display_name, url, page_title_raw)
    selected_video_data = [
        item for item in st.session_state.available_video_options
        if item[0] in st.session_state.selected_video_display_names
    ]

    if st.button("Processar Vídeos Selecionados", key="process_selected_videos"):
        if not selected_video_data:
            st.warning("Por favor, selecione pelo menos um vídeo para processar.")
        else:
            # Prepara os dados para processamento na seção 3
            st.session_state.processed_videos_data = {}
            st.session_state.download_statuses = {}
            st.session_state.downloaded_files = {} # Limpa arquivos baixados de sessão anterior
            st.session_state.batch_download_in_progress = False

            st.info("Obtendo informações de vídeo (formatos e tamanhos aproximados) em paralelo...")
            info_progress_bar = st.progress(0)
            info_progress_text = st.empty()
            total_selected = len(selected_video_data)
            
            # Usar ThreadPoolExecutor para obter informações de vídeo em paralelo
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_video_item = {executor.submit(get_video_info, item[1]): item for item in selected_video_data}
                
                for idx, future in enumerate(concurrent.futures.as_completed(future_to_video_item)):
                    video_item = future_to_video_item[future] # (display_string, url, page_title_raw)
                    url = video_item[1]
                    title_raw = video_item[2]
                    
                    video_info = future.result() # Obtém o resultado da thread
                    current_video_number = st.session_state.base_number + idx # Atribui número sequencial

                    st.session_state.processed_videos_data[url] = {
                        "display_name": video_item[0],
                        "url": url,
                        "page_title_raw": title_raw,
                        "current_video_number": current_video_number,
                        "video_info": video_info # Armazena as informações do yt-dlp
                    }
                    if video_info:
                        st.session_state.download_statuses[url] = 'pending' # Inicializa status
                    else:
                        st.session_state.download_statuses[url] = 'error_info_fetch'

                    info_progress_bar.progress((idx + 1) / total_selected)
                    info_progress_text.text(f"Processando informações de vídeo: {idx + 1}/{total_selected} vídeos.")

            info_progress_bar.empty()
            info_progress_text.empty()
            st.success("Informações de vídeo processadas!")
            st.rerun() # Re-executa o script para exibir a seção 3

# --- Seção 3: Detalhes e Download dos Vídeos ---
if st.session_state.processed_videos_data:
    st.header("3. Detalhes e Download dos Vídeos")
    
    # Ordena os vídeos para manter uma ordem consistente na exibição
    sorted_processed_urls = sorted(st.session_state.processed_videos_data.keys(), 
                                   key=lambda u: st.session_state.processed_videos_data[u]['current_video_number'])
    
    # --- Botão Baixar TODOS ---
    if st.session_state.batch_download_in_progress:
        st.info("Download em lote em progresso... Por favor, aguarde.")
        batch_progress_bar = st.progress(0)
        batch_status_text = st.empty()
        
        total_videos_to_download = len(st.session_state.processed_videos_data)
        downloaded_count = 0
        
        for idx, video_url in enumerate(sorted_processed_urls):
            video_data = st.session_state.processed_videos_data[video_url]
            current_video_number = video_data['current_video_number']

            # Se já baixado ou com erro anterior, atualiza contador e pula
            current_download_status = st.session_state.download_statuses.get(video_url)
            if current_download_status in ('completed', 'error', 'error_info_fetch'):
                downloaded_count += 1
                batch_progress_bar.progress(downloaded_count / total_videos_to_download)
                batch_status_text.text(f"Baixando vídeos: {downloaded_count}/{total_videos_to_download} concluídos (ou com status final).")
                continue
            
            # Obtém a resolução escolhida para este vídeo
            chosen_resolution_str = st.session_state.get(f"res_choice_{video_url}", "720p") # Valor padrão se não foi selecionado
            chosen_resolution_int = int(chosen_resolution_str.replace('p', ''))
            
            page_title_raw = video_data['page_title_raw']
            clean_page_title = clean_filename(page_title_raw)
            final_filename_base = f"{st.session_state.base_name}{current_video_number} {clean_page_title}"
            output_filename = f"{final_filename_base}_{chosen_resolution_str}.mp4"
            output_filepath = os.path.join(DOWNLOAD_DIR, output_filename)

            st.session_state.download_statuses[video_url] = 'downloading'
            batch_status_text.text(f"Baixando ({downloaded_count+1}/{total_videos_to_download}): '{output_filename}'...")
            
            try:
                ydl_opts = {
                    'format': f'bestvideo[height<={chosen_resolution_int}]+bestaudio/best[height<={chosen_resolution_int}]',
                    'outtmpl': output_filepath,
                    'noplaylist': True,
                    'quiet': True,
                    'retries': 5,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
                
                st.session_state.download_statuses[video_url] = 'completed'
                st.session_state.downloaded_files[video_url] = output_filepath
                downloaded_count += 1
                batch_progress_bar.progress(downloaded_count / total_videos_to_download)
                batch_status_text.text(f"Baixando vídeos: {downloaded_count}/{total_videos_to_download} concluídos.")
            except Exception as e:
                st.error(f"Erro ao baixar '{output_filename}': {e}")
                st.session_state.download_statuses[video_url] = 'error'
                downloaded_count += 1 # Conta como processado, mesmo com erro
                batch_progress_bar.progress(downloaded_count / total_videos_to_download)
                batch_status_text.text(f"Baixando vídeos: {downloaded_count}/{total_videos_to_download} concluídos (com erro).")

        st.session_state.batch_download_in_progress = False
        st.success("Download em lote concluído. Verifique o status de cada vídeo abaixo.")
        st.rerun() # Refresh UI to show final states
    else:
        if st.button("Baixar TODOS os vídeos selecionados", key="batch_download_btn"):
            if not st.session_state.processed_videos_data:
                st.warning("Nenhum vídeo processado para baixar.")
            else:
                st.session_state.start_batch_download = True
                st.rerun()

    st.markdown("---") # Separador para o botão de lote

    # --- Loop para exibir cada vídeo individualmente ---
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
            default_res_str = st.session_state.get(f"res_choice_{video_url}", list(resolution_options.keys())[0])
            try:
                default_res_idx = list(resolution_options.keys()).index(default_res_str)
            except ValueError:
                default_res_idx = 0 # Fallback se a resolução salva não estiver mais disponível
            
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

            # --- Lógica do Botão de Download Individual ---
            if download_status == 'pending':
                if st.button(f"Baixar {chosen_resolution_str} de '{clean_page_title}'", key=f"download_btn_{video_url}"):
                    st.session_state.download_statuses[video_url] = 'downloading'
                    st.session_state.processed_videos_data[video_url]['output_filepath'] = output_filepath
                    st.session_state.processed_videos_data[video_url]['chosen_resolution_int'] = chosen_resolution_int
                    st.session_state.processed_videos_data[video_url]['output_filename'] = output_filename
                    st.rerun()
            elif download_status == 'downloading':
                st.info(f"Download de '{output_filename}' em progresso...")
                try:
                    ydl_opts = {
                        'format': f'bestvideo[height<={chosen_resolution_int}]+bestaudio/best[height<={chosen_resolution_int}]',
                        'outtmpl': output_filepath,
                        'noplaylist': True,
                        'quiet': True,
                        'retries': 5,
                    }
                    with st.spinner(f"Baixando {output_filename}... Por favor, aguarde. Isso pode levar alguns minutos."):
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([video_url])
                    
                    st.success(f"Vídeo '{output_filename}' baixado com sucesso!")
                    st.session_state.download_statuses[video_url] = 'completed'
                    st.session_state.downloaded_files[video_url] = output_filepath
                    st.rerun()
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
                    file_size_bytes = os.path.getsize(downloaded_file_path)
                    file_size_mb = file_size_bytes / (1024 * 1024)
                    st.write(f"**Tamanho do arquivo baixado:** `{file_size_mb:.2f} MB`")
                    
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
                    st.rerun()
            
            st.markdown("---")
        else: # Se video_info for None (erro ao buscar informações)
            st.warning(f"Não foi possível obter informações de vídeo para: {video_url}. Ignorando este vídeo.")
            if download_status == 'error_info_fetch':
                 if st.button(f"Tentar Novamente Obter Info '{clean_page_title}'", key=f"retry_info_btn_{video_url}"):
                    # Limpa o cache para esta URL e re-tenta buscar info
                    get_video_info.clear() 
                    st.session_state.processed_videos_data[video_url]['video_info'] = get_video_info(video_url) 
                    if st.session_state.processed_videos_data[video_url]['video_info']:
                         st.session_state.download_statuses[video_url] = 'pending'
                    st.rerun()
            st.markdown("---")

else:
    if not st.session_state.available_video_options and not st.session_state.processed_videos_data and not st.session_state.batch_download_in_progress:
        st.info("Insira uma URL principal e clique em 'Buscar Links de Vídeo' para começar.")
    elif st.session_state.available_video_options and not st.session_state.processed_videos_data and not st.session_state.batch_download_in_progress:
        st.info("Selecione os vídeos e clique em 'Processar Vídeos Selecionados' para ver os detalhes e opções de download.")
