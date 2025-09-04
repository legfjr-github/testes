import streamlit as st
import requests
from bs4 import BeautifulSoup
import yt_dlp
import os
import re
from urllib.parse import urljoin # Importar para lidar com URLs relativas

# --- Configurações Iniciais ---
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

st.set_page_config(layout="wide", page_title="Downloader de Vídeos Inteligente")

st.title("🔗 Downloader de Vídeos Inteligente")
st.write("Este aplicativo busca links de vídeo em um site, permite que você selecione quais baixar e os salva nas resoluções 720p ou 1080p com um nome personalizado.")

# --- Funções Auxiliares ---

@st.cache_data(ttl=3600) # Cachear títulos por 1 hora para evitar requisições repetidas
def get_page_title(url):
    """Busca o título de uma página web."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
        # Tenta pegar um título de cabeçalho se não encontrar tag <title>
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.get_text(strip=True)
        return "Título Desconhecido"
    except requests.exceptions.RequestException as e:
        # Remover para não poluir o log no Streamlit a menos que seja para depuração
        # st.warning(f"Não foi possível obter o título da página {url}: {e}")
        return f"Erro ao obter título ({e})"

def clean_filename(title):
    """Limpa o título para ser usado como nome de arquivo."""
    title = re.sub(r'[\\/*?:"<>|]', "", title)  # Remove caracteres inválidos para nome de arquivo
    title = title.replace(" ", "_") # Opcional: substitui espaços por underscores
    return title.strip()

@st.cache_data(ttl=3600) # Cachear informações de vídeo por 1 hora
def get_video_info(url):
    """Obtém informações sobre o vídeo (tamanhos, formatos) sem baixar."""
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'force_generic_extractor': True, # Tenta extrair info mesmo que não seja um site 'reconhecido'
            'noplaylist': True, # Garante que não baixe playlists
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except yt_dlp.utils.DownloadError as e:
        st.error(f"Não foi possível extrair informações do vídeo em {url}: {e}")
        return None

def find_best_format(info_dict, height):
    """
    Encontra o melhor formato de vídeo para uma dada altura.
    Garante que os valores de 'tbr' sejam tratados como números para comparação.
    """
    best_format = None
    for f in info_dict.get('formats', []):
        if f.get('height') == height and f.get('vcodec') != 'none': # Deve ter vídeo
            # Obtém o bitrate para o formato atual, padronizando para 0.0 se não presente ou None
            current_tbr = f.get('tbr') or 0.0 

            # Verifica se é um formato de áudio/vídeo combinado ou um formato DASH apenas de vídeo
            if f.get('acodec') != 'none' or ('format_id' in f and 'dash' in f['format_id']):
                if not best_format:
                    best_format = f
                else:
                    # Obtém o bitrate para o melhor formato atual, padronizando para 0.0 se não presente ou None
                    best_format_tbr = best_format.get('tbr') or 0.0 
                    
                    if current_tbr > best_format_tbr:
                        best_format = f
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
main_url = st.text_input("Link do Site (URL principal):", "https://example.com") # Adicione um valor padrão para teste
base_name = st.text_input("Nome Base para o Vídeo:", "VideoBase")
base_number = st.number_input("Número Base para o Vídeo (será incrementado):", min_value=1, value=50)

# Inicializar session_state para armazenar os links encontrados com seus títulos
if 'available_video_options' not in st.session_state:
    st.session_state.available_video_options = [] # Stores (display_string, url) tuples
if 'selected_video_display_names' not in st.session_state:
    st.session_state.selected_video_display_names = [] # Stores the display strings selected by user

# Botão para buscar links
if st.button("Buscar Links de Vídeo"):
    st.session_state.available_video_options = []
    st.session_state.selected_video_display_names = [] # Limpa a seleção anterior ao buscar novos links
    
    if main_url:
        st.info(f"Buscando links em: {main_url}...")
        try:
            response = requests.get(main_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Usar um set para garantir URLs únicas
            unique_video_urls = set()
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                # Construir URL absoluta
                full_href = urljoin(main_url, href)
                
                if 'view_video' in full_href:
                    unique_video_urls.add(full_href)
            
            if unique_video_urls:
                progress_bar = st.progress(0)
                progress_text = st.empty()
                total_links = len(unique_video_urls)
                
                links_with_titles = []
                for idx, url in enumerate(sorted(list(unique_video_urls))): # Sort para ordem consistente
                    progress_text.info(f"Obtendo título para link {idx + 1}/{total_links}: {url}")
                    title = get_page_title(url)
                    display_name = f"{title} - {url}"
                    links_with_titles.append((display_name, url))
                    progress_bar.progress((idx + 1) / total_links)
                
                st.session_state.available_video_options = links_with_titles
                progress_bar.empty()
                progress_text.empty()
                st.success(f"Encontrados {len(st.session_state.available_video_options)} links únicos com 'view_video'.")
            else:
                st.warning("Nenhum link com 'view_video' encontrado nesta página.")
        except requests.exceptions.RequestException as e:
            st.error(f"Erro ao acessar a URL principal: {e}")
    else:
        st.warning("Por favor, insira uma URL válida para buscar os links.")

st.header("2. Selecione os Vídeos para Baixar")
if st.session_state.available_video_options:
    # Obter apenas os nomes de exibição para as opções do multiselect
    display_options = [item[0] for item in st.session_state.available_video_options]
    
    # Manter a seleção padrão se a lista de opções mudar (e forçar a revalidação se necessário)
    initial_selection = [
        d_name for d_name in st.session_state.selected_video_display_names
        if d_name in display_options
    ]

    selected_display_names = st.multiselect(
        "Selecione os vídeos que você deseja baixar:",
        options=display_options,
        default=initial_selection
    )
    st.session_state.selected_video_display_names = selected_display_names
    
    # Mapear os nomes de exibição selecionados de volta para suas URLs originais
    selected_links_urls = [
        url for display_name, url in st.session_state.available_video_options
        if display_name in selected_display_names
    ]
    
    if st.button("Processar Vídeos Selecionados"):
        if not selected_links_urls:
            st.warning("Por favor, selecione pelo menos um vídeo para processar.")
        else:
            # Cria um mapa de URL para o título limpo para fácil acesso
            # Pega o título antes do " - "
            url_to_title_map = {url: item[0].split(' - ')[0] for item in st.session_state.available_video_options for display_name, url in [item] if display_name in selected_display_names}
            
            current_video_number = base_number
            st.header("3. Detalhes e Download dos Vídeos")
            
            for i, video_url in enumerate(selected_links_urls):
                st.subheader(f"Processando Vídeo {i+1}: {video_url}")
                
                # Use o título que já foi buscado ou re-busque se por algum motivo não estiver no mapa
                page_title_raw = url_to_title_map.get(video_url, get_page_title(video_url))
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
                        f"Selecione a resolução para este vídeo (ID: {i}):", # Adiciona ID para unicidade da chave
                        options=list(resolution_options.keys()),
                        key=f"res_choice_{i}"
                    )
                    
                    chosen_resolution_int = int(chosen_resolution_str.replace('p', ''))
                    
                    final_filename_base = f"{base_name}{current_video_number} {clean_page_title}"
                    output_filename = f"{final_filename_base}_{chosen_resolution_str}.mp4"
                    output_filepath = os.path.join(DOWNLOAD_DIR, output_filename)
                    
                    st.info(f"O vídeo será salvo como: `{output_filename}`")

                    if st.button(f"Baixar {chosen_resolution_str} de '{clean_page_title}' (ID: {i})", key=f"download_btn_{i}"):
                        try:
                            # yt-dlp pode precisar de 'bestvideo[height<=H]+bestaudio/best[height<=H]' para combinar fluxos
                            ydl_opts = {
                                'format': f'bestvideo[height<={chosen_resolution_int}]+bestaudio/best[height<={chosen_resolution_int}]',
                                'outtmpl': output_filepath,
                                'noplaylist': True,
                                # Removendo progress_hooks complexos para evitar problemas.
                                # O st.spinner já indica que o download está em andamento.
                            }
                            with st.spinner(f"Baixando {output_filename}..."): # O spinner agora cobre todo o processo de download
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                    ydl.download([video_url])
                            
                            st.success(f"Vídeo '{output_filename}' baixado com sucesso!")
                            
                            # Oferecer link para download do arquivo salvo
                            if os.path.exists(output_filepath):
                                with open(output_filepath, "rb") as fp:
                                    st.download_button(
                                        label=f"Clique para Salvar '{output_filename}'",
                                        data=fp.read(),
                                        file_name=output_filename,
                                        mime="video/mp4",
                                        key=f"serve_download_{i}"
                                    )
                            else:
                                st.error(f"Erro: O arquivo {output_filename} não foi encontrado após o download.")
                            
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

# import streamlit as st
# import requests
# from bs4 import BeautifulSoup
# import yt_dlp
# import os
# import re
# from urllib.parse import urljoin # Importar para lidar com URLs relativas

# # --- Configurações Iniciais ---
# DOWNLOAD_DIR = "downloads"
# if not os.path.exists(DOWNLOAD_DIR):
#     os.makedirs(DOWNLOAD_DIR)

# st.set_page_config(layout="wide", page_title="Downloader de Vídeos Inteligente")

# st.title("🔗 Downloader de Vídeos Inteligente")
# st.write("Este aplicativo busca links de vídeo em um site, permite que você selecione quais baixar e os salva nas resoluções 720p ou 1080p com um nome personalizado.")

# # --- Funções Auxiliares ---

# @st.cache_data(ttl=3600) # Cachear títulos por 1 hora para evitar requisições repetidas
# def get_page_title(url):
#     """Busca o título de uma página web."""
#     try:
#         response = requests.get(url, timeout=10)
#         response.raise_for_status()
#         soup = BeautifulSoup(response.text, 'html.parser')
#         title_tag = soup.find('title')
#         if title_tag:
#             return title_tag.get_text(strip=True)
#         # Tenta pegar um título de cabeçalho se não encontrar tag <title>
#         h1_tag = soup.find('h1')
#         if h1_tag:
#             return h1_tag.get_text(strip=True)
#         return "Título Desconhecido"
#     except requests.exceptions.RequestException as e:
#         # st.warning(f"Não foi possível obter o título da página {url}: {e}") # Remover para não poluir o log no Streamlit
#         return f"Erro ao obter título ({e})"

# def clean_filename(title):
#     """Limpa o título para ser usado como nome de arquivo."""
#     title = re.sub(r'[\\/*?:"<>|]', "", title)  # Remove caracteres inválidos para nome de arquivo
#     title = title.replace(" ", "_") # Opcional: substitui espaços por underscores
#     return title.strip()

# @st.cache_data(ttl=3600) # Cachear informações de vídeo por 1 hora
# def get_video_info(url):
#     """Obtém informações sobre o vídeo (tamanhos, formatos) sem baixar."""
#     try:
#         ydl_opts = {
#             'quiet': True,
#             'skip_download': True,
#             'force_generic_extractor': True, # Tenta extrair info mesmo que não seja um site 'reconhecido'
#             'noplaylist': True, # Garante que não baixe playlists
#         }
#         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#             info = ydl.extract_info(url, download=False)
#             return info
#     except yt_dlp.utils.DownloadError as e:
#         st.error(f"Não foi possível extrair informações do vídeo em {url}: {e}")
#         return None

# def find_best_format(info_dict, height):
#     """Encontra o melhor formato de vídeo para uma dada altura."""
#     best_format = None
#     for f in info_dict.get('formats', []):
#         # Preferir formatos com áudio e vídeo separados (DASH) e com codecs conhecidos
#         if f.get('height') == height and f.get('vcodec') != 'none': # Deve ter vídeo
#             if f.get('acodec') != 'none': # Formato com áudio e vídeo juntos
#                 if not best_format or f.get('tbr', 0) > best_format.get('tbr', 0):
#                     best_format = f
#             elif 'format_id' in f and 'dash' in f['format_id']: # Pode ser um formato DASH (apenas vídeo)
#                  # Se for apenas vídeo, vamos combiná-lo mais tarde. Por enquanto, só pegamos o melhor vídeo.
#                  if not best_format or f.get('tbr', 0) > best_format.get('tbr', 0):
#                     best_format = f

#     return best_format


# def get_format_size(format_dict):
#     """Calcula o tamanho aproximado do arquivo em MB."""
#     if format_dict:
#         size_bytes = format_dict.get('filesize') or format_dict.get('filesize_approx')
#         if size_bytes:
#             return f"{size_bytes / (1024 * 1024):.2f} MB"
#     return "N/D"

# # --- Interface do Streamlit ---

# st.header("1. Insira o Link Base e Detalhes de Nomeação")
# main_url = st.text_input("Link do Site (URL principal):", "https://example.com") # Adicione um valor padrão para teste
# base_name = st.text_input("Nome Base para o Vídeo:", "VideoBase")
# base_number = st.number_input("Número Base para o Vídeo (será incrementado):", min_value=1, value=50)

# # Inicializar session_state para armazenar os links encontrados com seus títulos
# if 'available_video_options' not in st.session_state:
#     st.session_state.available_video_options = [] # Stores (display_string, url) tuples
# if 'selected_video_display_names' not in st.session_state:
#     st.session_state.selected_video_display_names = [] # Stores the display strings selected by user

# # Botão para buscar links
# if st.button("Buscar Links de Vídeo"):
#     st.session_state.available_video_options = []
#     st.session_state.selected_video_display_names = [] # Limpa a seleção anterior ao buscar novos links
    
#     if main_url:
#         st.info(f"Buscando links em: {main_url}...")
#         try:
#             response = requests.get(main_url, timeout=15)
#             response.raise_for_status()
#             soup = BeautifulSoup(response.text, 'html.parser')
            
#             # Usar um set para garantir URLs únicas
#             unique_video_urls = set()
#             for a_tag in soup.find_all('a', href=True):
#                 href = a_tag['href']
#                 # Construir URL absoluta
#                 full_href = urljoin(main_url, href)
                
#                 if 'view_video' in full_href:
#                     unique_video_urls.add(full_href)
            
#             if unique_video_urls:
#                 progress_bar = st.progress(0)
#                 progress_text = st.empty()
#                 total_links = len(unique_video_urls)
                
#                 links_with_titles = []
#                 for idx, url in enumerate(sorted(list(unique_video_urls))): # Sort para ordem consistente
#                     progress_text.info(f"Obtendo título para link {idx + 1}/{total_links}: {url}")
#                     title = get_page_title(url)
#                     display_name = f"{title} - {url}"
#                     links_with_titles.append((display_name, url))
#                     progress_bar.progress((idx + 1) / total_links)
                
#                 st.session_state.available_video_options = links_with_titles
#                 progress_bar.empty()
#                 progress_text.empty()
#                 st.success(f"Encontrados {len(st.session_state.available_video_options)} links únicos com 'view_video'.")
#             else:
#                 st.warning("Nenhum link com 'view_video' encontrado nesta página.")
#         except requests.exceptions.RequestException as e:
#             st.error(f"Erro ao acessar a URL principal: {e}")
#     else:
#         st.warning("Por favor, insira uma URL válida para buscar os links.")

# st.header("2. Selecione os Vídeos para Baixar")
# if st.session_state.available_video_options:
#     # Obter apenas os nomes de exibição para as opções do multiselect
#     display_options = [item[0] for item in st.session_state.available_video_options]
    
#     # Manter a seleção padrão se a lista de opções mudar (e forçar a revalidação se necessário)
#     initial_selection = [
#         d_name for d_name in st.session_state.selected_video_display_names
#         if d_name in display_options
#     ]

#     selected_display_names = st.multiselect(
#         "Selecione os vídeos que você deseja baixar:",
#         options=display_options,
#         default=initial_selection
#     )
#     st.session_state.selected_video_display_names = selected_display_names
    
#     # Mapear os nomes de exibição selecionados de volta para suas URLs originais
#     selected_links_urls = [
#         url for display_name, url in st.session_state.available_video_options
#         if display_name in selected_display_names
#     ]
    
#     if st.button("Processar Vídeos Selecionados"):
#         if not selected_links_urls:
#             st.warning("Por favor, selecione pelo menos um vídeo para processar.")
#         else:
#             # Cria um mapa de URL para o título limpo para fácil acesso
#             url_to_title_map = {url: item[0].split(' - ')[0] for item in st.session_state.available_video_options for display_name, url in [item] if display_name in selected_display_names}
            
#             current_video_number = base_number
#             st.header("3. Detalhes e Download dos Vídeos")
            
#             for i, video_url in enumerate(selected_links_urls):
#                 st.subheader(f"Processando Vídeo {i+1}: {video_url}")
                
#                 # Use o título que já foi buscado ou re-busque se por algum motivo não estiver no mapa
#                 page_title_raw = url_to_title_map.get(video_url, get_page_title(video_url))
#                 clean_page_title = clean_filename(page_title_raw)
                
#                 video_info = get_video_info(video_url)

#                 if video_info:
#                     st.write(f"Título da Página: **{page_title_raw}**")
                    
#                     format_720p = find_best_format(video_info, 720)
#                     format_1080p = find_best_format(video_info, 1080)
                    
#                     st.write(f"Tamanho aproximado (720p): {get_format_size(format_720p)}")
#                     st.write(f"Tamanho aproximado (1080p): {get_format_size(format_1080p)}")
                    
#                     resolution_options = {}
#                     if format_720p:
#                         resolution_options["720p"] = "720p"
#                     if format_1080p:
#                         resolution_options["1080p"] = "1080p"
                    
#                     if not resolution_options:
#                         st.warning("Nenhuma resolução 720p ou 1080p encontrada para este vídeo. Tente outra URL ou verifique a disponibilidade.")
#                         continue

#                     chosen_resolution_str = st.radio(
#                         f"Selecione a resolução para este vídeo (ID: {i}):", # Adiciona ID para unicidade da chave
#                         options=list(resolution_options.keys()),
#                         key=f"res_choice_{i}"
#                     )
                    
#                     chosen_resolution_int = int(chosen_resolution_str.replace('p', ''))
                    
#                     final_filename_base = f"{base_name}{current_video_number} {clean_page_title}"
#                     output_filename = f"{final_filename_base}_{chosen_resolution_str}.mp4"
#                     output_filepath = os.path.join(DOWNLOAD_DIR, output_filename)
                    
#                     st.info(f"O vídeo será salvo como: `{output_filename}`")

#                     if st.button(f"Baixar {chosen_resolution_str} de '{clean_page_title}' (ID: {i})", key=f"download_btn_{i}"):
#                         try:
#                             # yt-dlp pode precisar de 'bestvideo[height<=H]+bestaudio/best[height<=H]' para combinar fluxos
#                             ydl_opts = {
#                                 'format': f'bestvideo[height<={chosen_resolution_int}]+bestaudio/best[height<={chosen_resolution_int}]',
#                                 'outtmpl': output_filepath,
#                                 'noplaylist': True,
#                                 'progress_hooks': [lambda d: st.info(f"Status do download: {d['status']}. Arquivo: {d.get('filename', '')}. Progresso: {d.get('progress_text', '')}")] if d['status'] == 'downloading' else None,
#                             }
#                             with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#                                 with st.spinner(f"Baixando {output_filename}..."):
#                                     ydl.download([video_url])
                            
#                             st.success(f"Vídeo '{output_filename}' baixado com sucesso!")
                            
#                             # Oferecer link para download do arquivo salvo
#                             if os.path.exists(output_filepath):
#                                 with open(output_filepath, "rb") as fp:
#                                     st.download_button(
#                                         label=f"Clique para Salvar '{output_filename}'",
#                                         data=fp.read(),
#                                         file_name=output_filename,
#                                         mime="video/mp4",
#                                         key=f"serve_download_{i}"
#                                     )
#                             else:
#                                 st.error(f"Erro: O arquivo {output_filename} não foi encontrado após o download.")
                            
#                         except yt_dlp.utils.DownloadError as e:
#                             st.error(f"Erro ao baixar o vídeo {output_filename}: {e}")
#                         except Exception as e:
#                             st.error(f"Ocorreu um erro inesperado ao baixar: {e}")
                    
#                     current_video_number += 1
#                     st.markdown("---")
#                 else:
#                     st.warning(f"Não foi possível obter informações de vídeo para: {video_url}. Pulando.")
#                     st.markdown("---")

# else:
#     st.info("Insira uma URL principal e clique em 'Buscar Links de Vídeo' para começar.")

# # import streamlit as st
# # import requests
# # from bs4 import BeautifulSoup
# # import yt_dlp
# # import os
# # import re

# # # --- Configurações Iniciais ---
# # DOWNLOAD_DIR = "downloads"
# # if not os.path.exists(DOWNLOAD_DIR):
# #     os.makedirs(DOWNLOAD_DIR)

# # st.set_page_config(layout="wide", page_title="Downloader de Vídeos Inteligente")

# # st.title("🔗 Downloader de Vídeos Inteligente")
# # st.write("Este aplicativo busca links de vídeo em um site, permite que você selecione quais baixar e os salva nas resoluções 720p ou 1080p com um nome personalizado.")

# # # --- Funções Auxiliares ---

# # def get_page_title(url):
# #     """Busca o título de uma página web."""
# #     try:
# #         response = requests.get(url, timeout=10)
# #         response.raise_for_status()
# #         soup = BeautifulSoup(response.text, 'html.parser')
# #         title = soup.find('title')
# #         if title:
# #             return title.get_text(strip=True)
# #         return "Título Desconhecido"
# #     except requests.exceptions.RequestException as e:
# #         st.warning(f"Não foi possível obter o título da página {url}: {e}")
# #         return "Título Desconhecido"

# # def clean_filename(title):
# #     """Limpa o título para ser usado como nome de arquivo."""
# #     title = re.sub(r'[\\/*?:"<>|]', "", title)  # Remove caracteres inválidos para nome de arquivo
# #     title = title.replace(" ", "_") # Opcional: substitui espaços por underscores
# #     return title.strip()

# # def get_video_info(url):
# #     """Obtém informações sobre o vídeo (tamanhos, formatos) sem baixar."""
# #     try:
# #         ydl_opts = {
# #             'quiet': True,
# #             'skip_download': True,
# #             'force_generic_extractor': True, # Tenta extrair info mesmo que não seja um site 'reconhecido'
# #         }
# #         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
# #             info = ydl.extract_info(url, download=False)
# #             return info
# #     except yt_dlp.utils.DownloadError as e:
# #         st.error(f"Não foi possível extrair informações do vídeo em {url}: {e}")
# #         return None

# # def find_best_format(info_dict, height):
# #     """Encontra o melhor formato de vídeo para uma dada altura."""
# #     best_format = None
# #     for f in info_dict.get('formats', []):
# #         if f.get('height') == height and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
# #             if not best_format or f.get('tbr', 0) > best_format.get('tbr', 0): # tbr = total bitrate
# #                 best_format = f
# #     return best_format

# # def get_format_size(format_dict):
# #     """Calcula o tamanho aproximado do arquivo em MB."""
# #     if format_dict:
# #         # filesiz_approx é geralmente mais confiável que filesize
# #         size_bytes = format_dict.get('filesize') or format_dict.get('filesize_approx')
# #         if size_bytes:
# #             return f"{size_bytes / (1024 * 1024):.2f} MB"
# #     return "N/D"

# # # --- Interface do Streamlit ---

# # st.header("1. Insira o Link Base e Detalhes de Nomeação")
# # main_url = st.text_input("Link do Site (URL principal):", "https://example.com") # Adicione um valor padrão para teste
# # base_name = st.text_input("Nome Base para o Vídeo:", "VideoBase")
# # base_number = st.number_input("Número Base para o Vídeo (será incrementado):", min_value=1, value=50)

# # # Inicializar session_state para armazenar os links encontrados
# # if 'found_links' not in st.session_state:
# #     st.session_state.found_links = []
# # if 'selected_links' not in st.session_state:
# #     st.session_state.selected_links = []

# # # Botão para buscar links
# # if st.button("Buscar Links de Vídeo"):
# #     st.session_state.found_links = []
# #     st.session_state.selected_links = []
# #     if main_url:
# #         st.info(f"Buscando links em: {main_url}...")
# #         try:
# #             response = requests.get(main_url, timeout=15)
# #             response.raise_for_status()
# #             soup = BeautifulSoup(response.text, 'html.parser')
            
# #             # Encontrar todos os links que contêm 'view_video'
# #             links = []
# #             for a_tag in soup.find_all('a', href=True):
# #                 href = a_tag['href']
# #                 # Construir URL absoluta se for relativa
# #                 if href.startswith('/'):
# #                     full_href = requests.compat.urljoin(main_url, href)
# #                 else:
# #                     full_href = href
                
# #                 if 'view_video' in full_href and full_href not in links:
# #                     links.append(full_href)
            
# #             if links:
# #                 st.session_state.found_links = links
# #                 st.success(f"Encontrados {len(links)} links com 'view_video'.")
# #             else:
# #                 st.warning("Nenhum link com 'view_video' encontrado nesta página.")
# #         except requests.exceptions.RequestException as e:
# #             st.error(f"Erro ao acessar a URL principal: {e}")
# #     else:
# #         st.warning("Por favor, insira uma URL válida para buscar os links.")

# # st.header("2. Selecione os Vídeos para Baixar")
# # if st.session_state.found_links:
# #     selected_links_display = st.multiselect(
# #         "Selecione os links de vídeo que você deseja baixar:",
# #         options=st.session_state.found_links,
# #         default=st.session_state.selected_links # Mantém a seleção entre as execuções
# #     )
# #     st.session_state.selected_links = selected_links_display

# #     if st.button("Processar Vídeos Selecionados"):
# #         if not st.session_state.selected_links:
# #             st.warning("Por favor, selecione pelo menos um link para processar.")
# #         else:
# #             current_video_number = base_number
# #             st.header("3. Detalhes e Download dos Vídeos")
            
# #             for i, video_url in enumerate(st.session_state.selected_links):
# #                 st.subheader(f"Processando Vídeo {i+1}: {video_url}")
                
# #                 with st.spinner(f"Obtendo informações para {video_url}..."):
# #                     page_title_raw = get_page_title(video_url)
# #                     clean_page_title = clean_filename(page_title_raw)
                    
# #                     video_info = get_video_info(video_url)

# #                 if video_info:
# #                     st.write(f"Título da Página: **{page_title_raw}**")
                    
# #                     format_720p = find_best_format(video_info, 720)
# #                     format_1080p = find_best_format(video_info, 1080)
                    
# #                     st.write(f"Tamanho aproximado (720p): {get_format_size(format_720p)}")
# #                     st.write(f"Tamanho aproximado (1080p): {get_format_size(format_1080p)}")
                    
# #                     resolution_options = {}
# #                     if format_720p:
# #                         resolution_options["720p"] = "720p"
# #                     if format_1080p:
# #                         resolution_options["1080p"] = "1080p"
                    
# #                     if not resolution_options:
# #                         st.warning("Nenhuma resolução 720p ou 1080p encontrada para este vídeo. Tente outra URL ou verifique a disponibilidade.")
# #                         continue

# #                     chosen_resolution_str = st.radio(
# #                         f"Selecione a resolução para este vídeo ({video_url}):",
# #                         options=list(resolution_options.keys()),
# #                         key=f"res_choice_{i}"
# #                     )
                    
# #                     chosen_resolution_int = int(chosen_resolution_str.replace('p', ''))
                    
# #                     final_filename_base = f"{base_name}{current_video_number} {clean_page_title}"
# #                     output_filename = f"{final_filename_base}_{chosen_resolution_str}.mp4"
# #                     output_filepath = os.path.join(DOWNLOAD_DIR, output_filename)
                    
# #                     st.info(f"O vídeo será salvo como: `{output_filename}`")

# #                     if st.button(f"Baixar {chosen_resolution_str} de '{clean_page_title}'", key=f"download_btn_{i}"):
# #                         try:
# #                             ydl_opts = {
# #                                 'format': f'bestvideo[height<={chosen_resolution_int}]+bestaudio/best[height<={chosen_resolution_int}]',
# #                                 'outtmpl': output_filepath,
# #                                 'noplaylist': True,
# #                                 'progress_hooks': [lambda d: st.info(d['status']) if d['status'] == 'downloading' else None],
# #                             }
# #                             with yt_dlp.YoutubeDL(ydl_opts) as ydl:
# #                                 with st.spinner(f"Baixando {output_filename}..."):
# #                                     ydl.download([video_url])
                            
# #                             st.success(f"Vídeo '{output_filename}' baixado com sucesso!")
                            
# #                             # Oferecer link para download do arquivo salvo
# #                             with open(output_filepath, "rb") as fp:
# #                                 st.download_button(
# #                                     label=f"Clique para Salvar '{output_filename}'",
# #                                     data=fp.read(),
# #                                     file_name=output_filename,
# #                                     mime="video/mp4",
# #                                     key=f"serve_download_{i}"
# #                                 )
                            
# #                         except yt_dlp.utils.DownloadError as e:
# #                             st.error(f"Erro ao baixar o vídeo {output_filename}: {e}")
# #                         except Exception as e:
# #                             st.error(f"Ocorreu um erro inesperado ao baixar: {e}")
                    
# #                     current_video_number += 1
# #                     st.markdown("---")
# #                 else:
# #                     st.warning(f"Não foi possível obter informações de vídeo para: {video_url}. Pulando.")
# #                     st.markdown("---")

# # else:
# #     st.info("Insira uma URL principal e clique em 'Buscar Links de Vídeo' para começar.")
