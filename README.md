#QueimAlerta Brasil

Painel interativo em Python para monitoramento quase em tempo real de detecções de focos de calor ativos no Brasil.

Um foco de calor detectado por satélite não é automaticamente um incêndio florestal confirmado. Os dados podem incluir queimadas controladas, incêndios agrícolas, outras fontes de calor e falsos positivos.
Recursos atuais
Importa o arquivo CSV diário oficial do INPE para o Brasil e arquiva cada cópia baixada.
Valida as coordenadas e os campos obrigatórios da fonte.
Elimina registros duplicados com base no id estável do INPE.
Armazena as detecções e as execuções de ingestão em SQLite localmente ou PostgreSQL em contêineres.
Exibe um mapa interativo do Plotly, séries temporais, classificação por estado, filtros e uma tabela de registros recentes.
Atualiza o painel do navegador a cada 60 segundos.
Exibe a atualização mais recente da fonte e o status do pipeline.
Disponibiliza endpoints separados de disponibilidade do processo, prontidão e integridade dos dados.
Emite logs estruturados de ingestão em JSON, adequados para coleta pelo CloudWatch.

O roteiro detalhado está em PROJECT_PLAN.md.

Fonte de dados

A fonte principal é o portal de dados abertos do Programa Queimadas do INPE. O adaptador atual lê arquivos CSV diários do Brasil no servidor oficial de dados do INPE. Esses arquivos são atualizados ao longo do dia e contêm IDs da fonte, horário de observação em GMT, coordenadas, satélite, município, estado, identificadores do IBGE, bioma, campos meteorológicos e de risco de incêndio, além de FRP quando disponível.

O conteúdo que descreve fontes externas foi reformulado para cumprir as restrições de licenciamento.

Executar localmente com Python

É necessário ter o Python 3.12 ou superior. No PowerShell, execute o inicializador do Windows:

powershell
.\run-local.cmd


O inicializador cria .venv quando necessário, instala o projeto, inicializa o banco de dados SQLite local, atualiza o arquivo mais recente do INPE, exibe o status do pipeline e inicia o painel. Mantenha o terminal aberto enquanto estiver usando o sistema e, em seguida, abra http://127.0.0.1:8050. Pressione Ctrl+C para interrompê-lo.

Opções úteis do inicializador:

powershell
# Iniciar imediatamente com os dados já baixados
.\run-local.cmd --skip-ingest

# Baixar os sete arquivos diários mais recentes antes de iniciar
.\run-local.cmd --days 7

# Preparar e validar tudo sem iniciar o servidor web
.\run-local.cmd --prepare-only


O run-local.ps1 oferece o mesmo fluxo de trabalho quando a execução de scripts do PowerShell está habilitada. O inicializador .cmd é o padrão porque não exige alterações na política de execução.

Você também pode usar os comandos individuais do Python:

powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m queimalerta.cli init-db
.\.venv\Scripts\python.exe -m queimalerta.cli ingest --days 1
.\.venv\Scripts\python.exe -m queimalerta.dashboard.app


Os arquivos de origem podem ser grandes. Comece com um dia ao testar uma nova configuração.

Executar com Docker Compose

O Docker não é necessário para executar o projeto diretamente com Python. Quando o Docker estiver disponível:

powershell
docker compose up --build database dashboard
docker compose --profile jobs run --rm ingestion


A pilha do Compose utiliza PostgreSQL/PostGIS. Nesta primeira etapa, o sistema armazena as coordenadas em colunas numéricas indexadas e continua compatível com SQLite; a geometria nativa do PostGIS e as consultas por área visível do mapa estão previstas para a próxima fase de implementação.

Configuração

Copie .env.example para .env e altere os valores conforme necessário. As variáveis de ambiente substituem os valores padrão.

Variável	Padrão	Finalidade
QUEIMALERTA_DATABASE_URL	sqlite:///data/queimalerta.db	URL de conexão com o banco de dados SQLAlchemy
QUEIMALERTA_INPE_DAILY_URL	diretório oficial de dados diários do INPE para o Brasil	Diretório de origem
QUEIMALERTA_ARCHIVE_DIR	data/raw	Diretório de arquivamento dos dados brutos
QUEIMALERTA_REFRESH_SECONDS	60	Intervalo de atualização do navegador, em segundos
QUEIMALERTA_STALE_AFTER_MINUTES	30	Limite, em minutos, para considerar a ingestão desatualizada
QUEIMALERTA_MAX_MAP_POINTS	5000	Número máximo de pontos enviados ao mapa
QUEIMALERTA_HOST	127.0.0.1	Endereço de vinculação do servidor web
QUEIMALERTA_PORT	8050	Porta do servidor web
QUEIMALERTA_DEBUG	false	Modo de desenvolvimento do Dash
QUEIMALERTA_LOG_LEVEL	INFO	Nível de log da aplicação

Não faça commit do arquivo .env nem de credenciais.

Comandos
powershell
queimalerta init-db
queimalerta ingest --days 1
queimalerta status
queimalerta-dashboard


Na AWS, o EventBridge Scheduler deve executar o contêiner de ingestão a cada 10 minutos. Não incorpore um agendador ao processo do painel, pois várias réplicas web duplicariam as execuções dos trabalhos.

Endpoints de integridade
GET /health/live: confirma que o processo web está em execução.
GET /health/ready: verifica a conectividade com o banco de dados.
GET /health/data: informa a atualização dos dados e da ingestão e retorna HTTP 503 quando os dados estão desatualizados.
Limitações conhecidas da primeira etapa
A infraestrutura do AWS CDK e os alarmes do CloudWatch ainda não foram implementados.
As coordenadas ainda não são armazenadas como geometria nativa do PostGIS.
O filtro por município e as consultas pela área visível do mapa estão planejados para a próxima etapa.
O painel atual recupera no máximo 50.000 linhas filtradas para os gráficos e 5.000 para a renderização do mapa.
Não há autenticação; não exponha esta versão de desenvolvimento como uma interface administrativa.
