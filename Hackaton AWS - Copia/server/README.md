# 🔥 QueimAlerta — Monitoramento de Queimadas no Brasil

**App mobile** (PWA instalável + wrapper nativo Android via Capacitor) com
backend em **Python + Flask** e frontend em **HTML/CSS/JS**:

1. **Painel de ocorrências** — mostra o ranking de focos de queimadas em todo o
   Brasil, com **filtro por região, estado e cidade**.
2. **Reportar queimada agora** — formulário para registrar um foco que está
   acontecendo no momento (com estado/cidade do IBGE, intensidade, descrição e
   localização GPS opcional).
3. **Relatos ativos** — lista colaborativa dos focos reportados pela comunidade.

A interface foi desenhada **mobile-first**: barra de navegação inferior, botões
grandes para toque, áreas seguras (notch), modo tela cheia (standalone) e
funcionamento offline do "casco" do app via Service Worker.

## Fontes de dados públicas

- **IBGE — API de Localidades** (regiões, estados e municípios):
  https://servicodados.ibge.gov.br/api/docs/localidades
- **INPE — Programa Queimadas** (focos de calor):
  https://terrabrasilis.dpi.inpe.br/queimadas/portal/dados-abertos/

Os dados geográficos (regiões/estados/cidades) são carregados **ao vivo** da API
do IBGE. A base agregada de focos por estado (`data/occurrences.json`) é gerada
automaticamente na primeira execução e os relatos dos usuários somam-se a ela em
tempo real.

## Como executar

Requer **Python 3.10+**.

```bash
# 1. (opcional) criar um ambiente virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 2. instalar dependências
pip install -r requirements.txt

# 3. rodar o servidor
python app.py
```

Abra o navegador em: **http://127.0.0.1:5000**

O servidor agora escuta em `0.0.0.0`, então ele também fica acessível pelo
**celular na mesma rede Wi-Fi**. Ao iniciar, o Flask imprime o endereço de rede,
por exemplo `http://192.168.0.10:5000` — use esse endereço no celular.

## 📱 Instalar como app mobile

### Opção A — PWA (mais rápida, sem Android Studio)

1. No **celular**, abra o Chrome e acesse o endereço de rede do servidor
   (ex.: `http://192.168.0.10:5000`).
2. Menu do Chrome → **Instalar app / Adicionar à tela inicial**.
3. O QueimAlerta abre em tela cheia, com ícone próprio, como um app nativo.

> iOS: use o Safari → Compartilhar → **Adicionar à Tela de Início**.

### Opção B — APK nativo (Capacitor)

Requer **Node.js** e o **Android SDK** (Android Studio). Os arquivos já estão em
`mobile/`:

```bash
cd mobile
npm install
npm run add:android      # cria o projeto android/ (uma vez)
npm run sync             # copia o frontend (server/static) para www/ e sincroniza
npm run open:android     # abre no Android Studio para gerar o APK
# ou, por linha de comando:
npm run build:apk        # gera android/app/build/outputs/apk/debug/app-debug.apk
```

No app nativo os arquivos são servidos do próprio dispositivo, então é preciso
apontar para o servidor Flask:

- Abra o app → **⚙ Configurações** → informe o endereço (ex.:
  `http://192.168.0.10:5000`) → **Testar conexão** → **Salvar**; **ou**
- edite `mobile/www/config.js` antes do build, definindo `API_BASE`.

## Estrutura

```
Hackaton AWS/
├── server/                   # Backend + frontend (PWA)
│   ├── app.py                # Flask + integração IBGE + API de relatos + CORS
│   ├── requirements.txt      # Flask, requests
│   ├── data/                 # Gerado em runtime (occurrences.json, reports.json)
│   └── static/
│       ├── index.html        # Interface mobile (app bar + bottom nav + sheet)
│       ├── styles.css        # Estilo mobile-first (tema escuro, safe-areas)
│       ├── app.js            # Lógica + API configurável + Service Worker
│       ├── config.js         # Endereço da API (editável / sobrescrito no app)
│       ├── sw.js             # Service Worker (offline + cache)
│       ├── manifest.webmanifest
│       └── icons/            # Ícones do app (192, 512, maskable, apple-touch)
└── mobile/                   # Wrapper nativo (Capacitor → Android/iOS)
    ├── capacitor.config.json
    ├── package.json
    └── copyweb.js            # Copia server/static → mobile/www
```

## API

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/regioes` | Lista as 5 regiões (IBGE) |
| GET | `/api/estados?regiao=<id>` | Lista estados, opcionalmente por região |
| GET | `/api/municipios?uf=<SP>` | Lista municípios de um estado |
| GET | `/api/ocorrencias?nivel=uf\|regiao&regiao=&uf=&limit=` | Ranking de focos |
| GET | `/api/reports` | Lista relatos ativos |
| POST | `/api/reports` | Cria um relato (`uf`, `municipio`, `intensidade`, `descricao`, `lat`, `lon`) |
| DELETE | `/api/reports/<id>` | Marca um relato como resolvido |
| GET | `/health` | Verificação de saúde |

## Observação sobre os dados de focos

Os totais por estado em `data/occurrences.json` representam uma base agregada
(ordem de grandeza baseada em divulgações do INPE) para permitir a demonstração
funcionar offline. Para dados oficiais em tempo quase real, baixe os CSVs do
[Programa Queimadas do INPE](https://terrabrasilis.dpi.inpe.br/queimadas/portal/dados-abertos/)
e substitua o conteúdo de `data/occurrences.json` mantendo o formato
`[{ "uf": "SP", "municipio": null, "focos": 123 }, ...]`.
