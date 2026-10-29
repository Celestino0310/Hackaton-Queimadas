/*
 * Copia os arquivos do frontend (server/static) para mobile/www,
 * que e a pasta empacotada pelo Capacitor no app nativo.
 *
 * Uso: node copyweb.js
 */
const fs = require("fs");
const path = require("path");

const SRC = path.resolve(__dirname, "..", "server", "static");
const DST = path.resolve(__dirname, "www");

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

if (!fs.existsSync(SRC)) {
  console.error("Pasta de origem nao encontrada:", SRC);
  process.exit(1);
}

// limpa destino
fs.rmSync(DST, { recursive: true, force: true });
copyDir(SRC, DST);

console.log("Frontend copiado para:", DST);
console.log(
  "\nIMPORTANTE: no app nativo os arquivos sao servidos do dispositivo,\n" +
  "entao configure o endereco do servidor Flask dentro do app (⚙ Configuracoes)\n" +
  "ou edite www/config.js com o IP da maquina, ex: http://192.168.0.10:5000\n"
);
